# ElectriFix Diagnostics

UART-based e-scooter diagnostic tool with AI-powered fault analysis.

## Features

- **Serial Capture**: Captures UART communication between scooter dashboard and controller
- **Auto Baud Detection**: Automatically detects the correct baud rate
- **Protocol Parsing**: Supports Ninebot/Xiaomi and JP/QS-S4 protocols
- **AI Diagnosis**: Claude-powered intelligent fault analysis
- **Learning Database**: Tracks diagnoses to improve accuracy over time
- **Modern UI**: Professional, workshop-friendly interface

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Claude API Key (Optional but Recommended)

Create a `.env` file:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```

Or configure through the web interface after starting.

### 3. Run the Application

```bash
python run.py
```

### 4. Open in Browser

Navigate to: **http://localhost:3003**

## Hardware Setup

### USB-TTL Adapter Connection

Using a CP2102 or similar USB-TTL adapter:

1. **Adapter RX** → Controller/Dash TX line (listen only)
2. **Adapter GND** → Scooter GND
3. **Adapter TX** → Not connected (passive sniffing)

### Supported Protocols

| Protocol | Baud Rate | Scooters |
|----------|-----------|----------|
| JP/QS-S4 | 1200 | Dragon GTR, Kaabo, Chinese generics |
| Ninebot | 115200 | Xiaomi M365, Ninebot Max/E2 |

## Usage

### Basic Diagnosis Workflow

1. **Select Scooter Model** - Choose from pre-configured models
2. **Enter Symptoms** - Describe what the customer reported
3. **Connect & Capture** - Follow the guided test sequence
4. **Review Results** - AI provides diagnosis and recommendations

### Guided Test Sequence

When capturing data, follow this sequence for best results:

1. Power ON scooter - wait 5 seconds
2. Cycle through speed modes (1 → 2 → 3)
3. Pull and release brake lever
4. Slowly sweep throttle 0% → 100% → 0%
5. Power OFF scooter

## File Structure

```
electrifix-diagnostics/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── database.py          # SQLite database
│   ├── serial_capture.py    # Serial port handling
│   ├── analysis.py          # Anomaly detection
│   ├── ai_engine.py         # Claude API integration
│   └── protocol_parsers/    # Protocol implementations
├── frontend/
│   ├── index.html           # Main UI
│   └── js/app.js            # Frontend logic
├── data/
│   ├── baselines/           # Known-good captures
│   └── captures/            # Fault captures
├── run.py                   # Entry point
└── requirements.txt
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/status | System status |
| GET | /api/serial/ports | List serial ports |
| POST | /api/serial/start | Start capture |
| POST | /api/serial/stop | Stop capture |
| POST | /api/diagnose/analyze | Analyze capture |
| GET | /api/diagnose/history | Diagnosis history |
| GET | /api/models | Scooter models |

## Troubleshooting

### No Serial Ports Detected

- Ensure USB-TTL adapter is connected
- On Linux, add user to dialout group: `sudo usermod -a -G dialout $USER`
- Try unplugging and reconnecting the adapter

### No Data Captured

- Check wiring connections
- Ensure scooter is powered on
- Try auto-detect baud rate feature
- Verify correct protocol for your scooter model

### AI Diagnosis Not Working

- Check Claude API key is configured
- Verify internet connection
- Check API key has sufficient credits

## License

Internal tool for ElectriFix Perth.

## Support

For issues, contact the development team.
