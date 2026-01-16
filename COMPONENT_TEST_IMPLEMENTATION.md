# Component Test Screen - Implementation Prompt for Claude Code (Web)

## Project Context
This is the ElectriFix Diagnostics tool - a UART-based e-scooter diagnostic system. We capture serial data between the scooter dashboard and controller via USB-TTL adapter.

Repository: https://github.com/nickthelomas/electrifix-diagnostics

## Feature Request: Component Test Screen

Create a real-time visual diagnostic interface that shows live component states from UART data, with a "Learn" mode for baseline capture.

---

## 1. UI Layout & Wireframe

### New Tab: "Component Test"
Add a new navigation tab between "Diagnose" and "Models"

### Screen Layout (Desktop):
```
┌─────────────────────────────────────────────────────────────┐
│  Component Test - Live Diagnostics                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Learn Mode] [Test Mode]  [Connect] [Stop]                │
│                                                              │
│  Status: ● Connected - 115200 baud - JP/QS-S4 Protocol     │
│                                                              │
├──────────────────┬──────────────────────────────────────────┤
│                  │                                           │
│   SCOOTER        │   LIVE DATA PANEL                        │
│   DIAGRAM        │                                           │
│   (Image)        │   ┌─ Throttle ────────────────────────┐ │
│                  │   │  [████████░░░░░░░░░░] 45%         │ │
│   [Components    │   │  Expected: 40-50% ✓               │ │
│    highlighted]  │   └───────────────────────────────────┘ │
│                  │                                           │
│                  │   ┌─ Brake ───────────────────────────┐ │
│                  │   │  Status: ● ENGAGED                │ │
│                  │   │  Voltage: 3.2V  (Expected: 3.0V)  │ │
│                  │   └───────────────────────────────────┘ │
│                  │                                           │
│                  │   ┌─ Speed/Wheel ─────────────────────┐ │
│                  │   │  Speed: 23 km/h                   │ │
│                  │   │  RPM: 458                         │ │
│                  │   │  Wheel: [Spinning Animation]      │ │
│                  │   └───────────────────────────────────┘ │
│                  │                                           │
│                  │   ┌─ Battery ─────────────────────────┐ │
│                  │   │  Voltage: 52.4V  ✓                │ │
│                  │   │  Current: 8.2A                    │ │
│                  │   │  [████████████░░░] 85%            │ │
│                  │   └───────────────────────────────────┘ │
│                  │                                           │
│                  │   ┌─ Controls ────────────────────────┐ │
│                  │   │  Mode: [ECO] SPORT TURBO          │ │
│                  │   │  Headlight: ● ON                  │ │
│                  │   │  Cruise: ○ OFF                    │ │
│                  │   └───────────────────────────────────┘ │
│                  │                                           │
│                  │   ┌─ Diagnostics ─────────────────────┐ │
│                  │   │  Temperature: 35°C  ✓             │ │
│                  │   │  Packets/sec: 66                  │ │
│                  │   │  Error Code: 0x00 (None)          │ │
│                  │   └───────────────────────────────────┘ │
└──────────────────┴──────────────────────────────────────────┘
```

### Mobile Layout:
- Stack scooter diagram on top
- Live data panels below (full width)
- Collapsible sections

---

## 2. Data Field Mapping

### From JP/QS-S4 Protocol Parser (`backend/protocol_parsers/jp_qs_s4.py`)

**Dashboard → Controller Packet (Bytes 0-14):**
- `packet[3]` → Throttle (0-255) → Convert to percentage: `(value / 255) * 100`
- `packet[4]` bits → Brake status (check bit flags)
- `packet[5]` → Speed mode (1=Eco, 2=Sport, 3=Turbo)
- `packet[6]` → Headlight on/off (bit flag)
- `packet[7]` → Cruise control (bit flag)

**Controller → Dashboard Packet (Bytes 0-14):**
- `packet[3-4]` → Speed (2 bytes, little-endian) → km/h: `(value / 10)`
- `packet[5-6]` → Voltage (2 bytes) → Volts: `(value / 100)`
- `packet[7-8]` → Current (2 bytes) → Amps: `(value / 100)`
- `packet[9]` → Temperature °C
- `packet[10]` → Error code
- `packet[11-12]` → RPM/Motor speed (for wheel animation)

### From Ninebot Protocol Parser (`backend/protocol_parsers/ninebot.py`)

**Message Types:**
- `0x20` → Dashboard control messages
- `0x21` → Controller status messages
- `0x23` → Battery messages

Similar data extraction but different byte positions (see parser for specifics)

### WebSocket Data Source
Use existing `/ws/capture` WebSocket endpoint that streams:
```json
{
  "type": "capture_update",
  "capturing": true,
  "total_bytes": 1234,
  "packet_count": 82,
  "recent_hex": ["01030045...", "01040052..."]
}
```

