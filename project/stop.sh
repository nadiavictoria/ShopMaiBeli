#!/bin/bash

# Stop chatbot and server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.server.pid" ]; then
    SERVER_PID=$(cat "$SCRIPT_DIR/.server.pid")
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Stopping server (PID: $SERVER_PID)..."
        kill "$SERVER_PID"
    fi
    rm "$SCRIPT_DIR/.server.pid"
fi

if [ -f "$SCRIPT_DIR/.chatbot.pid" ]; then
    CHATBOT_PID=$(cat "$SCRIPT_DIR/.chatbot.pid")
    if kill -0 "$CHATBOT_PID" 2>/dev/null; then
        echo "Stopping chatbot (PID: $CHATBOT_PID)..."
        kill "$CHATBOT_PID"
    fi
    rm "$SCRIPT_DIR/.chatbot.pid"
fi

echo "Services stopped."
