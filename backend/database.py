"""
ElectriFix Diagnostics - Database Module
SQLite database for scooter models, baselines, and fault history
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DATABASE_PATH = Path(__file__).parent.parent / "data" / "electrifix_diag.db"


def get_db_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    """Initialize database with all required tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Scooter Models table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scooter_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL UNIQUE,
            manufacturer TEXT,
            protocol TEXT DEFAULT 'unknown',
            baud_rate INTEGER DEFAULT 9600,
            voltage TEXT,
            controller_type TEXT,
            wiring_diagram JSON,
            tap_point_instructions TEXT,
            tap_point_image TEXT,
            common_faults JSON,
            has_baseline INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Baselines table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            capture_type TEXT NOT NULL,
            raw_data BLOB,
            parsed_data JSON,
            packet_count INTEGER,
            checksum_errors INTEGER DEFAULT 0,
            capture_duration_ms INTEGER,
            notes TEXT,
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES scooter_models(id) ON DELETE CASCADE
        )
    ''')
    
    # Byte mappings table (for protocol analysis)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS byte_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            byte_position INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            description TEXT,
            min_value INTEGER,
            max_value INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES scooter_models(id) ON DELETE CASCADE,
            UNIQUE(model_id, byte_position)
        )
    ''')
    
    # Fault diagnoses table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fault_diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            customer_symptoms TEXT,
            capture_file TEXT,
            raw_anomalies JSON,
            comparison_results JSON,
            packet_stats JSON,
            ai_diagnosis TEXT,
            ai_confidence TEXT,
            ai_recommendations JSON,
            actual_fault TEXT,
            fix_applied TEXT,
            parts_cost REAL,
            labour_minutes INTEGER,
            diagnosis_correct INTEGER,
            notes TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES scooter_models(id)
        )
    ''')
    
    # Learning patterns table (aggregated from diagnoses)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER,
            anomaly_pattern TEXT NOT NULL,
            fault_category TEXT,
            occurrence_count INTEGER DEFAULT 1,
            correct_diagnoses INTEGER DEFAULT 0,
            common_fixes JSON,
            average_parts_cost REAL,
            average_labour_minutes INTEGER,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES scooter_models(id)
        )
    ''')

    # Component baselines table (for Component Test feature)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS component_baselines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            throttle_curve JSON,
            brake_voltage_min REAL,
            brake_voltage_max REAL,
            idle_voltage_min REAL,
            idle_voltage_max REAL,
            idle_current_min REAL,
            idle_current_max REAL,
            operating_current_min REAL,
            operating_current_max REAL,
            temperature_normal_min INTEGER,
            temperature_normal_max INTEGER,
            temperature_warning INTEGER DEFAULT 50,
            temperature_critical INTEGER DEFAULT 65,
            speed_modes JSON,
            rpm_per_kmh REAL DEFAULT 24.5,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES scooter_models(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE_PATH}")


