"""A mocked AlphaHound for the browser tests: the device endpoints and the dose WebSocket, no hardware needed.

    from ah_mock import install
    ah = install(page)            # then connect through the UI (port COM8) or call ah["connected"] = True

`ah` holds the state and call counters the tests inspect. The simulated stream has some shape (a gamma baseline with
bursts, a steady beta channel, a sparse alpha channel) so charts look like real data rather than flat lines.
"""
import json
import math
import threading
import time


def install(page, burst=40):
    """Route the AlphaHound endpoints of `page` to a mock; `burst` readings are sent immediately on WebSocket open."""
    ah = {"connected": False, "disconnect_calls": 0, "next_calls": 0, "details_status": 200, "clear_calls": 0}

    def ok(route, body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def route(pattern, handler):
        page.route(pattern, lambda r, q: handler(r, q))

    route("**/device/status", lambda r, q: ok(r, {"connected": ah["connected"], "dose_rate": 70.0 if ah["connected"] else None,
                                                  "temperature": 29.5, "comp_factor": 0.95, "cps": None}))
    route("**/device/ports", lambda r, q: ok(r, {"ports": [{"device": "COM8", "description": "USB Serial Device (COM8)"}]}))

    def connect(r, q):
        ah["connected"] = True
        ok(r, {"status": "connected", "port": "COM8"})
    route("**/device/connect", connect)

    def disconnect(r, q):
        ah["connected"] = False
        ah["disconnect_calls"] += 1
        ok(r, {"status": "disconnected"})
    route("**/device/disconnect", disconnect)

    def details(r, q):
        if ah["details_status"] != 200:
            ok(r, {"detail": "Device not connected"}, ah["details_status"])
        else:
            ok(r, {"model": "AlphaHound", "port": "COM8", "baudrate": 115200, "dose_rate_uRem_h": 70.0, "dose_rate_uSv_h": 0.7,
                   "dose_rate_avg_uRem_h": 64.5, "temperature": 29.5, "comp_factor": 0.95067, "cps": None, "cps_polling": True,
                   "dose_log_entries": 42})
    route("**/device/details", details)

    def display_next(r, q):
        ah["next_calls"] += 1
        ok(r, {"status": "ok", "action": "display_next"})
    route("**/device/display/next", display_next)
    route("**/device/probe", lambda r, q: ok(r, {"command": "P", "lines": ["CPS:270.25,162.53,6.87,770.13"]}))

    def clear(r, q):
        ah["clear_calls"] += 1
        ok(r, {"status": "ok", "cleared": 42})
    route("**/device/dose/log/clear", clear)

    def sample(n):
        gamma = 260 + 18 * math.sin(n / 9.0) + (45 if 14 <= n % 60 < 20 else 0) + (n % 5)
        beta = 150.5 + 6 * math.sin(n / 5.0)
        alpha = 6.25 + (3.5 if n % 11 == 0 else 0)
        return {"dose_rate": 60.0 + (n % 10), "dose_rate_avg": 64.5,
                "cps": {"gamma": round(gamma, 2), "beta": round(beta, 2), "alpha": round(alpha, 2), "dose": 770.0,
                        "total": round(gamma + beta + alpha, 2), "age_s": 0.2}}

    def ws(w):
        def run():
            n = 0
            while True:
                try:
                    w.send(json.dumps(sample(n)))
                    n += 1
                    time.sleep(0.02 if n < burst else 0.3)
                except Exception:
                    return
        threading.Thread(target=run, daemon=True).start()
    page.route_web_socket("**/ws/dose", ws)
    return ah
