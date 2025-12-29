"""Config flow for google_adk integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
)

from .const import (
    CONF_NAME,
    CONF_DESCRIPTION,
    CONF_MODEL,
    CONF_INSTRUCTIONS,
    CONF_GEMINI_API_KEY,
    DOMAIN,
)


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        vol.Schema(
            {
                vol.Required(CONF_GEMINI_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Required(CONF_NAME): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Required(CONF_MODEL): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Optional(CONF_DESCRIPTION): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_INSTRUCTIONS): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }
        )
    )
}

OPTIONS_FLOW = {
    "init": SchemaFlowFormStep(),
}


class GoogleADKConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config flow for Switch as X."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    VERSION = 1
    MINOR_VERSION = 1

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options[CONF_NAME])
