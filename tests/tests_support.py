"""Shared test doubles; never access user's settings, keys, microphone or speaker."""
class SilentSpeaker:
    def wait_quiet(self, timeout=2):
        return True
    def say(self, *args):
        pass
    def finish(self, *args):
        pass
    def close(self):
        pass


class FakeSettings:
    saved_voice = None
    def provider(self):
        return "Grok (xAI)"
    def model(self):
        return "test-model"
    def hotkey(self):
        return "Ctrl+Alt+Space"
    def voice_replies(self):
        return False
    def set_voice_preferences(self, hotkey, replies):
        FakeSettings.saved_voice = hotkey, replies
    def save_key(self, provider, key):
        assert key == ""
    def set_provider(self, *args):
        pass

    def image_inputs(self):
        return False
    def remember_chats(self):
        return False
    def set_experience_preferences(self, *args):
        pass

    def speech_options(self):
        return '',200,-1
    def set_speech_options(self,*args):
        pass
