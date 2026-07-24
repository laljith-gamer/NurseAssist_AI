from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Dict, Set
from datetime import datetime

from config import settings
from core.router import InputRouter
from database.models import init_database


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, patient_id: str):
        await websocket.accept()
        if patient_id not in self.active_connections:
            self.active_connections[patient_id] = set()
        self.active_connections[patient_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, patient_id: str):
        if patient_id in self.active_connections:
            self.active_connections[patient_id].discard(websocket)
            if not self.active_connections[patient_id]:
                del self.active_connections[patient_id]
    
    async def broadcast_to_patient(self, patient_id: str, message: dict):
        if patient_id in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[patient_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.add(connection)
            for conn in dead_connections:
                self.active_connections[patient_id].discard(conn)


manager = ConnectionManager()
router = InputRouter()
orchestrator = None


def get_orchestrator():
    global orchestrator
    if orchestrator is None:
        from services.assistant_orchestrator import AssistantOrchestrator
        orchestrator = AssistantOrchestrator()
    return orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    get_orchestrator()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.VERSION
    }


@app.websocket("/ws/{patient_id}")
async def websocket_endpoint(websocket: WebSocket, patient_id: str):
    await manager.connect(websocket, patient_id)
    orch = get_orchestrator()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            response = await orch.process_input(
                text=message.get("text", ""),
                patient_id=patient_id,
                context=message.get("context", {})
            )
            
            await websocket.send_json(response)
            
            if response.get("broadcast"):
                await manager.broadcast_to_patient(patient_id, {
                    "type": "update",
                    "data": response.get("broadcast_data")
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, patient_id)


@app.post("/api/input")
async def process_input(payload: dict):
    text = payload.get("text", "")
    patient_id = payload.get("patient_id")
    context = payload.get("context", {})
    
    orch = get_orchestrator()
    response = await orch.process_input(
        text=text,
        patient_id=patient_id,
        context=context
    )
    
    return response


@app.get("/api/patients")
async def get_patients():
    from database.repo.patient_repo import PatientRepository
    repo = PatientRepository()
    return repo.get_all_patients()


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    from database.repo.patient_repo import PatientRepository
    repo = PatientRepository()
    patient = repo.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.get("/api/patients/{patient_id}/vitals")
async def get_patient_vitals(patient_id: str, days: int = 30):
    from database.repo.vitals_repo import VitalsRepository
    repo = VitalsRepository()
    return repo.get_vitals_history(patient_id, days)


@app.get("/api/patients/{patient_id}/vitals/delta")
async def get_vitals_delta(patient_id: str):
    from core.change_detector import ChangeDetector
    detector = ChangeDetector()
    return detector.get_delta_metrics(patient_id)


@app.get("/api/patients/{patient_id}/medications")
async def get_patient_medications(patient_id: str):
    from database.repo.meds_repo import MedicationRepository
    repo = MedicationRepository()
    return repo.get_active_medications(patient_id)


@app.get("/api/stream/{patient_id}")
async def stream_updates(patient_id: str):
    async def event_generator():
        from database.repo.vitals_repo import VitalsRepository
        repo = VitalsRepository()
        last_check = datetime.utcnow()
        
        while True:
            await asyncio.sleep(2)
            updates = repo.get_updates_since(patient_id, last_check)
            if updates:
                last_check = datetime.utcnow()
                yield f"data: {json.dumps(updates)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)