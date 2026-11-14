# Jarvis — Windows voice, screen and browser assistant

Jarvis is the user-facing name. The existing AURA repository, `aura` Python
package, AURA settings/credential identifiers and `AURA.exe` packaging layout
remain for compatibility. Saved AI keys stay in the same Windows credential vault.
This is an incremental implementation of a screen-aware companion, not a claim
of complete feature or performance parity with another product.

## Start

Use Python 3.12+ on Windows, create/activate a virtual environment, install
`requirements.txt`, then run `python -m aura`. Open **Settings** for your existing
provider, model and API key. No new runtime dependencies or paid services were
added. Your selected endpoint/model must support streaming/tool calling; screen
questions additionally require an image-capable model.

The local source launcher delivered with the implementation starts this checkout
using its existing virtual environment. It is not a newly built standalone EXE.

## Voice and conversation

- Hold **Ctrl+Alt+Space** globally and release any member to send. Release all
  members before the next hold. Configure Ctrl/Alt/Shift/Win + Space or F1–F12 in
  Settings. Either Windows key is supported. The chord is observed rather than
  intercepted; avoid conflicts with other applications.
- The **Hold to talk** buttons use the same pipeline. Button capture ends on
  release or window deactivation. Global capture follows the actual chord state.
- “Jarvis, can you do this?” and an ordinary request both work after activation.
  There is no wake word or always-on microphone. Very short taps between polling
  ticks may not activate. Recording has a 120-second safety cap, replacing the
  old fixed six-second recording.
- Microphone audio goes directly to faster-whisper without temporary WAV files.
  One model is reused after its first load/download. Text streams into the UI;
  optional local spoken replies use one engine and a cancellable sentence queue.
- Settings include Windows voice selection, speech speed and microphone choice.
  Device identifiers may need reselecting after hardware changes. Real speech
  availability and quality depend on the installed Windows voice and driver.
- **Cancel / stop** or Escape stops the current interaction and clears guidance.
  New input supersedes old input. Late output, history commits and pending
  actions are rejected. Native model operations or network reads may take time
  to unwind. An already executed approved action cannot be undone by cancellation.
- Capture waits for earlier speech to stop. If a speech driver cannot confirm
  stopping, microphone capture is blocked until restart. Text remains usable.

## Floating Jarvis

Choose **Floating Jarvis** to replace the large workspace with a compact,
always-on-top panel. Drag the Jarvis title to move it. The panel shares the same
controller, input, screen-consent control, answer stream and stop control.
**Workspace** or **Close** returns to the full window. It is an interactive panel;
the separate annotation layer is the part that passes clicks through.

## Screen context and visual guidance

1. Select a model whose provider documents image support. In Settings, explicitly
   enable **My selected AI model accepts screen images**. This is a user-confirmed
   capability gate, not an automatic test of a remote model.
2. Choose the monitor in the workspace, or leave **Monitor under pointer**.
3. Select **Include screen once**, then type or hold-to-talk. One JPEG screenshot
   is attached to that request and sent to your configured AI provider. The
   checkbox resets. No continuous screen sampling or screenshot files are added.
4. Ask about what is visible or where to click. Jarvis may request arrows, circles
   or rectangles with short labels. Coordinates are validated and mapped from
   normalized image positions into the selected monitor's logical geometry.

Guidance is a transparent, input-transparent, non-focus-taking Qt window. It
performs no click or typing. It clears on cancellation/new input, monitor geometry
changes, tracked foreground-window changes/movement, or 60-second expiry. Changes
inside the same window (such as scrolling/content updates) are not completely
detected: share a fresh screen if the content changes. Image content and page
content are untrusted data and cannot grant approval for actions.

Jarvis requests Windows capture exclusion for its own windows; actual behavior
must be verified on the target Windows version. Captures remain in memory for the
active request/temporary guidance, and are not included in saved history. The AI
provider's handling of an explicitly shared image is governed by that provider.

## Session context and saved conversations

In-memory context is bounded to 12 completed user/assistant pairs and 24,000
characters. Interrupted/failed partial answers are not completed history. Tool
protocols remain inside their own turn; observed action results are retained as
text context. New conversation and accepting Settings reset active context.

**Remember completed chats on this PC** is off by default. When enabled, completed
text conversations are saved locally in
`%LOCALAPPDATA%\Jarvis\conversations.sqlite3`, retaining the most recent 30.
Images, audio, API keys and provider settings are not added by the history store.
The user's own text can contain private information: saved chats are unencrypted.

**Conversations** filters saved titles, restores a conversation and deletes a
selected conversation. Delete removes local records and prevents an in-flight
save from restoring them. Disabling saving stops future saves; existing records
remain accessible for deletion. Local deletion cannot retract data already sent
to an AI provider. New conversation clears the current transcript and activity;
it does not delete separately saved records.

## Supervised browser tasks

Type a task and choose **Run browser task**, or enable **Browser tools once**
for your next request. Jarvis can open a URL, read a page, click a target from a
fresh read, fill an approved field without submitting, or go back. The task runs
on background workers so the UI remains responsive. There is one supervised
conversational task at a time; new input cancels the previous task. **Activity /
tasks** shows status and recent results and offers Stop current task.

