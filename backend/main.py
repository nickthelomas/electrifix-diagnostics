"""
ElectriFix Diagnostics - Main FastAPI Application
E-scooter diagnostic tool with UART serial capture and AI-powered diagnosis.
"""

import os
import sys
import json
import csv
import io
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from database import (
    init_database, seed_default_models, get_all_models, get_model_by_id,
    create_model, update_model, delete_model, create_diagnosis,
    update_diagnosis_with_ai, complete_diagnosis, get_diagnosis_history,
    get_similar_faults, get_diagnosis_stats, create_baseline, get_baseline_for_model
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
IMAGES_DIR = FRONTEND_DIR / "images"


def check_database_integrity() -> Dict[str, any]:
    """Check database integrity at startup."""
    from database import get_db_connection
    issues = []
    warnings = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check all tables exist
        required_tables = ['scooter_models', 'baselines', 'fault_diagnoses', 'byte_mappings', 'learning_patterns']
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row['name'] for row in cursor.fetchall()]

        for table in required_tables:
            if table not in existing_tables:
                issues.append(f"Missing table: {table}")

        # Check foreign key integrity
        cursor.execute("PRAGMA foreign_key_check")
        fk_violations = cursor.fetchall()
        if fk_violations:
            issues.append(f"Foreign key violations found: {len(fk_violations)}")

        # Check for orphaned diagnoses (referencing non-existent models)
        cursor.execute('''
            SELECT COUNT(*) as count FROM fault_diagnoses d
            LEFT JOIN scooter_models m ON d.model_id = m.id
            WHERE m.id IS NULL
        ''')
        orphaned = cursor.fetchone()['count']
        if orphaned > 0:
            warnings.append(f"Orphaned diagnoses found: {orphaned}")

        # Check for missing capture files
        cursor.execute("SELECT id, capture_file FROM fault_diagnoses WHERE capture_file IS NOT NULL")
        for row in cursor.fetchall():
            if row['capture_file'] and not Path(row['capture_file']).exists():
                warnings.append(f"Missing capture file for diagnosis {row['id']}")

        # Run SQLite integrity check
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        if integrity != 'ok':
            issues.append(f"SQLite integrity check failed: {integrity}")

        conn.close()

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }

    except Exception as e:
        return {
            "healthy": False,
            "issues": [f"Database check failed: {str(e)}"],
            "warnings": []
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Initialize directories
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "baselines").mkdir(exist_ok=True)
    (DATA_DIR / "captures").mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)

    # Initialize database
    init_database()
    seed_default_models()

    # Run database integrity checks
    integrity_result = check_database_integrity()
    if not integrity_result["healthy"]:
        print("WARNING: Database integrity issues detected:")
        for issue in integrity_result["issues"]:
            print(f"  - {issue}")
    if integrity_result["warnings"]:
        print("Database warnings:")
        for warning in integrity_result["warnings"]:
            print(f"  - {warning}")

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

# CORS configuration
# In production, set ALLOWED_ORIGINS env var to restrict origins
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else ["*"]
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

