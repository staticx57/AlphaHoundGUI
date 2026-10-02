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

## Display replica and the device's mode slots

The details panel reproduces the 128x128 OLED (`static/js/device_screen.js`, rendered at 4x with a faint pixel grid), following RadView's
[AB+G user guide](https://www.radviewdetection.com/s/AlphaHoundABG.pdf) and [product page](https://www.radviewdetection.com/abg).

**The device does not cycle through all its modes.** It has four mode *slots* (M1-M4, filled in its Mode Selection menu from the 11 or so
modes), and its buttons, a shake, and the serial `E` / `Q` commands step through those four slots. The replica models exactly that: four
slots, a current slot, arrows that press E/Q on the device and advance the slot.

**There is no telemetry for it.** Tested on the AB+G (2026-10-02): pressing `E` twelve times on the raw port produced no text line and no change
in the dose stream's cadence or scale, and the values returned by `K` only jitter (live noise statistics). The device does not report which slot
or mode it is on, what the slots hold, button presses or shakes, battery level, brightness, the light-tight sensor, or the accelerometer. So the replica cannot read the
device's mode: set the slot and its mode once to match the device and keep stepping with the GUI arrows; a physical button press or a shake is invisible to the app.

Built from the data the link carries: ABY Spark (4), ABY AVG (3), Rolling (1, alpha + beta only, as in the guide), LP Spark (2),
Gamma Spectroscopy (9), Spectrogram (10), Analog Gauge (11), Sleep / Power Saver (12, large dose digits). Shown as unavailable: 2D and 3D AB spectroscopy (5, 6: need
alpha/beta pulse heights), Radon (7: computed on the device) and G-Force (13: accelerometer). The product page lists modes 1-7 and 9-12 (there is no Mode 8); the guide adds
G-Force and the Sleep mode. The top-bar mark follows the guide: a check when the mode uses the alpha/beta scintillator and it reports, an X otherwise.

## Firmware differences

The December 2025 notes (`ALPHAHOUND_SERIAL_COMMANDS.md`) describe an older firmware: `P` answered `UB=C`, `L` an activity threshold, no unprompted dose stream,
and `D`/`DA`/`DB` on the uRem/h scale. The firmware measured on 2026-10-02 streams the dose by itself, answers `P` with the `CPS:` line, answers `L` with a
temperature calibration table, and replies to `D`/`DA`/`DB` about 10x larger than the stream. `D`, `DA` and `DB` agree with each other within noise on both.
The driver therefore decides at run time: with a stream it never sends `DB`; without one it falls back to `DB` polling.

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

Server options for unattended use (a server started by `devctl restart` or `ensure` enables the first three when it
knows the port): `ALPHAHOUND_AUTOCONNECT_PORT=COM8` connects at startup (retrying while the port is busy),
`ALPHAHOUND_AUTORECONNECT=1` runs a watchdog that reconnects after a USB drop (seen once in testing: `ClearCommError ... The device does not
recognize the command`) or when the device goes silent for 20 s, and implies `ALPHAHOUND_KEEP_CONNECTED=1`, which keeps the device when the last
browser tab closes. A deliberate Disconnect (the button, `devctl disconnect`) is respected by the watchdog until the next Connect.
`GET /device/health` shows the link state (data age, last error, whether it was disconnected on purpose) and `devctl status` prints it.
Old note kept for reference: `ALPHAHOUND_AUTOCONNECT_PORT=COM8` connects at startup (retrying while the port is busy) and
`ALPHAHOUND_KEEP_CONNECTED=1` keeps the device when the last browser tab closes (a server started by `devctl restart` has it set).
The server log of a `devctl`-started server is `%TEMP%\alphahound_server.log`.
