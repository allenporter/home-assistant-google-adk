"""Local file memory service."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from google import genai
from google.adk.events.event import Event
from google.adk.memory.base_memory_service import (
    BaseMemoryService,
    SearchMemoryResponse,
)
from google.adk.memory.memory_entry import MemoryEntry
from google.genai.types import Content, Part

if TYPE_CHECKING:
    from google.adk.sessions.session import Session

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "google_adk.memory"

_SUMMARIZE_MEMORY_PROMPT = (
    "Summarize the key facts from this conversation that are worth remembering "
    "for future interactions. Be concise."
)

SUMMARIZATION_THRESHOLD = 25
METADATA_KEY = "__metadata__"
SUMMARIES_KEY = "__summaries__"


def _user_key(app_name: str, user_id: str) -> str:
    """Create a unique key for the user and app."""
    return f"{app_name}/{user_id}"


def _extract_words_lower(text: str) -> set[str]:
    """Extracts words (including digits) from a string and converts them to lowercase."""
    return set([word.lower() for word in re.findall(r"\w+", text)])


class LocalFileMemoryService(BaseMemoryService):
    """A local file-based memory service."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_key: str = STORAGE_KEY,
        summarize: bool = False,
        client: genai.Client | None = None,
        model_id: str | None = None,
    ) -> None:
        """Initialize the local file memory service."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, storage_key)
        self._lock = asyncio.Lock()
        self._session_events = {}
        self._loaded = False
        self._summarize = summarize
        self._client = client
        self._model_id = model_id
        self._summarizing_lock = asyncio.Lock()

    async def _async_load(self) -> None:
        """Load memory from storage."""
        if self._loaded:
            return

        data = await self._store.async_load()
        if data:
            self._session_events = data
        self._loaded = True

    async def _async_background_summarize(self, app_name: str, user_id: str) -> None:
        """Perform summarization in the background."""
        if not self._summarize or not self._client or not self._model_id:
            return

        user_key = _user_key(app_name, user_id)
        
        # Avoid concurrent summarization for the same user
        async with self._summarizing_lock:
            await self._async_load()
            user_data = self._session_events.get(user_key, {})
            metadata = user_data.get(METADATA_KEY, {})
            
            last_summarized_count = metadata.get("last_summarized_turn_count", 0)
            total_turns = metadata.get("total_turns", 0)
            
            if total_turns - last_summarized_count < SUMMARIZATION_THRESHOLD:
                return

            # Build transcript from all sessions
            transcript = ""
            # Get existing summaries
            summaries = user_data.get(SUMMARIES_KEY, [])
            for summary in summaries:
                 if summary_text := summary.get("content", {}).get("parts", [{}])[0].get("text"):
                     transcript += f"Previous Summary: {summary_text}\n"

            # Get new sessions since last summary
            # Note: This is an approximation since we don't have per-event turn counts easily without 
            # more complex metadata. For now, we'll just take all sessions.
            # In a more advanced version, we'd track which sessions are already summarized.
            for session_id, events in user_data.items():
                if session_id in (METADATA_KEY, SUMMARIES_KEY):
                    continue
                for event in events:
                    parts = event.get("content", {}).get("parts", [])
                    text = " ".join([p.get("text", "") for p in parts if p.get("text")])
                    if text:
                        transcript += f"{event.get('author', 'unknown')}: {text}\n"

            if not transcript:
                return

            try:
                _LOGGER.debug("Summarizing memory for user in background: %s", user_id)
                summary_prompt = f"{transcript}\n\n{_SUMMARIZE_MEMORY_PROMPT}"
                response = await self._client.aio.models.generate_content(
                    model=self._model_id, contents=summary_prompt
                )
                summary_text = response.text

                # Update summaries (we replace or append? User said "summarize every 50 turns")
                # Usually we want to keep it condensed, so we might replace the old summary with a new one 
                # that includes the old summary's context + new events.
                new_summary_event = {
                    "timestamp": datetime.now().isoformat(),
                    "author": "memory_summarizer",
                    "content": {
                        "role": "model",
                        "parts": [{"text": f"Memory Summary: {summary_text}"}],
                    },
                }
                
                # For now, let's keep it simple: replace previous summaries with the new one
                # to keep memory usage low, since the new summary should incorporate the old one.
                user_data[SUMMARIES_KEY] = [new_summary_event]
                metadata["last_summarized_turn_count"] = total_turns
                user_data[METADATA_KEY] = metadata
                
                await self._store.async_save(self._session_events)
                _LOGGER.debug("Background summarization complete for user: %s", user_id)
            except Exception as e:
                _LOGGER.error("Failed to perform background summarization: %s", e)

    @override
    async def add_session_to_memory(self, session: Session) -> None:
        """Add a session to memory."""
        _LOGGER.debug("Adding session to memory: %s", session.id)
        await self._async_load()

        user_key = _user_key(session.app_name, session.user_id)

        # Convert events to a serializable format
        serializable_events = []
        new_turns = 0
        for event in session.events:
            if not event.content or not event.content.parts:
                continue

            event_data = {
                "timestamp": datetime.fromtimestamp(event.timestamp).isoformat()
                if event.timestamp
                else None,
                "author": event.author,
                "content": {
                    "role": event.content.role,
                    "parts": [
                        {"text": part.text} for part in event.content.parts if part.text
                    ],
                },
            }
            serializable_events.append(event_data)
            new_turns += 1

        if not serializable_events:
            return

        async with self._lock:
            if user_key not in self._session_events:
                self._session_events[user_key] = {}
            user_data = self._session_events[user_key]
            user_data[session.id] = serializable_events
            
            # Update turn count metadata
            metadata = user_data.get(METADATA_KEY, {})
            total_turns = metadata.get("total_turns", 0) + new_turns
            metadata["total_turns"] = total_turns
            user_data[METADATA_KEY] = metadata

        await self._store.async_save(self._session_events)

        # Check for background summarization
        last_summarized = metadata.get("last_summarized_turn_count", 0)
        if (
            self._summarize 
            and total_turns - last_summarized >= SUMMARIZATION_THRESHOLD
        ):
            self._hass.async_create_task(
                self._async_background_summarize(session.app_name, session.user_id)
            )

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Search memory for relevant sessions and summaries."""
        _LOGGER.debug("Searching memory for query: %s", query)
        await self._async_load()
        user_key = _user_key(app_name, user_id)

        async with self._lock:
            user_data = self._session_events.get(user_key, {})

        words_in_query = _extract_words_lower(query)
        response = SearchMemoryResponse()

        # Helper to search a list of events and add to response
        def _search_events(events: list[dict[str, Any]]) -> None:
            for event_data in events:
                content_data = event_data.get("content", {})
                parts = content_data.get("parts", [])
                text_content = " ".join([p.get("text", "") for p in parts])

                words_in_event = _extract_words_lower(text_content)
                if not words_in_event:
                    continue

                if any(query_word in words_in_event for query_word in words_in_query):
                    reconstructed_content = Content(
                        role=content_data.get("role"),
                        parts=[Part(text=p.get("text", "")) for p in parts],
                    )

                    response.memories.append(
                        MemoryEntry(
                            content=reconstructed_content,
                            author=event_data.get("author"),
                            timestamp=event_data.get("timestamp") or "",
                        )
                    )

        # Search summaries
        _search_events(user_data.get(SUMMARIES_KEY, []))

        # Search regular sessions
        for key, session_events in user_data.items():
            if key in (METADATA_KEY, SUMMARIES_KEY):
                continue
            _search_events(session_events)

        return response
