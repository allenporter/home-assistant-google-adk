"""Module for agents."""

import logging

from google.adk.agents import BaseAgent, LlmAgent

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigSubentry

from .const import CONF_MODEL, CONF_INSTRUCTIONS, CONF_DESCRIPTION


_LOGGER = logging.getLogger(__name__)


async def async_create(hass: HomeAssistant, subentry: ConfigSubentry) -> BaseAgent:
    """Register all agents using the agent framework."""
    _LOGGER.debug("Registering Google ADK agent '%s'", subentry.title)
    return LlmAgent(
        name=subentry.title,
        model=subentry.data[CONF_MODEL],
        description=subentry.data[CONF_DESCRIPTION],
        instruction=subentry.data[CONF_INSTRUCTIONS],
    )
