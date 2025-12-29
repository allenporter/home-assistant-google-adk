"""Types for the Rulebook integration."""

from dataclasses import dataclass

from google.adk.agents import BaseAgent

from homeassistant.config_entries import ConfigEntry


@dataclass(frozen=True, kw_only=True)
class GoogleAdkContext:
    """Context for the Rulebook integration."""

    agent: BaseAgent


type GoogleAdkConfigEntry = ConfigEntry[GoogleAdkContext]
