"""Application settings via pydantic-settings.

Backend profiles are nested: ``AIDBG_DEFAULT__BASE_URL`` populates
``settings.profiles["default"].base_url``. Each agent references a profile by
name (``AIDBG_PROFILE_CODER=ollama``). Adding a backend is 3 env lines; no code
change beyond an ``.env`` entry.

pydantic-settings does not natively collapse ``AIDBG_<NAME>__<FIELD>`` env vars
into a ``dict[str, Model]``, so :class:`_ProfilesSource` does that grouping.
Known top-level fields (``PROFILE_*``, ``THEME`` …) are excluded from grouping.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_ENV_PREFIX = "AIDBG_"
_NESTED_DELIM = "__"

# Env keys (without prefix) that are real top-level fields, never profile groups.
_RESERVED = {
    "PROFILE_ORCHESTRATOR",
    "PROFILE_CODER",
    "PROFILE_RESEARCHER",
    "PROFILE_REVIEWER",
    "PROFILE_ANALYST",
    "THEME",
    "HISTORY_PATH",
    "MCP_CONFIG",
}


class ModelProfile(BaseModel):
    """One OpenAI-compatible backend (DeepSeek / Ollama / vLLM / OpenAI)."""

    base_url: str = "http://localhost:11434/v1"
    api_key: str = "not-needed"
    model: str = "deepseek-chat"


class _ProfilesSource(PydanticBaseSettingsSource):
    """Collapse ``AIDBG_<NAME>__<FIELD>`` env vars into ``profiles[name]``."""

    def __init__(self, settings_cls: type[BaseSettings], env: dict[str, str]):
        super().__init__(settings_cls)
        self._env = env

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:  # noqa: D102
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        grouped: dict[str, dict[str, str]] = {}
        for raw_key, value in self._env.items():
            if not raw_key.startswith(_ENV_PREFIX):
                continue
            key = raw_key[len(_ENV_PREFIX) :]
            if _NESTED_DELIM not in key:
                continue
            name, _, field = key.partition(_NESTED_DELIM)
            if name in _RESERVED or not field:
                continue
            grouped.setdefault(name.lower(), {})[field.lower()] = value
        if not grouped:
            return {}
        return {"profiles": {name: ModelProfile(**vals) for name, vals in grouped.items()}}


class Settings(BaseSettings):
    """Root settings. Loaded from environment + ``.env`` with ``AIDBG_`` prefix."""

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profiles: dict[str, ModelProfile] = {}

    # Which profile each agent uses.
    profile_orchestrator: str = "default"
    profile_coder: str = "default"
    profile_researcher: str = "default"
    profile_reviewer: str = "default"
    profile_analyst: str = "default"

    # UI + persistence.
    theme: str = "aidbg-black"
    history_path: str = ".aidbg/history.jsonl"
    mcp_config: str = "mcp_servers.json"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Merge process env + .env for profile grouping; init_settings wins.
        merged = _read_dotenv(cls.model_config.get("env_file")) | dict(os.environ)
        profiles = _ProfilesSource(settings_cls, merged)
        return (init_settings, env_settings, dotenv_settings, profiles, file_secret_settings)

    def profile_for(self, agent_name: str) -> ModelProfile:
        """Resolve the backend profile an agent should use.

        Falls back to ``default`` (then to a stock :class:`ModelProfile`) if the
        named profile is missing, so a typo in ``.env`` degrades gracefully.
        """
        name = getattr(self, f"profile_{agent_name}", "default")
        return self.profiles.get(name) or self.profiles.get("default") or ModelProfile()


def _read_dotenv(path: Any) -> dict[str, str]:
    """Minimal ``.env`` reader (``KEY=VALUE`` lines) for profile grouping."""
    result: dict[str, str] = {}
    if not path or not os.path.isfile(path):
        return result
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def load_settings() -> Settings:
    """Load settings from environment and ``.env``.

    Guarantees at least a ``default`` profile exists.
    """
    settings = Settings()
    if "default" not in settings.profiles:
        settings.profiles["default"] = ModelProfile()
    return settings
