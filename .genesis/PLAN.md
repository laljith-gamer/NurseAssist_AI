# NurseAssist_AI — Plan

## Milestones

| ID | Goal | Verification | Status |
|---|---|---|---|
| M1 | Replace synthetic NLP templates with reproducible nursing data and integrate BioClinicalBERT. | Train, hold out test split, export parity test, and quality gate pass (TF-IDF + BERT). | Completed pipeline validation, tests, and TF-IDF parity metrics |
| M2 | Make on-device Gemma replies single-turn, concise, and safe. | Test several unrelated prompts in one session; no prompt/history echo or repetition. | Needs device verification |
| M3 | Require nurse review before every AI-proposed chart write. | Stage a vital and medication proposal; confirm and discard each on device. | Implemented; needs device verification |
| M4 | Bundle Gemma 3 1B IT as a Flutter asset; remove HuggingFace download. | Clean install launches and initializes the model from the bundled asset. | Implemented |
| M5 | Keep chats, nursing observations, and AI context strictly patient-scoped. | Switch between two patients; verify New chat, History, notes, and model context never cross patients. | Implemented; needs device verification |
| M6 | Improve UI aesthetics to a professional standard and upgrade all Flutter dependencies to recent versions. | Visual review of glassmorphism/typography and `flutter pub outdated` shows no major stragglers. | Completed |
| M7 | Build and install a release APK. | `flutter build apk --release` from `frontend`. | Pending |

## Current decision

The Gemma 3 1B IT model (~1 GB) is downloaded on-demand from a GitHub Release on the first launch.
This keeps the core APK extremely lightweight (< 50MB) while providing the full offline 
AI capability once initialized.

The separate small nursing-observation update is trained from Microsoft's
public SYNUR dataset combined with synthetic clinical templates. It uses a 
fixed-size < 100K parameter Multi-Layer Perceptron (MLP). It is advisory context only; 
the nurse must confirm all chart proposals before they are stored. A clinical reasoning 
layer on the device infers higher severity states (e.g., Hemodynamic Instability) 
from the raw predictions.

**BioClinicalBERT** was considered as a training-time feature extractor but disabled 
due to environment compatibility (PyTorch DLL loading issues). The pipeline falls back 
gracefully to TF-IDF features (max 256) while retaining the MLP reasoning engine.
The exported app artifact remains a lightweight JSON file (< 1MB).

Each patient has isolated chat sessions, history, nursing observations, and a
bounded local memory summary. The local Gemma prompt receives only that
selected patient's summary. A new chat starts with an empty transcript while
retaining the selected patient's local clinical memory.

**Continuous Adaptation**: The ML pipeline is driven by implicit reinforcement
learning. A weekly GitHub Actions workflow checks a telemetry drop folder for
implicit usage signals (AI proposals that nurses actually confirmed). If new
usage data exists, it ingests it into the training dataset and retrains the
model. If no new data exists, it skips training to save resources. We are currently implementing the telemetry feedback loop to safely collect de-identified feedback from the device and pipe it to the training workflow.
