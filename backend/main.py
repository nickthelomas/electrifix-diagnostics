"""
ElectriFix Diagnostics - Main FastAPI Application
E-scooter diagnostic tool with UART serial capture and AI-powered diagnosis.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from database import (
    init_database, seed_default_models, get_all_models, get_model_by_id,
    create_model, create_diagnosis, update_diagnosis_with_ai, complete_diagnosis,
    get_diagnosis_history, get_similar_faults, get_diagnosis_stats
)
from serial_capture import SerialCapture, get_capture_instance
from analysis import DiagnosticAnalyzer
from ai_engine import get_ai_engine, configure_ai_engine
from protocol_parsers import NinebotParser, JPParser, GenericParser

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Initialize database
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "baselines").mkdir(exist_ok=True)
    (DATA_DIR / "captures").mkdir(exist_ok=True)
    init_database()
    seed_default_models()
    
    # Configure AI if key is available
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key:
        configure_ai_engine(api_key)
        print("Claude AI engine configured")
    else:
        print("Warning: OPENROUTER_API_KEY not set - AI diagnosis disabled")
    
    yield
    
    # Cleanup
    capture = get_capture_instance()
    if capture.is_capturing:
        capture.stop_capture()


app = FastAPI(
    title="ElectriFix Diagnostics",
    description="E-scooter UART diagnostic tool with AI-powered fault analysis",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# Pydantic models for API
class ScooterModelCreate(BaseModel):
    model_name: str
    manufacturer: Optional[str] = None
    protocol: str = "unknown"
    baud_rate: int = 9600
    voltage: Optional[str] = None
    controller_type: Optional[str] = None
    wiring_diagram: Optional[dict] = None
    tap_point_instructions: Optional[str] = None
    common_faults: Optional[List[str]] = None


class DiagnosisCreate(BaseModel):
    model_id: int
    customer_symptoms: Optional[str] = None


class DiagnosisOutcome(BaseModel):
    actual_fault: str
    fix_applied: str
    parts_cost: Optional[float] = None
    labour_minutes: Optional[int] = None
    diagnosis_correct: bool
    notes: Optional[str] = None


class APIKeyConfig(BaseModel):
    api_key: str


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


# ===== API Routes =====

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>ElectriFix Diagnostics</h1><p>Frontend not found. Please build the frontend.</p>")


@app.get("/api/status")
async def get_status():
    """Get system status."""
    ai_engine = get_ai_engine()
    capture = get_capture_instance()
    
    return {
        "status": "ok",
        "ai_configured": ai_engine.is_configured(),
        "serial_capturing": capture.is_capturing,
        "version": "1.0.0"
    }


@app.get("/api/stats")
async def get_stats():
    """Get diagnosis statistics."""
    return get_diagnosis_stats()


# ----- Serial Port Routes -----

@app.get("/api/serial/ports")
async def list_serial_ports():
    """List available serial ports."""
    capture = get_capture_instance()
    ports = capture.list_available_ports()
    return {"ports": ports}


@app.post("/api/serial/detect-baud")
async def detect_baud_rate(port: str):
    """Auto-detect baud rate for a port."""
    capture = get_capture_instance()
    
    if capture.is_capturing:
        raise HTTPException(400, "Capture already in progress")
    
    baud, protocol = capture.auto_detect_baud_rate(port)
    
    if baud is None:
        return {
            "success": False,
            "message": "Could not detect baud rate. Ensure scooter is powered on."
        }
    
    return {
        "success": True,
        "baud_rate": baud,
        "protocol": protocol
    }


@app.post("/api/serial/start")
async def start_capture(port: str, baud_rate: int = 9600):
    """Start serial capture."""
    capture = get_capture_instance()
    
    if capture.is_capturing:
        raise HTTPException(400, "Capture already in progress")
    
    success = capture.start_capture(port, baud_rate)
    
    if not success:
        raise HTTPException(400, f"Failed to open port {port}")
    
    return {"status": "capturing", "port": port, "baud_rate": baud_rate}


@app.post("/api/serial/stop")
async def stop_capture():
    """Stop serial capture and return data."""
    capture = get_capture_instance()
    
    if not capture.is_capturing:
        return {"status": "not_capturing", "data": None}
    
    session = capture.stop_capture()
    
    if session:
        # Combine all captured data
        raw_data = b''.join(p.raw_bytes for p in session.packets)
        
        return {
            "status": "stopped",
            "total_bytes": session.total_bytes,
            "packet_count": len(session.packets),
            "duration_ms": int((session.end_time - session.start_time).total_seconds() * 1000),
            "hex_preview": raw_data[:500].hex() if raw_data else ""
        }
    
    return {"status": "stopped", "data": None}


@app.get("/api/serial/status")
async def capture_status():
    """Get current capture status."""
    capture = get_capture_instance()
    
    if not capture.is_capturing:
        return {"capturing": False}
    
    session = capture.current_session
    return {
        "capturing": True,
        "port": session.port if session else None,
        "baud_rate": session.baud_rate if session else None,
        "total_bytes": session.total_bytes if session else 0,
        "packet_count": len(session.packets) if session else 0
    }


# ----- Scooter Model Routes -----

@app.get("/api/models")
async def list_models():
    """List all scooter models."""
    models = get_all_models()
    return {"models": models}


@app.get("/api/models/{model_id}")
async def get_model(model_id: int):
    """Get a specific scooter model."""
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    return model


@app.post("/api/models")
async def add_model(model: ScooterModelCreate):
    """Add a new scooter model."""
    model_data = model.dict()
    model_id = create_model(model_data)
    return {"id": model_id, "message": "Model created"}


# ----- Diagnosis Routes -----

@app.post("/api/diagnose/analyze")
async def analyze_capture(
    model_id: int,
    customer_symptoms: Optional[str] = None
):
    """Analyze captured data and generate diagnosis."""
    capture = get_capture_instance()
    
    # Get captured data
    if capture.is_capturing:
        session = capture.stop_capture()
    else:
        # Check if we have data from a previous capture
        session = capture.current_session
    
    if not session or session.total_bytes == 0:
        raise HTTPException(400, "No capture data available")
    
    # Get model info
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    
    # Combine raw data
    raw_data = b''.join(p.raw_bytes for p in session.packets)
    
    # Analyze
    analyzer = DiagnosticAnalyzer()
    result = analyzer.analyze_capture(raw_data, model.get("protocol", "auto"))
    
    # Get anomalies for AI
    anomaly_list = analyzer.get_anomalies_for_ai()
    
    # Save capture file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_filename = f"{timestamp}_{model.get('model_name', 'unknown').replace(' ', '_')}.bin"
    capture_path = DATA_DIR / "captures" / capture_filename
    capture_path.write_bytes(raw_data)
    
    # Create diagnosis record
    diagnosis_data = {
        "model_id": model_id,
        "customer_symptoms": customer_symptoms,
        "capture_file": str(capture_path),
        "raw_anomalies": [a.description for a in result.anomalies],
        "comparison_results": {
            "match_percentage": result.match_percentage,
            "summary": result.summary
        },
        "packet_stats": result.packet_stats
    }
    diagnosis_id = create_diagnosis(diagnosis_data)
    
    # Get AI diagnosis if configured
    ai_result = None
    ai_engine = get_ai_engine()
    
    if ai_engine.is_configured():
        similar_faults = get_similar_faults(model_id, [a.description for a in result.anomalies])
        
        ai_result = ai_engine.diagnose(
            model_name=model.get("model_name", "Unknown"),
            protocol=result.packet_stats.get("protocol", "unknown"),
            customer_symptoms=customer_symptoms or "",
            comparison_summary=result.summary,
            anomaly_list=anomaly_list,
            packet_stats=result.packet_stats,
            similar_faults=similar_faults
        )
        
        if ai_result and not ai_result.get("error"):
            update_diagnosis_with_ai(diagnosis_id, ai_result)
    
    return {
        "diagnosis_id": diagnosis_id,
        "analysis": {
            "protocol": result.packet_stats.get("protocol"),
            "match_percentage": result.match_percentage,
            "summary": result.summary,
            "anomalies": [
                {
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description
                }
                for a in result.anomalies
            ],
            "packet_stats": result.packet_stats
        },
        "ai_diagnosis": ai_result
    }


@app.get("/api/diagnose/history")
async def diagnosis_history(limit: int = 50, model_id: Optional[int] = None):
    """Get diagnosis history."""
    history = get_diagnosis_history(limit, model_id)
    return {"history": history}


@app.post("/api/diagnose/{diagnosis_id}/complete")
async def complete_diagnosis_outcome(diagnosis_id: int, outcome: DiagnosisOutcome):
    """Record the outcome of a diagnosis."""
    complete_diagnosis(diagnosis_id, outcome.dict())
    return {"message": "Diagnosis outcome recorded"}


# ----- Settings Routes -----

@app.post("/api/settings/api-key")
async def set_api_key(config: APIKeyConfig):
    """Set Claude API key."""
    success = configure_ai_engine(config.api_key)
    
    if success:
        # Save to .env file
        env_path = BASE_DIR / ".env"
        with open(env_path, "w") as f:
            f.write(f"OPENROUTER_API_KEY={config.api_key}\n")
        
        return {"message": "API key configured successfully"}
    
    return {"message": "Failed to configure API key", "success": False}


@app.get("/api/settings/ai-status")
async def ai_status():
    """Check AI configuration status."""
    ai_engine = get_ai_engine()
    return {
        "configured": ai_engine.is_configured(),
        "model": ai_engine.model,
        "usage": ai_engine.get_usage_stats()
    }


# ----- WebSocket for real-time capture -----

@app.websocket("/ws/capture")
async def websocket_capture(websocket: WebSocket):
    """WebSocket endpoint for real-time capture data."""
    await manager.connect(websocket)
    capture = get_capture_instance()
    
    try:
        while True:
            # Send current capture status
            if capture.is_capturing and capture.current_session:
                session = capture.current_session
                
                # Get recent packets
                recent_packets = session.packets[-10:] if session.packets else []
                
                await websocket.send_json({
                    "type": "capture_update",
                    "capturing": True,
                    "total_bytes": session.total_bytes,
                    "packet_count": len(session.packets),
                    "recent_hex": [p.hex_string[-100:] for p in recent_packets]
                })
            else:
                await websocket.send_json({
                    "type": "capture_update",
                    "capturing": False
                })
            
            await asyncio.sleep(0.5)  # Update every 500ms
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3003)
