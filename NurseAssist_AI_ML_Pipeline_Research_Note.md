# NurseAssist AI — Clinical Observation Model Pipeline

**Research note — architecture, mechanics, terminology, and findings**
Scope: `ml_pipeline/` (Python training + CI/CD) and `lib/` (Flutter mobile app), as reflected in `train-models.yml` and `validate-pr.yml`.

---

## 1. What this system is

NurseAssist AI is an **offline-first clinical assistant app for nurses**, built in Flutter. Its core interaction is a chat interface backed by a quantized on-device LLM (`Gemma3-1B-IT`, ~1 GB, downloaded from GitHub Releases in the background using native download managers). Talking to a 1B-parameter LLM for every keystroke is slow, so the app front-loads a **fast, deterministic/statistical layer** in front of it:

1. A regex-based **intent classifier** and **entity extractor** (`nlp/intent_classifier.py`, `nlp/entity_extractor.py`) — catches obvious commands ("record BP 120/80") in well under 100 ms, no ML involved.
2. A small **clinical observation model** — the subject of this note — which reads a nurse's free-text note and *suggests* structured observation labels ("Hypertension", "Chest pain", "Alert and oriented" …) as context for the LLM. It never writes to a chart by itself; the code repeatedly enforces "advisory only."

This note covers how that observation model is trained, exported, gated through CI/CD, shipped as a GitHub Release, and consumed by the phone.

---

## 2. Pipeline at a glance

*(See the two flow diagrams above — training pipeline, then release-to-device pipeline.)*

The system has two loosely-coupled halves that only meet at a GitHub Release:

- **Half A — Python/scikit-learn, runs in GitHub Actions.** Downloads data, engineers features, trains a small neural net, exports it to a portable JSON format, self-verifies it, and publishes it.
- **Half B — Dart/Flutter, runs on the phone.** Polls GitHub Releases, downloads the JSON package, re-validates it, installs it atomically, and re-implements the model's forward pass natively so it can score text with no server round-trip.

Because these are two independent reimplementations of the same math, in two different languages, most of the interesting engineering — and the most interesting risk — lives at the seam between them.

---

## 3. Stage-by-stage walkthrough

### 3.1 Data sources

| Source | What it is | How it's used |
|---|---|---|
| **SYNUR** (`microsoft/SYNUR` on Hugging Face) | Synthetic nurse dictations paired with expert-labeled observations. `synur_dataset.py` pins an exact dataset **revision hash** (not `main`) and validates row shape + a minimum download size before trusting it — a later upstream dataset change can't silently alter a released model. | Base train/dev/test splits. |
| **MTSamples** (`clinical_dataset.py`) | Real, de-identified medical transcriptions. No human labels exist for the target taxonomy, so the code applies **weak supervision**: ~18 hand-written regex rules (e.g. "spO2 ... <90" → `Hypoxia`) auto-label each note. Records that match zero rules are discarded. | Appended to train/dev/test (80/10/10 split) to add real clinical language on top of synthetic SYNUR text. |
| **Field telemetry** (`telemetry_drop/*.json`, `ingest_telemetry.py`) | JSON logs of `{transcript, accepted_labels}` — i.e. cases where a nurse *kept* a suggested label, used as implicit positive feedback. | **Currently a dead end — see Finding 4.2.** |

### 3.2 Feature engineering

Two feature families are computed and concatenated:

- **TF‑IDF over character n-grams** (`analyzer="char_wb"`, n-grams of length 3–6, capped at 256 dimensions, L2-normalized). Character n-grams (rather than word tokens) are deliberately chosen because they degrade gracefully on typos, abbreviations, and the shorthand nurses actually type ("SOB", "A&O x3"), and — importantly — because a TF-IDF vocabulary + IDF table is trivial to re-implement in 40 lines of Dart with no external NLP library.
- **BioClinicalBERT embeddings**, PCA-reduced to 256 dimensions (`nlp/bioclinicalbert_embedder.py`). BioClinicalBERT is a BERT model further pre-trained on MIMIC-III clinical notes, so it already "understands" clinical phrasing, negation, and abbreviations far better than a generic language model or bag-of-n-grams. Embeddings are cached to disk keyed by a content hash so repeated training runs skip the forward pass. **This 768→256-dim PCA step runs only at training time; the embedder is never shipped to the phone** (a transformer model is far too large/slow for on-device use here).

