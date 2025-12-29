"""Config flow for google_adk integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
import logging

import voluptuous as vol

from homeassistant.helpers import selector
from homeassistant.config_entries import (
    ConfigFlowResult,
    ConfigEntryState,
    ConfigEntry,
    SOURCE_REAUTH,
    ConfigSubentryFlow,
    ConfigFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback


from .const import (
    CONF_NAME,
    CONF_DESCRIPTION,
    CONF_MODEL,
    CONF_INSTRUCTIONS,
    CONF_API_KEY,
    DOMAIN,
    DEFAULT_TITLE,
)

_LOGGER = logging.getLogger(__name__)

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_MODEL: "gemini-3-flash-preview",
}


STEP_API_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
    }
)


class GoogleADKConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch as X."""

    VERSION = 1
    MINOR_VERSION = 1

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options[CONF_NAME])

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self.async_step_api()

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is not None:
            return await self.async_step_api()

        reauth_entry = self._get_reauth_entry()
        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={
                CONF_NAME: reauth_entry.title,
                CONF_API_KEY: reauth_entry.data.get(CONF_API_KEY, ""),
            },
        )

    async def async_step_api(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            if self.source == SOURCE_REAUTH:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data=user_input,
                )
            return self.async_create_entry(
                title=DEFAULT_TITLE,
                data=user_input,
                # Let the user specify everything about the agent themselves
                subentries=[],
            )
        return self.async_show_form(
            step_id="api",
            data_schema=STEP_API_DATA_SCHEMA,
            description_placeholders={
                "api_key_url": "https://aistudio.google.com/app/apikey"
            },
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": LLMSubentryFlowHandler,
        }


class LLMSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing conversation subentries."""

    last_rendered_recommended = False

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_set_options(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Set conversation options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        errors: dict[str, str] = {}

        if user_input is None:
            _LOGGER.debug("set up is_new: %s", self._is_new)
            if self._is_new:
                options: dict[str, Any] = RECOMMENDED_CONVERSATION_OPTIONS.copy()
            else:
                # If this is a reconfiguration, we need to copy the existing options
                # so that we can show the current values in the form.
                options = self._get_reconfigure_subentry().data.copy()
        else:
            options = user_input
            _LOGGER.debug("save is_new: %s", self._is_new)
            if self._is_new:
                return self.async_create_entry(
                    title=user_input.pop(CONF_NAME),
                    data=user_input,
                )

            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=user_input,
            )

        schema = await _options_schema_factory(self._is_new, options)
        return self.async_show_form(
            step_id="set_options", data_schema=vol.Schema(schema), errors=errors
        )

    async_step_reconfigure = async_step_set_options
    async_step_user = async_step_set_options


async def _options_schema_factory(is_new: bool, options: dict[str, Any]) -> vol.Schema:
    """Return schema for an options flow."""
    schema: dict[vol.Required | vol.Optional, Any] = {}
    if is_new:
        schema[vol.Required(CONF_NAME)] = str
    schema.update(
        {
            vol.Required(
                CONF_MODEL,
                default=options.get(CONF_MODEL),
            ): selector.TextSelector(selector.TextSelectorConfig()),
            vol.Required(
                CONF_DESCRIPTION,
                default=options.get(CONF_DESCRIPTION, ""),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_INSTRUCTIONS,
                default=options.get(CONF_INSTRUCTIONS, ""),
            ): selector.TemplateSelector(),
        }
    )
    _LOGGER.debug("Is new: %s", is_new)
    _LOGGER.debug("Schema generated: %s", schema)
    return schema