**Modify WebSocket to also send parsed data:**
```json
{
  "type": "component_data",
  "timestamp": 1234567890,
  "throttle": 45,
  "brake": true,
  "speed": 23.5,
  "voltage": 52.4,
  "current": 8.2,
  "temperature": 35,
  "mode": "sport",
  "headlight": true,
  "cruise": false,
  "rpm": 458,
  "error_code": 0
}
```

---

## 3. Visual Component Mapping

### Scooter Diagram (`frontend/images/scooter-diagram.png`)
Generic scooter illustration with labeled areas for highlighting:

**Interactive/Highlighted Regions:**
1. **Throttle grip** - Highlight intensity based on throttle %
2. **Brake lever** - Red glow when engaged
3. **Front wheel** - CSS rotation animation based on RPM
4. **Rear wheel** - CSS rotation animation based on RPM
5. **Headlight** - Yellow glow when on
6. **Display/Dashboard** - Green when receiving data
7. **Battery pack** - Color code: Green (>80%), Yellow (40-80%), Red (<40%)
8. **Motor** - Heat waves/glow based on temperature
9. **Mode buttons** - Highlight active mode (Eco/Sport/Turbo)
10. **Controller box** - Pulse when packets received

### Color Coding System:
- **Green** = Normal/Within baseline range
- **Yellow** = Slight deviation (10-20% outside baseline)
- **Red** = Significant deviation (>20% outside baseline)
- **Blue** = Active/Engaged
- **Gray** = Inactive/Disconnected

### Animations:
- **Wheel rotation** - CSS transform rotate, speed based on RPM
- **Throttle bar** - Smooth transitions with CSS
- **Brake light** - Pulsing red when engaged
- **Headlight glow** - SVG filter glow effect
- **Data pulse** - Subtle pulse on diagram when packets received

---

## 4. Learn Mode Workflow

### Learn Mode Tab

#### Step 1: Setup
```
┌─────────────────────────────────────────────────┐
│  Learn Mode - Capture Baseline Data            │
├─────────────────────────────────────────────────┤
│                                                  │
│  Select Scooter Model:                          │
│  [Dragon GTR V2 ▼]                              │
│                                                  │
│  This mode captures data from a KNOWN-GOOD      │
│  working scooter to establish baseline ranges.  │
│                                                  │
│  [Start Learning Process]                       │
└─────────────────────────────────────────────────┘
```

#### Step 2: Guided Test Sequence
```
┌─────────────────────────────────────────────────┐
│  Learning: Dragon GTR V2                        │
├─────────────────────────────────────────────────┤
│  Progress: ████████░░░░░░░░ 45%                │
│                                                  │
│  Current Step (3/8):                            │
│  ✓ 1. Power ON and wait                        │
│  ✓ 2. Idle state capture                       │
│  → 3. Slowly apply throttle 0% → 100%          │
│    4. Release throttle                          │
│    5. Apply brake                               │
│    6. Cycle speed modes                         │
│    7. Toggle headlight                          │
│    8. Power OFF                                 │
│                                                  │
│  Capturing throttle curve...                    │
│  [Throttle: ████████░░░░░░░░] 47%              │
│                                                  │
│  [Abort] [Skip Step] [Complete]                │
└─────────────────────────────────────────────────┘
```

#### Step 3: Save Baseline
```
┌─────────────────────────────────────────────────┐
│  Baseline Learning Complete!                    │
├─────────────────────────────────────────────────┤
│  Model: Dragon GTR V2                           │
│  Duration: 2m 34s                               │
│  Packets Captured: 10,234                       │
│                                                  │
│  Learned Parameters:                            │
│  • Throttle response curve: ✓                   │
│  • Brake activation: 3.2V ± 0.2V                │
│  • Idle voltage: 52.4V ± 1.0V                   │
│  • Speed modes: 3 detected                      │
│  • Temperature range: 22-35°C                   │
│  • Normal current: 0.5-15.0A                    │
│                                                  │
│  Notes (optional):                              │
│  [Text area for technician notes]              │
│                                                  │
│  [Save Baseline]  [Discard]                     │
└─────────────────────────────────────────────────┘
```

### Database Schema Addition

Add to `backend/database.py`:

```python
def save_component_baseline(model_id: int, baseline_data: Dict):
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
        "speed_modes": [1, 2, 3],  # Detected modes
        "rpm_per_kmh": 19.5,  # Ratio for wheel animation
        "notes": "Baseline captured from shop demo unit"
    }
    """
```

---

## 5. Test Mode Workflow

### Test Mode Tab

