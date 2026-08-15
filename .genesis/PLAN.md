# NurseAssist_AI — Plan

## Milestones

| ID | Goal | Verification | Status |
|---|---|---|---|
| M1 | Replace synthetic NLP templates with reproducible nursing data and integrate BioClinicalBERT. | Train, hold out test split, export parity test, and quality gate pass (TF-IDF + BERT). | Completed pipeline validation, tests, and TF-IDF parity metrics |
| M2 | Make on-device Gemma replies single-turn, concise, and safe. | Test several unrelated prompts in one session; no prompt/history echo or repetition. | Needs device verification |
| M3 | Require nurse review before every AI-proposed chart write. | Stage a vital and medication proposal; confirm and discard each on device. | Implemented; needs device verification |
| M4 | Fetch Gemma 3 1B IT directly from Hugging Face. | Clean install launches and initializes the model directly from Hugging Face CDN. | Implemented |
| M5 | Keep chats, nursing observations, and AI context strictly patient-scoped. | Switch between two patients; verify New chat, History, notes, and model context never cross patients. | Implemented; needs device verification |
| M6 | Improve UI aesthetics to a professional standard and upgrade all Flutter dependencies to recent versions. | Visual review of glassmorphism/typography and `flutter pub outdated` shows no major stragglers. | Completed |
| M7 | Build and install a release APK. | `flutter build apk --release` from `frontend`. | Pending |
| M8 | Create GitHub Actions workflow to build and store iOS IPA. | Verify `ios-ipa` artifact in GitHub Actions. | Implemented |

## Current decision

The Gemma 3 1B IT model (~550 MB) is downloaded on-demand directly from Hugging Face's global CDN on the first launch for vastly improved speed compared to GitHub Releases.
This keeps the core APK extremely lightweight (< 50MB) while providing the full offline AI capability once initialized.

The separate small nursing-observation model uses knowledge distillation: a BERT+TF-IDF teacher trains in CI, then a TF-IDF-only student is distilled for mobile export. This ensures perfect train/serve parity while retaining BERT's clinical intelligence. The student model uses a fixed-size MLP with a < 750K parameter budget. It is advisory context only; the nurse must confirm all chart proposals before they are stored.

Each patient has isolated chat sessions, history, nursing observations, and a bounded local memory summary. The local Gemma prompt receives only that selected patient's summary.

**Continuous Adaptation**: The ML pipeline is driven by implicit reinforcement learning. A weekly GitHub Actions workflow checks a telemetry drop folder for implicit usage signals (AI proposals that nurses actually confirmed). If new usage data exists, it ingests it into the training dataset and retrains the model.

## Recent Activity Log

- 2026-08-15: Comprehensive project summary documented in docs/PROJECT_SUMMARY.md, covering all three components (frontend Flutter app, ML pipeline, relay), data flow, and current development status.
- 2026-08-15: Overhauled the AI layer to allow the on-device Gemma 3 1B model to exhibit natural conversational intelligence instead of acting strictly as a rigid JSON extractor. Consolidated to a single-inference architecture combining structured JSON with friendly, contextual replies.
- 2026-08-15: Upgraded the Vitals Chart UI to dynamically support any database schema type. Scaled up the ML pipeline (train_observation_model.py) from 100K parameter cap to 500K parameter cap with deeper layers, retrained, and exported the new 172K parameter model.
- 2026-08-15: Major ML pipeline overhaul — implemented knowledge distillation to fix critical train/serve BERT skew. Added 8 new clinical labels (Headache, Weakness, Fever, Dehydration, Insomnia, Dizziness, Pain, Edema) with negation-aware weak supervision. Improved LLM prompt for narrative nursing input, enhanced fallback parser for conversational vitals/meds/summarization, and made AI responses friendly and contextual.
