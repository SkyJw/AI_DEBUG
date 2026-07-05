"""Build pydantic-ai models from settings profiles.

All backends are OpenAI-compatible, so a profile maps directly onto
``OpenAIChatModel`` + ``OpenAIProvider(base_url, api_key)``.
"""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from aidbg.config.settings import ModelProfile


def build_model(profile: ModelProfile) -> OpenAIChatModel:
    """Construct an ``OpenAIChatModel`` for the given backend profile."""
    provider = OpenAIProvider(base_url=profile.base_url, api_key=profile.api_key)
    return OpenAIChatModel(profile.model, provider=provider)
