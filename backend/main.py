from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import asyncio
from alphahound_serial import device as alphahound_device
from routers import device, analysis, isotopes

# Track active WebSocket connections for session management
active_websockets = set()

# Rate limiter: 60 requests per minute per IP
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(device.router)
app.include_router(analysis.router)
app.include_router(isotopes.router)

# Mount static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

# Keep WebSocket here for stability (simplest path) or in router
# Moving it to main.py avoids any router prefix complexity for WS which can be finicky
@app.websocket("/ws/dose")
async def websocket_dose_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time dose rate streaming with session management"""
    await websocket.accept()
    active_websockets.add(websocket)
    print(f"[WebSocket] Client connected. Active connections: {len(active_websockets)}")
    
    try:
        while True:
            if alphahound_device.is_connected():
                dose = alphahound_device.get_dose_rate()
                await websocket.send_json({"dose_rate": dose})
            else:
                await websocket.send_json({"dose_rate": None, "status": "disconnected"})
            await asyncio.sleep(1)
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
    finally:
        # Remove from active connections
        active_websockets.discard(websocket)
        print(f"[WebSocket] Client disconnected. Active connections: {len(active_websockets)}")
        
        # Auto-disconnect device if no active sessions (prevents zombie connections)
        if len(active_websockets) == 0 and alphahound_device.is_connected():
            print("[WebSocket] No active clients. Auto-disconnecting device to prevent port locking...")
            alphahound_device.disconnect()
        
        # Only close if the connection is still open
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()

if __name__ == "__main__":
    import uvicorn
    # Default: 0.0.0.0 allows both localhost AND LAN access
    # Access locally at: http://localhost:3200
    # Access from LAN at: http://<your-ip>:3200
    uvicorn.run(app, host="0.0.0.0", port=3200, log_level="info")
