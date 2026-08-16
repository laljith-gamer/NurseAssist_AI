# CURRENT
- active_loop: frontend-ai-enhancements
- target: Fix rigid regex constraints, improve on-device Gemma comprehension, add offline terminology
- iteration: 11
- last_gate: User feedback requesting natural conversation, offline dictionary, and ML reinforcement
- last_action: "Updated LlmService prompt to allow diagnoses, updated ClinicalCommandParser to capture conversational replies instead of falling back to regex, added automatic submitIntentFeedback to PatientProvider for ML reinforcement, and created TerminologyService for offline clinical dictionary lookups."
- next_action: "Ready for release APK (M7)."
- model: `compact_clinical_mlp` (Sklearn MLP, compact (256,128) TF-IDF student distilled from BERT teacher)
- sidecar_data: Microsoft SYNUR + MTSamples with negation-aware weak supervision
- tokens_used: not tracked
- skills_loaded: []

- notes: The app is now capable of interpreting complex narrative diagnoses natively via the Gemma model without regex interference, standardizing terms against a bundled JSON dictionary, and silently recording feedback signals for the continuous ML pipeline.
