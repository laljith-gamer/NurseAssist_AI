# NurseAssist AI

NurseAssist is an **Offline-First Flutter Application** designed for healthcare professionals to record vitals, medications, and clinical notes quickly and securely using on-device ML Inference.

## Architecture

NurseAssist is completely **Offline-First**. 
1. **No Cloud Backend**: The application does not require a backend API, FastAPI, or Render instance to function. All interactions are handled locally on the device.
2. **Local ML Inference**: Natural Language Processing (Intent Classification & Entity Extraction) is executed directly in Dart on the device using exported deterministic weights (`intent_weights.json`) and patterns (`ner_patterns.json`).
3. **No Online Dependencies**: Patient data, historical metrics, and NLP feedback are stored exclusively in the local SQLite database.

## Model Training & CI/CD

Model training and updates are completely automated via **GitHub Actions**.

- **Commit-Triggered Training**: Pushing changes to ML-related files (`backend/scripts/`, `backend/nlp/`) triggers the `.github/workflows/train-models.yml` workflow.
- **Model Validation**: The pipeline trains the `intent_model.pkl` and `ner_model` using Scikit-Learn and spaCy, verifying their outputs.
- **Deterministic Export**: To achieve native iOS/Android support without heavy C++ bridging, the pipeline exports the canonical python models into efficient JSON-based representations (`intent_weights.json` and `ner_patterns.json`).
- **Immutable Releases**: A versioned zip file (`nurseassist-model-vX.zip`) containing the models and a SHA-256 metadata file is packaged and published to **GitHub Releases**.

## Model Updates (Mobile App)

The mobile application acts as a client that occasionally checks for model updates from GitHub Releases:
1. **Lightweight Check**: When the app starts, it fetches the latest release metadata from GitHub asynchronously without blocking the user.
2. **Atomic Installation**: If a newer model is found, the app downloads it, verifies the SHA-256 checksums, and installs it atomically into device storage.
3. **Safe Rollback**: If the new model fails to load or is corrupted, the application will transparently roll back to the previously installed model version, ensuring uninterrupted offline access.

## Getting Started

### Flutter App

1. Install Flutter dependencies:
```bash
cd frontend
flutter pub get
```

2. Run the application (supports iOS, Android, macOS, Windows):
```bash
flutter run
```

*Note: The app will start in Offline Mode and automatically download the latest AI model from GitHub Releases on first launch.*

### Local ML Development

If you wish to modify the ML training data or architecture:

1. Install Python dependencies:
```bash
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

2. Train Models (will generate `.pkl` and `ner_model/`):
```bash
python scripts/train_intent_model.py
python scripts/train_ner_model.py
```

3. Export Models for Flutter (simulating the GitHub Action):
```bash
python scripts/export_models.py vLocal
```

## Security & Privacy
Because NurseAssist AI executes entirely on-device, sensitive Patient Health Information (PHI) never leaves the smartphone or tablet. The only network request made is an anonymous GET request to GitHub to download newer ML models.
