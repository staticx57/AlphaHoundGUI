# AlphaHound serial protocol (as observed) and remote control

What the AB+G does on its USB serial port (115200 8N1, COM port, e.g. `COM8`), as measured with
`backend/tools/devctl.py probe` and a passive read of the port (2026-10-02, AB+G, firmware not reported).
Nothing here is vendor documentation: RadView does not publish the protocol. The manufacturer's AlphaView web
page ([alphaview](https://www.radviewdetection.com/alphaview)) and the third-party driver
([NuclearGeekETH/AlphaHound](https://github.com/NuclearGeekETH/AlphaHound)) were used as references.

## Device to host

| Line | Meaning |
|---|---|
| bare number, ~5 per second, unprompted | dose rate stream, uRem/h scale (noisy: individual values 45-88 around a mean of ~66 in the test) |
| `CPS:<gamma>,<beta>,<alpha>,<dose>` | reply to `P`. Rates are counts per second. The 4th field is on the **nSv/h** scale (about 10x the stream: 707 against 70.7 uRem/h) |
| single number | reply to `D`, `DA` or `DB`: also ~10x the stream (nSv/h scale), a smoothed value |
| `Temp:<C>`, `CompFactor:<f>`, `Comp`, then 1024 `count,energy` lines | reply to `G` (gamma spectrum). Temperature and compensation factor are reported only here |

Older firmware (as in the third-party driver's capture) did not stream, and `D`/`DA`/`DB` replied on the stream's scale.
The driver therefore treats `DB` polling as a fallback: if no bare number arrives within 3 s of connecting, it polls `DB`;
otherwise it uses the stream and never sends `DB`. Mixing the two was a bug: every `DB` reply briefly put a 10x spike in the
real-time dose.

## Host to device

| Command | Effect |
|---|---|
| `P` | per-channel CPS line (above). Polled once a second, never within 0.5 s of `DB` |
| `G` | gamma spectrum download (1024 channels, device energy axis 10 keV to ~7.4 MeV). Requested once after connecting |
| `W` | clear the device spectrum |
| `E` / `Q` | next / previous display mode |
| `D`, `DA`, `DB` | dose (see above). Allowed through `POST /device/probe` |
| `A`, `B`, `RA`, `RB`, `SpecA`, `SpecB`, `COUNT`, `ALL`, `?` | no reply seen; effect unknown, so the probe endpoint refuses them |

`GA` and `GB` return the same gamma spectrum as `G`: there is no separate alpha or beta spectrum on the serial link.

## What the app exposes

`GET /device/status` (adds `cps` and `dose_rate_avg`), `GET /device/cps`, `GET /device/details`, `GET /device/dose/log` and
`/device/dose/log.csv` (one averaged row per second, kept in `backend/data/dose_log.jsonl` across restarts), `POST /device/dose/log/clear`,
`POST /device/probe {"command": "D|DA|DB|P"}`, and the dose WebSocket `/ws/dose` (`{"dose_rate", "dose_rate_avg", "cps"}`).
Connecting a busy port returns 409 with a readable message. An AlphaHound acquisition also records the mean gamma / beta / alpha CPS and
peak total CPS (`channels` in the acquisition status, `AcquisitionInfo` in the N42).

## Display replica

The details panel reproduces the 128x128 OLED (`static/js/device_screen.js`). The product page lists 11 modes (1-7 and 9-12; there is
no Mode 8). Built from what the link carries: 1 Rolling Graph, 2 Low Power Sparkles, 3 Average Counts, 4 ABY Split Sparkles,
9 Gamma Spectroscopy, 10 Spectrogram (from successive spectra), 11 Analog Gauge, 12 Power Saver. Not reproducible from serial data and shown as
such: 5 and 6 (alpha/beta spectroscopy needs per-event pulse heights, not rates) and 7 (radon approximation, computed on the device). The device
does not report its current mode or button presses, so the replica keeps its own mode.

## Managing it without a browser

`backend/tools/devctl.py` (needs only the Python standard library):

```
python backend/tools/devctl.py status
python backend/tools/devctl.py connect [--port COM8]      # retries while the port is busy; remembers the port
python backend/tools/devctl.py disconnect
python backend/tools/devctl.py restart                     # stop server, start it detached, reconnect what was connected
python backend/tools/devctl.py ensure                      # start the server if down, then connect the AlphaHound
python backend/tools/devctl.py probe P
python backend/tools/devctl.py rc-connect --mac AA:BB:CC:DD:EE:FF   # Radiacode over Bluetooth
```

Server options for unattended use: `ALPHAHOUND_AUTOCONNECT_PORT=COM8` connects at startup (retrying while the port is busy) and
`ALPHAHOUND_KEEP_CONNECTED=1` keeps the device when the last browser tab closes (a server started by `devctl restart` has it set).
The server log of a `devctl`-started server is `%TEMP%\alphahound_server.log`.
