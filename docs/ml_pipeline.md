# ML Pipeline Plan: Continuous On-Device Adaptation

## 1. Overview
The goal of this ML pipeline is to create a self-improving loop (Implicit Reinforcement Learning) without requiring explicit data curation or internet connectivity during operations. As nurses use the app, their interactions act as supervised labels. We use these labels to continuously fine-tune the on-device language model (Gemma) and the observation extraction model (TF-IDF/MLP).

## 2. Data Collection (Offline Telemetry)
We cannot stream data to the cloud. Instead, the `PatientProvider` silently logs interactions to the local `telemetry_queue` SQLite table.
- **Positive Labels (Gold Standard):** When a nurse dictates a prompt, the AI generates a clinical record, and the nurse taps "Confirm & Save" without modifying it.
- **Negative Labels (Hard Negatives):** When the AI generates a record, but the nurse taps "Discard" or heavily edits the JSON/record before saving.

## 3. Data Extraction & Syncing
When the device connects to the hospital's secure intranet (e.g., during a shift change or charging cycle), a background service (`SyncWorker`) runs:
1. Extracts the `telemetry_queue` pairs `[User Prompt -> Final Edited JSON]`.
2. Securely transmits them to the hospital's central on-premise server.
3. Clears the local device queue to save storage.

## 4. Retraining Pipeline (Weekly CI/CD)
A scheduled GitHub Actions workflow (or Jenkins job) runs weekly on the central server:
1. **Dataset Aggregation:** Pulls the week's telemetry data from all devices.
2. **Preprocessing:** Filters out any prompts containing identifiable patient names (using a localized NER filter), replacing them with `[PATIENT_NAME]`.
3. **Supervised Fine-Tuning (SFT):**
   - We use the Gold Standard pairs to fine-tune the lightweight Gemma 3 1B model using LoRA (Low-Rank Adaptation) on the central GPU server.
   - We use the Negative Labels for Direct Preference Optimization (DPO), teaching the model what *not* to do (e.g., punishing hallucinated fields or excessive chattiness from irritated nurses).
4. **Knowledge Distillation (Observation Model):**
   - The large BERT teacher model scores the new data.
   - The small on-device `compact_clinical_mlp` (TF-IDF student) is retrained on this new data to improve its symptom extraction accuracy (e.g., catching typos like "dizy" -> "Dizziness").

## 5. Model Deployment
1. The new model weights (Gemma LoRA adapters and the MLP `.pkl`/`.tflite` files) are exported.
2. The pipeline pushes these optimized weights to the hospital's local CDN.
3. The next time the nurse's app launches on the intranet, it seamlessly downloads the updated delta weights in the background.

## 6. Security & Privacy Guarantees
- No data ever leaves the hospital's firewall.
- All reinforcement learning happens completely anonymously.
- Patient names are stripped before entering the training corpus.