The two 256-dim blocks are horizontally stacked into a 512-dim input vector.

### 3.3 Model training (`train_observation_model.py`)

- **Architecture:** an `sklearn.neural_network.MLPClassifier`, hidden layers (128, 64), ReLU activations, multi-label sigmoid output — described in the code as a "Compact Clinical MLP." A hard budget of **100,000 parameters** is enforced by summing `coefs_` + `intercepts_` after every fit and raising if it's exceeded — this is what keeps the exported JSON small enough to download and run instantly on a phone.
- **Label selection is a two-stage filter, not a fixed list:** candidate labels must appear ≥8 times in training data; of those, a label only survives into the shipped model if, on the dev set at the globally-best decision threshold, it has ≥4 positive dev examples **and** a per-label F1 ≥ 0.40. This is a quality bar on the *taxonomy itself* — a rare or noisy label (e.g. "Respiratory interventions", support 24) doesn't make the cut just because it's clinically interesting; it has to be learnable from the data actually available. In the current model that leaves 9 labels (from a larger candidate pool).
- **Threshold search:** rather than a fixed 0.5 cutoff, a grid of thresholds (0.10–0.90) is scored by micro‑F1 on dev and the best one becomes part of the shipped artifact (current model: 0.25).
- **Two-phase fit:** first fit on train → select labels/threshold using dev; then **retrain from scratch on train+dev combined**, and report final numbers on the held-out test split. This is standard practice to avoid "spending" dev data only on early-stopping/hyperparameters while still squeezing the model's final training pass out of every labeled example that isn't test data.
- **Current measured performance** (from the checked-in metrics): held-out micro‑F1 **0.625**, macro‑F1 **0.590**, across 9 selected labels, trained on 122/101/199 SYNUR train/dev/test rows plus 1,950 MTSamples-derived rows.

### 3.4 Export to mobile format (`export_mobile_models.py`)

The pickled scikit-learn artifact (vectorizer, MLP, PCA, labels, threshold) is flattened into a single portable JSON (`observations.json`, `"type": "compact_clinical_mlp"`, `format_version: 2`): the TF‑IDF vocabulary + IDF table, and the MLP's three weight/bias matrices (transposed for row-major dot products). A `metadata.json` records the model version, training dataset stats, and metrics, and both files are SHA‑256 hashed and zipped into `nurseassist-observation-model-<version>.zip`.

### 3.5 Verification gate (`verify_mobile_export.py`)

This script is a **Python re-implementation of the Dart inference path**, run in CI before anything ships:

- **Export parity** — hand-computes char‑wb TF‑IDF + a manual MLP forward pass (`relu → relu → sigmoid`) for three probe sentences and asserts the exported JSON reproduces the pickled model's `predict_proba` output to 1e‑5. Because the mobile runtime uses TF‑IDF only, this check **zero-pads out the BERT portion of the input vector** to simulate what the phone will actually see (more on this below).
- **Quality gate** — fails the build if fewer than 3 labels were selected, or if validation/held-out micro‑F1 falls below 0.40.
- **Regression-vs-baseline** — compares this run's held-out micro‑F1 against a committed `baseline_metrics.json`; fails if it drops by more than 0.02, or if the label count shrinks. On the very first run (no baseline yet) this check is skipped with a printed warning.

### 3.6 CI/CD workflows

