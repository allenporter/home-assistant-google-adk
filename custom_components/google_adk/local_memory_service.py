"""Local file memory service."""

from __future__ import annotations

import logging
import re
import threading
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
        self._lock = threading.Lock()
        self._session_events: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._loaded = False
        self._summarize = summarize
        self._client = client
        self._model_id = model_id

    async def _async_load(self) -> None:
        """Load memory from storage."""
        if self._loaded:
            return

        data = await self._store.async_load()
        if data:
            self._session_events = data
        self._loaded = True

    async def _async_summarize_session(self, session: Session) -> list[Event]:
        """Summarize the session and return a list of events to store."""
        if not self._summarize or not self._client or not self._model_id:
            return session.events

        try:
            # Build transcript for summarization
            transcript = ""
            for event in session.events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            transcript += f"{event.author}: {part.text}\n"

            if not transcript:
                return session.events

            _LOGGER.debug("Summarizing session for memory: %s", session.id)
            summary_prompt = f"{transcript}\n\n{_SUMMARIZE_MEMORY_PROMPT}"
            response = await self._client.aio.models.generate_content(
                model=self._model_id, contents=summary_prompt
            )
            summary_text = response.text

            # Create a synthetic event with the summary
            summary_event = Event(
                author="memory_summarizer",
                content=Content(parts=[Part(text=f"Memory Summary: {summary_text}")]),
            )
            return [summary_event]
        except Exception as e:
            _LOGGER.error("Failed to summarize session in memory service: %s", e)
            return session.events

    @override
    async def add_session_to_memory(self, session: Session) -> None:
        """Add a session to memory."""
        _LOGGER.debug("Adding session to memory: %s", session.id)
        await self._async_load()

        events_to_serialize = await self._async_summarize_session(session)

        user_key = _user_key(session.app_name, session.user_id)

        # Convert events to a serializable format
        # We only care about the content parts for memory retrieval
        serializable_events = []
        for event in events_to_serialize:
            if not event.content or not event.content.parts:
                continue

            # Basic serialization of the event content
            # We are reconstructing a simplified version of the event structure for storage
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

        if not serializable_events:
            return

        with self._lock:
            if user_key not in self._session_events:
                self._session_events[user_key] = {}
            self._session_events[user_key][session.id] = serializable_events

        await self._store.async_save(self._session_events)

    @override
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Search memory for relevant sessions."""
        _LOGGER.debug("Searching memory for query: %s", query)
        await self._async_load()
        user_key = _user_key(app_name, user_id)

        with self._lock:
            session_event_lists = self._session_events.get(user_key, {})

        words_in_query = _extract_words_lower(query)
        response = SearchMemoryResponse()

        for session_events in session_event_lists.values():
            for event_data in session_events:
                # Reconstruct content parts from stored data
                content_data = event_data.get("content", {})
                parts = content_data.get("parts", [])
                text_content = " ".join([p.get("text", "") for p in parts])

                words_in_event = _extract_words_lower(text_content)
                if not words_in_event:
                    continue

                if any(query_word in words_in_event for query_word in words_in_query):
                    # Reconstruct MemoryEntry
                    # We need to recreate the Content object for the MemoryEntry
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

        return response
