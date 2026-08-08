import os

file_path = "intelligence/llm/local_inference.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update __init__
init_patch = """        self.provider = settings.LLM_PROVIDER.lower().strip()

        # Embedded settings
        self.embedded_repo_id = getattr(settings, "EMBEDDED_REPO_ID", "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        self.embedded_filename = getattr(settings, "EMBEDDED_FILENAME", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
        self._llama = None"""

content = content.replace("        self.provider = settings.LLM_PROVIDER.lower().strip()", init_patch)

# 2. Update generate
gen_orig = """        try:
            if self._is_openai_compatible_provider():
                response = await self._call_openai_compatible(prompt)
            else:
                response = await self._call_ollama(prompt)
            return response.content"""
gen_patch = """        try:
            if self.provider == "embedded":
                response = await self._call_embedded(prompt)
            elif self._is_openai_compatible_provider():
                response = await self._call_openai_compatible(prompt)
            else:
                response = await self._call_ollama(prompt)
            return response.content"""
content = content.replace(gen_orig, gen_patch)

# 3. Update generate_stream
stream_orig = """        try:
            if self._is_openai_compatible_provider():
                # Keep stream contract simple for OpenAI-compatible providers:
                # return a single full chunk when requested via stream API.
                response = await self._call_openai_compatible(prompt)
                yield response.content
            else:
                async for chunk in self._stream_ollama(prompt):
                    yield chunk"""
stream_patch = """        try:
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
                    yield chunk"""
content = content.replace(stream_orig, stream_patch)


# 4. Insert new embedded methods
embedded_methods = """
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
                stop=["User:", "\\n\\n"]
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
                stop=["User:", "\\n\\n"],
                stream=True
            )
            
        stream = await asyncio.to_thread(_stream_gen)
        
        for output in stream:
            chunk = output["choices"][0]["text"]
            if chunk:
                yield chunk
                await asyncio.sleep(0.01)

    async def _call_openai_compatible"""

content = content.replace("    async def _call_openai_compatible", embedded_methods)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patch successful!")