def seed_default_models():
    """Seed database with default scooter models."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    default_models = [
        {
            "model_name": "Dragon GTR V2",
            "manufacturer": "Dragon",
            "protocol": "jp_qs_s4",
            "baud_rate": 1200,
            "voltage": "48V",
            "controller_type": "JP 25A dual",
            "wiring_diagram": json.dumps({
                "dash_connector_pins": 6,
                "pin_1": "Battery positive",
                "pin_2": "GND",
                "pin_3": "TX (green)",
                "pin_4": "RX (white)",
                "pin_5": "Brake signal",
                "pin_6": "Light switch"
            }),
            "tap_point_instructions": "6-pin connector behind folding stem. Access by removing stem cover plate (2x Allen bolts).",
            "common_faults": json.dumps([
                "Water ingress in stem connector",
                "Rear controller MOSFET failure",
                "Throttle hall sensor drift"
            ])
        },
        {
            "model_name": "Dragon GTS",
            "manufacturer": "Dragon",
            "protocol": "jp_qs_s4",
            "baud_rate": 1200,
            "voltage": "60V",
            "controller_type": "JP 30A dual",
            "tap_point_instructions": "Similar to GTR V2 - stem connector access.",
            "common_faults": json.dumps([
                "Display communication failure",
                "Controller overheating"
            ])
        },
        {
            "model_name": "Kaabo Mantis 10 Pro",
            "manufacturer": "Kaabo",
            "protocol": "jp_qs_s4",
            "baud_rate": 1200,
            "voltage": "52V",
            "controller_type": "Minimotors controller",
            "tap_point_instructions": "Connector under deck plate near stem.",
            "common_faults": json.dumps([
                "Throttle calibration issues",
                "BMS communication errors"
            ])
        },
        {
            "model_name": "Kaabo Wolf Warrior X",
            "manufacturer": "Kaabo",
            "protocol": "jp_qs_s4",
            "baud_rate": 1200,
            "voltage": "60V",
            "controller_type": "Sine wave controller",
            "tap_point_instructions": "Main connector behind stem plate.",
            "common_faults": json.dumps([
                "Motor phase wire issues",
                "Display flickering"
            ])
        },
        {
            "model_name": "Ninebot Max G30",
            "manufacturer": "Segway-Ninebot",
            "protocol": "ninebot",
            "baud_rate": 115200,
            "voltage": "36V",
            "controller_type": "Integrated ESC",
            "tap_point_instructions": "Requires opening deck. Connector on main board.",
            "common_faults": json.dumps([
                "BMS lockout",
                "Speed limiting after firmware update",
                "Dashboard connection errors"
            ])
        },
        {
            "model_name": "Xiaomi M365",
            "manufacturer": "Xiaomi",
            "protocol": "ninebot",
            "baud_rate": 115200,
            "voltage": "36V",
            "controller_type": "Integrated ESC",
            "tap_point_instructions": "Connector inside stem or under deck.",
            "common_faults": json.dumps([
                "Bluetooth module failure",
                "Brake sensor issues",
                "Motor hall sensor failure"
            ])
        },
        {
            "model_name": "Ninebot E2",
            "manufacturer": "Segway-Ninebot",
            "protocol": "ninebot",
            "baud_rate": 115200,
            "voltage": "36V",
            "controller_type": "Integrated",
            "tap_point_instructions": "Entry level model - limited diagnostic access.",
            "common_faults": json.dumps([
                "Battery degradation",
                "Motor noise"
            ])
        },
        {
            "model_name": "Generic Chinese QS-S4",
            "manufacturer": "Various",
            "protocol": "jp_qs_s4",
            "baud_rate": 1200,
            "voltage": "48V/60V",
            "controller_type": "QS-S4 display compatible",
            "tap_point_instructions": "Standard 6-pin connector from display to controller.",
            "common_faults": json.dumps([
                "Display communication loss",
                "Throttle signal issues"
            ])
        }
    ]
    
    for model in default_models:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO scooter_models 
                (model_name, manufacturer, protocol, baud_rate, voltage, 
                 controller_type, wiring_diagram, tap_point_instructions, common_faults)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                model.get("model_name"),
                model.get("manufacturer"),
                model.get("protocol"),
                model.get("baud_rate"),
                model.get("voltage"),
                model.get("controller_type"),
                model.get("wiring_diagram", "{}"),
                model.get("tap_point_instructions"),
                model.get("common_faults", "[]")
            ))
        except Exception as e:
            print(f"Error inserting {model.get('model_name')}: {e}")
    
    conn.commit()
    conn.close()
    print("Default scooter models seeded.")


# Model CRUD operations
def get_all_models() -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scooter_models ORDER BY manufacturer, model_name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_model_by_id(model_id: int) -> Optional[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scooter_models WHERE id = ?", (model_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_model(model_data: Dict) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scooter_models 
        (model_name, manufacturer, protocol, baud_rate, voltage, 
         controller_type, wiring_diagram, tap_point_instructions, common_faults)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        model_data.get("model_name"),
        model_data.get("manufacturer"),
        model_data.get("protocol", "unknown"),
        model_data.get("baud_rate", 9600),
        model_data.get("voltage"),
        model_data.get("controller_type"),
        json.dumps(model_data.get("wiring_diagram", {})),
        model_data.get("tap_point_instructions"),
        json.dumps(model_data.get("common_faults", []))
    ))
    model_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return model_id


# Diagnosis CRUD operations
def create_diagnosis(diagnosis_data: Dict) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO fault_diagnoses 
        (model_id, customer_symptoms, capture_file, raw_anomalies, 
         comparison_results, packet_stats, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    ''', (
        diagnosis_data.get("model_id"),
        diagnosis_data.get("customer_symptoms"),
        diagnosis_data.get("capture_file"),
        json.dumps(diagnosis_data.get("raw_anomalies", [])),
        json.dumps(diagnosis_data.get("comparison_results", {})),
        json.dumps(diagnosis_data.get("packet_stats", {}))
    ))
    diagnosis_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return diagnosis_id


def update_diagnosis_with_ai(diagnosis_id: int, ai_results: Dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE fault_diagnoses 
        SET ai_diagnosis = ?, ai_confidence = ?, ai_recommendations = ?, status = 'diagnosed'
        WHERE id = ?
    ''', (
        ai_results.get("diagnosis"),
        ai_results.get("confidence"),
        json.dumps(ai_results.get("recommendations", [])),
        diagnosis_id
    ))
    conn.commit()
    conn.close()


def complete_diagnosis(diagnosis_id: int, outcome_data: Dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE fault_diagnoses
        SET actual_fault = ?, fix_applied = ?, parts_cost = ?,
            labour_minutes = ?, diagnosis_correct = ?, notes = ?,
            status = 'completed', completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        outcome_data.get("actual_fault"),
        outcome_data.get("fix_applied"),
        outcome_data.get("parts_cost"),
        outcome_data.get("labour_minutes"),
        1 if outcome_data.get("diagnosis_correct") else 0,
        outcome_data.get("notes"),
        diagnosis_id
    ))
    conn.commit()

    # Update learning patterns for future diagnosis improvement
    _update_learning_patterns(cursor, diagnosis_id, outcome_data)

    conn.commit()
    conn.close()


def _update_learning_patterns(cursor, diagnosis_id: int, outcome_data: Dict):
    """Update learning patterns table with completed diagnosis outcomes."""
    try:
        # Get the diagnosis details
        cursor.execute('''
            SELECT model_id, raw_anomalies, actual_fault, fix_applied,
                   parts_cost, labour_minutes, diagnosis_correct
            FROM fault_diagnoses WHERE id = ?
        ''', (diagnosis_id,))
        row = cursor.fetchone()
        if not row:
            return

        model_id = row["model_id"]
        raw_anomalies = row["raw_anomalies"]
        actual_fault = outcome_data.get("actual_fault") or row["actual_fault"]
        fix_applied = outcome_data.get("fix_applied") or row["fix_applied"]
        parts_cost = outcome_data.get("parts_cost") or row["parts_cost"]
        labour_minutes = outcome_data.get("labour_minutes") or row["labour_minutes"]
        is_correct = 1 if outcome_data.get("diagnosis_correct") else 0

        # Create a pattern key from the anomalies
        if isinstance(raw_anomalies, str):
            anomalies_list = json.loads(raw_anomalies)
        else:
            anomalies_list = raw_anomalies or []

        # Create a normalized pattern string (sorted anomalies)
        pattern = "|".join(sorted(set(str(a)[:50] for a in anomalies_list[:5]))) if anomalies_list else "no_anomalies"

        # Check if pattern already exists
        cursor.execute('''
            SELECT id, occurrence_count, correct_diagnoses, common_fixes,
                   average_parts_cost, average_labour_minutes
            FROM learning_patterns
            WHERE model_id = ? AND anomaly_pattern = ?
        ''', (model_id, pattern))
        existing = cursor.fetchone()

        if existing:
            # Update existing pattern
            new_count = existing["occurrence_count"] + 1
            new_correct = existing["correct_diagnoses"] + is_correct

            # Update average costs
            old_avg_cost = existing["average_parts_cost"] or 0
            new_avg_cost = ((old_avg_cost * existing["occurrence_count"]) + (parts_cost or 0)) / new_count

            old_avg_labour = existing["average_labour_minutes"] or 0
            new_avg_labour = int(((old_avg_labour * existing["occurrence_count"]) + (labour_minutes or 0)) / new_count)

            # Update common fixes
            common_fixes = json.loads(existing["common_fixes"]) if existing["common_fixes"] else []
            if fix_applied and fix_applied not in common_fixes:
                common_fixes.append(fix_applied)
                common_fixes = common_fixes[-10:]  # Keep last 10

            cursor.execute('''
                UPDATE learning_patterns
                SET occurrence_count = ?, correct_diagnoses = ?, common_fixes = ?,
                    average_parts_cost = ?, average_labour_minutes = ?,
                    fault_category = ?, last_seen = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_count, new_correct, json.dumps(common_fixes),
                  new_avg_cost, new_avg_labour, actual_fault, existing["id"]))
        else:
            # Insert new pattern
            cursor.execute('''
                INSERT INTO learning_patterns
                (model_id, anomaly_pattern, fault_category, occurrence_count,
                 correct_diagnoses, common_fixes, average_parts_cost, average_labour_minutes)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ''', (model_id, pattern, actual_fault, is_correct,
                  json.dumps([fix_applied] if fix_applied else []),
                  parts_cost or 0, labour_minutes or 0))

    except Exception as e:
        print(f"Warning: Failed to update learning patterns: {e}")


def get_diagnosis_history(limit: int = 50, model_id: Optional[int] = None) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if model_id:
        cursor.execute('''
            SELECT d.*, m.model_name, m.manufacturer 
            FROM fault_diagnoses d
            JOIN scooter_models m ON d.model_id = m.id
            WHERE d.model_id = ?
            ORDER BY d.created_at DESC LIMIT ?
        ''', (model_id, limit))
    else:
        cursor.execute('''
            SELECT d.*, m.model_name, m.manufacturer 
            FROM fault_diagnoses d
            JOIN scooter_models m ON d.model_id = m.id
            ORDER BY d.created_at DESC LIMIT ?
        ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_similar_faults(model_id: int, anomalies: List[str], limit: int = 5) -> List[Dict]:
    """Find similar historical faults for AI context."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get completed diagnoses for this model
    cursor.execute('''
        SELECT * FROM fault_diagnoses 
        WHERE model_id = ? AND status = 'completed'
        ORDER BY created_at DESC LIMIT ?
    ''', (model_id, limit * 2))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Score by anomaly similarity (simple matching)
    results = []
    for row in rows:
        row_dict = dict(row)
        stored_anomalies = json.loads(row_dict.get("raw_anomalies", "[]"))
        match_count = len(set(anomalies) & set(stored_anomalies))
        if match_count > 0:
            row_dict["match_score"] = match_count
            results.append(row_dict)
    
    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return results[:limit]


