"""Provider configuration for OpenAI-compatible APIs and Anthropic."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    default_model: str

PROVIDERS = {
    "Grok (xAI)": Provider("Grok (xAI)", "https://api.x.ai/v1", "grok-4-latest"),
    "OpenAI (GPT)": Provider("OpenAI (GPT)", "https://api.openai.com/v1", "gpt-4.1-mini"),
    "Claude (Anthropic)": Provider("Claude (Anthropic)", "https://api.anthropic.com", "claude-sonnet-4-5"),
    "DeepSeek": Provider("DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
    "OpenRouter": Provider("OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4.1-mini"),
    "Ollama (local)": Provider("Ollama (local)", "http://127.0.0.1:11434/v1", "llama3.1"),
}

def make_client(provider, api_key):
    if provider == "Claude (Anthropic)":
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    from openai import OpenAI
    return OpenAI(api_key=api_key or "ollama", base_url=PROVIDERS[provider].base_url)
