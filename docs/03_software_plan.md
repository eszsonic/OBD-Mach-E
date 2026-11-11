# Software plan: Windows / Python probe for a 2025 Mach-E over a vLinker MC+

## 1. Objective and success criteria

Determine, with data rather than guesswork, which limiter is drawing the grey bar:

1. **Fault vs. operating limiter** — read the DTC memory of BECM, SOBDMC, SOBDMB, PCM, SOBDM, DCDC,
   BCM, GWM. Any `testFailed`/`confirmedDTC` entry ends the question in favour of "fault".
2. **Which operating limiter** — log SOC, pack min/max temperature, BECM discharge-power limit,
   cell spread, contactor voltages, inverter/motor temperatures at ~1 Hz while the number of bars is
   recorded (phone video of the cluster with the laptop clock in frame), across conditions designed
   to separate the hypotheses (section 5).
3. Deliverable per session: a CSV plus a short report from `diagnose`.

## 2. Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. FORScan (Windows, free licence for reading)** | Ford module database incl. 2025; reads DTCs from *all* modules in minutes; live PIDs with Ford names; works with the vLinker MC+ over Bluetooth (user reports) | Closed; logging/analysis clumsy; cannot script experiments; occasional Bluetooth trouble on Windows | **Do first** (15-minute DTC sweep). It also answers the 2025 BECM-address question immediately |
| **B. Own Python tool on the ELM327/STN adapter (this repo)** | Scriptable, reproducible logging; decoder validated against 2,500 real-car responses; read-only by construction; runs on the hardware you own | ELM throughput ≈ 10–20 requests/s over Bluetooth; adapter/Windows COM quirks; 2025 DID support unverified | **Primary instrument** for the correlation study |
| C. python-can + udsoncan/can-isotp on a real CAN interface (PCAN-USB, Kvaser, or Raspberry Pi + PiCAN as in mme-record) | Proper ISO-TP, higher rate, two channels (HS+MS) | New hardware; mme-record is Linux/SocketCAN | Upgrade path if ELM rate limits the study |
| D. python-OBD library | Easy mode-01 reads | Single header, no DTC-by-status, weak multi-frame handling | Rejected |
| E. Phone apps (Car Scanner ELM OBD2 with its Mach-E profile; Torque Pro + the forum CSV) | Zero code | No experiment control, limited export | Useful sanity check only |

Recommendation: **A then B**. If B cannot reach the BECM on the 2025 car, use A to find the address
and update `data/modules.json`.

## 3. Architecture (implemented)

```
src/mache_obd/
  elm327.py   SerialTransport (pyserial) + Elm327 driver: AT init, target selection, ISO-TP reassembly,
              29-bit option, retries on NRC 0x78
  uds.py      0x22 / 0x19 02 / 0x3E builders, positive/negative response parsing, Ford DTC strings
  signals.py  loads data/mache_signals.csv, bit-field extraction and scaling, enums
  probe.py    Session: module ping/scan, DTC sweep, power-limit snapshot, DID sweep, CSV logger,
              diagnose() heuristics with the community thresholds
  sim.py      ELM emulator fed from tests/fixtures_obdb.json (offline dry runs)
  cli.py      ports | info | scan | dtc | snapshot | diagnose | log | sweep
data/         signal table (OBDb, CC BY-SA 4.0), module map (mme-record, MIT)
tests/        2,508 real-response fixtures + protocol/pipeline tests
```

Design choices worth noting:

* Headers on + auto-formatting on: the adapter handles flow control, the host sees every frame and
  reassembles, which makes 11-bit, 29-bit and non-standard id pairs uniform.
* The decoder is table-driven; adding a DID is a CSV row.
* Verification status from OBDb is carried in the table (`filter` column) so the tool can say
  "unverified on 2025" instead of silently trusting a scale.
* Read-only: no clear/write/routine services exist in the code.

## 4. Work plan

| Phase | Content | Acceptance |
|---|---|---|
| 0 (done) | Research; DID/module tables; driver; decoder; simulator; tests | `pytest` green; `--sim` dry run produces a report |
| 1 Bench | Pair adapter on Windows, `ports`, `info` (expect `ELM327 v…`, `STN…`, 12–15 V) | Adapter answers `ATI`/`STI`/`ATRV` |
| 2 Reachability | Car in **Ready** (foot on brake, Start). `scan`; if BECM silent → `scan --range 700-7F7`, then `--addressing 29`, then `sweep --module BECM` | BECM answers `3E00`; `22 4845` returns SOC that matches the cluster |
| 3 Validation | `snapshot`; compare SOC, pack T, 12 V with cluster/FordPass; check `4815` behaves (should be ~63.75 saturated at high SOC & warm pack; should fall when bars appear) | Three independent values agree with the cluster |
| 4 DTC sweep | `dtc` (mask FF) and FORScan sweep | Both agree; archive output |
| 5 Correlation study | `log --period 1` through the protocol in section 5 | CSV + video; plot `4815`, SOC, T_min, bar count vs time |
| 6 Analysis & report | Identify the limiter; if fault indicators appear, hand DTCs + logs to the dealer | Written conclusion with data |

## 5. Experimental protocol for the correlation study

Each run: start logging before Ready, keep the cluster on video with the laptop clock visible,
note bar count at each change. One variable per run.

1. **SOC sweep, warm pack**: start at >85 % after a preconditioned departure; drive normally
   until ~60 %. Expect: 0 bars above ~74 %, 1 bar below. `4815` should step at the same time.
2. **Cold soak, high SOC**: car at >80 %, parked outside overnight at <10 °C, no preconditioning.
   Expect 1–2 bars at start that vanish as `T_min` rises above ~15 °C and `48E0` leaves "Heat".
3. **Preconditioned departure**: same SOC and ambient as run 2 but with departure time set.
   Expect 0 bars; confirms temperature attribution.
4. **Key-cycle test**: whenever a bar is present with SOC >74 % and `T_min` >15 °C, power off, lock,
   wait 3 min, restart. If the bar disappears with no change in logged values → stale limiter state.
5. **Post-DCFC** (optional): log from end of a DCFC session for 20 min.

Analysis: bars vs `MACHE_MAX_DISCH_PWR_LIM` (4815), `MACHE_HVBAT_CHG_PWR_LIM` (48FB),
`MACHE_T_RANGE_MIN`, `MACHE_HVBAT_SOC_DISP`; a fault case will show bars that are independent of all
of them and usually a DTC.

## 6. Risks and open questions

* **2025 BECM reachability** (see docs/02 §3). Mitigations built in; FORScan as oracle.
* **Scaling of 4815/4852** is unverified; treat as ordinal until validated against a known event
  (e.g. the 5-second limiter, which must show as a drop).
* **Bluetooth on Windows**: the MC+ pairs as classic SPP ("vLinker MC-Android", PIN 1234); BLE
  profiles do not create a COM port. Windows may create two COM ports (incoming/outgoing); use the
  outgoing one. The adapter sleeps when idle; `ATZ` wakes it.
* **ELM throughput**: ~35 DIDs per snapshot ≈ 2–3 s; fine for a 1 Hz study if the list is trimmed
  (edit `POWER_LIMIT_SET`).
* **Modules sleep** in accessory mode; most tests need the car in Ready. Operate the laptop as a
  passenger or with the car parked.
* **Non-GT cluster**: if the car is not a GT/Rally, there is no bar display to correlate; the study
  then relies on `4815` and measured power (`V·I` at wide-open pedal).