if IS_PRODUCTION and ALLOWED_ORIGINS == ["*"]:
    # Default production origins if not specified
    ALLOWED_ORIGINS = ["http://localhost:3003", "http://127.0.0.1:3003"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Mount static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Mount images directory for wiring diagrams
if IMAGES_DIR.exists():
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


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

    @validator('api_key')
    def validate_api_key_format(cls, v):
        """Validate API key format - must start with sk- and be reasonable length."""
        v = v.strip()
        if not v:
            raise ValueError('API key cannot be empty')
        if len(v) < 20:
            raise ValueError('API key appears too short')
        if len(v) > 200:
            raise ValueError('API key appears too long')
        # OpenRouter keys typically start with sk-or- or similar patterns
        if not (v.startswith('sk-') or v.startswith('pk-')):
            raise ValueError('API key should start with sk- or pk-')
        return v


class SimulationConfigModel(BaseModel):
    """Configuration for simulation mode."""
    enabled: bool = False
    protocol: str = "jp_qs_s4"
    fault: str = "none"
    fault_probability: float = 0.1

    @validator('protocol')
    def validate_protocol(cls, v):
        if v not in ['jp_qs_s4', 'ninebot']:
            raise ValueError('Protocol must be jp_qs_s4 or ninebot')
        return v

    @validator('fault')
    def validate_fault(cls, v):
        valid_faults = ['none', 'stuck_throttle', 'checksum_errors', 'no_response',
                       'intermittent', 'overvoltage', 'undervoltage', 'motor_error']
        if v not in valid_faults:
            raise ValueError(f'Invalid fault type. Must be one of: {valid_faults}')
        return v

    @validator('fault_probability')
    def validate_probability(cls, v):
        if not 0 <= v <= 1:
            raise ValueError('Fault probability must be between 0 and 1')
        return v


class GuidedTestStep(BaseModel):
    """A step in the guided test sequence."""
    step_number: int
    title: str
    instruction: str
    expected_result: str
    action: Optional[str] = None  # 'capture', 'analyze', 'check'


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
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
    signal_quality = capture.get_signal_quality()

    return {
        "capturing": True,
        "port": session.port if session else None,
        "baud_rate": session.baud_rate if session else None,
        "total_bytes": session.total_bytes if session else 0,
        "packet_count": len(session.packets) if session else 0,
        "is_simulated": session.is_simulated if session else False,
        "signal_quality": signal_quality
    }


@app.get("/api/serial/signal-quality")
async def get_signal_quality():
    """Get real-time signal quality indicator."""
    capture = get_capture_instance()
    return capture.get_signal_quality()


# ----- Simulation Mode Routes -----

@app.post("/api/simulation/configure")
async def configure_simulation(config: SimulationConfigModel):
    """Configure simulation mode."""
    capture = get_capture_instance()
    capture.configure_simulation(
        enabled=config.enabled,
        protocol=config.protocol,
        fault=config.fault,
        fault_probability=config.fault_probability
    )
    return {
        "message": "Simulation configured",
        "enabled": config.enabled,
        "protocol": config.protocol,
        "fault": config.fault
    }


@app.get("/api/simulation/status")
async def get_simulation_status():
    """Get current simulation mode status."""
    capture = get_capture_instance()
    config = capture.simulation_config
    return {
        "enabled": config.enabled,
        "protocol": config.protocol,
        "fault": config.fault.value if hasattr(config.fault, 'value') else str(config.fault),
        "fault_probability": config.fault_probability
    }


@app.post("/api/simulation/start")
async def start_simulation_capture(
    protocol: str = "jp_qs_s4",
    fault: str = "none",
    fault_probability: float = 0.1
):
    """Start capture in simulation mode."""
    capture = get_capture_instance()

    if capture.is_capturing:
        raise HTTPException(400, "Capture already in progress")

    # Configure and start simulation
    capture.configure_simulation(
        enabled=True,
        protocol=protocol,
        fault=fault,
        fault_probability=fault_probability
    )

    baud_rate = 1200 if protocol == "jp_qs_s4" else 115200
    success = capture.start_capture("SIMULATED", baud_rate)

    if not success:
        raise HTTPException(400, "Failed to start simulation")

    return {
        "status": "capturing",
        "mode": "simulation",
        "protocol": protocol,
        "fault": fault
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


@app.put("/api/models/{model_id}")
async def update_model_endpoint(model_id: int, model: ScooterModelCreate):
    """Update an existing scooter model."""
    model_data = model.dict()
    success = update_model(model_id, model_data)
    if not success:
        raise HTTPException(404, "Model not found")
    return {"message": "Model updated"}


@app.delete("/api/models/{model_id}")
async def delete_model_endpoint(model_id: int):
    """Delete a scooter model."""
    success = delete_model(model_id)
    if not success:
        raise HTTPException(404, "Model not found")
    return {"message": "Model deleted"}


# ----- Baseline Routes -----

@app.post("/api/baselines/capture")
async def capture_baseline(model_id: int, notes: Optional[str] = None):
    """Capture and save a baseline for a scooter model."""
    capture = get_capture_instance()

    # Get captured data
    if capture.is_capturing:
        session = capture.stop_capture()
    else:
        session = capture.last_session

    if not session or session.total_bytes == 0:
        raise HTTPException(400, "No capture data available. Please capture data first.")

    # Get model info
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    # Combine raw data
    raw_data = b''.join(p.raw_bytes for p in session.packets)

    # Analyze to get stats
    analyzer = DiagnosticAnalyzer()
    result = analyzer.analyze_capture(raw_data, model.get("protocol", "auto"))

    # Calculate duration
    duration_ms = 0
    if session.end_time and session.start_time:
        duration_ms = int((session.end_time - session.start_time).total_seconds() * 1000)

    # Save baseline
    baseline_data = {
        "model_id": model_id,
        "capture_type": "working",
        "raw_data": raw_data,
        "parsed_data": result.packet_stats,
        "packet_count": result.packet_stats.get("total_packets", 0),
        "checksum_errors": result.packet_stats.get("invalid_checksums", 0),
        "capture_duration_ms": duration_ms,
        "notes": notes
    }
    baseline_id = create_baseline(baseline_data)

    return {
        "baseline_id": baseline_id,
        "message": "Baseline captured successfully",
        "stats": {
            "total_bytes": session.total_bytes,
            "packet_count": result.packet_stats.get("total_packets", 0),
            "duration_ms": duration_ms
        }
    }


@app.get("/api/baselines/{model_id}")
async def get_baseline(model_id: int):
    """Get the baseline for a model."""
    baseline = get_baseline_for_model(model_id)
    if not baseline:
        raise HTTPException(404, "No baseline found for this model")
    # Don't return raw binary data in JSON
    baseline.pop("raw_data", None)
    return baseline


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
        session = capture.last_session

    if not session or session.total_bytes == 0:
        raise HTTPException(400, "No capture data available. Please capture data first.")
    
    # Get model info
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    
    # Combine raw data
    raw_data = b''.join(p.raw_bytes for p in session.packets)
    
    # Analyze with baseline comparison if available
    analyzer = DiagnosticAnalyzer()

    # Load baseline for comparison if it exists
    baseline = get_baseline_for_model(model_id)
    if baseline and baseline.get("parsed_data"):
        try:
            parsed_data = baseline.get("parsed_data")
            if isinstance(parsed_data, str):
                import json
                parsed_data = json.loads(parsed_data)
            analyzer.set_baseline({"stats": parsed_data})
        except Exception as e:
            print(f"Warning: Could not load baseline for comparison: {e}")

    result = analyzer.analyze_capture(raw_data, model.get("protocol", "auto"))
    
    # Get anomalies for AI
    anomaly_list = analyzer.get_anomalies_for_ai()
    
    # Save capture file (sanitize model name to prevent path traversal)
    import re
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_model_name = re.sub(r'[^\w\-]', '_', model.get('model_name', 'unknown'))
    capture_filename = f"{timestamp}_{safe_model_name}.bin"
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


@app.get("/api/diagnose/{diagnosis_id}")
async def get_diagnosis(diagnosis_id: int):
    """Get a specific diagnosis by ID."""
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.*, m.model_name, m.manufacturer
        FROM fault_diagnoses d
        JOIN scooter_models m ON d.model_id = m.id
        WHERE d.id = ?
    ''', (diagnosis_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Diagnosis not found")
    return dict(row)


# ----- Export Routes -----

@app.get("/api/export/diagnosis/{diagnosis_id}/pdf")
async def export_diagnosis_pdf(diagnosis_id: int):
    """Export a single diagnosis as PDF report."""
    from database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.*, m.model_name, m.manufacturer, m.protocol, m.voltage
        FROM fault_diagnoses d
        JOIN scooter_models m ON d.model_id = m.id
        WHERE d.id = ?
    ''', (diagnosis_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Diagnosis not found")

    diagnosis = dict(row)

    # Generate HTML report (simple PDF alternative)
    html_content = _generate_diagnosis_report_html(diagnosis)

    return HTMLResponse(
        content=html_content,
        headers={
            "Content-Disposition": f"attachment; filename=diagnosis_{diagnosis_id}_report.html"
        }
    )


@app.get("/api/export/history/csv")
async def export_history_csv(model_id: Optional[int] = None, limit: int = 1000):
    """Export fault history as CSV."""
    history = get_diagnosis_history(limit, model_id)

    if not history:
        raise HTTPException(404, "No history data found")

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = [
        'id', 'model_name', 'manufacturer', 'customer_symptoms', 'status',
        'ai_diagnosis', 'ai_confidence', 'actual_fault', 'fix_applied',
        'parts_cost', 'labour_minutes', 'diagnosis_correct', 'created_at', 'completed_at'
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()

    for record in history:
        # Clean up JSON fields for CSV
        row = {k: v for k, v in record.items() if k in fieldnames}
        writer.writerow(row)

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=diagnosis_history_{timestamp}.csv"
        }
    )


@app.get("/api/export/capture/{diagnosis_id}/bin")
async def export_capture_bin(diagnosis_id: int):
    """Export raw capture data as .bin file with metadata JSON."""
    from database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.*, m.model_name, m.manufacturer, m.protocol, m.baud_rate
        FROM fault_diagnoses d
        JOIN scooter_models m ON d.model_id = m.id
        WHERE d.id = ?
    ''', (diagnosis_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Diagnosis not found")

    diagnosis = dict(row)
    capture_file = diagnosis.get('capture_file')

    if not capture_file or not Path(capture_file).exists():
        raise HTTPException(404, "Capture file not found")

    # Read the binary data
    raw_data = Path(capture_file).read_bytes()

    # Create metadata JSON
    metadata = {
        "diagnosis_id": diagnosis_id,
        "model_name": diagnosis.get('model_name'),
        "manufacturer": diagnosis.get('manufacturer'),
        "protocol": diagnosis.get('protocol'),
        "baud_rate": diagnosis.get('baud_rate'),
        "customer_symptoms": diagnosis.get('customer_symptoms'),
        "captured_at": diagnosis.get('created_at'),
        "file_size_bytes": len(raw_data),
        "packet_stats": json.loads(diagnosis.get('packet_stats', '{}'))
    }

    # Return as zip-like structure or just the bin file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{diagnosis_id}_{timestamp}.bin"

    # Also save metadata as sidecar file
    metadata_path = Path(capture_file).with_suffix('.json')
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return Response(
        content=raw_data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Metadata": json.dumps(metadata)
        }
    )


@app.get("/api/export/capture/{diagnosis_id}/metadata")
async def export_capture_metadata(diagnosis_id: int):
    """Export capture metadata as JSON."""
    from database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.*, m.model_name, m.manufacturer, m.protocol, m.baud_rate
        FROM fault_diagnoses d
        JOIN scooter_models m ON d.model_id = m.id
        WHERE d.id = ?
    ''', (diagnosis_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Diagnosis not found")

    diagnosis = dict(row)
    capture_file = diagnosis.get('capture_file')

    file_size = 0
    if capture_file and Path(capture_file).exists():
        file_size = Path(capture_file).stat().st_size

    metadata = {
        "diagnosis_id": diagnosis_id,
        "model_name": diagnosis.get('model_name'),
        "manufacturer": diagnosis.get('manufacturer'),
        "protocol": diagnosis.get('protocol'),
        "baud_rate": diagnosis.get('baud_rate'),
        "customer_symptoms": diagnosis.get('customer_symptoms'),
        "captured_at": diagnosis.get('created_at'),
        "file_size_bytes": file_size,
        "packet_stats": json.loads(diagnosis.get('packet_stats', '{}')),
        "comparison_results": json.loads(diagnosis.get('comparison_results', '{}')),
        "raw_anomalies": json.loads(diagnosis.get('raw_anomalies', '[]')),
        "ai_diagnosis": diagnosis.get('ai_diagnosis'),
        "ai_confidence": diagnosis.get('ai_confidence')
    }

    return metadata


def _generate_resolution_section(diagnosis: dict) -> str:
    """Generate resolution section HTML for completed diagnoses."""
    parts_cost = diagnosis.get('parts_cost') or 0
    labour_minutes = diagnosis.get('labour_minutes') or 0
    return f'''<h2>Resolution</h2>
    <div class="info-grid">
        <div class="info-box">
            <label>Actual Fault</label>
            <span>{diagnosis.get('actual_fault', 'N/A')}</span>
        </div>
        <div class="info-box">
            <label>Fix Applied</label>
            <span>{diagnosis.get('fix_applied', 'N/A')}</span>
        </div>
        <div class="info-box">
            <label>Parts Cost</label>
            <span>${parts_cost:.2f}</span>
        </div>
        <div class="info-box">
            <label>Labour Time</label>
            <span>{labour_minutes} minutes</span>
        </div>
    </div>'''


def _generate_diagnosis_report_html(diagnosis: dict) -> str:
    """Generate HTML report for diagnosis."""
    anomalies = json.loads(diagnosis.get('raw_anomalies', '[]'))
    packet_stats = json.loads(diagnosis.get('packet_stats', '{}'))
    comparison = json.loads(diagnosis.get('comparison_results', '{}'))
    recommendations = json.loads(diagnosis.get('ai_recommendations', '[]'))

    anomaly_html = ""
    for a in anomalies:
        anomaly_html += f"<li>{a}</li>"

    rec_html = ""
    for r in recommendations:
        rec_html += f"<li>{r}</li>"

    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Diagnosis Report #{diagnosis.get('id')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        h1 {{ color: #1e40af; border-bottom: 2px solid #1e40af; padding-bottom: 10px; }}
        h2 {{ color: #374151; margin-top: 30px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .info-box {{ background: #f3f4f6; padding: 15px; border-radius: 8px; }}
        .info-box label {{ font-weight: bold; color: #6b7280; display: block; margin-bottom: 5px; }}
        .info-box span {{ font-size: 1.1em; }}
        .severity-critical {{ color: #dc2626; }}
        .severity-high {{ color: #ea580c; }}
        .severity-medium {{ color: #ca8a04; }}
        .severity-low {{ color: #16a34a; }}
        .ai-box {{ background: #eff6ff; padding: 20px; border-radius: 8px; border-left: 4px solid #3b82f6; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 0.9em; }}
        @media print {{ body {{ margin: 20px; }} }}
    </style>
</head>
<body>
    <h1>ElectriFix Diagnostic Report</h1>

    <div class="info-grid">
        <div class="info-box">
            <label>Diagnosis ID</label>
            <span>#{diagnosis.get('id')}</span>
        </div>
        <div class="info-box">
            <label>Date</label>
            <span>{diagnosis.get('created_at', 'N/A')}</span>
        </div>
        <div class="info-box">
            <label>Scooter Model</label>
            <span>{diagnosis.get('manufacturer', '')} {diagnosis.get('model_name', 'Unknown')}</span>
        </div>
        <div class="info-box">
            <label>Protocol</label>
            <span>{diagnosis.get('protocol', 'Unknown').upper()}</span>
        </div>
        <div class="info-box">
            <label>Status</label>
            <span>{diagnosis.get('status', 'pending').title()}</span>
        </div>
        <div class="info-box">
            <label>Health Score</label>
            <span>{comparison.get('match_percentage', 'N/A')}%</span>
        </div>
    </div>

    <h2>Customer Symptoms</h2>
    <p>{diagnosis.get('customer_symptoms') or 'No symptoms reported'}</p>

    <h2>Detected Issues ({len(anomalies)})</h2>
    <ul>{anomaly_html or '<li>No issues detected</li>'}</ul>

    <h2>Packet Statistics</h2>
    <div class="info-grid">
        <div class="info-box">
            <label>Total Packets</label>
            <span>{packet_stats.get('total_packets', 'N/A')}</span>
        </div>
        <div class="info-box">
            <label>Checksum Error Rate</label>
            <span>{packet_stats.get('checksum_error_rate', 0)}%</span>
        </div>
    </div>

    <h2>AI Diagnosis</h2>
    <div class="ai-box">
        <p><strong>Confidence:</strong> {diagnosis.get('ai_confidence', 'N/A')}</p>
        <p>{diagnosis.get('ai_diagnosis') or 'AI diagnosis not available'}</p>
    </div>

    {f'<h2>Recommendations</h2><ul>{rec_html}</ul>' if rec_html else ''}

    {_generate_resolution_section(diagnosis) if diagnosis.get('status') == 'completed' else ''}

    <div class="footer">
        <p>Generated by ElectriFix Diagnostics | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>This report is for diagnostic reference only.</p>
    </div>
</body>
</html>'''


# ----- Guided Test Sequence Routes -----

GUIDED_TEST_STEPS = [
    {
        "step_number": 1,
        "title": "Visual Inspection",
        "instruction": "Visually inspect the scooter for obvious damage, loose connections, or water damage. Check the display, throttle, and brake lever.",
        "expected_result": "No visible damage or loose components",
        "action": None
    },
    {
        "step_number": 2,
        "title": "Power On Test",
        "instruction": "Power on the scooter and observe the display. Note any error codes shown on the display.",
        "expected_result": "Display powers on, shows normal startup sequence",
        "action": None
    },
    {
        "step_number": 3,
        "title": "Connect Diagnostic Cable",
        "instruction": "Connect the USB-TTL adapter to the diagnostic port. Refer to the wiring diagram for your scooter model.",
        "expected_result": "Cable connected, serial port appears in list",
        "action": "connect"
    },
    {
        "step_number": 4,
        "title": "Select Port and Baud Rate",
        "instruction": "Select the correct serial port from the dropdown. Use Auto-Detect to find the correct baud rate, or select it manually based on your scooter model.",
        "expected_result": "Port selected, baud rate detected/selected",
        "action": "configure"
    },
    {
        "step_number": 5,
        "title": "Baseline Capture (Idle)",
        "instruction": "With the scooter powered on but stationary (wheels off ground), start capture for 5-10 seconds to record idle communication.",
        "expected_result": "Capture shows data flowing, no checksum errors",
        "action": "capture"
    },
    {
        "step_number": 6,
        "title": "Throttle Response Test",
        "instruction": "With wheels off ground, slowly apply throttle while capturing. Observe if throttle values change in the data.",
        "expected_result": "Throttle values increase smoothly with input",
        "action": "capture"
    },
    {
        "step_number": 7,
        "title": "Brake Test",
        "instruction": "Apply brake lever while capturing. Verify brake signal appears in the data.",
        "expected_result": "Brake signal detected when lever is pulled",
        "action": "capture"
    },
    {
        "step_number": 8,
        "title": "Analyze Results",
        "instruction": "Stop capture and run analysis. Review the detected issues and AI diagnosis.",
        "expected_result": "Analysis complete, issues identified if present",
        "action": "analyze"
    }
]


@app.get("/api/guided-test/steps")
async def get_guided_test_steps():
    """Get the guided test sequence steps."""
    return {"steps": GUIDED_TEST_STEPS, "total_steps": len(GUIDED_TEST_STEPS)}


@app.get("/api/guided-test/steps/{step_number}")
async def get_guided_test_step(step_number: int):
    """Get a specific guided test step."""
    if step_number < 1 or step_number > len(GUIDED_TEST_STEPS):
        raise HTTPException(404, "Step not found")
    return GUIDED_TEST_STEPS[step_number - 1]


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


# ----- Database Health Routes -----

@app.get("/api/health/database")
async def get_database_health():
    """Get database health status."""
    return check_database_integrity()


# ----- Wiring Diagram Routes -----

@app.get("/api/models/{model_id}/wiring-diagram")
async def get_wiring_diagram(model_id: int):
    """Get wiring diagram info for a model."""
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    # Check for image file
    image_path = model.get('tap_point_image')
    image_url = None

    if image_path:
        full_path = IMAGES_DIR / image_path
        if full_path.exists():
            image_url = f"/images/{image_path}"

    # Parse wiring diagram JSON
    wiring_data = model.get('wiring_diagram')
    if isinstance(wiring_data, str):
        try:
            wiring_data = json.loads(wiring_data)
        except:
            wiring_data = {}

    return {
        "model_id": model_id,
        "model_name": model.get('model_name'),
        "wiring_diagram": wiring_data,
        "tap_point_instructions": model.get('tap_point_instructions'),
        "image_url": image_url
    }


@app.post("/api/models/{model_id}/wiring-diagram/upload")
async def upload_wiring_diagram(model_id: int, image_data: str = None):
    """Upload/update wiring diagram image for a model (base64 encoded)."""
    from database import get_db_connection
    import base64

    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    if not image_data:
        raise HTTPException(400, "No image data provided")

    # Decode base64 image
    try:
        # Handle data URL format
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
    except Exception as e:
        raise HTTPException(400, f"Invalid image data: {e}")

    # Save image file
    filename = f"wiring_{model_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    image_path = IMAGES_DIR / filename
    image_path.write_bytes(image_bytes)

    # Update model with image path
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scooter_models SET tap_point_image = ? WHERE id = ?",
        (filename, model_id)
    )
    conn.commit()
    conn.close()

    return {
        "message": "Wiring diagram uploaded",
        "image_url": f"/images/{filename}"
    }


# Entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3003)
