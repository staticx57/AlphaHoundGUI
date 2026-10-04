import logging
import os

# Configure logging before project imports so import-time messages are shown.
# Override verbosity with ALPHAHOUND_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR.
logging.basicConfig(
    level=os.environ.get("ALPHAHOUND_LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s [%(name)s] %(message)s",
)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import threading
import time
from contextlib import asynccontextmanager
from devices.alphahound_serial import device as alphahound_device
from routers import device, analysis, isotopes, device_radiacode, nuclear, export

logger = logging.getLogger(__name__)

# Track active WebSocket connections for session management
active_websockets = set()
WS_DISCONNECT_GRACE_S = 10  # seconds to wait for a reconnect before releasing the device

# Unattended operation (both opt-in; the defaults keep the interactive behaviour):
#   ALPHAHOUND_KEEP_CONNECTED=1       do not release the AlphaHound when the last browser tab closes
#   ALPHAHOUND_AUTOCONNECT_PORT=COM8  connect to this serial port at startup (retried while it is busy)
#   ALPHAHOUND_AUTORECONNECT=1        with the port above: keep it connected, reconnecting after a USB drop or a
#                                     silent device (a deliberate Disconnect is respected until the next Connect)
_TRUE = ("1", "true", "yes")
AUTORECONNECT = os.environ.get("ALPHAHOUND_AUTORECONNECT", "").strip().lower() in _TRUE
# A watchdog that keeps the device connected must not be undone by the "last browser tab closed" release
KEEP_CONNECTED = AUTORECONNECT or os.environ.get("ALPHAHOUND_KEEP_CONNECTED", "").strip().lower() in _TRUE

# Rate limiter: 60 requests per minute per IP
limiter = Limiter(key_func=get_remote_address)
@asynccontextmanager
async def lifespan(_app):
    """Startup work (on_event handlers are deprecated). The functions are defined below; they are looked up when the server starts."""
    await _startup_dose_log()
    await _startup_autoconnect()
    yield


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: the UI is served from this same origin, so cross-origin access is off by
# default. Set ALPHAHOUND_CORS_ORIGINS="http://host1:3000,http://host2" to allow others.
_cors_origins = [o.strip() for o in os.environ.get("ALPHAHOUND_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Routers
app.include_router(device.router)
app.include_router(device_radiacode.router)
app.include_router(analysis.router)
app.include_router(nuclear.router)
app.include_router(export.router)
app.include_router(isotopes.router)


# Browsers must revalidate the UI's own files on every load. Without this they may reuse a
# stale module (e.g. an old api.js imported by a new main.js), which silently ignored new options.
# Revalidation is a cheap 304 when nothing changed.
@app.middleware("http")
async def revalidate_ui_files(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

WATCHDOG_INTERVAL_S = 5.0
WATCHDOG_SILENCE_S = 20.0   # a connected device normally sends several dose lines per second


def watchdog_step(port: str, silence_s: float = WATCHDOG_SILENCE_S) -> str:
    """One watchdog pass. Returns what it did: paused | ok | reconnected | failed | restarted | waiting."""
    dev = alphahound_device
    if dev.user_disconnected:
        return "paused"
    if dev.is_connected():
        health = dev.get_health()
        age = health.get("data_age_s")
        since = health.get("connected_for_s") or 0
        # silent for too long (device switched off, cable half out): drop the link and reopen it
        if (age is not None and age > silence_s) or (age is None and since > silence_s):
            logger.warning(f"[Watchdog] No data from the AlphaHound for {age or since}s: reconnecting")
            dev.disconnect()
            time.sleep(1.0)
            return "restarted" if dev.connect(port) else "failed"
        return "ok"
    if dev.connect(port):
        logger.info(f"[Watchdog] AlphaHound reconnected on {port}")
        return "reconnected"
    return "failed"


def _watchdog_loop(port: str):
    failures = 0
    while True:
        time.sleep(WATCHDOG_INTERVAL_S)
        try:
            result = watchdog_step(port)
        except Exception as e:  # never let the watchdog die
            logger.error(f"[Watchdog] {e}")
            continue
        if result == "failed":
            failures += 1
            if failures == 1 or failures % 12 == 0:   # about once a minute, not every pass
                logger.warning(f"[Watchdog] {port}: {alphahound_device.get_last_error()} (failure {failures})")
        else:
            failures = 0


def autoconnect_alphahound(port: str, attempts: int = 15, delay_s: float = 2.0) -> bool:
    """Connect the AlphaHound at startup. A just-restarted server often finds the port still held, so retry."""
    for attempt in range(1, attempts + 1):
        if alphahound_device.is_connected():
            return True
        if alphahound_device.connect(port):
            logger.info(f"[AutoConnect] AlphaHound connected on {port} (attempt {attempt})")
            return True
        logger.warning(f"[AutoConnect] {port}: {alphahound_device.get_last_error()} (attempt {attempt}/{attempts})")
        time.sleep(delay_s)
    logger.error(f"[AutoConnect] Giving up on {port} after {attempts} attempts")
    return False


DOSE_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dose_log.jsonl")


async def _startup_dose_log():
    # Keep the AlphaHound dose history across restarts (ALPHAHOUND_DOSE_LOG=off to keep it in memory only)
    if os.environ.get("ALPHAHOUND_DOSE_LOG", "").strip().lower() != "off":
        alphahound_device.enable_log_persistence(DOSE_LOG_FILE)


async def _startup_autoconnect():
    port = os.environ.get("ALPHAHOUND_AUTOCONNECT_PORT", "").strip()
    if port:
        threading.Thread(target=autoconnect_alphahound, args=(port,), daemon=True, name="autoconnect").start()
        if AUTORECONNECT:
            threading.Thread(target=_watchdog_loop, args=(port,), daemon=True, name="watchdog").start()


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
    logger.info(f"[WebSocket] Client connected. Active connections: {len(active_websockets)}")
    
    try:
        while True:
            if alphahound_device.is_connected():
                dose = alphahound_device.get_dose_rate()
                await websocket.send_json({"dose_rate": dose, "cps": alphahound_device.get_cps(),
                                           "dose_rate_avg": alphahound_device.get_dose_rate_avg()})
            else:
                await websocket.send_json({"dose_rate": None, "status": "disconnected"})
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass                                  # the tab was closed or reloaded: normal, and reported below as a disconnect
    except Exception as e:
        logger.error(f"[WebSocket] Error: {type(e).__name__}: {e}")
    finally:
        # Remove from active connections
        active_websockets.discard(websocket)
        logger.info(f"[WebSocket] Client disconnected. Active connections: {len(active_websockets)}")
        
        # Auto-disconnect device if no active sessions (prevents zombie connections)
        # Grace period so a page refresh (disconnect then immediate reconnect) keeps the device.
        if len(active_websockets) == 0 and alphahound_device.is_connected() and not KEEP_CONNECTED:
            await asyncio.sleep(WS_DISCONNECT_GRACE_S)
            if len(active_websockets) == 0 and alphahound_device.is_connected():
                logger.info("[WebSocket] No active clients. Auto-disconnecting device to prevent port locking...")
                alphahound_device.disconnect()
        
        # Safely attempt to close - may already be closed by client
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed, ignore

if __name__ == "__main__":
    import uvicorn
    # Default: 0.0.0.0 allows both localhost AND LAN access
    # Access locally at: http://localhost:3200
    # Access from LAN at: http://<your-ip>:3200
    uvicorn.run(app, host="0.0.0.0", port=3200, log_level="info")
