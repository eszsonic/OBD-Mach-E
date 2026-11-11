# CLAUDE.md — project guide for Claude Code sessions

## What this repository is

A research write-up plus a **read-only Python diagnostic probe** for a 2025 Ford Mustang Mach-E.
The owner sees a single grey power-limit bar ("jail bar") on the cluster and wants to know which
limiter (state of charge, pack temperature, stale state, or a fault) is responsible. The probe talks
UDS (ISO 14229 over ISO-TP) to the car's modules through a Vgate vLinker MC+ Bluetooth adapter
(ELM327/STN command set) from a Windows laptop.

Read `docs/01_power_limit_findings.md` first; it holds the hypotheses and their evidence.
`docs/03_software_plan.md` is the roadmap and the experimental protocol.

## Layout

```
src/mache_obd/
  elm327.py   adapter driver: AT init, target selection, ISO-TP reassembly, expected-prefix filtering
  uds.py      0x22 / 0x19 02 / 0x3E builders and parsers, NRC names, Ford DTC strings (P0ADE-00)
  signals.py  Signal dataclass, CSV loader, bit extraction, OBDb decode semantics (enum, sign, clamp, null)
  probe.py    Session (ping/scan, DTCs, snapshot, sweep, CSV log), POWER_LIMIT_SET, diagnose() heuristics
  sim.py      ELM emulator driven by tests/fixtures_obdb.json (offline dry runs, tests)
  cli.py      argparse CLI; `python -m mache_obd` or the `mache-obd` entry point
data/
  mache_signals.csv   188 signals flattened from OBDb's signal set (CC BY-SA 4.0) — the decoder table
  modules.json        45 module addresses + bus (from mme-record, MIT)
  ATTRIBUTION.md      provenance and licence of every data file
tests/
  fixtures_obdb.json  2,508 real responses captured from 2021–2026 cars (OBDb), incl. 408 multi-frame
  test_signals.py     decodes every fixture through the real reassembly path and compares to OBDb
  test_uds_elm.py     DTC strings, negative responses, ISO-TP join, simulator end-to-end pipeline
docs/                 findings, network/DIDs, software plan, adapter guide, sources
```

## Commands

```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest -q                                            # must stay green (≈15 s, 2,516 tests)
python -m mache_obd --sim tests/fixtures_obdb.json --sim-year 2024 diagnose   # offline dry run
python -m mache_obd --port COM5 diagnose             # on the car (Windows)
```

Tests need no hardware. There is no CI yet; run `pytest` before every commit.

## Hard rules

1. **The tool is read-only. Never add vehicle-writing services**: no `0x14` ClearDiagnosticInformation,
   no `0x2E` WriteDataByIdentifier, no `0x31` RoutineControl, no `0x10 03` extended session,
   no `0x27` security access, no `0x2F` IO control, no as-built changes. If a task seems to need one,
   stop and ask the user.
2. Do not invent DIDs, scalings or thresholds. Every signal row in `data/mache_signals.csv` comes
   from OBDb; every limiter threshold in `probe.diagnose()` and the docs is cited to a forum thread
   and labelled "community-measured". Keep that labelling. New values need a source or an on-car
   measurement recorded in the docs.
3. Keep `data/mache_signals.csv` and `tests/fixtures_obdb.json` under CC BY-SA 4.0 attribution
   (see `data/ATTRIBUTION.md`). Code is MIT.
4. The decoder must keep OBDb semantics (`decode_signal`): enum map → two's complement if signed →
   `raw*mul/div+add` → `None` at `nullmin`/`nullmax` sentinels → clamp to `[min,max]`. The fixture
   test enforces this; do not "fix" a fixture to make a decoder change pass.
5. Do not change `tests/fixtures_obdb.json` by hand. Regenerate it from the OBDb repository
   (`tests/test_cases/*/commands/*.yaml`, service 0x22 only) if you need newer captures.

## How to extend

* **Add a signal / DID**: append a row to `data/mache_signals.csv` (hdr, rax, did hex, id, name,
  bix, len, mul, div, add, signed, unit, min, max, nullmin, nullmax, map JSON, map_desc JSON, dbg,
  filter JSON, desc). If it bears on power limitation, add `(hdr, did, label)` to
  `probe.POWER_LIMIT_SET`. Add a fixture-style test if you have a real response.
* **Add a module**: append to `data/modules.json` (request_id/response_id are 3-hex-digit strings,
  response is request+8 on this platform). Add its name to `probe.DTC_MODULES` if it can set
  power-relevant DTCs.
* **Add a diagnosis rule**: extend `probe.diagnose()`; return plain sentences, state the threshold
  and its provenance, never a certainty.
* **Add a CLI command**: `cli.py` subparsers; keep every command usable with `--sim`.
* **29-bit / other addressing**: `Elm327.set_target` handles 11- and 29-bit; the per-module
  response id lives in `modules.json`, not in code.

## Known caveats to keep in mind

* OBDb's single 2025 capture answered no BECM (`7E4`) or SOBDM (`7E2`) DIDs; 2024 and 2026 cars do.
  Until the owner's car is probed, treat BECM reachability on MY2025 as unknown (docs/02 §3).
* DID `4815` (max discharge power limit) scaling is unverified for 2024–25; `4852` is "debug" in OBDb.
* The vLinker MC+ must be paired as classic SPP ("vLinker MC-Android", PIN 1234) to get a COM port.
  Whether its MS-CAN switching (`STP53`) works is unverified; MS-CAN is not needed for this project.
* Nothing in `src/` has run against a real car or adapter yet. When it does, record adapter
  identity (`info`), `scan` results and any deviations in `docs/` and open issues for mismatches.

## Style

Python ≥3.10, standard library plus pyserial only at runtime; type hints; dataclasses; no global
state; logging via `logging`, user output via `print` in `cli.py` only. Keep functions small enough
to test with the simulator. Commit messages: imperative subject, body explains the evidence.
