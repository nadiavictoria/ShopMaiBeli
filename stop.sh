#!/bin/bash
echo "Stopping ShopMaiBeli services..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "Backend stopped" || echo "Backend was not running"
pkill -f "chainlit run app.py" 2>/dev/null && echo "Frontend stopped" || echo "Frontend was not running"
echo "Done."
