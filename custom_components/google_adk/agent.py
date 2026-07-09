"""Module for agents."""

import logging
import json
from typing import Any, Optional, cast
from slugify import slugify
from collections.abc import Callable, Awaitable

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.google_llm import Gemini
from google.genai.types import (
    FunctionDeclaration,
    Schema,
)
from voluptuous_openapi import convert

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import llm

from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.sessions import Session

from .const import (
    CONF_MODEL,
    CONF_INSTRUCTIONS,
    CONF_DESCRIPTION,
    DOMAIN,
    CONF_MEMORY_ENABLED,
)

CONF_USE_INTERACTIONS_API = "use_interactions_api"


_LOGGER = logging.getLogger(__name__)


def _to_json_schema(schema: Any) -> Any:
    """Recursively lowercase type fields to produce valid JSON Schema from a Gemini schema dict."""
    if isinstance(schema, dict):
        return {
            k: v.lower() if k == "type" and isinstance(v, str) else _to_json_schema(v)
            for k, v in schema.items()
        }
    if isinstance(schema, list):
        return [_to_json_schema(item) for item in schema]
    return schema


_EMPTY_JSON_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


async def async_create(
    hass: HomeAssistant, subentry: ConfigSubentry, llm_context: llm.LLMContext
) -> BaseAgent:
    """Register all agents using the agent framework."""
    _LOGGER.debug("Registering Google ADK agent '%s'", subentry.title)
    use_interactions_api = subentry.data.get(CONF_USE_INTERACTIONS_API, False)
    tools: list[Any] = await _async_create_tools(
        hass, subentry, llm_context, use_interactions_api=use_interactions_api
    )
    sub_agents = await _async_create_sub_agents(hass, subentry, llm_context)

    memory_enabled = subentry.data.get(CONF_MEMORY_ENABLED, False)
    if memory_enabled:
        tools.append(PreloadMemoryTool())

    model_name = subentry.data[CONF_MODEL]
    if use_interactions_api:
        model = Gemini(model=model_name, use_interactions_api=True)
    else:
        model = model_name

    agent = LlmAgent(
        name=slugify(subentry.title, separator="_"),
        model=model,
        description=subentry.data[CONF_DESCRIPTION],
        instruction=subentry.data[CONF_INSTRUCTIONS],
        tools=tools,
        sub_agents=sub_agents,
    )

    if memory_enabled:
        agent.after_agent_callback = _create_memory_callback(hass, subentry)

    return agent


