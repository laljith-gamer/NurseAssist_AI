from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Do not let unrelated process variables such as DEBUG=release break a
        # model build. Project overrides use NURSEASSIST_DEBUG, etc.
        env_prefix="NURSEASSIST_",
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
    # - "embedded": local model via llama-cpp-python (auto downloads)
    # - "ollama": local model via Ollama generate API
    # - "openai_compatible": OpenAI-compatible chat API
    LLM_PROVIDER: str = "openai_compatible"

    # Embedded settings
    EMBEDDED_REPO_ID: str = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
    EMBEDDED_FILENAME: str = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

    # Ollama settings
    LLM_MODEL: str = "tinyllama-1.1b-chat-v1.0.Q4_K_M"
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_TIMEOUT: int = 0  # 0 disables request timeout

    # OpenAI-compatible settings (NVIDIA Integrate works with these)
    OPENAI_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "meta/llama-3.1-8b-instruct"
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

    # BioClinicalBERT training-time feature extraction
    BIOCLINICALBERT_MODEL: str = "emilyalsentzer/Bio_ClinicalBERT"
    BIOCLINICALBERT_MAX_LENGTH: int = 512
    BIOCLINICALBERT_BATCH_SIZE: int = 32
    BIOCLINICALBERT_CACHE_DIR: Path = BASE_DIR / "data" / ".cache" / "bioclinicalbert"
    USE_BIOCLINICALBERT: bool = True
    
    BP_NORMAL_SYSTOLIC: tuple = (90, 120)
    BP_NORMAL_DIASTOLIC: tuple = (60, 80)
    HR_NORMAL_RANGE: tuple = (60, 100)
    TEMP_NORMAL_RANGE: tuple = (36.1, 37.2)
    SPO2_NORMAL_MIN: float = 95.0
    RR_NORMAL_RANGE: tuple = (12, 20)
    
    WEBSOCKET_HEARTBEAT: int = 30
    SSE_RETRY_MS: int = 3000
    
    # GitHub Actions Integration
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_OWNER: str = "laljith-gamer"
    GITHUB_REPOSITORY: str = "NurseAssist_AI"
    GITHUB_WORKFLOW_ID: str = "train-models.yml"

    # ── MLP Training Configuration ──────────────────────────────────────
    MLP_HIDDEN_SIZES: tuple = (512, 256, 128)
    MLP_MAX_ITER: int = 80
    MLP_LEARNING_RATE: float = 0.001
    MLP_BATCH_SIZE: int = 32
    MLP_ALPHA: float = 0.01
    MLP_PARAM_BUDGET: int = 1_500_000
    TFIDF_MAX_FEATURES: int = 1024
    PCA_COMPONENTS: int = 1024
    SEED: int = 42

    # ── Knowledge Distillation ──────────────────────────────────────────
    DISTILL_TEMPERATURE: float = 2.0
    DISTILL_ALPHA: float = 0.5
    DISTILL_THRESHOLD: float = 0.4

    # ── Label Selection ─────────────────────────────────────────────────
    MIN_TRAIN_SUPPORT: int = 8
    MIN_DEV_SUPPORT: int = 4
    MIN_DEV_LABEL_F1: float = 0.40

    # ── Quality Gates ───────────────────────────────────────────────────
    MIN_VALIDATION_MICRO_F1: float = 0.30
    MIN_HELD_OUT_TEST_MICRO_F1: float = 0.40
    MAX_HELD_OUT_REGRESSION: float = 0.05
    MIN_SELECTED_LABELS: int = 3

    # ── Negation Detection ──────────────────────────────────────────────
    NEGATION_WINDOW: int = 40

    # ── MTSamples Dataset ───────────────────────────────────────────────
    MTSAMPLES_MAX_RECORDS: int = 3000

    # ── Export ──────────────────────────────────────────────────────────
    EXPORT_FLOAT_PRECISION: int = 6
    
settings = Settings()

os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.VECTOR_STORE_PATH, exist_ok=True)

# Trigger GitHub Actions
# Another trigger
# Third trigger
