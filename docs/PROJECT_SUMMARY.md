# NurseAssist AI Project Summary

## Overview
NurseAssist AI is an offline-first Flutter nursing assistant app for Android, iOS, and web. It enables nurses to record patient vitals, medications, and nursing observations via voice or text chat with on-device AI assistance. No patient data is sent to any cloud backend - everything is stored in local SQLite.

The app features a professional Clinical Glass UI - dark mode default, glassmorphic cards, dynamic mesh gradients, pulse animations on vitals, and adaptive desktop/mobile layouts.

---

## Architecture Overview

The project is split into three loosely-coupled parts:
1. Frontend (Flutter mobile app)
2. ML Pipeline (Python training)
3. Relay (Cloudflare Worker for telemetry ingestion)


### 1. Frontend (frontend/) - Flutter Mobile App

Tech Stack: Flutter SDK 3.24+, Dart, flutter_gemma (MediaPipe/LiteRT), sqflite, provider, fl_chart, speech_to_text, connectivity_plus, google_fonts, flutter_animate

#### Core Services

| Service | File | Responsibility |
|---------|------|----------------|
| LlmService | lib/services/llm_service.dart | On-device LLM. Downloads Gemma 3 1B IT model (gemma3-1b-it-int4.task, ~1 GB) from Hugging Face CDN on first launch. MediaPipe/LiteRT .task format only. Low-temperature inference, single-turn reset, control-token stripping, graceful fallback when unavailable. |
| ClinicalCommandParser | lib/services/clinical_command_parser.dart | Safety gate. Parses LLM JSON output (requires v:1 version field), validates vital ranges (BP 40-260 systolic, HR 20-260, SpO2 40-100, etc.), rejects malformed responses. Regex fallback parser for offline mode. |
| LocalNlpService | lib/services/local_nlp_service.dart | Runs the lightweight observation model (compact MLP as observations.json ~1 MB) entirely in Dart. TF-IDF char n-grams to MLP forward pass to sigmoid to threshold to clinical reasoning rules (e.g., Hypertension + Tachycardia to Hemodynamic Instability). |
| ModelManager | lib/services/model_manager.dart | OTA updates for the nursing-observation model from GitHub Releases. SHA-256 verification, atomic extraction with zip-slip protection, auto-rollback on failure. |
| TelemetryService | lib/services/telemetry_service.dart | Optional, consent-gated. Collects de-identified label accept/dismiss feedback (PII redacted on-device: MRNs, room numbers, names). Syncs to Cloudflare Worker relay over WiFi, throttled to 4-hour intervals. |
| ApiService | lib/services/api_service.dart | Facade over LocalDbService. Returns plain maps so the presentation layer can migrate to REST later. |
| LocalDbService | lib/services/local_db_service.dart | SQLite layer (sqflite/sqflite_common_ffi). Handles patients, vitals, medications, nursing notes, chat sessions, telemetry queue. Schema version 5 with migrations. |

#### State Management
- PatientProvider - Central coordinator. Routes messages through: local NLP hint to LLM interpretation to ClinicalCommandParser to nurse confirmation required before writing.
- SettingsProvider - Theme, backend URL, telemetry consent, sync timestamps (via shared_preferences).
- SyncService - Connectivity monitoring (WiFi status).

#### Key Screens and Widgets

| Component | File | Description |
|-----------|------|-------------|
| DashboardScreen | lib/screens/dashboard_screen.dart | Main screen. Desktop: 3-column layout (chat + vitals chart + patient sidebar). Mobile: TabBar (Chat / Vitals / Score). Model management widget in settings modal. |
| ChatInterface | lib/widgets/chat_interface.dart | Nurse chat with speech-to-text, suggestion feedback dialogs, telemetry opt-in flow, proposal confirmation UI. |
| PatientSidebar | lib/widgets/patient_sidebar.dart | Patient selection, admit dialog, animated list items. |
| VitalHistoryCharts | lib/widgets/charts/vital_history_charts.dart | fl_chart line charts for each vital type with critical thresholds. |
| VitalSignsDeltaChart | lib/widgets/charts/vital_signs_delta_chart.dart | Current vitals with trend arrows and pulse animation. |
| ClinicalChangeBanner | lib/widgets/clinical_change_banner.dart | Animated alert banner for critical vitals. |
| PatientScoreTab | lib/widgets/patient_score_tab.dart | Clinical assessment scores with glassmorphic cards. |
| ChatHistoryDrawer | lib/widgets/chat_history_drawer.dart | Sliding drawer with chat history + AI memory context tabs. |

#### Safety and Privacy Design
- Human-in-the-loop: Every AI proposal (vitals, medications, notes) is shown as a proposal card; nurse must tap Confirm & Save before any data is written.
- Advisory-only observation model: Provides context hints to the LLM but can never chart by itself.
- Range validation: All vitals validated against physiological ranges before acceptance.
- Patient scoping: Switching patients clears all chat history, notes, observations, and LLM context - no cross-patient data leakage.
- PII redaction: Telemetry redacts room numbers, MRNs (6+ digits), and patient names before any network transmission.
- Local data store: nurseassist_offline.db SQLite stores all patient data, chat sessions, and telemetry queue locally.

