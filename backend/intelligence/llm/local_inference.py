from typing import AsyncGenerator, Dict, List, Optional
import asyncio
import aiohttp
from dataclasses import dataclass

from config import settings
from intelligence.llm.prompt_templates import PromptTemplates


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    finish_reason: str


class LocalLLM:
    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower().strip()

        # Embedded settings
        self.embedded_repo_id = getattr(settings, "EMBEDDED_REPO_ID", "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        self.embedded_filename = getattr(settings, "EMBEDDED_FILENAME", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
        self._llama = None

        # Ollama settings
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.timeout = settings.LLM_TIMEOUT

        # OpenAI-compatible settings
        self.openai_base_url = settings.OPENAI_BASE_URL
        self.openai_api_key = settings.OPENAI_API_KEY
        self.openai_model = settings.OPENAI_MODEL
        self.openai_temperature = settings.OPENAI_TEMPERATURE
        self.openai_top_p = settings.OPENAI_TOP_P
        self.openai_max_tokens = settings.OPENAI_MAX_TOKENS
        self.openai_frequency_penalty = settings.OPENAI_FREQUENCY_PENALTY
        self.openai_presence_penalty = settings.OPENAI_PRESENCE_PENALTY
        self.openai_enable_thinking = settings.OPENAI_ENABLE_THINKING
        self.openai_clear_thinking = settings.OPENAI_CLEAR_THINKING
        self.openai_request_timeout_seconds = settings.OPENAI_REQUEST_TIMEOUT_SECONDS

        # Fast mode keeps latency predictable and prevents long waits in chat.
        self.fast_response_mode = settings.FAST_RESPONSE_MODE
        self.fast_max_tokens = settings.FAST_MAX_TOKENS
        self.llm_deadline_seconds = (
            settings.LLM_TIMEOUT_MS / 1000.0 if settings.LLM_TIMEOUT_MS > 0 else None
        )

        self._openai_client = None
        self.templates = PromptTemplates()

    async def generate(
        self,
        query: str,
        context: str = "",
        retrieved_docs: List = None,
        template_name: str = "clinical_assistant"
    ) -> str:
        prompt = self.templates.build_prompt(
            template_name=template_name,
            query=query,
            context=context,
            retrieved_docs=retrieved_docs or []
        )

        try:
            if self.provider == "embedded":
                response = await self._call_embedded(prompt)
            elif self._is_openai_compatible_provider():
                response = await self._call_openai_compatible(prompt)
            else:
                response = await self._call_ollama(prompt)
            return response.content
        except Exception:
            return self._generate_fallback_response(query, context)

    async def generate_stream(
        self,
        query: str,
        context: str = "",
        retrieved_docs: List = None,
        template_name: str = "clinical_assistant"
    ) -> AsyncGenerator[str, None]:
        prompt = self.templates.build_prompt(
            template_name=template_name,
            query=query,
            context=context,
            retrieved_docs=retrieved_docs or []
        )

        try:
            if self.provider == "embedded":
                async for chunk in self._stream_embedded(prompt):
                    yield chunk
            elif self._is_openai_compatible_provider():
                # Keep stream contract simple for OpenAI-compatible providers:
                # return a single full chunk when requested via stream API.
                response = await self._call_openai_compatible(prompt)
                yield response.content
            else:
                async for chunk in self._stream_ollama(prompt):
                    yield chunk
        except Exception:
            yield self._generate_fallback_response(query, context)


    def _get_embedded_client(self):
        if self._llama is not None:
            return self._llama
            
        try:
            from huggingface_hub import hf_hub_download
            from llama_cpp import Llama
            
            print(f"Downloading/Loading embedded model {self.embedded_filename}...")
            model_path = hf_hub_download(
                repo_id=self.embedded_repo_id,
                filename=self.embedded_filename,
                cache_dir=str(settings.DATA_DIR)
            )
            
            self._llama = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=4,
                verbose=False
            )
            print("Embedded model loaded successfully.")
            return self._llama
        except Exception as e:
            print(f"Failed to initialize embedded LLM: {e}")
            raise

    async def _call_embedded(self, prompt: str) -> LLMResponse:
        llama = await asyncio.to_thread(self._get_embedded_client)
        max_tokens = self.fast_max_tokens if self.fast_response_mode else 512
        
        def _request():
            return llama(
                prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                top_p=0.9,
                stop=["</s>", "<|user|>", "<|system|>"]
            )
            
        response = await asyncio.to_thread(_request)
        content = response["choices"][0]["text"]
        
        return LLMResponse(
            content=content.strip(),
            model=self.embedded_filename,
            tokens_used=response.get("usage", {}).get("total_tokens", 0),
            finish_reason="stop"
        )

    async def _stream_embedded(self, prompt: str) -> AsyncGenerator[str, None]:
        llama = await asyncio.to_thread(self._get_embedded_client)
        max_tokens = self.fast_max_tokens if self.fast_response_mode else 512
        
        def _stream_gen():
            return llama(
                prompt,
                max_tokens=max_tokens,
                temperature=0.3,
                top_p=0.9,
                stop=["</s>", "<|user|>", "<|system|>"],
                stream=True
            )
            
        stream = await asyncio.to_thread(_stream_gen)
        
        for output in stream:
            chunk = output["choices"][0]["text"]
            if chunk:
                yield chunk
                await asyncio.sleep(0.01)

    async def _call_openai_compatible(self, prompt: str) -> LLMResponse:
        client = self._get_openai_client()
        extra_body = self._build_openai_extra_body()
        max_tokens = min(self.openai_max_tokens, self.fast_max_tokens) if self.fast_response_mode else self.openai_max_tokens
        temperature = 0.2 if self.fast_response_mode else self.openai_temperature

        def _request():
            request_kwargs = {
                "model": self.openai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "top_p": self.openai_top_p,
                "max_tokens": max_tokens,
                "frequency_penalty": self.openai_frequency_penalty,
                "presence_penalty": self.openai_presence_penalty,
                "stream": False,
                "extra_body": extra_body,
            }
            if self.openai_request_timeout_seconds > 0:
                request_kwargs["timeout"] = self.openai_request_timeout_seconds

            return client.chat.completions.create(
                **request_kwargs
            )

        request_task = asyncio.to_thread(_request)
        if self.llm_deadline_seconds is not None and self.llm_deadline_seconds > 0:
            completion = await asyncio.wait_for(request_task, timeout=self.llm_deadline_seconds)
        else:
            completion = await request_task

        choice = completion.choices[0] if completion.choices else None
        message = choice.message if choice else None
        content = message.content if message and message.content is not None else ""
        finish_reason = choice.finish_reason if choice and choice.finish_reason else "complete"
        usage = completion.usage.total_tokens if getattr(completion, "usage", None) else 0

        return LLMResponse(
            content=content,
            model=getattr(completion, "model", self.openai_model),
            tokens_used=usage,
            finish_reason=finish_reason
        )

    async def _call_ollama(self, prompt: str) -> LLMResponse:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": self.fast_max_tokens if self.fast_response_mode else 512
            }
        }

        request_timeout = self._resolve_ollama_timeout()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request_timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return LLMResponse(
                        content=data.get("response", ""),
                        model=data.get("model", self.model),
                        tokens_used=data.get("eval_count", 0),
                        finish_reason=data.get("done_reason", "complete")
                    )
                raise Exception(f"Ollama API error: {response.status}")

    async def _stream_ollama(self, prompt: str) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": self.fast_max_tokens if self.fast_response_mode else 512
            }
        }

        request_timeout = self._resolve_ollama_timeout()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=request_timeout)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ollama API error: {response.status}")

                async for line in response.content:
                    if line:
                        try:
                            import json
                            data = json.loads(line.decode())
                            if "response" in data:
                                yield data["response"]
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

    def _is_openai_compatible_provider(self) -> bool:
        return self.provider in {"openai_compatible", "openai", "nvidia"}

    def _get_openai_client(self):
        if self._openai_client is not None:
            return self._openai_client

        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OPENAI-compatible provider") from exc

        client_kwargs = {
            "base_url": self.openai_base_url,
            "api_key": self.openai_api_key,
        }
        if self.openai_request_timeout_seconds > 0:
            client_kwargs["timeout"] = self.openai_request_timeout_seconds

        self._openai_client = OpenAI(**client_kwargs)
        return self._openai_client

    def _resolve_ollama_timeout(self) -> Optional[float]:
        configured_timeout = float(self.timeout) if self.timeout is not None else 0.0
        candidates = [value for value in (configured_timeout, self.llm_deadline_seconds) if value and value > 0]
        if not candidates:
            return None
        return min(candidates)

    def _build_openai_extra_body(self) -> Optional[Dict]:
        if self.fast_response_mode or not self.openai_enable_thinking:
            return None

        return {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": self.openai_clear_thinking
            }
        }

    def _generate_fallback_response(self, query: str, context: str) -> str:
        query_lower = query.lower()

        if "blood pressure" in query_lower or "bp" in query_lower:
            return "Blood pressure should be monitored regularly. Normal BP is less than 120/80 mmHg. Elevated readings may require medication adjustment or lifestyle modifications. Please consult with the physician for specific recommendations."

        if "medication" in query_lower or "med" in query_lower:
            return "For medication-related questions, please verify the current medication list and administration schedule. Always check for allergies and potential drug interactions before administration."

        if "vital" in query_lower:
            return "Vital signs should be assessed and documented regularly. Report any significant changes or abnormal values to the healthcare team promptly."

        if "pain" in query_lower:
            return "Pain should be assessed using a standardized scale (0-10). Document the location, quality, and duration. Reassess after interventions to evaluate effectiveness."

        return "I can help you with patient vitals, medications, and clinical information. Please provide more specific details about what you need assistance with."

    async def summarize_patient(
        self,
        patient_data: Dict,
        vitals_history: List,
        medications: List
    ) -> str:
        context = self._build_patient_context(patient_data, vitals_history, medications)

        return await self.generate(
            query="Provide a concise clinical summary of this patient's current status.",
            context=context,
            template_name="patient_summary"
        )

    async def analyze_trends(
        self,
        vital_type: str,
        readings: List[Dict],
        patient_context: str = ""
    ) -> str:
        readings_text = "\n".join([
            f"- {r.get('timestamp', 'N/A')}: {r.get('value', 'N/A')} {r.get('unit', '')}"
            for r in readings[:10]
        ])

        context = f"""
Vital Sign: {vital_type}
Recent Readings:
{readings_text}

Patient Context: {patient_context}
"""

        return await self.generate(
            query=f"Analyze the trend in {vital_type} readings and provide clinical interpretation.",
            context=context,
            template_name="trend_analysis"
        )

    async def answer_clinical_question(
        self,
        question: str,
        patient_context: str = "",
        retrieved_docs: List = None
    ) -> str:
        return await self.generate(
            query=question,
            context=patient_context,
            retrieved_docs=retrieved_docs,
            template_name="clinical_qa"
        )

    def _build_patient_context(
        self,
        patient_data: Dict,
        vitals_history: List,
        medications: List
    ) -> str:
        context_parts = []

        if patient_data:
            context_parts.append(f"""
Patient: {patient_data.get('name', 'Unknown')}
Age: {patient_data.get('age', 'Unknown')} | Gender: {patient_data.get('gender', 'Unknown')}
Diagnosis: {patient_data.get('primary_diagnosis', 'N/A')}
Allergies: {patient_data.get('allergies', 'None known')}
Code Status: {patient_data.get('code_status', 'N/A')}
""")

        if vitals_history:
            latest = vitals_history[0] if vitals_history else {}
            context_parts.append(f"""
Latest Vitals:
- BP: {latest.get('systolic', 'N/A')}/{latest.get('diastolic', 'N/A')} mmHg
- HR: {latest.get('heart_rate', 'N/A')} bpm
- Temp: {latest.get('temperature', 'N/A')}
- SpO2: {latest.get('spo2', 'N/A')}%
- RR: {latest.get('respiratory_rate', 'N/A')}
""")

        if medications:
            med_list = ", ".join([
                f"{m.get('name', 'Unknown')} {m.get('dose', '')}"
                for m in medications[:10]
            ])
            context_parts.append(f"""
Active Medications: {med_list}
""")

        return "\n".join(context_parts)

    async def check_model_availability(self) -> Dict:
        if self._is_openai_compatible_provider():
            try:
                client = self._get_openai_client()

                def _list_models():
                    return client.models.list()

                models_response = await asyncio.to_thread(_list_models)
                model_ids = [m.id for m in getattr(models_response, "data", []) if getattr(m, "id", None)]

                return {
                    "available": True,
                    "models": model_ids,
                    "current_model": self.openai_model,
                    "model_loaded": self.openai_model in model_ids if model_ids else True
                }
            except Exception as e:
                return {
                    "available": False,
                    "error": str(e)
                }

        try:
            url = f"{self.base_url}/api/tags"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        model_names = [m.get("name", "") for m in models]

                        return {
                            "available": True,
                            "models": model_names,
                            "current_model": self.model,
                            "model_loaded": self.model in model_names
                        }
                    return {
                        "available": False,
                        "error": f"API returned status {response.status}"
                    }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
