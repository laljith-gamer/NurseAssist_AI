# NurseAssist_AI — Plan

## Milestones

| ID | Goal | Verification | Status |
|---|---|---|---|
| M1 | Keep deterministic nursing commands usable without an LLM. | Run Flutter tests and manually verify command parsing. | Implemented; re-verify after changes |
| M2 | Make on-device Gemma replies single-turn, concise, and safe. | Test several unrelated prompts in one session; no prompt/history echo or repetition. | Needs device verification |
| M3 | Serve one valid MediaPipe/LiteRT `.task` model from the public Hugging Face bucket. | Clean install downloads and initializes it. | Ready for device verification |
| M4 | Build and install a release APK. | `flutter build apk --release` from `frontend`. | Pending after M3 |

## Current decision

The 2.71 GB model is delivered directly from the public Hugging Face bucket.
GitHub Release assets are limited to under 2 GiB, so the model-upload workflow
has been removed. The app model filename and bucket URL must stay aligned.
