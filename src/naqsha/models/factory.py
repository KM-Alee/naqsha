"""Construct a ``ModelClient`` from a validated ``RunProfile``."""

from __future__ import annotations

from naqsha.models.anthropic import AnthropicMessagesModelClient
from naqsha.models.base import ModelClient
from naqsha.models.fake import FakeModelClient
from naqsha.models.gemini import GeminiGenerateContentModelClient
from naqsha.models.ollama import OllamaChatModelClient
from naqsha.models.openai_compat import OpenAiCompatModelClient
from naqsha.profiles import DEFAULT_FAKE_SCRIPT, ProfileValidationError, RunProfile


def model_client_from_profile(profile: RunProfile) -> ModelClient:
    """Wire the profile's ``model`` field to a concrete ``ModelClient`` implementation."""

    kind = profile.model
    if kind == "fake":
        scripted = profile.fake_model_messages
        msgs = scripted if scripted is not None else DEFAULT_FAKE_SCRIPT
        return FakeModelClient(list(msgs))

    if kind == "openai_compat":
        if profile.openai_compat is None:
            raise ProfileValidationError("openai_compat profile section is missing.")
        oc = profile.openai_compat
        return OpenAiCompatModelClient(
            base_url=oc.base_url,
            model=oc.model,
            api_key_env=oc.api_key_env,
            timeout_seconds=oc.timeout_seconds,
        )

    if kind == "anthropic":
        if profile.anthropic is None:
            raise ProfileValidationError("anthropic profile section is missing.")
        a = profile.anthropic
        return AnthropicMessagesModelClient(
            base_url=a.base_url,
            model=a.model,
            api_key_env=a.api_key_env,
            timeout_seconds=a.timeout_seconds,
            max_tokens=a.max_tokens,
            anthropic_version=a.anthropic_version,
        )

    if kind == "gemini":
        if profile.gemini is None:
            raise ProfileValidationError("gemini profile section is missing.")
        g = profile.gemini
        return GeminiGenerateContentModelClient(
            base_url=g.base_url,
            model=g.model,
            api_key_env=g.api_key_env,
            timeout_seconds=g.timeout_seconds,
        )

    if kind == "ollama":
        if profile.ollama is None:
            raise ProfileValidationError("ollama profile section is missing.")
        o = profile.ollama
        return OllamaChatModelClient(
            base_url=o.base_url,
            model=o.model,
            api_key_env=o.api_key_env,
            timeout_seconds=o.timeout_seconds,
        )

    raise ProfileValidationError(f"Unsupported model adapter {kind!r}.")
