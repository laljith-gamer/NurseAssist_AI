# NurseAssist_AI — Plan

## Milestones

| ID | Goal | Verification | Status |
|---|---|---|---|
| M1 | Keep deterministic nursing commands usable without an LLM. | Run Flutter tests and manually verify command parsing. | Implemented; re-verify after changes |
| M2 | Make on-device Gemma replies single-turn, concise, and safe. | Test several unrelated prompts in one session; no prompt/history echo or repetition. | Needs device verification |
| M3 | Publish one valid MediaPipe/LiteRT `.task` model matching the app contract. | GitHub Actions upload succeeds; clean install downloads and initializes it. | Blocked by invalid/missing model source |
| M4 | Build and install a release APK. | `flutter build apk --release` from `frontend`. | Pending after M3 |

## Current decision

The GitHub Release is the delivery destination for the app. It cannot also be
the workflow's first-download source. The source may be a public Hugging Face
bucket file or a gated Hugging Face model. Only the gated option requires an
`HF_TOKEN` GitHub secret with access.
