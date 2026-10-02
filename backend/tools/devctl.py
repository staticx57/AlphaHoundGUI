#!/usr/bin/env python
"""
devctl: manage the AlphaHoundGUI server and its device connections from the command line.

Built for unattended / remote work: a server restart drops the AlphaHound serial connection, and
reconnecting it normally needs someone at the browser. This does the whole cycle.

    python backend/tools/devctl.py status
    python backend/tools/devctl.py connect [--port COM8] [--wait 30]
    python backend/tools/devctl.py disconnect
    python backend/tools/devctl.py restart [--no-reconnect] [--log FILE]
    python backend/tools/devctl.py ensure            # start the server if down, connect the device if not
    python backend/tools/devctl.py probe D|DA|DB|P   # raw reply of one read-only device command
    python backend/tools/devctl.py rc-connect --mac AA:BB:..   /   rc-disconnect   (Radiacode over BLE)

Exit status is 0 on success and 1 on failure, so it can be chained. The port is remembered in
backend/data/devctl_state.json (override with --port). A server started by `restart` runs with
ALPHAHOUND_KEEP_CONNECTED=1, so closing the last browser tab does not release the device, and (when the
AlphaHound was connected) with ALPHAHOUND_AUTOCONNECT_PORT / ALPHAHOUND_AUTORECONNECT=1, so the server itself
reconnects after a USB drop or a silent device. `disconnect` is respected until the next `connect`.
Set ALPHAHOUND_URL to manage a server that is not on http://127.0.0.1:3200.
"""
import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BACKEND = pathlib.Path(__file__).resolve().parents[1]
STATE_FILE = BACKEND / "data" / "devctl_state.json"
BASE = os.environ.get("ALPHAHOUND_URL", "http://127.0.0.1:3200").rstrip("/")  # not "localhost": Windows tries IPv6 first (slow)
SERVER_PORT = urllib.parse.urlparse(BASE).port or 80
DEFAULT_LOG = pathlib.Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".") / "alphahound_server.log"


# ------------------------------------------------------------------ helpers

def say(msg):
    try:
        print(msg, flush=True)
    except OSError:          # the reader closed the pipe (e.g. `devctl status | head -1`): not an error
        pass


def call(method, path, body=None, timeout=10):
    """(status, parsed JSON or None). status is None when the server cannot be reached."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return None, None


def detail_of(body):
    if isinstance(body, dict):
        return str(body.get("detail", body))
    return str(body)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(**updates):
    state = load_state()
    state.update(updates)
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as e:
        say(f"warning: could not save {STATE_FILE}: {e}")


def server_up():
    return call("GET", "/device/status", timeout=3)[0] == 200


def wait_for(cond, timeout, interval=0.5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(interval)
    return cond()


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def listening_pids(port):
    """PIDs of processes listening on the TCP port."""
    pids = set()
    if os.name == "nt":
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
                pids.add(int(parts[4]))
    else:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        pids.update(int(p) for p in out.split() if p.isdigit())
    return pids


def kill_pid(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
    else:
        os.kill(pid, 9)


# ------------------------------------------------------------------ server

def stop_server():
    pids = listening_pids(SERVER_PORT)
    if not pids:
        say(f"server: nothing listening on port {SERVER_PORT}")
        return True
    for pid in pids:
        say(f"server: stopping PID {pid}")
        kill_pid(pid)
    if not wait_for(lambda: not port_in_use(SERVER_PORT), 20):
        say("server: port is still in use after 20 s")
        return False
    return True


def start_server(log_path, port=None):
    """Start the server detached. With a port, it connects the AlphaHound itself and a watchdog keeps it connected
    (a USB drop or a silent device is recovered; a deliberate `devctl disconnect` is respected)."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("ALPHAHOUND_KEEP_CONNECTED", "1")
    if port:
        env.setdefault("ALPHAHOUND_AUTOCONNECT_PORT", port)
        env.setdefault("ALPHAHOUND_AUTORECONNECT", "1")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                                   | 0x08000000)  # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "main.py"], cwd=str(BACKEND), stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, **kwargs)
    say(f"server: started PID {proc.pid}, log {log_path}")
    if not wait_for(server_up, 90):
        say("server: did not come up within 90 s (see the log)")
        return False
    say("server: up")
    return True


