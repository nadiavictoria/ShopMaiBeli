#!/bin/bash

# Start frontend and backend in background
# IMPORTANT: Run from project root to ensure imports work correctly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify we're in the project root
cd "$SCRIPT_DIR"

echo "Starting ShopMaiBeli services..."
echo "Project root: $SCRIPT_DIR"
echo ""

# Start backend using uvicorn (stays in project root)
echo "Starting backend on port 8888..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8888 > backend.log 2>&1 &
SERVER_PID=$!
echo "Backend started with PID: $SERVER_PID"

# Give backend a moment to start
sleep 2

# Start frontend using chainlit (stays in project root)
echo "Starting frontend on port 8000..."
chainlit run frontend/app.py --port 8000 > frontend.log 2>&1 &
CHATBOT_PID=$!
echo "Frontend started with PID: $CHATBOT_PID"

# Save PIDs to file for later stop
echo "$SERVER_PID" > "$SCRIPT_DIR/.server.pid"
echo "$CHATBOT_PID" > "$SCRIPT_DIR/.chatbot.pid"

echo ""
echo "========================================="
echo "Both services started in background."
echo "========================================="
echo ""
echo "Frontend: http://localhost:8000"
echo "Backend:  http://localhost:8888/health"
echo ""
echo "To view logs:"
echo "  Backend:  tail -f backend.log"
echo "  Frontend: tail -f frontend.log"
echo ""
echo "To stop services, run: ./stop.sh"
echo "========================================="
