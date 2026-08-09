import os
import json
import httpx
import asyncio
import zipfile
import shutil
import hashlib
from typing import Dict, Any, Optional
from config import settings
from datetime import datetime
import tempfile
import time

class ModelManager:
    def __init__(self):
        self.github_token = settings.GITHUB_TOKEN
        self.owner = settings.GITHUB_OWNER
        self.repo = settings.GITHUB_REPOSITORY
        self.workflow_id = settings.GITHUB_WORKFLOW_ID
        self.api_base = f"https://api.github.com/repos/{self.owner}/{self.repo}"

    def _get_headers(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    async def trigger_training(self) -> Dict[str, Any]:
        if not self.github_token:
            return {"success": False, "message": "GitHub token not configured"}

        url = f"{self.api_base}/actions/workflows/{self.workflow_id}/dispatches"
        data = {"ref": "main"}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self._get_headers(), json=data)
                if response.status_code == 204:
                    return {"success": True, "message": "Model training started"}
                else:
                    return {"success": False, "message": f"Failed to trigger: {response.text}"}
            except Exception as e:
                return {"success": False, "message": f"Error triggering workflow: {str(e)}"}

    async def get_status(self) -> Dict[str, Any]:
        if not self.github_token:
            return {"status": "error", "message": "GitHub token not configured"}

        url = f"{self.api_base}/actions/runs?per_page=1"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    runs = data.get("workflow_runs", [])
                    if not runs:
                        return {"status": "unknown", "message": "No runs found"}
                    
                    latest_run = runs[0]
                    status = latest_run.get("status")
                    conclusion = latest_run.get("conclusion")
                    
                    if status == "completed":
                        if conclusion == "success":
                            return {"status": "success", "message": "Training completed"}
                        else:
                            return {"status": "failed", "message": f"Training {conclusion}"}
                    else:
                        return {"status": "running", "message": "Training in progress"}
                else:
                    return {"status": "error", "message": f"Failed to fetch status: {response.text}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    async def get_latest_model_metadata(self) -> Dict[str, Any]:
        """Returns the currently active local model metadata."""
        metadata_path = settings.DATA_DIR / "metadata.json"
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                return {"error": str(e)}
        return {"version": "unknown", "status": "no_metadata"}
    
    async def update_models(self) -> Dict[str, Any]:
        if not self.github_token:
            return {"success": False, "message": "GitHub token not configured"}

        release_url = f"{self.api_base}/releases/latest"
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                # 1. Get latest release
                resp = await client.get(release_url, headers=self._get_headers())
                if resp.status_code != 200:
                    return {"success": False, "message": f"Failed to fetch release: {resp.text}"}
                
                release_data = resp.json()
                assets = release_data.get("assets", [])
                
                model_asset = next((a for a in assets if a["name"] == "models.zip"), None)
                if not model_asset:
                    return {"success": False, "message": "No models.zip asset found in the latest release"}

                download_url = model_asset["url"] # Use API url with Accept header to download
                
                # 2. Download into temp dir
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = os.path.join(temp_dir, "models.zip")
                    headers = self._get_headers()
                    headers["Accept"] = "application/octet-stream"
                    
                    async with client.stream('GET', download_url, headers=headers) as stream_resp:
                        if stream_resp.status_code != 200:
                             return {"success": False, "message": f"Failed to download asset: {stream_resp.status_code}"}
                        with open(zip_path, 'wb') as f:
                            async for chunk in stream_resp.aiter_bytes():
                                f.write(chunk)
                                
                    # 3. Extract
                    extract_dir = os.path.join(temp_dir, "extracted")
                    os.makedirs(extract_dir, exist_ok=True)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                    
                    metadata_path = os.path.join(extract_dir, "metadata.json")
                    if not os.path.exists(metadata_path):
                        return {"success": False, "message": "metadata.json missing in release"}
                        
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        
                    # 4. Verify Checksums
                    intent_model_path = os.path.join(extract_dir, "intent_model.pkl")
                    ner_model_dir = os.path.join(extract_dir, "ner_model")
                    
                    if os.path.exists(intent_model_path):
                        intent_sha = self._calculate_file_sha256(intent_model_path)
                        expected_sha = metadata.get("intent_model", {}).get("sha256")
                        if expected_sha and intent_sha != expected_sha:
                            return {"success": False, "message": "Checksum mismatch for intent_model.pkl"}
                            
                    if os.path.exists(ner_model_dir):
                        ner_sha = self._calculate_dir_sha256(ner_model_dir)
                        expected_sha = metadata.get("ner_model", {}).get("sha256")
                        if expected_sha and ner_sha != expected_sha:
                             return {"success": False, "message": "Checksum mismatch for ner_model"}

                    # 5. Validate (Load using classes)
                    from nlp.intent_classifier import IntentClassifier
                    from nlp.entity_extractor import EntityExtractor
                    
                    # Temporarily load them to ensure they aren't corrupted
                    try:
                        import pickle
                        import spacy
                        with open(intent_model_path, 'rb') as f:
                            pickle.load(f)
                        spacy.load(ner_model_dir)
                    except Exception as e:
                        return {"success": False, "message": f"Model validation failed: {str(e)}"}
                        
                    # 6. Backup and Swap
                    backup_dir = settings.DATA_DIR / f"backup_{int(time.time())}"
                    os.makedirs(backup_dir, exist_ok=True)
                    
                    # Backup old
                    old_intent = settings.DATA_DIR / "intent_model.pkl"
                    old_ner = settings.DATA_DIR / "ner_model"
                    old_meta = settings.DATA_DIR / "metadata.json"
                    
                    if old_intent.exists():
                        shutil.copy2(old_intent, backup_dir / "intent_model.pkl")
                    if old_ner.exists():
                        shutil.copytree(old_ner, backup_dir / "ner_model", dirs_exist_ok=True)
                    if old_meta.exists():
                         shutil.copy2(old_meta, backup_dir / "metadata.json")
                         
                    # Install new
                    if os.path.exists(intent_model_path):
                        shutil.copy2(intent_model_path, old_intent)
                    if os.path.exists(ner_model_dir):
                        if old_ner.exists():
                            shutil.rmtree(old_ner)
                        shutil.copytree(ner_model_dir, old_ner)
                    shutil.copy2(metadata_path, old_meta)
                    
                    # 7. Hot Reload
                    from main import get_orchestrator
                    orch = get_orchestrator()
                    if orch and hasattr(orch, 'intent_classifier'):
                        orch.intent_classifier._load_model()
                    if orch and hasattr(orch, 'entity_extractor'):
                        orch.entity_extractor._load_model()
                        
                    return {"success": True, "message": "Models updated successfully", "version": metadata.get("version")}
                    
            except Exception as e:
                return {"success": False, "message": f"Error during update: {str(e)}"}

    def _calculate_file_sha256(self, filepath: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
        
    def _calculate_dir_sha256(self, dirpath: str) -> str:
        sha256_hash = hashlib.sha256()
        for root, _, files in sorted(os.walk(dirpath)):
            for file in sorted(files):
                filepath = os.path.join(root, file)
                with open(filepath, "rb") as f:
                     for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