#### Connect and Monitor
```
┌──────────────────────────────────────────────────────────┐
│  Component Test - Dragon GTR V2                          │
│  Status: ● Live  |  Baseline: ✓ Loaded  |  67 pkts/sec  │
├──────────────────────────────────────────────────────────┤
│  [Diagram shows live component states]                   │
│                                                           │
│  ┌─ Real-time Comparison ─────────────────────────────┐ │
│  │                         Current    Baseline  Status │ │
│  │  Throttle:              45%        40-55%     ✓    │ │
│  │  Brake Voltage:         3.1V       3.0-3.4V   ✓    │ │
│  │  Battery Voltage:       52.3V      51-53V     ✓    │ │
│  │  Current Draw:          7.8A       2-18A      ✓    │ │
│  │  Temperature:           38°C       20-40°C    ✓    │ │
│  │  Speed Mode:            Sport      1/2/3      ✓    │ │
│  │  RPM:                   445        -          -    │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                           │
│  ⚠ Anomaly Detected:                                     │
│  └─ None - All components within normal range           │
└──────────────────────────────────────────────────────────┘
```

### Anomaly Detection Display
When values deviate:
```
┌─ Real-time Comparison ─────────────────────────────┐
│                         Current    Baseline  Status │
│  Throttle:              12%        40-55%     ⚠    │ ← Yellow warning
│  Brake Voltage:         0.1V       3.0-3.4V   ✗    │ ← Red error
│  Battery Voltage:       47.2V      51-53V     ⚠    │ ← Yellow warning
└────────────────────────────────────────────────────┘

⚠ Anomalies Detected (3):
  1. 🔴 Brake voltage LOW (0.1V) - Expected: 3.0-3.4V
     → Likely: Brake sensor disconnected or faulty wiring

  2. 🟡 Throttle reading LOW (12%) - Expected: 40-55%
     → Possible: Throttle calibration issue or sensor fault

  3. 🟡 Battery voltage LOW (47.2V) - Expected: 51-53V
     → Battery may be discharged or cell imbalance
```

---

## 6. Technical Implementation Details

### Backend Changes

#### New API Endpoints (`backend/main.py`)

```python
@app.get("/api/component-test/status")
async def get_component_test_status():
    """Get current component states from live capture."""

@app.post("/api/component-test/start-learn")
async def start_learn_mode(model_id: int):
    """Start learning mode for a scooter model."""

@app.post("/api/component-test/save-baseline")
async def save_component_baseline(model_id: int, baseline_data: dict):
    """Save learned baseline data."""

@app.get("/api/component-test/baseline/{model_id}")
async def get_component_baseline(model_id: int):
    """Get baseline data for comparison."""
```

#### Enhanced WebSocket (`backend/main.py`)

Modify `/ws/capture` to parse and send component data in real-time:

```python
@app.websocket("/ws/component-test")
async def websocket_component_test(websocket: WebSocket):
    """
    WebSocket for real-time component state updates.

    Sends parsed component data every 100ms:
    - Throttle %
    - Brake status
    - Speed, voltage, current
    - Mode, lights, error codes
    - Comparison to baseline (if loaded)
    """
```

#### Parser Enhancement

Add method to protocol parsers:

```python
def parse_to_components(self, raw_data: bytes) -> Dict:
    """
    Parse raw packet into component-friendly format.

    Returns:
    {
        "throttle_percent": 45,
        "brake_engaged": True,
        "speed_kmh": 23.5,
        "voltage": 52.4,
        "current": 8.2,
        "temperature": 35,
        "mode": "sport",
        "headlight": True,
        "cruise": False,
        "rpm": 458,
        "error_code": 0
    }
    """
```

### Frontend Implementation

#### New Files to Create:

1. `frontend/component-test.html` (or integrate into index.html)
2. `frontend/js/component-test.js` - Component test logic
3. `frontend/css/component-test.css` - Animations and styling
4. `frontend/images/scooter-diagram.png` - Generic scooter image

#### JavaScript Structure:

```javascript
class ComponentTestController {
    constructor() {
        this.websocket = null;
        this.baseline = null;
        this.currentData = {};
        this.learnMode = false;
        this.learnStep = 0;
    }

    connect() {
        // Connect to WebSocket
        // Start receiving component data
    }

    updateDisplay(componentData) {
        // Update all visual elements
        this.updateThrottle(componentData.throttle_percent);
        this.updateBrake(componentData.brake_engaged);
        this.updateWheels(componentData.rpm);
        this.updateBattery(componentData.voltage);
        this.updateMode(componentData.mode);
        // ... etc

        if (this.baseline) {
            this.compareToBaseline(componentData);
        }
    }

    updateThrottle(percent) {
        // Update throttle bar
        // Highlight throttle on scooter diagram
    }

    updateWheels(rpm) {
        // Rotate wheel SVG/image based on RPM
        const rotationSpeed = rpm * 0.1; // Adjust for visual effect
        wheelElement.style.animation = `spin ${60/rotationSpeed}s linear infinite`;
    }

    compareToBaseline(current) {
        // Compare each value to baseline ranges
        // Update status indicators (✓ ⚠ ✗)
        // Display anomalies
    }

    startLearnMode(modelId) {
        // Initialize learn sequence
        // Guide user through steps
    }
}
```

