# NurseAssist_AI — KICKOFF

NurseAssist is a Flutter nursing-assistant app with deterministic clinical
commands and an on-demand on-device Gemma 2 2B INT8 model.

To resume work:

1. Read `.genesis/checkpoints/CURRENT.md` for the immediate next action.
2. Read `.genesis/wiki/index.md` for the architecture and model contract.
3. Read `.genesis/PLAN.md` for the active milestones.
4. Read `.genesis/implementation-notes.html` for verified implementation facts.

The Gemma 2 2B INT8 model is downloaded on-demand from an ungated Hugging Face bucket on the first launch. Network download is required initially, after which it runs entirely offline.
