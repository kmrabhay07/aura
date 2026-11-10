"""Store non-secret preferences in QSettings and API keys in Windows Credential Manager."""
import os
from PySide6.QtCore import QSettings
from .providers import PROVIDERS

SERVICE = "AURA-Desktop-Agent"

class Settings:
    def __init__(self):
        self.store = QSettings("AURA", "DesktopAgent")

    def provider(self):
        value = self.store.value("provider", "OpenAI (GPT)")
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
            saved = keyring.get_password(SERVICE, provider)
        except keyring.errors.KeyringError:
            saved = None
        if saved:
            return saved
        if provider == "OpenAI (GPT)":
            return os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("OPEN_API_KEY", "").strip()
        if provider == "Grok (xAI)":
            return os.getenv("XAI_API_KEY", "")
        return ""

    def hotkey(self):
        from .hotkey import DEFAULT_HOTKEY
        return self.store.value("voice/hotkey", DEFAULT_HOTKEY)

    def voice_replies(self):
        return self.store.value("voice/replies", False, type=bool)

    def set_voice_preferences(self, hotkey, replies):
        from .hotkey import parse_hotkey
        parse_hotkey(hotkey)
        self.store.setValue("voice/hotkey", hotkey.strip())
        self.store.setValue("voice/replies", bool(replies))

    def image_inputs(self):
        return self.store.value('experience/image_inputs',False,type=bool)

    def remember_chats(self):
        return self.store.value('experience/remember_chats',False,type=bool)

    def set_experience_preferences(self, image_inputs, remember_chats):
        self.store.setValue('experience/image_inputs',bool(image_inputs))
        self.store.setValue('experience/remember_chats',bool(remember_chats))

    def speech_options(self):
        return (self.store.value('voice/id',''),self.store.value('voice/rate',200,type=int),
                self.store.value('voice/input_device',-1,type=int))

    def set_speech_options(self, voice, rate, device):
        self.store.setValue('voice/id',str(voice))
        self.store.setValue('voice/rate',max(100,min(300,int(rate))))
        self.store.setValue('voice/input_device',int(device))
