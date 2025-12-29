"""Module for agents."""

import logging
from typing import Any, Optional, cast
from slugify import slugify

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.adk.agents import BaseAgent, LlmAgent
from google.genai.types import (
    FunctionDeclaration,
    Schema,
    Tool,
)
from voluptuous_openapi import convert

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import llm

from .const import CONF_MODEL, CONF_INSTRUCTIONS, CONF_DESCRIPTION, DOMAIN


_LOGGER = logging.getLogger(__name__)


async def async_create(
    hass: HomeAssistant, subentry: ConfigSubentry, llm_context: llm.LLMContext
) -> BaseAgent:
    """Register all agents using the agent framework."""
    _LOGGER.debug("Registering Google ADK agent '%s'", subentry.title)
    tools = await _async_create_tools(hass, subentry, llm_context)
    sub_agents = await _async_create_sub_agents(hass, subentry, llm_context)
    return LlmAgent(
        name=slugify(subentry.title, separator="_"),
        model=subentry.data[CONF_MODEL],
        description=subentry.data[CONF_DESCRIPTION],
        instruction=subentry.data[CONF_INSTRUCTIONS],
        tools=tools,
        sub_agents=sub_agents,
    )


def _sub_agent_entry(entry_id: str, hass: HomeAssistant) -> ConfigSubentry | None:
    """Get sub_agent config entry by ID."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        for subentry in entry.subentries.values():
            if subentry.subentry_id == entry_id:
                return subentry
    return None


async def _async_create_sub_agents(
    hass: HomeAssistant, subentry: ConfigSubentry, llm_context: llm.LLMContext
) -> BaseAgent:
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
        self, llm_api: llm.LLMApi, tool: llm.Tool, hass: HomeAssistant
    ) -> None:
        """Initialize the Home Assistant Tool."""
        super().__init__(name=tool.name, description=tool.description)
        self._llm_api = llm_api
        self._llm_tool = tool
        if tool.parameters.schema:
            self._parameters = _format_schema(convert(tool.parameters))
        else:
            self._parameters = None

    def _get_declaration(self) -> Optional[FunctionDeclaration]:
        """Gets the OpenAPI specification of this tool in the form of a FunctionDeclaration."""
        return FunctionDeclaration(
            name=self._name,
            description=self._description,
            parameters=self._parameters,
        )

    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> Any:
        """Run the tool asynchronously."""
        tool_input = llm.ToolInput(
            tool_name=self._name,
            tool_args=args,
        )
        return await self._llm_api.async_call_tool(tool_input)


async def _async_create_tools(
    hass: HomeAssistant,
    subentry: ConfigSubentry,
    llm_context: llm.LLMContext,
) -> list[Tool]:
    """Create tools for a given agent subentry."""
    tools = []
    if subentry.data.get("tools"):
        llm_api = await llm.async_get_api(hass, subentry.data["tools"], llm_context)
        for tool in llm_api.tools:
            tools.append(AdkLlmTool(llm_api, tool, hass))
    return tools
