# NurseAssist_AI Wiki

## Runtime architecture

- `frontend/lib/services/llm_service.dart` owns download, installation, engine initialization, single-turn chat reset, and response cleanup.
- The LLM is optional. Structured clinical commands must work when no model is installed or when LLM inference fails.
- `flutter_gemma` with `flutter_gemma_mediapipe` loads a MediaPipe/LiteRT `.task` model. Other formats such as GGUF, ONNX, and PyTorch weights are not valid replacements.

## Model-release contract

| Location | Required value |
|---|---|
| App model filename | `gemma-2-2b-it-int4.task` |
| App release URL | GitHub Release `v1.0.0` asset with that filename |
| Workflow input filename | Same filename |
| Workflow source | A direct model-host download URL, not the destination GitHub Release URL |

The workflow downloads the source URL with the `HF_TOKEN` secret, validates it is larger than 1 MB, then uploads it to the GitHub Release. A `Not Found` file of nine bytes means the source URL is wrong, gated without permission, or the destination release URL was mistakenly used as the source.

## Known quality guardrails

- Clear chat history before each unrelated user request.
- Use conservative generation settings.
- Strip model control tokens and reject prompt echoes.
- Do not treat a repeated or malformed LLM response as a clinical result.
