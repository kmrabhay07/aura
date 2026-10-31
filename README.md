# AURA — Windows AI Desktop Assistant

AURA is an experimental Windows desktop assistant powered by Grok (xAI API). It has a dark PySide6 interface and a constrained tool-calling agent for opening URLs, searching the web, and launching a few allowlisted Windows applications.

## Getting started (Windows)

1. Install Python 3.12+.
2. Clone the repository and open a terminal in its root.
3. Create a virtual environment: `py -m venv .venv`
4. Activate: `.venv\Scripts\activate`
5. Install: `pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and set your xAI API key.
7. Launch: `python -m aura.main`

## Safety

Never commit `.env`, credentials, or tokens. The current agent exposes only three allowlisted actions and does not yet automate ChatGPT or Apple Music playback. Browser URLs and search pages are opened, not controlled with Playwright. The project is a starter, not a finished autonomous agent.

## Roadmap

- Modern QML desktop UI with activity timeline and settings
- Browser automation with Playwright and verified actions
- Expanded Windows UI Automation with permission prompts
- Voice input/output and media controls
- Tests, packaging, and security hardening

## Voice and browser preview

The **Speak** button records six seconds of audio and transcribes it locally with faster-whisper, then submits the recognized command to the same Grok agent. The first transcription may download a model. This is push-to-talk, not an always-on wake-word assistant.

Install Chromium once with `python -m playwright install chromium`. The browser tool currently opens pages and Google searches; Apple Music playback, ChatGPT interaction, and arbitrary browser clicks are not yet implemented.

The UI uses a dark PySide6 Widgets design; QML and more advanced styling remain on the roadmap. `scripts/build.ps1` is an experimental packaging script, not a verified release build.

**Current limitations:** No cancellation during execution, no persisted conversation memory, no automated media playback, and no general-purpose desktop control. Review commands before execution. Never commit secrets.
