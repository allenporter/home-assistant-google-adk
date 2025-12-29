"""Tests for the config flow."""

from unittest.mock import patch


from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.core import HomeAssistant


from custom_components.google_adk.const import (
    CONF_NAME,
    DOMAIN,
    CONF_MODEL,
    CONF_GEMINI_API_KEY,
    CONF_DESCRIPTION,
    CONF_INSTRUCTIONS,
)


async def test_select_device(
    hass: HomeAssistant,
    zwave_device_id: str,
) -> None:
    """Test selecting a device in the configuration flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result.get("type") is FlowResultType.FORM
    assert result.get("errors") is None

    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "assistant_agent",
                CONF_GEMINI_API_KEY: "test_api_key",
                CONF_MODEL: "gemini-2.5-flash",
                CONF_DESCRIPTION: "A helper agent that can answer users' questions.",
                CONF_INSTRUCTIONS: "You are an agent to help answer users' various questions.",
            },
        )
        await hass.async_block_till_done()

    assert result.get("type") is FlowResultType.CREATE_ENTRY
    assert result.get("title") == "assistant_agent"
    assert result.get("data") == {}
    assert result.get("options") == {
        CONF_NAME: "assistant_agent",
        CONF_GEMINI_API_KEY: "test_api_key",
        CONF_MODEL: "gemini-2.5-flash",
        CONF_DESCRIPTION: "A helper agent that can answer users' questions.",
        CONF_INSTRUCTIONS: "You are an agent to help answer users' various questions.",
    }
    assert len(mock_setup.mock_calls) == 1