#### CSS Animations:

```css
/* Wheel rotation */
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.wheel {
    animation: spin 2s linear infinite;
    animation-play-state: paused;
}

.wheel.rotating {
    animation-play-state: running;
}

/* Brake light pulse */
@keyframes brake-pulse {
    0%, 100% { opacity: 1; filter: drop-shadow(0 0 5px red); }
    50% { opacity: 0.7; filter: drop-shadow(0 0 10px red); }
}

.brake-light.active {
    animation: brake-pulse 0.5s ease-in-out infinite;
}

/* Component highlight */
.component-highlight {
    filter: drop-shadow(0 0 8px #00ff00);
    transition: filter 0.3s ease;
}

.component-warning {
    filter: drop-shadow(0 0 8px #ffaa00);
}

.component-error {
    filter: drop-shadow(0 0 8px #ff0000);
}
```

---

## 7. Implementation Steps

### Phase 1: Backend Real-time Parsing
1. Add `parse_to_components()` method to JP and Ninebot parsers
2. Create `/ws/component-test` WebSocket endpoint
3. Test real-time component data extraction

### Phase 2: Basic UI
1. Add "Component Test" tab to navigation
2. Create basic layout with data panels
3. Connect WebSocket and display live values
4. Test with real or simulated data

### Phase 3: Visual Scooter Diagram
1. Add scooter diagram image
2. Implement SVG/CSS overlays for highlighting
3. Add wheel rotation animation
4. Add brake light, headlight effects
5. Wire up live data to visual elements

### Phase 4: Baseline System
1. Add baseline storage to database
2. Create "Learn Mode" UI with guided steps
3. Implement baseline capture logic
4. Add baseline comparison in Test Mode

### Phase 5: Anomaly Detection
1. Implement comparison logic (current vs baseline)
2. Add color-coded status indicators
3. Display anomaly alerts with suggestions
4. Add export/report functionality

---

## 8. Testing Checklist

- [ ] Real-time throttle display updates smoothly
- [ ] Brake light activates instantly when brake engaged
- [ ] Wheels rotate at correct speed based on RPM
- [ ] Battery voltage updates and color codes correctly
- [ ] Mode buttons highlight correctly (Eco/Sport/Turbo)
- [ ] Headlight glows when on
- [ ] Temperature displays and warns at thresholds
- [ ] Learn mode guides through all steps
- [ ] Baseline saves and loads correctly
- [ ] Test mode compares to baseline accurately
- [ ] Anomalies display with correct severity
- [ ] Works with both JP/QS-S4 and Ninebot protocols
- [ ] Mobile responsive layout
- [ ] WebSocket reconnects on disconnect
- [ ] Handles missing/corrupt packets gracefully

---

## 9. Expected User Experience

### Technician Workflow - Learn Mode:
1. Tech selects "Component Test" tab
2. Clicks "Learn Mode"
3. Selects scooter model
4. Connects known-good scooter
5. Follows on-screen guided sequence
6. System captures baseline data
7. Saves with notes
8. Ready for testing faulty scooters

### Technician Workflow - Test Mode:
1. Selects "Component Test" tab
2. Clicks "Test Mode"
3. Selects scooter model (loads baseline)
4. Connects faulty scooter
5. **Instantly sees** live component states
6. Watches scooter diagram come alive
7. Sees green/yellow/red indicators
8. Identifies faulty components visually
9. Gets suggested diagnostics for anomalies

### Example Diagnosis:
"Customer complains throttle not working" →
Tech connects scooter →
Throttle bar stays at 0% even when pressed →
Scooter diagram shows throttle grip in RED →
System shows: "Throttle: 0% (Expected: 40-80% when pressed) ✗" →
Immediate diagnosis: Throttle sensor disconnected/faulty

---

## 10. Future Enhancements (Optional)

- Record and playback component test sessions
- Side-by-side comparison of two scooters
- Export component test reports to PDF
- Add more advanced animations (smoke from motor when overheating, etc.)
- Sound effects for brake, throttle, errors
- Integration with AI diagnosis to suggest fixes
- Mobile app for field testing
- Multi-scooter diagram library (model-specific images)

---

## Summary

This feature transforms the diagnostic tool from "data analyzer" to "live component tester" - making it intuitive and powerful for workshop technicians. The Learn mode ensures accurate baselines, and the visual feedback makes diagnosis instant and obvious.

All the data is already being captured - we just need to parse it and visualize it in real-time!