# ------------------------------------------------------------------ AlphaHound

def alphahound_status():
    code, body = call("GET", "/device/status")
    return body if code == 200 and isinstance(body, dict) else None


def pick_port(explicit):
    if explicit:
        return explicit
    code, body = call("GET", "/device/ports")
    ports = body.get("ports", []) if code == 200 and isinstance(body, dict) else []
    names = [p["device"] for p in ports]
    remembered = load_state().get("alphahound_port")
    if remembered and remembered in names:
        return remembered
    usb = [p["device"] for p in ports if "usb serial" in p.get("description", "").lower()]
    if len(usb) == 1:
        return usb[0]
    raise SystemExit(f"cannot choose a serial port (remembered: {remembered}, USB serial candidates: {usb}, "
                     f"all: {names}); pass --port")


def connect_alphahound(port=None, wait=30):
    st = alphahound_status()
    if st is None:
        say("connect: server is not reachable")
        return False
    if st.get("connected"):
        say("connect: AlphaHound already connected")
        return True
    port = pick_port(port)
    deadline = time.time() + wait
    attempt = 0
    while True:
        attempt += 1
        code, body = call("POST", "/device/connect", {"port": port}, timeout=20)
        if code == 200:
            break
        msg = detail_of(body)
        if time.time() >= deadline:
            say(f"connect: failed on {port}: HTTP {code} {msg}")
            return False
        say(f"connect: {port} not ready (HTTP {code}: {msg}); retrying")
        time.sleep(2)
    # confirm the device is really answering: a dose reading (or temperature) arrives within a couple of seconds
    def reading_ready():
        s = alphahound_status() or {}
        return bool(s.get("connected") and (s.get("dose_rate") or s.get("temperature")))

    ok = wait_for(reading_ready, 12)
    st = alphahound_status() or {}
    code, details = call("GET", "/device/details")
    details = details if code == 200 and isinstance(details, dict) else {}
    save_state(alphahound_port=port)
    cps = details.get("cps")
    say(f"connect: AlphaHound connected on {port} (attempt {attempt}); dose {st.get('dose_rate')} uRem/h, "
        f"temp {st.get('temperature')} C, cps {cps if cps else 'none yet'}")
    if not ok:
        say("connect: warning: no dose/temperature reading yet (the device may still be starting)")
    return True


def disconnect_alphahound():
    code, _ = call("POST", "/device/disconnect")
    if code is None:
        say("disconnect: server is not reachable")
        return False
    done = wait_for(lambda: not (alphahound_status() or {}).get("connected"), 5)
    say("disconnect: AlphaHound disconnected" if done else "disconnect: still reported connected")
    return done


# ------------------------------------------------------------------ Radiacode

def radiacode_connected():
    code, body = call("GET", "/radiacode/status")
    return bool(code == 200 and isinstance(body, dict) and body.get("connected"))


def connect_radiacode(mac, wait=30):
    if radiacode_connected():
        say("rc-connect: Radiacode already connected")
        return True
    mac = mac or load_state().get("radiacode_mac")
    if not mac:
        say("rc-connect: no MAC address (pass --mac AA:BB:CC:DD:EE:FF)")
        return False
    end = time.time() + wait
    while True:
        code, body = call("POST", "/radiacode/connect", {"use_bluetooth": True, "bluetooth_mac": mac}, timeout=60)
        if code == 200:
            save_state(radiacode_mac=mac)
            say(f"rc-connect: Radiacode connected ({mac})")
            return True
        if time.time() >= end:
            say(f"rc-connect: failed: HTTP {code} {detail_of(body)}")
            return False
        say(f"rc-connect: not ready (HTTP {code}: {detail_of(body)}); retrying")
        time.sleep(3)


def disconnect_radiacode():
    code, _ = call("POST", "/radiacode/disconnect")
    say("rc-disconnect: done" if code == 200 else f"rc-disconnect: HTTP {code}")
    return code == 200


# ------------------------------------------------------------------ commands