| | `validate-pr.yml` | `train-models.yml` |
|---|---|---|
| Trigger | Pull request touching pipeline paths | Push to `main`, **or** weekly cron (Sun 00:00) |
| Gate | None beyond normal PR review | GitHub Environment `production-release` — configured (per the workflow's own comment) to require a human approval before the job runs |
| Dependencies installed | `requirements.txt` only | `requirements.txt` **+ explicit `torch` (CPU wheel) + `scipy`** |
| Practical effect | BioClinicalBERT unavailable → trains/validates **TF‑IDF-only** | BioClinicalBERT available → trains **TF‑IDF + BERT** |
| On success | Uploads artifacts + posts a metrics summary to the PR | Publishes a GitHub Release with the zip, and **commits the new `baseline_metrics.json` back to `main`** so the next run has something to regress against |
| Scheduled run only fires if | — | a `check-telemetry` job finds new files in `telemetry_drop/` |

The weekly cron plus the telemetry gate is the "continuous learning" story: the intent is that as nurses use the app, accepted-label telemetry accumulates, and the Sunday job retrains against it automatically — but only when there's genuinely new signal, so a quiet week doesn't burn a CI run for nothing.

### 3.7 Mobile release consumption (`model_manager.dart`)

`ModelManager` polls `GET /repos/.../releases`, finds the newest release carrying a `nurseassist-observation-model-*.zip` asset, and if its version differs from what's installed:

1. Downloads the zip, extracts it into a **staging** directory (rejecting anything outside the expected `{observations.json, metadata.json}` file set, and rejecting zip paths containing `..` or leading `/` — basic zip-slip protection).
2. Checks `metadata.json`'s `schema_version == 2` and that its declared version matches the release tag.
3. Verifies each artifact's SHA‑256 against the hash recorded in `metadata.json`.
4. Runs a **local structural validation** of `observations.json` before trusting it (`_validateExportedModel`).
5. Only then does it atomically swap directories: `current → previous`, `staging → current`. If any step after the swap fails, it rolls `previous` back to `current` — a partially-installed model can never end up live.

### 3.8 On-device inference (`local_nlp_service.dart`)

Independently re-implements char‑wb n-gram tokenization, TF‑IDF weighting, and the same three-layer MLP forward pass in pure Dart — this is the code path that `verify_mobile_export.py` (§3.5) is checking against ahead of time. On top of the raw label scores, it applies three **hard-coded clinical composition rules** (e.g. `Hypertension` + `Tachycardia` present together ⇒ surface `Hemodynamic Instability`) before handing the result to the LLM as context.

---

## 4. Findings

Ordinary code review surfaces a few things worth flagging — these aren't stylistic nitpicks, they're places where the system's actual behavior diverges from what the code around it implies.

### 4.1 — Mobile install step validates the wrong schema *(Resolved)*

`export_mobile_models.py` emits `observations.json` with `"type": "compact_clinical_mlp"` and the payload nested under an `"mlp"` key (`layer1_weight`, `layer2_weight`, `output_weight`, …). `local_nlp_service.dart` — the code that actually *scores text* on-device — correctly expects exactly that shape.

Previously, `model_manager.dart`'s `_validateExportedModel` checked for an older schema (`multi_label_sgd_classifier`), which caused all modern model installations to fail.

**Resolution:** This has now been fixed! `_validateExportedModel` now accurately verifies the `compact_clinical_mlp` schema and dimension checks, allowing new model updates to ship and install successfully.

### 4.2 — Field telemetry is ingested but never trained on

`ingest_telemetry.py` reads `telemetry_drop/*.json`, converts entries into `SynurExample` objects, and pickles them to `data/.cache/telemetry/telemetry_examples.pkl`. `train-models.yml` runs this script as an explicit step before training. But `train_observation_model.py` never reads that pickle — its data loading is `load_all_splits()` (SYNUR) plus `load_mtsamples_dataset()` (MTSamples) only. The weekly cron's whole premise (§3.6) is "retrain when new telemetry arrives," yet the retrain that follows doesn't actually use it. Right now the telemetry gate decides *whether* to run a training job that would produce the same result as any other week.

### 4.3 — PR validation exercises a different feature set than production training

Because `requirements.txt` doesn't list `torch`, and only `train-models.yml` installs it explicitly (§3.6), `validate-pr.yml` always trains and quality-gates a **TF‑IDF-only** model — `BioClinicalBertEmbedder._ensure_loaded()` raises, the broad `except Exception` in `train_observation_model.py` catches it, and training silently falls back. The model that a reviewer sees pass or fail the quality gate on a PR is not the same feature configuration that will actually be trained and released on merge. This isn't necessarily unsafe — the CI code paths are the same, and a TF-IDF-only run is a legitimate (if weaker) sanity check — but it does mean the PR gate can't actually catch a regression that only shows up once BERT features are back in the mix.

### 4.4 — Deliberate train/serve feature skew

The MLP is trained on a 512-dim vector (256 TF‑IDF + 256 BERT‑PCA), but the phone can only supply the first 256 (TF‑IDF) dimensions — it has no BERT embedder. Both `verify_mobile_export.py` and the real Dart runtime handle this the same way: **zero-pad the missing 256 dimensions.** This is a conscious, consistently-implemented tradeoff (not a bug — the parity check exists precisely to keep the two paths honest with each other), but it does mean the polished held-out F1 numbers in `metadata.json` describe a model that briefly saw BERT features during training and dev-set label selection, while the version actually running in a nurse's hand only ever sees the TF‑IDF half of what it learned on. There's no on-device number that measures the *TF‑IDF-only* model's accuracy directly.

### 4.5 — Duplicated clinical logic, two languages, one source of truth missing

The same three composition rules (`Hypertension`+`Tachycardia` → `Hemodynamic Instability`, etc.) exist in both `ml_pipeline/nlp/clinical_reasoning.py` and `lib/lib/services/local_nlp_service.dart`. Only the Dart copy actually runs at inference time; the Python module doesn't appear to be imported by the training or export scripts. Nothing enforces that a future edit to one is mirrored in the other.

### 4.6 — Core training/export logic has no unit tests

`tests/` covers the deterministic NLU layer (`intent_classifier`, `entity_extractor`, `preprocessor`) and `synur_dataset`'s row validation thoroughly (7 tests). There is no test file for `train_observation_model.py`, `export_mobile_models.py`, `verify_mobile_export.py`, or `clinical_dataset.py` — their correctness is currently established only by running the full pipeline end-to-end in CI, which is slow feedback for a logic bug (e.g. in label selection or the export's weight transpose) compared to a focused unit test.

