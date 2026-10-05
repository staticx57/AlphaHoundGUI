# Multi-user plan

Status: proposal, nothing implemented. Written 2026-10-04.

## Where things stand

The server already outlives the browser: an acquisition runs on the server, writes its partial spectrum every minute,
and any page that opens shows it (reload, another tab, another computer on the LAN). Saved runs are listed from the
server's folder, so every viewer sees the same ones. What the code assumes today:

| Assumption | Where | Consequence with several people |
|---|---|---|
| One acquisition at a time, for all devices | `AcquisitionManager` is a singleton | An AlphaHound run and a Radiacode run cannot overlap |
| One driver object per device type | `alphahound_serial.device`, `radiacode_device` | Fine for one instrument of each kind, not two AlphaHounds |
| No login; listens on `0.0.0.0:3200` | `main.py` | Anyone on the network can open the page and use every control |
| Every control is open to every viewer | device and acquisition routes | A second viewer can Stop a run or Clear the device spectrum (wipes the counts) |
| Settings, theme and file history live in the browser | `localStorage`: `analysisSettings`, `fileHistory`, `theme`, `ahScreen*` | Each person and each computer has their own, nothing is shared |
| Each tab polls on its own | status every 2 s, details every 5 s, one dose WebSocket per tab | Load grows with viewers. The analysis is cached per spectrum, so ten viewers cost one analysis, but ten times the requests |
| The AlphaHound is released when the last tab closes | `main.py`, WebSocket cleanup | Harmless now that a running acquisition is exempt |
| Nothing records who did what | everywhere | A run's file does not say who started or stopped it |

## Goal

Several people watch the same instruments at once, from their own computers, without getting in each other's way. One
of them operates at a time; the others can see everything and cannot destroy a run by accident.

## Phases

Each phase stands on its own and can ship separately.

### 1. Many viewers, one operator

- **Push instead of poll.** One server-side broadcast (the existing dose WebSocket, or a second one) carries the
  acquisition state and a spectrum version number. A page fetches the spectrum only when the version changes. Ten
  viewers then cost one message per change, not ten requests every 2 s.
- **A control lock.** Starting an acquisition makes that browser the operator, identified by a random token kept in its
  own storage. Stop, Clear, Display, Connect and Disconnect need the token. Other viewers see the controls greyed out,
  with "Operated from <name/computer>" and a **Take over** button that asks for confirmation and tells the current
  operator.
- **Record who did it.** The start, stop and clear events, with time and operator name, go into the run's N42 metadata
  and a small JSON log beside the saved runs.

### 2. Identity and access

Decide the trust model first (see Decisions below). Then:

- A name per person, entered once and stored in the browser. That's enough at home or in a trusted lab, and it already
  makes the records in phase 1 readable.
- For a shared network, a PIN or password before any control works. Viewing stays open, or also needs it.
- Off the local network: HTTPS and a real login, or keep the server LAN-only and reach it through a VPN. The second is
  far less work and much safer.

### 3. Shared and personal data

- Saved runs gain an owner, a title and notes (a JSON sidecar per run), editable from History.
- Settings move to the server, per person, with the browser copy as a fallback when offline. Thresholds and the
  confidence settings then follow the person, not the computer.
- The browser's file history stays personal: it is a list of what that person opened.

### 4. Several acquisitions and devices at once

- One acquisition manager per connected device, addressed by device id: `/device/{id}/acquisition/...`. An AlphaHound
  and a Radiacode can then record at the same time.
- Device registry instead of module-level singletons, so two AlphaHounds on two ports are possible.
- The UI shows one acquisition panel per device.

This is the largest change and only worth doing if overlapping runs are actually needed.

## Decisions needed

1. **Trust model.** Home network with people you trust, a shared lab network, or access from outside? This decides how
   much of phase 2 is needed.
2. **Taking over.** Can any viewer take control after confirming, or only someone with the PIN?
3. **Concurrent runs.** Is recording on the AlphaHound and the Radiacode at the same time a real need (phase 4)?
4. **Names.** Free text per browser, or a fixed list of people?

## Risks

- Destructive commands from a second viewer (Clear wipes the device's counts) are the main danger today. Phase 1's
  lock removes it and is worth doing even for one person with two tabs open.
- Serial and Bluetooth links have one owner. Every command must keep going through the server's single driver object,
  never directly from a page.
- The push channel must not become the new hang. A slow viewer must never hold up the acquisition: send with a timeout
  and drop viewers that fall behind.
