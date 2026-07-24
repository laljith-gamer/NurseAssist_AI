from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Dict, Optional, Set
from datetime import datetime

from config import settings
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
orchestrator = None


def get_orchestrator():
    global orchestrator
    if orchestrator is None:
        from services.assistant_orchestrator import AssistantOrchestrator
        orchestrator = AssistantOrchestrator()
    return orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing database...")
    init_database()
    print("Database initialized successfully")
    get_orchestrator()
    print("Orchestrator initialized")
    yield
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/api/patients")
async def get_patients():
    try:
        from database.repo.patient_repo import PatientRepository
        repo = PatientRepository()
        patients = repo.get_all_patients()
        print(f"Returning {len(patients)} patients")
        return JSONResponse(content=patients)
    except Exception as e:
        print(f"Error fetching patients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    try:
        from database.repo.patient_repo import PatientRepository
        repo = PatientRepository()
        patient = repo.get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        return JSONResponse(content=patient)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching patient: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}/vitals")
async def get_patient_vitals(patient_id: str, days: int = 30):
    try:
        from database.repo.vitals_repo import VitalsRepository
        repo = VitalsRepository()
        vitals = repo.get_vitals_history(patient_id, days)
        return JSONResponse(content=vitals)
    except Exception as e:
        print(f"Error fetching vitals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}/vitals/delta")
async def get_vitals_delta(patient_id: str):
    try:
        from core.change_detector import ChangeDetector
        detector = ChangeDetector()
        delta = detector.get_delta_metrics(patient_id)
        return JSONResponse(content=delta)
    except Exception as e:
        print(f"Error fetching delta: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}/medications")
async def get_patient_medications(patient_id: str):
    try:
        from database.repo.meds_repo import MedicationRepository
        repo = MedicationRepository()
        medications = repo.get_active_medications(patient_id)
        return JSONResponse(content=medications)
    except Exception as e:
        print(f"Error fetching medications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/patients/{patient_id}/chat/sessions")
async def list_chat_sessions(patient_id: str):
    try:
        from database.repo.chat_repo import ChatRepository
        repo = ChatRepository()
        sessions = repo.list_sessions(patient_id)
        return JSONResponse(content=sessions)
    except Exception as e:
        print(f"Error fetching chat sessions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat sessions")


@app.post("/api/patients/{patient_id}/chat/sessions")
async def create_chat_session(patient_id: str, payload: Optional[dict] = None):
    try:
        from database.repo.chat_repo import ChatRepository
        repo = ChatRepository()
        title = None
        if isinstance(payload, dict):
            title = payload.get("title")
        chat_session = repo.create_session(patient_id=patient_id, title=title)
        return JSONResponse(content=chat_session)
    except Exception as e:
        print(f"Error creating chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create chat session")


@app.get("/api/patients/{patient_id}/chat/sessions/{session_id}")
async def get_chat_session(patient_id: str, session_id: str):
    try:
        from database.repo.chat_repo import ChatRepository
        repo = ChatRepository()
        chat_session = repo.get_session(
            patient_id=patient_id,
            session_id=session_id,
            include_messages=True
        )
        if not chat_session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return JSONResponse(content=chat_session)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching chat session: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat session")


@app.post("/api/input")
async def process_input(payload: dict):
    try:
        text = payload.get("text", "")
        patient_id = payload.get("patient_id")
        context = payload.get("context", {})
        session_id = payload.get("session_id")
        user_timestamp = payload.get("timestamp")
        
        orch = get_orchestrator()
        response = await orch.process_input(
            text=text,
            patient_id=patient_id,
            context=context
        )

        if patient_id and text:
            try:
                from database.repo.chat_repo import ChatRepository

                chat_repo = ChatRepository()
                chat_session = chat_repo.ensure_session(patient_id=patient_id, session_id=session_id)
                resolved_session_id = chat_session.get("id")

                chat_repo.append_exchange(
                    patient_id=patient_id,
                    session_id=resolved_session_id,
                    user_content=text,
                    assistant_content=response.get("message", ""),
                    user_timestamp=user_timestamp,
                    assistant_timestamp=datetime.utcnow().isoformat(),
                    assistant_metadata=response.get("data"),
                )

                response_data = response.get("data")
                if not isinstance(response_data, dict):
                    response_data = {}
                response_data["session_id"] = resolved_session_id
                response["data"] = response_data
            except Exception as chat_error:
                print(f"Chat persistence warning: {chat_error}")
        
        return JSONResponse(content=response)
    except Exception as e:
        print(f"Error processing input: {e}")
        raise HTTPException(status_code=500, detail="Failed to process input")


@app.websocket("/ws/{patient_id}")
async def websocket_endpoint(websocket: WebSocket, patient_id: str):
    await manager.connect(websocket, patient_id)
    orch = get_orchestrator()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "success": False,
                    "message": "Invalid JSON payload",
                    "type": "error",
                    "data": {}
                })
                continue
            
            try:
                response = await orch.process_input(
                    text=message.get("text", ""),
                    patient_id=patient_id,
                    context=message.get("context", {})
                )
            except Exception as e:
                print(f"WebSocket processing error: {e}")
                await websocket.send_json({
                    "success": False,
                    "message": "Failed to process message",
                    "type": "error",
                    "data": {}
                })
                continue
            
            await websocket.send_json(response)
            
            if response.get("broadcast"):
                await manager.broadcast_to_patient(patient_id, {
                    "type": "update",
                    "data": response.get("broadcast_data")
                })
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, patient_id)


@app.get("/api/stream/{patient_id}")
async def stream_updates(patient_id: str):
    async def event_generator():
        from database.repo.vitals_repo import VitalsRepository
        repo = VitalsRepository()
        last_check = datetime.utcnow()
        yield f"retry: {settings.SSE_RETRY_MS}\n\n"
        
        while True:
            await asyncio.sleep(2)
            updates = repo.get_updates_since(patient_id, last_check)
            if updates:
                latest_created_at = updates[-1].get("created_at")
                if latest_created_at:
                    try:
                        last_check = datetime.fromisoformat(latest_created_at)
                    except ValueError:
                        last_check = datetime.utcnow()
                else:
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
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