---

## 5. Why the design choices make sense (the parts working as intended)

- **Pinned dataset revision + license constant + SHA‑256 manifest** (`synur_dataset.py`): a clinical-adjacent model's training data provenance is auditable and reproducible — nobody can point to "SYNUR" six months from now and mean six different things.
- **Hard 100K-parameter budget + CPU-only PyTorch for BERT**: keeps the *shippable* artifact tiny (the exported package is a few hundred KB) while still letting the *training-time* feature extractor use a much larger model — the expensive part never has to leave the CI runner.
- **`environment: production-release` human-approval gate**: for a tool that surfaces clinical suggestions, "a script pushed a new model to every phone unattended" is a real risk; the workflow comment is explicit that this is enforced by a repo setting, not by YAML alone.
- **Python-side re-implementation of the Dart inference path as a pre-release check**: catches export/format drift *before* a release is cut, in the one language (Python) where the "ground truth" model already lives — this is exactly the kind of check that should have also existed for `model_manager.dart`'s installer (see 4.1).
- **Atomic install with automatic rollback**: a network blip or a corrupted download degrades to "keep using the last known-good model," never to "app has no model" or "app has a half-written model."
- **MTSamples via weak supervision**: SYNUR alone is small (122/101/199 rows); grafting on regex-labeled real clinical transcriptions is a pragmatic way to add real-world language diversity without hand-labeling thousands of notes.

---

## 6. Glossary