def cmd_status(args):
    up = server_up()
    say(f"server: {'up' if up else 'DOWN'} ({BASE})")
    if not up:
        return False
    st = alphahound_status() or {}
    code, h = call("GET", "/device/health")
    h = h if code == 200 and isinstance(h, dict) else {}
    if st.get("connected"):
        say(f"alphahound: connected, dose {st.get('dose_rate')} uRem/h, temp {st.get('temperature')} C, "
            f"cps {st.get('cps')}")
        age = h.get("data_age_s")
        note = "" if age is None or age < 10 else "  <-- no data for a while"
        say(f"alphahound link: port {h.get('port')}, last data {age}s ago, connected for {h.get('connected_for_s')}s{note}")
    elif h.get("user_disconnected"):
        say("alphahound: disconnected on purpose (a watchdog will not reconnect it until the next connect)")
    else:
        say("alphahound: not connected")
    say(f"radiacode: {'connected' if radiacode_connected() else 'not connected'}")
    return True


def cmd_connect(args):
    return connect_alphahound(args.port, args.wait)


def cmd_disconnect(args):
    return disconnect_alphahound()


def cmd_restart(args):
    ah = alphahound_status() or {}
    ah_was = bool(ah.get("connected"))
    if ah_was:
        code, details = call("GET", "/device/details")
        if code == 200 and isinstance(details, dict) and details.get("port"):
            save_state(alphahound_port=details["port"])
    rc_was = radiacode_connected()
    say(f"restart: before: alphahound {'connected' if ah_was else 'not connected'}, "
        f"radiacode {'connected' if rc_was else 'not connected'}")
    if not stop_server():
        return False
    time.sleep(2)  # let the OS release the serial port the old process held
    keep_port = None
    if not args.no_reconnect and (ah_was or args.always_connect):
        try:
            keep_port = pick_port(args.port)
        except SystemExit:
            keep_port = None
    if not start_server(pathlib.Path(args.log), keep_port):
        return False
    ok = True
    if not args.no_reconnect:
        if ah_was or args.always_connect:
            ok = connect_alphahound(args.port, args.wait) and ok
        if rc_was and load_state().get("radiacode_mac"):
            ok = connect_radiacode(None, args.wait) and ok
    return ok


def cmd_ensure(args):
    if not server_up():
        say("ensure: server is down, starting it")
        try:
            keep_port = pick_port(args.port)
        except SystemExit:
            keep_port = None
        if not start_server(pathlib.Path(args.log), keep_port):
            return False
    return connect_alphahound(args.port, args.wait)


def cmd_probe(args):
    code, body = call("POST", "/device/probe", {"command": args.command}, timeout=15)
    if code != 200:
        say(f"probe: HTTP {code} {detail_of(body)}")
        return False
    lines = body.get("lines", [])
    say(f"> {args.command}")
    say("\n".join(lines) if lines else "(no reply)")
    return True


def cmd_rc_connect(args):
    return connect_radiacode(args.mac, args.wait)


def cmd_rc_disconnect(args):
    return disconnect_radiacode()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, help=kw.pop("help", None))
        p.set_defaults(fn=fn)
        return p

    add("status", cmd_status, help="show server and device state")
    p = add("connect", cmd_connect, help="connect the AlphaHound serial port")
    p.add_argument("--port"); p.add_argument("--wait", type=float, default=30, help="seconds to keep retrying")
    add("disconnect", cmd_disconnect, help="disconnect the AlphaHound")
    p = add("restart", cmd_restart, help="restart the server and reconnect what was connected")
    p.add_argument("--port"); p.add_argument("--wait", type=float, default=30)
    p.add_argument("--no-reconnect", action="store_true")
    p.add_argument("--always-connect", action="store_true", help="connect the AlphaHound even if it was not before")
    p.add_argument("--log", default=str(DEFAULT_LOG))
    p = add("ensure", cmd_ensure, help="make sure the server is up and the AlphaHound connected")
    p.add_argument("--port"); p.add_argument("--wait", type=float, default=30); p.add_argument("--log", default=str(DEFAULT_LOG))
    p = add("probe", cmd_probe, help="send a read-only device command and print the raw reply")
    p.add_argument("command", choices=["D", "DA", "DB", "P"])
    p = add("rc-connect", cmd_rc_connect, help="connect the Radiacode over Bluetooth")
    p.add_argument("--mac"); p.add_argument("--wait", type=float, default=30)
    add("rc-disconnect", cmd_rc_disconnect, help="disconnect the Radiacode")

    args = parser.parse_args(argv)
    return 0 if args.fn(args) else 1


if __name__ == "__main__":
    sys.exit(main())