### 2. ML Pipeline (ml_pipeline/) - Python Training

Tech Stack: Python 3.11, scikit-learn, numpy, Hugging Face datasets/transformers, pytest

#### Pipeline Stages

1. **Data Sources**
   - Microsoft SYNUR - Synthetic nurse dictations, pinned revision hash, validated
   - MTSamples - Real de-identified transcriptions, weakly supervised via 18 regex rules
   - Telemetry - Consent-based field feedback (transcript + accepted labels)

2. **Feature Engineering**
   - TF-IDF over char n-grams (3-6, 256 features, L2-normalized)
   - BioClinicalBERT (768-dim, PCA to 256-dim) - **disabled** due to PyTorch DLL issues
   - Combined: 512-dim input vector

3. **Model Training** (train_observation_model.py)
   - sklearn MLPClassifier (128->64 hidden, ReLU, multi-label sigmoid)
   - Parameter budget: <100K (~42K actual)
   - Label selection: min support + dev F1 >= 0.40
   - Threshold tuning: grid search 0.10-0.90

4. **Export** (export_mobile_models.py)
   - Serializes to observations.json (~400 KB)
   - ZIP with metadata.json (SHA-256, metrics, version)

5. **Verification** (verify_mobile_export.py)
   - Parity check: rel_tol=1e-5 vs sklearn model
   - Quality gate: micro-F1 >= 0.40, >= 3 labels
   - Regression check: vs baseline_metrics.json

---

### 3. Relay (relay/) - Telemetry Ingestion Edge Worker

- src/index.js - POST /intake with Bearer auth to GitHub Contents API
- test.js - 6 test cases (405, 404, 401 x2, 400, 202)
- wrangler.toml - Cloudflare Worker configuration

---

## Data Flow

1. Nurse speaks/types a message
2. LocalNlpService suggests advisory labels via observation MLP
3. LlmService generates JSON via Gemma 3 1B IT (if ready)
4. ClinicalCommandParser validates JSON + ranges
5. Fallback: regex parser if Gemma unavailable
6. Proposal card shown - nurse taps Confirm & Save
7. ApiService writes to local SQLite
8. If telemetry consent: de-identified verdicts queued
9. WiFi sync to Cloudflare relay to GitHub Actions re-train

---
## Testing

### Frontend Tests (frontend/test/)

| Test File | Coverage |
|-----------|----------|
| clinical_command_parser_test.dart | 9 tests: versioned JSON, unversioned rejection, observation proposals, vital parsing, Q&A disambiguation, medication parsing |
| services/model_manager_test.dart | Model schema validation, SGD rejection, dimension matching |
| services/telemetry_service_test.dart | PII redaction: rooms, MRNs, names |

### ML Pipeline Tests (ml_pipeline/tests/)

| Test File | Coverage |
|-----------|----------|
| test_train_observation_model.py | Label selection, parameter budget, threshold tuning |
| test_export_mobile_models.py | Export format, weight shapes, SHA-256 |
| test_bioclinicalbert.py | BERT extraction (skipped if torch unavailable) |
| test_entity_extractor.py | Regex vital/med/room extraction |
| test_intent_classifier.py | Nursing shorthand intent classification |
| test_preprocessor.py | Text cleaning and normalization |
| test_synur_dataset.py | SYNUR loading and row validation |

### Relay Tests (relay/test.js)

| Case | Expected |
|------|----------|
| GET /intake | 405 |
| POST /unknown | 404 |
| POST /intake (no auth) | 401 |
| POST /intake (wrong secret) | 401 |
| POST /intake (bad payload) | 400 |
| POST /intake (valid) | 202 |

---
## Current Development Status

Per .genesis/checkpoints/CURRENT.md:
- Active loop: ml-pipeline-optimization
- Iteration: 9
- Last gate: ML pipeline unit tests pass and TF-IDF parity evaluation
- Model artifact: compact_clinical_mlp (Sklearn MLP, ~42K params)
- Next milestone: M7 - Build and install release APK
- Next action: Wait for user to review UI corrections, then build APK

### Milestones

| ID | Goal | Status |
|----|------|--------|
| M1 | Replace synthetic NLP with reproducible nursing data + BioClinicalBERT | Completed |
| M2 | Single-turn, safe Gemma replies | Needs device verification |
| M3 | Nurse review before every chart write | Implemented; needs device verification |
| M4 | Fetch Gemma 3 1B IT from Hugging Face | Implemented |
| M5 | Strict patient-scoped data isolation | Implemented; needs device verification |
| M6 | Professional UI + dependency upgrades | Completed |
| M7 | Build and install release APK | Pending |
| M8 | GitHub Actions iOS IPA workflow | Implemented |

### Key Decisions
- Gemma 3 1B IT downloads from Hugging Face CDN (APK < 50 MB)
- BioClinicalBERT disabled (PyTorch DLL issues); falls back to TF-IDF + MLP
- Patient data strictly isolated per-patient
- Telemetry feedback loop for continuous adaptation
