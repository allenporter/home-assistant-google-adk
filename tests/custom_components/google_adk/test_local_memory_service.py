"""Tests for the local file memory service."""

from unittest.mock import patch, AsyncMock, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.google_adk.local_memory_service import LocalFileMemoryService
from google.adk.sessions import Session
from google.adk.events.event import Event
from google.genai.types import Content, Part


async def test_memory_service_save_load(hass: HomeAssistant) -> None:
    """Test saving and loading sessions."""

    # Mock Store to verify logic without file I/O
    with patch(
        "custom_components.google_adk.local_memory_service.Store"
    ) as mock_store_cls:
        mock_store = mock_store_cls.return_value
        mock_store.async_load = AsyncMock(return_value=None)
        mock_store.async_save = AsyncMock()

        service = LocalFileMemoryService(hass)

        session = Session(
            id="test_session",
            app_name="test_app",
            user_id="test_user",
            events=[
                Event(
                    author="user", content=Content(parts=[Part(text="I love apples.")])
                )
            ],
        )

        await service.add_session_to_memory(session)

        # Verify save was called
        mock_store.async_save.assert_called_once()
        saved_data = mock_store.async_save.call_args[0][0]
        assert "test_app/test_user" in saved_data
        assert "test_session" in saved_data["test_app/test_user"]

        # Now simulate loading from this data in a new service
        mock_store.async_load.return_value = saved_data

        service2 = LocalFileMemoryService(hass)
        response = await service2.search_memory(
            app_name="test_app", user_id="test_user", query="apples"
        )

        assert len(response.memories) == 1
        memory = response.memories[0]
        assert memory.content is not None
        assert memory.content.parts is not None
        assert len(memory.content.parts) > 0
        assert memory.content.parts[0].text == "I love apples."


async def test_memory_service_search(hass: HomeAssistant) -> None:
    """Test searching memory."""
    with patch(
        "custom_components.google_adk.local_memory_service.Store"
    ) as mock_store_cls:
        mock_store = mock_store_cls.return_value
        mock_store.async_load = AsyncMock(return_value=None)
        mock_store.async_save = AsyncMock()

        service = LocalFileMemoryService(hass)

        session1 = Session(
            id="s1",
            app_name="app",
            user_id="user",
            events=[
                Event(
                    author="user",
                    content=Content(parts=[Part(text="My cat is black.")]),
                )
            ],
        )
        session2 = Session(
            id="s2",
            app_name="app",
            user_id="user",
            events=[
                Event(author="user", content=Content(parts=[Part(text="I love dogs.")]))
            ],
        )

        await service.add_session_to_memory(session1)
        await service.add_session_to_memory(session2)

        # Search for "cat"
        response = await service.search_memory(
            app_name="app", user_id="user", query="cat"
        )
        assert len(response.memories) == 1
        memory = response.memories[0]
        assert memory.content is not None
        assert memory.content.parts is not None
        assert len(memory.content.parts) > 0
        assert (text := memory.content.parts[0].text) is not None
        assert "cat" in text

        # Search for "dogs"
        response = await service.search_memory(
            app_name="app", user_id="user", query="dogs"
        )
        assert len(response.memories) == 1
        memory = response.memories[0]
        assert memory.content is not None
        assert memory.content.parts is not None
        assert len(memory.content.parts) > 0
        assert (text := memory.content.parts[0].text) is not None
        assert "dogs" in text

        # Search for something unrelated
        response = await service.search_memory(
            app_name="app", user_id="user", query="bird"
        )
        assert len(response.memories) == 0


async def test_memory_service_isolation(hass: HomeAssistant) -> None:
    """Test memory isolation between different storage keys."""
    with patch(
        "custom_components.google_adk.local_memory_service.Store"
    ) as mock_store_cls:
        # We need to handle two different instances of Store
        mock_stores = {}

        def get_mock_store(hass, version, key):
            if key not in mock_stores:
                m = MagicMock()
                m.async_load = AsyncMock(return_value=None)
                m.async_save = AsyncMock()
                mock_stores[key] = m
            return mock_stores[key]

        mock_store_cls.side_effect = get_mock_store

        service1 = LocalFileMemoryService(hass, storage_key="key1")
        service2 = LocalFileMemoryService(hass, storage_key="key2")

        session = Session(
            id="s1",
            app_name="app",
            user_id="user",
            events=[
                Event(
                    author="user",
                    content=Content(parts=[Part(text="Secret code is 1234.")]),
                )
            ],
        )

        await service1.add_session_to_memory(session)

        # Service 1 should find it
        response1 = await service1.search_memory(
            app_name="app", user_id="user", query="1234"
        )
        assert len(response1.memories) == 1

        # Service 2 should NOT find it
        response2 = await service2.search_memory(
            app_name="app", user_id="user", query="1234"
        )
        assert len(response2.memories) == 0


async def test_memory_service_numeric_search(hass: HomeAssistant) -> None:
    """Test searching for numbers in memory."""
    with patch(
        "custom_components.google_adk.local_memory_service.Store"
    ) as mock_store_cls:
        mock_store = mock_store_cls.return_value
        mock_store.async_load = AsyncMock(return_value=None)
        mock_store.async_save = AsyncMock()

        service = LocalFileMemoryService(hass)

        session = Session(
            id="s1",
            app_name="app",
            user_id="user",
            events=[
                Event(
                    author="user",
                    content=Content(parts=[Part(text="My phone is 123456.")]),
                )
            ],
        )

        await service.add_session_to_memory(session)

        # Search for "123456"
        response = await service.search_memory(
            app_name="app", user_id="user", query="123456"
        )
        assert len(response.memories) == 1
        memory = response.memories[0]
        assert memory.content is not None
        assert memory.content.parts is not None
        assert len(memory.content.parts) > 0
        assert (text := memory.content.parts[0].text) is not None
        assert "123456" in text


async def test_memory_service_background_summarization(hass: HomeAssistant) -> None:
    """Test background summarization when threshold is reached."""
    with patch(
        "custom_components.google_adk.local_memory_service.Store"
    ) as mock_store_cls:
        mock_store = mock_store_cls.return_value
        mock_store.async_load = AsyncMock(return_value=None)
        mock_store.async_save = AsyncMock()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is a summary."
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        service = LocalFileMemoryService(
            hass, summarize=True, client=mock_client, model_id="test-model"
        )

        # Add 24 messages (turns)
        events = []
        for i in range(24):
            events.append(
                Event(author="user", content=Content(parts=[Part(text=f"Turn {i}")]))
            )

        session = Session(
            id="session1",
            app_name="app",
            user_id="user",
            events=events,
        )

        await service.add_session_to_memory(session)
        mock_client.aio.models.generate_content.assert_not_called()

        # Add 1 more message to hit the threshold (25)
        session2 = Session(
            id="session2",
            app_name="app",
            user_id="user",
            events=[
                Event(author="user", content=Content(parts=[Part(text="Final turn")]))
            ],
        )

        await service.add_session_to_memory(session2)

        # Wait for background task
        await hass.async_block_till_done()

        # Verify summarization was called
        mock_client.aio.models.generate_content.assert_called_once()

        # Verify summary is in storage
        saved_data = mock_store.async_save.call_args[0][0]
        user_data = saved_data["app/user"]
        assert "__summaries__" in user_data
        assert (
            "Memory Summary: This is a summary."
            in user_data["__summaries__"][0]["content"]["parts"][0]["text"]
        )

        # Verify history is preserved
        assert "session1" in user_data
        assert "session2" in user_data