def get_diagnosis_stats() -> Dict:
    """Get overall diagnosis statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM fault_diagnoses")
    total = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as completed FROM fault_diagnoses WHERE status = 'completed'")
    completed = cursor.fetchone()["completed"]
    
    cursor.execute("SELECT COUNT(*) as correct FROM fault_diagnoses WHERE diagnosis_correct = 1")
    correct = cursor.fetchone()["correct"]
    
    cursor.execute('''
        SELECT m.model_name, COUNT(*) as count 
        FROM fault_diagnoses d
        JOIN scooter_models m ON d.model_id = m.id
        GROUP BY m.model_name
        ORDER BY count DESC LIMIT 5
    ''')
    top_models = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    accuracy = (correct / completed * 100) if completed > 0 else 0
    
    return {
        "total_diagnoses": total,
        "completed_diagnoses": completed,
        "correct_diagnoses": correct,
        "accuracy_percentage": round(accuracy, 1),
        "top_models": top_models
    }


def create_baseline(baseline_data: Dict) -> int:
    """Create a new baseline capture."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO baselines
        (model_id, capture_type, raw_data, parsed_data, packet_count,
         checksum_errors, capture_duration_ms, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        baseline_data.get("model_id"),
        baseline_data.get("capture_type", "working"),
        baseline_data.get("raw_data"),
        json.dumps(baseline_data.get("parsed_data", {})),
        baseline_data.get("packet_count", 0),
        baseline_data.get("checksum_errors", 0),
        baseline_data.get("capture_duration_ms"),
        baseline_data.get("notes")
    ))
    baseline_id = cursor.lastrowid

    # Update model to indicate it has a baseline
    cursor.execute('''
        UPDATE scooter_models SET has_baseline = 1 WHERE id = ?
    ''', (baseline_data.get("model_id"),))

    conn.commit()
    conn.close()
    return baseline_id


