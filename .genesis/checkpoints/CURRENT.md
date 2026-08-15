# CURRENT
- active_loop: ml-pipeline-overhaul
- target: Knowledge-distilled TF-IDF student model with accurate clinical observations
- iteration: 10
- last_gate: User-reported false positive observation tags from screenshots
- last_action: "Major ML pipeline overhaul: (1) Knowledge distillation to fix train/serve BERT skew, (2) Added 8 new clinical labels with negation detection, (3) Improved LLM prompt for narrative nursing text, (4) Enhanced fallback parser for conversational vitals/meds, (5) Friendly AI responses when LLM fails."
- next_action: "Verify training completes, run export + parity check, update baseline, push to GitHub."
- model: `compact_clinical_mlp` (Sklearn MLP, TF-IDF student distilled from BERT teacher)
- sidecar_data: Microsoft SYNUR + MTSamples with negation-aware weak supervision
- tokens_used: not tracked
- skills_loaded: []

- notes: Root cause of wrong observation tags was train/serve feature skew (BERT+TF-IDF training vs TF-IDF-only inference). Knowledge distillation preserves BERT intelligence while ensuring perfect parity. New labels cover Headache, Weakness, Fever, Dehydration, Insomnia, Dizziness, Pain, Edema. Frontend now handles narrative nursing input and summarization requests.
