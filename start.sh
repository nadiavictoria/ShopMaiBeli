#!/bin/bash
set -e

echo "Starting ShopMaiBeli..."

# Start FastAPI backend
cd backend
uvicorn main:app --host 0.0.0.0 --port 8888 --reload &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID)"
cd ..

# Start Chainlit frontend
cd frontend
chainlit run app.py --host 0.0.0.0 --port 8000 &
FRONTEND_PID=$!
echo "Frontend started (PID $FRONTEND_PID)"
cd ..

echo ""
echo "ShopMaiBeli is running:"
echo "  Frontend: http://localhost:8000"
echo "  Backend:  http://localhost:8888"
echo ""
echo "Press Ctrl+C to stop both services."

wait
