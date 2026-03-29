#!/bin/bash

# Stop frontend and backend services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.server.pid" ]; then
    SERVER_PID=$(cat "$SCRIPT_DIR/.server.pid")
    kill "$SERVER_PID" 2>/dev/null && echo "Backend (PID $SERVER_PID) stopped."
    rm "$SCRIPT_DIR/.server.pid"
fi

if [ -f "$SCRIPT_DIR/.chatbot.pid" ]; then
    CHATBOT_PID=$(cat "$SCRIPT_DIR/.chatbot.pid")
    kill "$CHATBOT_PID" 2>/dev/null && echo "Frontend (PID $CHATBOT_PID) stopped."
    rm "$SCRIPT_DIR/.chatbot.pid"
fi
