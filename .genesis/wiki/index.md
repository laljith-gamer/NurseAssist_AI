# NurseAssist_AI Wiki

## Runtime architecture

- `frontend/lib/services/llm_service.dart` owns download, installation, engine initialization, single-turn chat reset, and response cleanup.
- The LLM is optional. Structured clinical commands must work when no model is installed or when LLM inference fails.
- `flutter_gemma` with `flutter_gemma_mediapipe` loads a MediaPipe/LiteRT `.task` model. Other formats such as GGUF, ONNX, and PyTorch weights are not valid replacements.

## Model-release contract

| Location | Required value |
|---|---|
| App model filename | `Gemma2-2B-IT_multi-prefill-seq_q8_ekv1280.task` |
| App model URL | Public Hugging Face bucket direct-file URL |
| Model type | MediaPipe/LiteRT `.task`, Gemma 2 INT8, 2.71 GB |

The app downloads directly from the bucket because the model exceeds GitHub's
2 GiB per-release-asset limit. A `Not Found` response means the bucket file
name or direct-file URL is wrong.

## Known quality guardrails

- Clear chat history before each unrelated user request.
- Use conservative generation settings.
- Strip model control tokens and reject prompt echoes.
- Do not treat a repeated or malformed LLM response as a clinical result.
