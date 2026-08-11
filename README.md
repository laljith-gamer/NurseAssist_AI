# NurseAssist AI

NurseAssist is an offline-first Flutter assistant for nurses. It records and
reviews local patient vitals and medication documentation without sending
patient data to a cloud backend.

## How the AI path works

1. The optional on-device Gemma 2 model interprets normal nurse language into
   a compact structured proposal.
2. A small data-backed nursing-observation model provides optional context;
   it is advisory only and cannot create a value or record.
3. The app validates the proposed fields and safe numeric ranges locally.
4. The nurse reviews a visible proposal card and taps **Confirm & Save**.

No model can select a patient, prescribe, diagnose, or write a record without
the nurse's confirmation. When Gemma is unavailable, the app retains a limited
offline command fallback, but it also uses the same confirmation step.

## Models

- **Gemma 2 2B IT Q8**: optional 2.71 GB on-device `.task` model, downloaded
  directly from the public Hugging Face bucket. It is not delivered through
  GitHub Releases because GitHub assets are limited to 2 GiB.
- **Nursing observation model**: a TF-IDF/SGD sidecar model trained from
  [Microsoft SYNUR](https://huggingface.co/datasets/microsoft/SYNUR), a public
  CDLA-Permissive-2.0 dataset of synthetic expert-nurse dictations and
  structured observations. When available, training-time features are
  enhanced with **BioClinicalBERT** embeddings (see below).
- **BioClinicalBERT** (`emilyalsentzer/Bio_ClinicalBERT`): a BERT model
  pre-trained on clinical notes from MIMIC-III. It is used **only during
  training** to generate richer clinical-language features that are combined
  with TF-IDF before fitting the SGD classifier. BioClinicalBERT is *not*
  shipped to mobile devices — the exported model remains a lightweight JSON
  file. When `torch` and `transformers` are not installed, the pipeline
  falls back gracefully to TF-IDF-only training.

SYNUR is valuable for reproducible nursing-language evaluation, but it is
synthetic research data—not EHR data. The release pipeline measures held-out
performance and blocks a model release beneath its quality gate. Those metrics
are evidence for this limited advisory task, not a claim of clinical accuracy
or approval for autonomous documentation.

## Training and release

The GitHub Actions workflow trains only the small nursing-observation sidecar;
it does **not** download, fine-tune, or upload the large Gemma task model.

```powershell
cd ml_pipeline
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu  # optional, for BioClinicalBERT
python scripts/train_observation_model.py
python scripts/export_mobile_models.py
python scripts/verify_mobile_export.py
```

The trainer downloads the exact pinned SYNUR revision, uses its MEDIQA train
and development splits for fitting/selection, holds the test split out, writes
metrics, exports `observations.json`, and packages a verified
`nurseassist-observation-model-*.zip`. When BioClinicalBERT is available, the
training report includes a side-by-side comparison of TF-IDF-only vs.
TF-IDF+BERT held-out metrics. Flutter verifies the manifest hashes and
installs the package atomically with rollback.

## Run the app

```powershell
cd frontend
flutter pub get
flutter run
```

The core local record store works without an internet connection. The app may
check GitHub Releases for a newer small nursing-language package; the Gemma
download is explicitly initiated by the user.

## Safety and privacy

- Patient records, chat history, and feedback are stored in local SQLite.
- Never use the app as a source of diagnosis, treatment, medication orders, or
  emergency guidance.
- Verify all AI-proposed values against the patient and source documentation
  before saving.