Browser tasks use installed Microsoft Edge and a dedicated profile at
`%LOCALAPPDATA%\Jarvis\BrowserProfile`. They do not attach to your personal browser
profile or copy accounts/cookies from other apps. Sign in manually in the Jarvis
browser if a site needs an account. Chrome/Edge extension bridging into existing
profiles is not implemented. Playwright's driver is bundled; Edge itself is not.

Every browser step requires a one-time approval showing the site and exact
operation/control/text. No is the default. Read again after an action to verify
its outcome and get fresh target identifiers. Navigation, target changes or a
changed review invalidate the pending action. Password, code, payment-detail,
secret and upload fields are blocked; the model cannot supply JavaScript to run.
Only fixed inspection/action routines are used. The browser runtime is assigned
to an app-owned Windows job for child-process cleanup on exit; if that isolation
cannot be established, browser launch fails closed. This uses internal Playwright
process metadata and requires validation after Playwright upgrades.

This browser agent is an initial implementation: one page, bounded rounds,
a limited control snapshot and no file-upload/download tools. It is not a
complete browser automation or general desktop-control system. Existing
allowlisted app, media and URL actions also retain their approval boundary.
Lock screen remains disabled. No automatic sending, purchasing or account
connections are enabled by installation or screen sharing.

## Windows packaging

The existing layout is `dist/AURA/AURA.exe` beside `_internal`, and the artifact
is `AURA-Windows`; the visible assistant remains Jarvis. The Windows workflow
runs on main pushes, pull requests and manual dispatch. It retains the PyAV
compatibility guard and collects faster-whisper data, including the Silero VAD
ONNX file at `_internal/faster_whisper/assets/silero_vad_v6.onnx`.

The workflow now also collects Playwright's driver data rather than excluding
Playwright. `scripts/verify-package.ps1` runs the frozen
`--verify-voice-assets <report.json>` check, which loads VAD, processes silence
and verifies the browser driver executable/CLI files. It does not open a browser,
record audio, capture a desktop or make an AI request. The workflow uploads app
files directly, avoiding a wrapper ZIP inside GitHub's artifact ZIP. Keep the
required `_internal/base_library.zip`. Extract once and run the EXE.

No new standalone EXE has been verified for these local changes. The prior
successful build at commit 2622d21 verifies only the earlier VAD packaging fix.
A new Windows build, frozen checks and manual testing are required before release.
The app is not code-signed. The local build script requires PyInstaller and the
existing requirements; no Chromium download is needed for the Edge-based agent.

## Checks and manual acceptance

Run `python -m pytest -q`, `python -m compileall -q aura tests` and
`python -m pip check`. Tests fake keyboard states, audio devices, speech engines,
AI providers and browser pages. They render synthetic Qt widgets; they never
capture the user's desktop or launch the real browser. Real installed VAD is
tested on silence, and installed browser driver files are checked without running
them. Test success does not establish live microphone, hotkey, vision, browser,
speech, Windows process-guard or end-to-end latency behavior.

Manually verify on Windows, in source and then packaged:

- Shortcut release order, repeats, focus changes, short taps, >6-second recordings,
  microphone denial/disconnect, rapid cancellation and close during each stage.
- Actual speech stops before capture; chosen voices/speed/devices work.
- Selected-monitor sharing is explicit, own windows are excluded, image-capable
  provider calls work, and no screenshot/audio files appear in saved history.
- Guidance alignment on negative-coordinate and mixed-DPI monitors, click-through,
  focus preservation, cancellation, expiry and window movement. Refresh after
  scrolling or content changes.
- Saved-history opt-in, restart/restore, title filtering, deletion and late-save
  protection. API keys remain in the original credential vault.
- Browser approval denial/expiry, changed target/site invalidation, protected
  fields, login by hand, observed outcomes and all child processes closing when
  Jarvis exits. Test only the approved task, not unattended privileged workflows.

## Remaining parity work

Full-duplex realtime cloud voice, automatic model prewarming, richer audio/device
routing, concurrent/scheduled agents, personal-browser extension bridging,
third-party account integrations and rich 3D drawing are not implemented here.
Any new paid speech service/account connection requires a separate explicit choice.
Wake-word activation remains a separate, explicitly opt-in proposal.

## OpenAI setup

OpenAI (GPT) is the default for new setups. Existing provider selections are
preserved. Select OpenAI (GPT) in Jarvis Settings to use one credential for
chat, screen-aware requests, conversation context and tool decisions. Enter
the key in Settings to store it in Windows Credential Manager, or provide
OPENAI_API_KEY at runtime. OPEN_API_KEY also works as a fallback.
Microphone transcription and spoken replies use the existing local engines.

The manual **Check OpenAI credential** workflow on main maps the repository
secret OPEN_API_KEY to OPENAI_API_KEY for one model-access check. The Windows
build and downloadable EXE do not receive the secret.