| Term | Plain-language meaning |
|---|---|
| **SYNUR** | Microsoft's public dataset of synthetic nurse dictations + expert-structured observations; used here as the "gold standard" labeled dataset. |
| **MTSamples** | A public dataset of real, de-identified medical transcription samples; has no labels for this project's taxonomy, so labels are inferred by regex ("weak supervision"). |
| **Weak supervision** | Generating training labels with cheap heuristics (regexes, keyword rules) instead of human annotation — noisier, but free and fast to produce at scale. |
| **TF‑IDF** | *Term Frequency–Inverse Document Frequency*: weights how "distinctive" a token is to a document versus how common it is overall. Here the "tokens" are 3–6 character n-grams, not words, so it's robust to typos and clinical shorthand. |
| **char_wb analyzer** | scikit-learn's n-gram mode that generates n-grams only *within word boundaries* (with padding spaces), rather than sliding across an entire sentence. |
| **BioClinicalBERT** | A BERT-family language model further pre-trained on MIMIC‑III ICU clinical notes, so it has learned clinical abbreviations, negation patterns, and terminology that a general-purpose model wouldn't. |
| **PCA (Principal Component Analysis)** | Compresses BioClinicalBERT's native 768-dimension embedding down to 256 dimensions while preserving as much information as possible — needed to keep the combined feature vector small enough for a tiny classifier. |
| **MLP (Multi-Layer Perceptron)** | The simplest kind of neural network: stacked fully-connected layers with a nonlinearity (here ReLU) between them. Small, fast, and easy to hand-port to another language (Dart) — unlike a transformer. |
| **Multi-label classification** | Each input can have zero, one, or several correct labels simultaneously (a note can be both "Chest pain" and "Anxious"), as opposed to picking exactly one class. |
| **Micro‑F1 / Macro‑F1 / Samples‑F1** | Three ways to average precision/recall across multiple labels: *micro* pools all label decisions together (dominated by common labels), *macro* averages each label's F1 equally (rare labels count as much as common ones), *samples* averages per-example. Using more than one avoids being fooled by a model that's only good at the most frequent label. |
| **Decision threshold** | The probability cutoff above which a label is considered "predicted." Searched over a grid here rather than fixed at 0.5, because multi-label sigmoid outputs aren't well-calibrated to any particular cutoff by default. |
| **Quality gate** | An automated pass/fail check in CI/CD that blocks a release if a metric falls below a minimum bar. |
| **Regression check** | Compares a new model's metrics against a previously-shipped "baseline" to catch the model getting *worse* over time, not just bad in absolute terms. |
| **Parity check** | Confirms that a re-implementation (here, the exported JSON format, and separately the Dart runtime) produces bit-for-bit-equivalent output to the original (the pickled scikit-learn model), so nothing was lost in translation. |
| **SHA‑256 checksum** | A cryptographic fingerprint of a file's bytes; comparing checksums confirms a downloaded file is exactly what the publisher intended, not corrupted or tampered with in transit. |
| **GitHub Environment / required reviewers** | A GitHub repository setting that pauses a workflow job until a designated person manually approves it — the human-in-the-loop gate before this pipeline can auto-publish to production. |
| **OTA (over-the-air) update** | Delivering an update to an already-installed app without going through an app-store binary release — here, just a small JSON model file fetched from a GitHub Release. |
| **Zip-slip** | A path-traversal vulnerability class where a malicious zip entry name (e.g. `../../etc/passwd`) writes outside the intended extraction folder; `ModelManager` guards against it explicitly. |
| **Advisory-only model** | A model whose output is only ever shown as a *suggestion* alongside human judgment — it cannot write to a record, trigger an action, or bypass a person's review. Repeated throughout this codebase as an explicit design constraint, not an incidental property. |

---

## 7. Suggested next steps

1. ~~**Fix `_validateExportedModel` in `model_manager.dart`** to check for `compact_clinical_mlp` / the `mlp` sub-object instead of the retired SGD schema — this is currently the single blocker on shipping any model update at all.~~ *(Completed)*
2. **Wire `telemetry_examples.pkl` into `train_observation_model.py`** (or remove the `ingest_telemetry.py` step and the `check-telemetry` gate from `train-models.yml` if continuous learning from field data isn't ready yet) so the weekly workflow's behavior matches its stated purpose.
3. **Install `torch`/`scipy` in `validate-pr.yml` too** (even if only for a lighter-weight check), so a PR is validated against the same feature configuration that will actually train on merge.
4. Add unit tests around `train_observation_model.py`'s label-selection logic and `export_mobile_models.py`'s weight-transpose/export shape, so a regression there surfaces in seconds, not after a full pipeline run.
5. Consider a small on-device-only evaluation metric (TF‑IDF features alone, no BERT) reported in `metadata.json`, so the number a release is judged by reflects what actually ships.
