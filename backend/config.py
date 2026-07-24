from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Digital Clinical Nurse Assistant"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    BASE_DIR: Path = Path(__file__).parent
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = DATA_DIR / "clinical.db"
    VECTOR_STORE_PATH: Path = DATA_DIR / "vector_store"
    MEDICAL_VOCAB_PATH: Path = DATA_DIR / "medical_vocab.db"
    # LLM provider options:
    # - "ollama": local model via Ollama generate API
    # - "openai_compatible": OpenAI-compatible chat API (e.g. NVIDIA Integrate)
    LLM_PROVIDER: str = "ollama"

    # Ollama settings
    LLM_MODEL: str = "tinyllama-1.1b-chat-v1.0.Q4_K_M"
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_TIMEOUT: int = 0  # 0 disables request timeout

    # OpenAI-compatible settings (NVIDIA Integrate works with these)
    OPENAI_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "nvidia/nvidia-nemotron-nano-9b-v2"
    OPENAI_TEMPERATURE: float = 0.2
    OPENAI_TOP_P: float = 0.95
    OPENAI_MAX_TOKENS: int = 384
    OPENAI_FREQUENCY_PENALTY: float = 0.0
    OPENAI_PRESENCE_PENALTY: float = 0.0
    OPENAI_ENABLE_THINKING: bool = False
    OPENAI_CLEAR_THINKING: bool = False
    OPENAI_REQUEST_TIMEOUT_SECONDS: float = 0.0  # 0 disables request timeout
    
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSIONS: int = 768
    
    MAX_CONTEXT_TOKENS: int = 4096
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.7
    
    INTENT_CONFIDENCE_THRESHOLD: float = 0.85
    ENTITY_CONFIDENCE_THRESHOLD: float = 0.80
    
    DETERMINISTIC_TIMEOUT_MS: int = 50
    NLP_TIMEOUT_MS: int = 80
    LLM_TIMEOUT_MS: int = 0  # 0 disables orchestrator deadline
    FAST_RESPONSE_MODE: bool = True
    FAST_MAX_TOKENS: int = 256
    
    BP_NORMAL_SYSTOLIC: tuple = (90, 120)
    BP_NORMAL_DIASTOLIC: tuple = (60, 80)
    HR_NORMAL_RANGE: tuple = (60, 100)
    TEMP_NORMAL_RANGE: tuple = (36.1, 37.2)
    SPO2_NORMAL_MIN: float = 95.0
    RR_NORMAL_RANGE: tuple = (12, 20)
    
    WEBSOCKET_HEARTBEAT: int = 30
    SSE_RETRY_MS: int = 3000
    
settings = Settings()

os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.VECTOR_STORE_PATH, exist_ok=True)
