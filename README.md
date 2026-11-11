# OBD-Mach-E — why is my 2025 Mach-E showing a power-limit bar?

Research notes plus a **read-only Windows/Python probe** that talks UDS to the Mustang Mach-E's
battery, inverter and powertrain modules through a Vgate vLinker MC+ (ELM327/STN-compatible)
Bluetooth adapter. Goal: tell apart an ordinary operating limiter (state of charge, pack
temperature, recent load) from a fault, and log the quantities behind the grey "jail bar".

**Short answer from the research** (details and sources in `docs/01_power_limit_findings.md`):
a single grey bar with no wrench light is, on the evidence available, almost always one of two
operating limiters — displayed SOC at or below ~74 %, or a battery pack below ~15 °C / 60 °F — or a
stale limiter state that a key cycle clears. A genuine fault (contactor / HV junction box, BECM
state-of-health error) shows many bars together with a wrench or "Service Vehicle Soon" and sets
DTCs. Those thresholds are owner-measured, not Ford specifications, which is exactly why the tool
exists: to measure rather than assume.

## Repository layout

| Path | Content |
|---|---|
| `docs/01_power_limit_findings.md` | What the bar means, catalogue of causes with thresholds, ranked hypotheses, questions for the owner |
| `docs/02_vehicle_network_and_dids.md` | OBD pins, gateway, module addresses, the DIDs that matter, ELM command sequence, 2025 caveat |
| `docs/03_software_plan.md` | Alternatives (FORScan, this tool, python-can, python-OBD, phone apps), architecture, work plan, experimental protocol, risks |
| `docs/04_adapter_vlinker_mcplus_windows.md` | Pairing, COM port, verification, troubleshooting |
| `docs/sources.md` | Everything consulted |
| `data/mache_signals.csv` | 188 decoded signals (OBDb, CC BY-SA 4.0) |
| `data/modules.json` | 45 module addresses and buses (mme-record, MIT) |
| `src/mache_obd/` | Driver, UDS/DTC parsing, decoder, probe/diagnose logic, simulator, CLI |
| `tests/` | 2,500 real-car response fixtures + protocol and pipeline tests |

## Quick start (Windows, PowerShell)

```powershell
py -3 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest -q                                   # offline: decoder vs 2,500 real responses

# pair "vLinker MC-Android" (PIN 1234), note the outgoing COM port, put the car in Ready
mache-obd ports
mache-obd --port COM5 info                  # adapter identity, 12 V reading
mache-obd --port COM5 scan                  # which modules answer
mache-obd --port COM5 dtc                   # fault memory of BECM/SOBDMC/SOBDMB/PCM/...
mache-obd --port COM5 diagnose              # DTCs + snapshot + ranked assessment
mache-obd --port COM5 log --out drive1.csv --period 1
mache-obd --port COM5 sweep --module BECM   # discover DIDs if the tables disagree with the car
mache-obd --sim tests/fixtures_obdb.json --sim-year 2024 diagnose   # no car needed
```

If the BECM does not answer on the 2025 car (see `docs/02`, §3): `scan --range 700-7F7`, then
`--addressing 29`, then confirm with FORScan and update `data/modules.json`.

## Status

* Protocol layer, decoder, DTC parsing and CLI are implemented and tested **offline** against
  real responses captured from 2021–2026 cars by the OBDb project and a forum CAN capture.
* **Not yet run against a car or the physical adapter.** Phases 1–6 in `docs/03` describe the
  bench and on-car validation steps and the correlation study.
* The tool never writes to the vehicle: no DTC clearing, no DID writes, no routines, no sessions
  beyond default.

## Licences

Code: MIT. `data/mache_signals.csv` and `tests/fixtures_obdb.json` derive from OBDb and remain
CC BY-SA 4.0 (see `data/ATTRIBUTION.md`).
