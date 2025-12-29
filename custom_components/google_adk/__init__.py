"""google_adk custom component."""

from __future__ import annotations

import os
import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .types import GoogleAdkConfigEntry
from .const import CONF_API_KEY

_LOGGER = logging.getLogger(__name__)


PLATFORMS: tuple[Platform] = (Platform.CONVERSATION,)


async def async_setup_entry(hass: HomeAssistant, entry: GoogleAdkConfigEntry) -> bool:
    """Set up a config entry."""
    if os.environ.get("GOOGLE_API_KEY") is None:
        _LOGGER.info("Setting GOOGLE_API_KEY environment variable")
        os.environ["GOOGLE_API_KEY"] = entry.data[CONF_API_KEY]
    else:
        _LOGGER.info("GOOGLE_API_KEY environment variable already set")

    await hass.config_entries.async_forward_entry_setups(
        entry,
        platforms=PLATFORMS,
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoogleAdkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )


async def async_reload_entry(hass: HomeAssistant, entry: GoogleAdkConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
