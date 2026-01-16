#!/bin/bash
# ElectriFix Diagnostics Launcher
# Starts the server and opens browser

cd "$(dirname "$0")"

# Check if server is already running
if lsof -Pi :3003 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Server already running, opening browser..."
    xdg-open http://localhost:3003
    exit 0
fi

# Start the server in background
echo "Starting ElectriFix Diagnostics server..."
./venv/bin/python run.py > /tmp/electrifix.log 2>&1 &
SERVER_PID=$!

# Wait for server to be ready (max 15 seconds)
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:3003/api/status >/dev/null 2>&1; then
        echo "Server ready!"
        sleep 1
        xdg-open http://localhost:3003
        exit 0
    fi
    sleep 0.5
done

echo "Server failed to start. Check /tmp/electrifix.log for errors."
exit 1
