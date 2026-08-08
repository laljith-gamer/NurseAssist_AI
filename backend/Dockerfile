FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for llama-cpp-python
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Create user for HF Spaces (requires running as non-root)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app
COPY --chown=user . $HOME/app

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Download Spacy model
RUN python -m spacy download en_core_web_sm

# Pre-train the models if they don't exist
RUN python scripts/train_intent_model.py || true
RUN python scripts/train_ner_model.py || true

# Expose port for HuggingFace Spaces
EXPOSE 7860

# Run the FastAPI server on port 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