def get_baseline_for_model(model_id: int) -> Optional[Dict]:
    """Get the most recent baseline for a model."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM baselines WHERE model_id = ?
        ORDER BY captured_at DESC LIMIT 1
    ''', (model_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_model(model_id: int, model_data: Dict) -> bool:
    """Update an existing scooter model."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE scooter_models
        SET model_name = ?, manufacturer = ?, protocol = ?, baud_rate = ?,
            voltage = ?, controller_type = ?, wiring_diagram = ?,
            tap_point_instructions = ?, common_faults = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        model_data.get("model_name"),
        model_data.get("manufacturer"),
        model_data.get("protocol", "unknown"),
        model_data.get("baud_rate", 9600),
        model_data.get("voltage"),
        model_data.get("controller_type"),
        json.dumps(model_data.get("wiring_diagram", {})),
        model_data.get("tap_point_instructions"),
        json.dumps(model_data.get("common_faults", [])),
        model_id
    ))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


def delete_model(model_id: int) -> bool:
    """Delete a scooter model."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM scooter_models WHERE id = ?', (model_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


# Component Baseline CRUD operations
def save_component_baseline(model_id: int, baseline_data: Dict) -> int:
    """
    Save learned component baseline data.

    baseline_data = {
        "throttle_curve": [0, 10, 25, 45, 70, 90, 100],  # Response at different %
        "brake_voltage": {"min": 3.0, "max": 3.4},
        "idle_voltage": {"min": 51.0, "max": 53.0},
        "idle_current": {"min": 0.3, "max": 0.8},
        "operating_current": {"min": 2.0, "max": 18.0},
        "temperature_normal": {"min": 20, "max": 40},
        "temperature_warning": 50,
        "temperature_critical": 65,
        "speed_modes": [0, 1, 2],  # Detected modes
        "rpm_per_kmh": 24.5,  # Ratio for wheel animation
        "notes": "Baseline captured from shop demo unit"
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if baseline already exists for this model
    cursor.execute('SELECT id FROM component_baselines WHERE model_id = ?', (model_id,))
    existing = cursor.fetchone()

    brake_v = baseline_data.get("brake_voltage", {})
    idle_v = baseline_data.get("idle_voltage", {})
    idle_c = baseline_data.get("idle_current", {})
    op_c = baseline_data.get("operating_current", {})
    temp = baseline_data.get("temperature_normal", {})

    if existing:
        # Update existing baseline
        cursor.execute('''
            UPDATE component_baselines SET
                throttle_curve = ?,
                brake_voltage_min = ?, brake_voltage_max = ?,
                idle_voltage_min = ?, idle_voltage_max = ?,
                idle_current_min = ?, idle_current_max = ?,
                operating_current_min = ?, operating_current_max = ?,
                temperature_normal_min = ?, temperature_normal_max = ?,
                temperature_warning = ?, temperature_critical = ?,
                speed_modes = ?, rpm_per_kmh = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE model_id = ?
        ''', (
            json.dumps(baseline_data.get("throttle_curve", [])),
            brake_v.get("min"), brake_v.get("max"),
            idle_v.get("min"), idle_v.get("max"),
            idle_c.get("min"), idle_c.get("max"),
            op_c.get("min"), op_c.get("max"),
            temp.get("min"), temp.get("max"),
            baseline_data.get("temperature_warning", 50),
            baseline_data.get("temperature_critical", 65),
            json.dumps(baseline_data.get("speed_modes", [])),
            baseline_data.get("rpm_per_kmh", 24.5),
            baseline_data.get("notes"),
            model_id
        ))
        baseline_id = existing['id']
    else:
        # Insert new baseline
        cursor.execute('''
            INSERT INTO component_baselines
            (model_id, throttle_curve, brake_voltage_min, brake_voltage_max,
             idle_voltage_min, idle_voltage_max, idle_current_min, idle_current_max,
             operating_current_min, operating_current_max, temperature_normal_min,
             temperature_normal_max, temperature_warning, temperature_critical,
             speed_modes, rpm_per_kmh, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model_id,
            json.dumps(baseline_data.get("throttle_curve", [])),
            brake_v.get("min"), brake_v.get("max"),
            idle_v.get("min"), idle_v.get("max"),
            idle_c.get("min"), idle_c.get("max"),
            op_c.get("min"), op_c.get("max"),
            temp.get("min"), temp.get("max"),
            baseline_data.get("temperature_warning", 50),
            baseline_data.get("temperature_critical", 65),
            json.dumps(baseline_data.get("speed_modes", [])),
            baseline_data.get("rpm_per_kmh", 24.5),
            baseline_data.get("notes")
        ))
        baseline_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return baseline_id


def get_component_baseline(model_id: int) -> Optional[Dict]:
    """Get component baseline data for a model."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM component_baselines WHERE model_id = ?', (model_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    baseline = dict(row)
    # Parse JSON fields
    if baseline.get('throttle_curve'):
        baseline['throttle_curve'] = json.loads(baseline['throttle_curve'])
    if baseline.get('speed_modes'):
        baseline['speed_modes'] = json.loads(baseline['speed_modes'])

    # Structure the data for easier consumption
    return {
        "id": baseline.get("id"),
        "model_id": baseline.get("model_id"),
        "throttle_curve": baseline.get("throttle_curve", []),
        "brake_voltage": {
            "min": baseline.get("brake_voltage_min"),
            "max": baseline.get("brake_voltage_max")
        },
        "idle_voltage": {
            "min": baseline.get("idle_voltage_min"),
            "max": baseline.get("idle_voltage_max")
        },
        "idle_current": {
            "min": baseline.get("idle_current_min"),
            "max": baseline.get("idle_current_max")
        },
        "operating_current": {
            "min": baseline.get("operating_current_min"),
            "max": baseline.get("operating_current_max")
        },
        "temperature_normal": {
            "min": baseline.get("temperature_normal_min"),
            "max": baseline.get("temperature_normal_max")
        },
        "temperature_warning": baseline.get("temperature_warning", 50),
        "temperature_critical": baseline.get("temperature_critical", 65),
        "speed_modes": baseline.get("speed_modes", []),
        "rpm_per_kmh": baseline.get("rpm_per_kmh", 24.5),
        "notes": baseline.get("notes"),
        "created_at": baseline.get("created_at"),
        "updated_at": baseline.get("updated_at")
    }


def delete_component_baseline(model_id: int) -> bool:
    """Delete component baseline for a model."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM component_baselines WHERE model_id = ?', (model_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success


if __name__ == "__main__":
    init_database()
    seed_default_models()
