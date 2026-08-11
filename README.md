# NurseAssist AI

NurseAssist is an offline-first Flutter assistant designed specifically for nurses. It enables secure, local recording and review of patient vitals and medication documentation without ever sending patient data to a cloud backend.

The app features a professional **Clinical Glass** UI, providing a modern, frictionless experience while maintaining strict local data privacy.

---

## Intelligent Architecture

NurseAssist AI combines a sophisticated local frontend with an evolving, offline-first ML pipeline.

### 1. The Core AI Interpreter (Gemma 2)
The app uses an optional on-device **Gemma 2 2B IT Q8** model (2.71 GB). This model interprets natural nursing language (e.g., *"Record BP 120/80"*) into a compact, structured proposal. No clinical decisions or diagnoses are made; it strictly structures dictation for charting.

### 2. The Nursing Observation Sidecar
A smaller, data-backed nursing-observation model runs alongside the interpreter to provide contextual validation. It is trained from [Microsoft SYNUR](https://huggingface.co/datasets/microsoft/SYNUR), a public CDLA-Permissive-2.0 dataset of synthetic expert-nurse dictations.
- **BioClinicalBERT Integration**: During training, we extract semantic embeddings using `emilyalsentzer/Bio_ClinicalBERT` (pre-trained on MIMIC-III clinical notes). These are combined with TF-IDF features to create a highly accurate classifier. 
- **Lightweight Export**: BioClinicalBERT is *only* used during training. The final model exported to the mobile device remains a lightweight JSON file, avoiding heavy on-device neural network execution.

### 3. Continuous Implicit Adaptation (Reinforcement Learning)
NurseAssist is designed to adapt to the nurses who use it.
- As nurses interact with the app (confirming or discarding AI proposals), the app generates anonymized, privacy-scrubbed telemetry logs.
- **Weekly Self-Training**: A GitHub Actions workflow runs every Sunday. If new telemetry logs are found in the `telemetry_drop/` directory, the pipeline automatically ingests the implicit feedback, retrains the sidecar model, measures held-out performance, and issues a new model release. If no telemetry is found, it skips training.

---

## How the App Works (The AI Path)

1. **Dictation**: The nurse speaks or types into the interface.
2. **Interpretation**: The on-device Gemma model structures the input.
3. **Validation**: The app checks the proposed fields against safe numeric ranges locally.
4. **Review**: The nurse reviews a visible proposal card and taps **Confirm & Save**.
5. **Telemetry**: The nurse's acceptance/rejection is logged locally and later synced as anonymized telemetry to continuously train the AI.

> [!IMPORTANT]
> No model can select a patient, prescribe, diagnose, or write a record without the nurse's confirmation. When Gemma is unavailable, the app falls back gracefully to a limited offline regex-based parser, maintaining the same rigorous confirmation step.

---

## Setup and Development

### Running the Frontend

The frontend features a "Clinical Glass" aesthetic with dynamic mesh gradients, glassmorphic headers, and subtle micro-animations (like pulsing clinical alerts). 

```powershell
cd frontend
flutter pub get
flutter run
```
*Note: The app may check GitHub Releases for updated sidecar models, but the core local record store (SQLite) works entirely without an internet connection.*

### Running the ML Pipeline Locally

The GitHub Actions workflow normally handles this, but you can train the sidecar model manually:

```powershell
cd ml_pipeline
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu  # optional, required for BioClinicalBERT
python scripts/train_observation_model.py
python scripts/export_mobile_models.py
python scripts/verify_mobile_export.py
```
The trainer downloads the pinned SYNUR revision, appends any local telemetry, extracts BioClinicalBERT features, fits the model, and packages a verified `nurseassist-observation-model-*.zip`.

---

## Safety and Privacy

- **100% Local**: Patient records, chat history, and telemetry are stored in local SQLite databases.
- **Advisory Only**: Never use the app as a source of diagnosis, treatment, medication orders, or emergency guidance.
- **Human-in-the-Loop**: Always verify all AI-proposed values against the patient and source documentation before charting.
