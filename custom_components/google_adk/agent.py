"""Module for agents."""

import logging

from google.adk.agents import BaseAgent, LlmAgent

from homeassistant.core import HomeAssistant

from .const import CONF_NAME, CONF_MODEL, CONF_INSTRUCTIONS, CONF_DESCRIPTION
from .types import GoogleAdkConfigEntry


_LOGGER = logging.getLogger(__name__)


async def async_create(
    hass: HomeAssistant, config_entry: GoogleAdkConfigEntry
) -> BaseAgent:
    """Register all agents using the agent framework."""
    _LOGGER.debug("Registering Google ADK agent '%s'", config_entry.options[CONF_NAME])
    return LlmAgent(
        name=config_entry.options[CONF_NAME],
        model=config_entry.options[CONF_MODEL],
        description=config_entry.options[CONF_DESCRIPTION],
        instruction=config_entry.options[CONF_INSTRUCTIONS],
    )
