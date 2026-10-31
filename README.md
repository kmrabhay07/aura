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

Never commit `.env`, credentials, or tokens. The current agent exposes only three allowlisted actions and does not yet automate ChatGPT or Apple Music playback. Browser URLs and search pages are opened in the default browser; advanced page control is not implemented. The project is a starter, not a finished autonomous agent.

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

## Multiple AI providers

Open **AI Provider / API Key** in the sidebar, select Grok, OpenAI, Claude, DeepSeek, OpenRouter, or local Ollama, enter a compatible model ID and your own API key, then save. Credentials are stored using Python keyring (Windows Credential Manager on Windows). Model availability and API compatibility depend on each provider. No provider keys are bundled.

## Windows executable

The GitHub Actions workflow `.github/workflows/windows-build.yml` builds an experimental Windows application and uploads `AURA-Windows.zip` to the workflow run's **Artifacts** section. Extract the ZIP and run `AURA.exe` inside its folder. The build is not code-signed. Browser binaries are not bundled; Playwright browser automation may require `python -m playwright install chromium` on the target machine. Voice recognition may download a Whisper model at first use. No Windows release has been verified yet.

## Current build and browser behavior

The Windows workflow now packages `aura/__main__.py` and checks for `dist/AURA/AURA.exe`. The packaged EXE is **not verified** until a GitHub Actions run completes successfully and its artifact is inspected. Browser commands use the default browser and retain normal sign-in sessions. Apple Music search opens search results, but playback selection is not automated. Voice input requires microphone permission; local Whisper model files may download on first use. Spoken responses are optional.
