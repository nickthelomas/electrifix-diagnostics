# ElectriFix Diagnostics - Conversation Summary

## Project Overview

Built a web-based e-scooter UART diagnostic tool for Nick's ElectriFix Perth workshop.

## What Was Built

### Core Features
- **Serial Capture Engine**: Captures UART data between scooter dashboard and controller
- **Auto Baud Detection**: Tests common rates (1200, 9600, 115200, etc.)
- **Protocol Parsers**: 
  - Ninebot/Xiaomi (115200 baud)
  - JP/QS-S4 Chinese generic (1200 baud)
  - Generic/unknown protocol handler
- **AI Diagnosis**: OpenRouter API with Claude 3.5 Haiku for intelligent fault analysis
- **Learning Database**: SQLite storing diagnoses, outcomes, and accuracy tracking
- **Modern Web UI**: Vanilla JS frontend, mobile-friendly

### Pre-configured Scooter Models
- Dragon GTR V2, GTS
- Kaabo Mantis 10 Pro, Wolf Warrior X
- Ninebot Max G30, E2
- Xiaomi M365
- Generic Chinese QS-S4

## Technical Stack
- **Backend**: Python 3, FastAPI, SQLite
- **Frontend**: HTML, Tailwind CSS, Vanilla JavaScript
- **AI**: OpenRouter API (Claude 3.5 Haiku)
- **Serial**: pyserial library

## File Structure
```
~/electrifix-diagnostics/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── database.py          # SQLite database
│   ├── serial_capture.py    # Serial port handling
│   ├── analysis.py          # Anomaly detection
│   ├── ai_engine.py         # OpenRouter integration
│   └── protocol_parsers/    # Ninebot, JP, Generic parsers
├── frontend/
│   ├── index.html           # Main UI
│   └── js/app.js            # Frontend logic
├── data/
│   ├── electrifix_diag.db   # SQLite database
│   ├── baselines/           # Known-good captures
│   └── captures/            # Fault captures
├── venv/                    # Python virtual environment
├── .env                     # OpenRouter API key
├── run.py                   # Entry point
└── requirements.txt
```

## Configuration

### OpenRouter API Key
Already configured in `.env`:
```
OPENROUTER_API_KEY=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
```

### AI Model
Using **Claude 3.5 Haiku** via OpenRouter - cost-effective (~/data/data/com.termux/files/usr/bin/bash.25/M input tokens) and capable.

## How to Run

```bash
cd ~/electrifix-diagnostics
./venv/bin/python run.py
```

Then open: **http://localhost:3003**

## Hardware Setup

### USB-TTL Adapter (CP2102)
- **Adapter RX** → Controller/Dash TX line (passive sniffing)
- **Adapter GND** → Scooter GND
- **Adapter TX** → Not connected

When connected, appears as `/dev/ttyUSB0`

### If port not detected:
```bash
sudo usermod -a -G dialout nick
# Then log out and back in
```

## Usage Workflow

1. **Select Scooter Model** from dropdown
2. **Enter Customer Symptoms** (what they reported)
3. **Connect USB-TTL adapter** and select port
4. **Start Capture** and perform test sequence:
   - Power ON, wait 5 seconds
   - Cycle speed modes 1→2→3
   - Pull/release brake
   - Sweep throttle 0%→100%→0%
   - Power OFF
5. **Stop Capture** and click **Analyze**
6. Review AI diagnosis and recommendations

## Server Locations

- **Laptop (primary)**: http://localhost:3003 or http://192.168.50.61:3003
- **K8 server (backup)**: Files at /home/k8-aiden/electrifix-diagnostics/

## Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /api/status | System status, AI config |
| GET /api/serial/ports | List available ports |
| POST /api/serial/start | Start capture |
| POST /api/serial/stop | Stop capture |
| POST /api/diagnose/analyze | Run AI analysis |
| GET /api/models | List scooter models |
| GET /api/diagnose/history | Past diagnoses |

## Future Enhancements Discussed
- Baseline capture system for known-good scooters
- Learning from diagnosis outcomes
- WebSocket real-time capture display
- Export to CSV

## Troubleshooting

### No serial ports showing
- Check USB adapter is connected
- Run: `ls /dev/ttyUSB*`
- Add user to dialout group (see above)

### AI not working
- Check .env file has API key
- Verify internet connection
- Check OpenRouter account has credits

### Server won't start
```bash
# Check if port in use
sudo lsof -i :3003
# Kill if needed
pkill -f 'uvicorn.*3003'
```

---
*Generated: January 2026*
*Built with Claude Code*
