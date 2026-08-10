# NurseAssist AI

NurseAssist is an **offline-first Flutter application** for recording and reviewing patient vitals, medication documentation, and clinical notes. Core clinical commands are parsed deterministically and stored on the device; the on-device ML models and optional LLM enhance, but never gate, that path.

## Architecture

NurseAssist is completely **Offline-First**. 
1. **No Cloud Backend**: The application does not require a backend API, FastAPI, or Render instance to function. All interactions are handled locally on the device.
2. **Local command path**: Commands such as `BP 120/80`, `Temp 38.1 C`, and `Administered Zofran 4 mg PO` are parsed locally, persisted in SQLite, and answered from those records.
3. **Local ML inference**: Intent classification and entity extraction run directly in Dart from verified exported JSON models (`intent.json`, `ner.json`) after they are downloaded.
4. **No clinical cloud dependency**: Patient data, historical metrics, chat history, and NLP feedback are stored exclusively in the local SQLite database.

## Model Training & CI/CD

Model training and updates are completely automated via **GitHub Actions**.

- **Commit-Triggered Training**: Pushing changes to `ml_pipeline/` triggers `.github/workflows/train-models.yml`.
- **Model Validation**: The pipeline trains `intent_model.pkl` and `ner_model.pkl`, exports their weights, and verifies that the JSON predictions match the Scikit-Learn classifiers before release.
- **Deterministic Export**: To achieve native iOS/Android support without heavy C++ bridging, the pipeline exports the canonical classifiers into efficient JSON representations (`intent.json` and `ner.json`).
- **Immutable Releases**: A versioned zip file (`nurseassist-model-vX.zip`) containing the models and a SHA-256 metadata file is packaged and published to **GitHub Releases**.

## Model Updates (Mobile App)

The mobile application acts as a client that occasionally checks for model updates from GitHub Releases:
1. **Lightweight Check**: When the app starts, it checks GitHub Releases for the newest `nurseassist-model-*.zip` asynchronously without blocking clinical commands.
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

*Note: The app is usable immediately without a model download. When online, it automatically installs the latest verified NLP package from GitHub Releases. The larger conversational LLM is optional.*

### Local ML Development

If you wish to modify the ML training data or architecture:

1. Install Python dependencies:
```bash
cd ml_pipeline
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
python scripts/export_mobile_models.py
python scripts/verify_mobile_export.py
```

## Security & Privacy
Because NurseAssist AI executes entirely on-device, sensitive Patient Health Information (PHI) never leaves the smartphone or tablet. The only network request made is an anonymous GET request to GitHub to download newer ML models.
