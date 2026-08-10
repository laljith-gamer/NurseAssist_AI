# NurseAssist_AI — Plan

## Milestones

| ID | Goal | Verification | Status |
|---|---|---|---|
| M1 | Replace synthetic NLP templates with reproducible nursing data. | Train, hold out test split, export parity test, and quality gate pass. | Implemented locally; workflow pending first run |
| M2 | Make on-device Gemma replies single-turn, concise, and safe. | Test several unrelated prompts in one session; no prompt/history echo or repetition. | Needs device verification |
| M3 | Require nurse review before every AI-proposed chart write. | Stage a vital and medication proposal; confirm and discard each on device. | Implemented; needs device verification |
| M4 | Serve one valid MediaPipe/LiteRT `.task` model from the public Hugging Face bucket. | Clean install downloads and initializes it. | Ready for device verification |
| M5 | Keep chats, nursing observations, and AI context strictly patient-scoped. | Switch between two patients; verify New chat, History, notes, and model context never cross patients. | Implemented; needs device verification |
| M6 | Build and install a release APK. | `flutter build apk --release` from `frontend`. | Pending after M2–M5 |

## Current decision

The 2.71 GB model is delivered directly from the public Hugging Face bucket.
GitHub Release assets are limited to under 2 GiB, so the model-upload workflow
has been removed. The app model filename and bucket URL must stay aligned.

The separate small nursing-observation update is trained from Microsoft's
public SYNUR dataset. It is advisory context only; the nurse must confirm all
chart proposals before they are stored.

Each patient has isolated chat sessions, history, nursing observations, and a
bounded local memory summary. The local Gemma prompt receives only that
selected patient's summary. A new chat starts with an empty transcript while
retaining the selected patient's local clinical memory.