def _sub_agent_entry(entry_id: str, hass: HomeAssistant) -> ConfigSubentry | None:
    """Get sub_agent config entry by ID."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        for subentry in entry.subentries.values():
            if subentry.subentry_id == entry_id:
                return subentry
    return None


async def _async_create_sub_agents(
    hass: HomeAssistant, subentry: ConfigSubentry, llm_context: llm.LLMContext
) -> list[BaseAgent]:
    """Create sub_agents for a given agent subentry."""
    sub_agents: list[BaseAgent] = []
    for sub_agent_id in subentry.data.get("sub_agents", []):
        if (sub_agent_entry := _sub_agent_entry(sub_agent_id, hass)) is None:
            _LOGGER.warning(
                "Sub-agent with ID '%s' not found for agent '%s'",
                sub_agent_id,
                subentry.title,
            )
            continue
        sub_agent = await async_create(hass, sub_agent_entry, llm_context)
        sub_agents.append(sub_agent)
    return sub_agents


SUPPORTED_SCHEMA_KEYS = {
    # Gemini API does not support all of the OpenAPI schema
    # SoT: https://ai.google.dev/api/caching#Schema
    "type",
    "format",
    "description",
    "nullable",
    "enum",
    "max_items",
    "min_items",
    "properties",
    "required",
    "items",
}


def _camel_to_snake(name: str) -> str:
    """Convert camel case to snake case."""
    return "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")


def _format_schema(schema: dict[str, Any]) -> Schema:
    """Format the schema to be compatible with Gemini API."""
    if subschemas := schema.get("allOf"):
        for subschema in subschemas:  # Gemini API does not support allOf keys
            if "type" in subschema:  # Fallback to first subschema with 'type' field
                return _format_schema(subschema)
        return _format_schema(
            subschemas[0]
        )  # Or, if not found, to any of the subschemas

    result = {}
    for key, val in schema.items():
        key = _camel_to_snake(key)
        if key not in SUPPORTED_SCHEMA_KEYS:
            continue
        if key == "type":
            val = val.upper()
        elif key == "format":
            # Gemini API does not support all formats, see: https://ai.google.dev/api/caching#Schema
            # formats that are not supported are ignored
            if schema.get("type") == "string" and val not in ("enum", "date-time"):
                continue
            if schema.get("type") == "number" and val not in ("float", "double"):
                continue
            if schema.get("type") == "integer" and val not in ("int32", "int64"):
                continue
            if schema.get("type") not in ("string", "number", "integer"):
                continue
        elif key == "items":
            val = _format_schema(val)
        elif key == "properties":
            val = {k: _format_schema(v) for k, v in val.items()}
        result[key] = val

    if result.get("enum") and result.get("type") != "STRING":
        # enum is only allowed for STRING type. This is safe as long as the schema
        # contains vol.Coerce for the respective type, for example:
        # vol.All(vol.Coerce(int), vol.In([1, 2, 3]))
        result["type"] = "STRING"
        result["enum"] = [str(item) for item in result["enum"]]

    if result.get("type") == "OBJECT" and not result.get("properties"):
        # An object with undefined properties is not supported by Gemini API.
        # Fallback to JSON string. This will probably fail for most tools that want it,
        # but we don't have a better fallback strategy so far.
        result["properties"] = {"json": {"type": "STRING"}}
        result["required"] = []
    return cast(Schema, result)


class AdkLlmTool(BaseTool):
    """Home Assistant Tool wrapper."""

    def __init__(
        self,
        llm_api: llm.APIInstance,
        tool: llm.Tool,
        hass: HomeAssistant,
        use_interactions_api: bool = False,
    ) -> None:
        """Initialize the Home Assistant Tool."""
        super().__init__(name=tool.name, description=tool.description)
        self._llm_api = llm_api
        self._llm_tool = tool
        self._use_interactions_api = use_interactions_api
        if tool.parameters.schema:
            self._parameters = _format_schema(convert(tool.parameters))
        else:
            self._parameters = None

    def _get_declaration(self) -> Optional[FunctionDeclaration]:
        """Gets the OpenAPI specification of this tool in the form of a FunctionDeclaration."""
        if self._use_interactions_api:
            # The Interactions API requires JSON Schema (lowercase types) and always
            # needs a parameters field. Use parameters_json_schema to bypass the
            # Gemini Schema model_dump which produces uppercase types (STRING, OBJECT, etc.)
            # that the Interactions API rejects.
            json_schema = (
                _to_json_schema(self._parameters)
                if self._parameters is not None
                else _EMPTY_JSON_SCHEMA
            )
            return FunctionDeclaration(
                name=self.name,
                description=self.description,
                parameters_json_schema=json_schema,
            )
        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=self._parameters,
        )

    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> Any:
        """Run the tool asynchronously."""
        tool_input = llm.ToolInput(
            tool_name=self.name,
            tool_args=args,
        )
        tool_response = await self._llm_api.async_call_tool(tool_input)
        if hasattr(tool_response, "response"):
            response_data = tool_response.response
        else:
            response_data = tool_response

        if isinstance(response_data, (dict, list)):
            return json.dumps(response_data)
        return str(response_data)


async def _async_create_tools(
    hass: HomeAssistant,
    subentry: ConfigSubentry,
    llm_context: llm.LLMContext,
    use_interactions_api: bool = False,
) -> list[BaseTool]:
    """Create tools for a given agent subentry."""
    tools = []
    if subentry.data.get("tools"):
        llm_api = await llm.async_get_api(hass, subentry.data["tools"], llm_context)
        for tool in llm_api.tools:
            try:
                tools.append(
                    AdkLlmTool(
                        llm_api, tool, hass, use_interactions_api=use_interactions_api
                    )
                )
            except Exception as e:
                _LOGGER.warning("Skipping tool '%s' due to schema conversion error: %s", tool.name, e)
    return tools


def _create_memory_callback(
    hass: HomeAssistant, subentry: ConfigSubentry
) -> Callable[[CallbackContext], Awaitable[None]]:
    """Create a callback to save session to memory."""

    async def auto_save_session_to_memory_callback(
        callback_context: CallbackContext,
    ) -> None:
        """Save session to memory."""
        session: Session = callback_context._invocation_context.session
        memory_service = callback_context._invocation_context.memory_service

        if not memory_service:
            _LOGGER.warning("Memory service not available in context")
            return

        await memory_service.add_session_to_memory(session)

    return auto_save_session_to_memory_callback
