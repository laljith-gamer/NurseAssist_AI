# CURRENT
- active_loop: frontend-ai-enhancements
- target: Fix rigid regex constraints, improve on-device Gemma comprehension, add offline terminology
- iteration: 12
- last_gate: User feedback requesting natural conversation, offline dictionary, and ML reinforcement
- last_action: "Fixed silent native crash on iOS by bypassing a bug in flutter_gemma's isModelInstalled check which caused repetitive installations."
- next_action: "Wait for further user feedback or proceed to release APK (M7)."
- model: `compact_clinical_mlp` (Sklearn MLP, compact (256,128) TF-IDF student distilled from BERT teacher)
- sidecar_data: Microsoft SYNUR + MTSamples with negation-aware weak supervision
- tokens_used: not tracked
- skills_loaded: []

- notes: The app is now capable of properly sending every prompt to the AI and extracting data deterministically instead of falling back to the regex parser due to session crashes.
Bug Fixed: LlmService missing asset crash
Bug Fixed: HF 401 Unauthorized download error by switching to public mirror
Bug Fixed: LLM context limit crash fixed by clearing history before queries
Bug Fixed: Fallback parser erroneously interpreting nursing notes with 'yesterday' as trend queries.
Bug Fixed: Silent native crash on iOS due to `isModelInstalled` bug causing repeated `installModel()` calls. Fixed by attempting to load the active model directly.

## Bug Fixes
 - Added a retry loop to the on-device AI generation to prevent it from immediately falling back to regex when it produces invalid JSON.
 - Fixed dropped prompts when AI is generating by adding a wait queue
 - Fixed fallback to correctly return null for unversioned JSON
 - Fixed parser incorrectly capturing 'yesterday' as queryTrends intent instead of note intent.

## Prompt Engineering
 - Rewrote the Gemma 3 1B system prompt in llm_service.dart to strictly enforce JSON using User/Assistant dialogue paradigms and strict boundaries, drastically reducing conversational hallucinations.
 - Removed manual Assistant: suffix from prompts to prevent confusion for the chat model interface.
 - Added simulated local test suite (llm_prompt_test.dart) to verify parsing robustness.