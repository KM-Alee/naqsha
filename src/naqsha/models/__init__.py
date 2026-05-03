"""Model Client ports and adapters."""

from typing import TYPE_CHECKING

__all__ = [
    "AnthropicMessagesModelClient",
    "GeminiGenerateContentModelClient",
    "ModelInvocationError",
    "OllamaChatModelClient",
    "OpenAiCompatModelClient",
    "model_client_from_profile",
]

if TYPE_CHECKING:
    from naqsha.models.anthropic import AnthropicMessagesModelClient
    from naqsha.models.errors import ModelInvocationError
    from naqsha.models.gemini import GeminiGenerateContentModelClient
    from naqsha.models.ollama import OllamaChatModelClient
    from naqsha.models.openai_compat import OpenAiCompatModelClient


def __getattr__(name: str):
    if name == "AnthropicMessagesModelClient":
        from naqsha.models.anthropic import AnthropicMessagesModelClient

        return AnthropicMessagesModelClient
    if name == "GeminiGenerateContentModelClient":
        from naqsha.models.gemini import GeminiGenerateContentModelClient

        return GeminiGenerateContentModelClient
    if name == "ModelInvocationError":
        from naqsha.models.errors import ModelInvocationError

        return ModelInvocationError
    if name == "OllamaChatModelClient":
        from naqsha.models.ollama import OllamaChatModelClient

        return OllamaChatModelClient
    if name == "OpenAiCompatModelClient":
        from naqsha.models.openai_compat import OpenAiCompatModelClient

        return OpenAiCompatModelClient
    if name == "model_client_from_profile":
        from naqsha.models.factory import model_client_from_profile

        return model_client_from_profile
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
