"""Tests for the config flow."""

from unittest.mock import patch


from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.google_adk.const import (
    CONF_NAME,
    DOMAIN,
    CONF_MODEL,
    CONF_API_KEY,
    CONF_DESCRIPTION,
    CONF_INSTRUCTIONS,
)


async def test_config_flow(hass: HomeAssistant) -> None:
    """Test creating the config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result.get("type") is FlowResultType.FORM
    assert not result.get("errors")

    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "test_api_key",
            },
        )
        await hass.async_block_till_done()

    assert result.get("type") is FlowResultType.CREATE_ENTRY
    assert result.get("title") == "Google ADK"
    assert result.get("data") == {
        CONF_API_KEY: "test_api_key",
    }
    assert len(mock_setup.mock_calls) == 1


async def test_conversation_agent_subentry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
) -> None:
    """Test config flow with conversation agent subentry."""
    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    assert len(config_entry.subentries) == 1

    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, "conversation"),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM, result
    assert result["step_id"] == "set_options"
    assert not result["errors"]

    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry", return_value=True
    ) as mock_setup:
        result2 = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            result["data_schema"](  # type: ignore[call-non-callable]
                {
                    CONF_NAME: "assistant_agent",
                    CONF_MODEL: "gemini-2.5-flash",
                    CONF_DESCRIPTION: "A helper agent that can answer users' questions.",
                    CONF_INSTRUCTIONS: "You are an agent to help answer users' various questions.",
                }
            ),
        )
        await hass.async_block_till_done()

    assert result2.get("type") is FlowResultType.CREATE_ENTRY
    assert result2.get("title") == "assistant_agent"
    assert result2.get("data") == {
        CONF_MODEL: "gemini-2.5-flash",
        CONF_DESCRIPTION: "A helper agent that can answer users' questions.",
        CONF_INSTRUCTIONS: "You are an agent to help answer users' various questions.",
    }
    assert len(config_entry.subentries) == 2

    it = iter(config_entry.subentries.values())
    next(it)  # Skip the first subentry
    new_subentry = next(it)
    assert new_subentry.subentry_type == "conversation"
    assert new_subentry.title == "assistant_agent"
    assert new_subentry.data == {
        CONF_MODEL: "gemini-2.5-flash",
        CONF_DESCRIPTION: "A helper agent that can answer users' questions.",
        CONF_INSTRUCTIONS: "You are an agent to help answer users' various questions.",
    }

    assert len(mock_setup.mock_calls) == 1




async def test_subentry_options_reconfiguration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test config flow options."""
    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    subentry = next(iter(config_entry.subentries.values()))
    assert subentry.subentry_type == "conversation"

    # Initiate the options flow
    options_flow = await config_entry.start_subentry_reconfigure_flow(
        hass, subentry.subentry_id
    )

    # Check that the form is pre-filled with the current options
    schema = options_flow["data_schema"]
    defaults = schema({})  # type: ignore[misc]
    assert defaults[CONF_MODEL] == "gemini-2.5-flash"
    assert (
        defaults[CONF_DESCRIPTION] == "A helper agent that can answer users' questions."
    )
    assert (
        defaults[CONF_INSTRUCTIONS]
        == "You are an agent to help answer users' various questions."
    )

    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.subentries.async_configure(
            options_flow["flow_id"],
            {
                CONF_MODEL: "gemini-3-flash",
                CONF_DESCRIPTION: "Updated description.",
                CONF_INSTRUCTIONS: "Updated instructions.",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert len(mock_setup.mock_calls) == 1

    assert subentry.data == {
        CONF_MODEL: "gemini-3-flash",
        CONF_DESCRIPTION: "Updated description.",
        CONF_INSTRUCTIONS: "Updated instructions.",
    }

async def test_reconfigure_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test reconfigure flow for updating API key."""
    assert config_entry.state is config_entries.ConfigEntryState.LOADED

    # Start reconfigure flow (link to config entry via context)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": config_entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert not result.get("errors")

    # Submit new API key
    with patch(f"custom_components.{DOMAIN}.async_setup_entry", return_value=True) as mock_setup:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "new_api_key"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert len(mock_setup.mock_calls) == 1
    assert config_entry.data[CONF_API_KEY] == "new_api_key"
