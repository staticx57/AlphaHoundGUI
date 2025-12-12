from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import asyncio
from alphahound_serial import device as alphahound_device
from routers import device, analysis, isotopes

app = FastAPI()

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
    """WebSocket endpoint for real-time dose rate streaming"""
    await websocket.accept()
    try:
        while True:
            if alphahound_device.is_connected():
                dose = alphahound_device.get_dose_rate()
                await websocket.send_json({"dose_rate": dose})
            else:
                await websocket.send_json({"dose_rate": None, "status": "disconnected"})
            await asyncio.sleep(1)
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    # For localhost only: uvicorn.run(app, host="127.0.0.1", port=3200)
    # For LAN access, use: uvicorn.run(app, host="0.0.0.0", port=3200)
    # Then access from other devices at: http://<your-ip>:3200
    uvicorn.run(app, host="0.0.0.0", port=3200)
