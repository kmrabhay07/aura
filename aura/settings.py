"""Store non-secret preferences in QSettings and API keys in Windows Credential Manager."""
import os
from PySide6.QtCore import QSettings
from .providers import PROVIDERS

SERVICE = "AURA-Desktop-Agent"

class Settings:
    def __init__(self):
        self.store = QSettings("AURA", "DesktopAgent")

    def provider(self):
        value = self.store.value("provider", "Grok (xAI)")
        return value if value in PROVIDERS else "Grok (xAI)"

    def model(self):
        return self.store.value("model", PROVIDERS[self.provider()].default_model)

    def set_provider(self, provider, model):
        if provider not in PROVIDERS:
            raise ValueError("Unsupported provider")
        self.store.setValue("provider", provider)
        self.store.setValue("model", model.strip() or PROVIDERS[provider].default_model)

    def save_key(self, provider, key):
        import keyring
        if key:
            keyring.set_password(SERVICE, provider, key.strip())

    def api_key(self, provider):
        import keyring
        try:
            return keyring.get_password(SERVICE, provider) or (os.getenv("XAI_API_KEY", "") if provider == "Grok (xAI)" else "")
        except keyring.errors.KeyringError:
            return os.getenv("XAI_API_KEY", "") if provider == "Grok (xAI)" else ""
