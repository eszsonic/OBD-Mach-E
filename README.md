# OBD-Mach-E

Research notes and a **read-only diagnostic probe** for the Ford Mustang Mach-E, written for a 2025
car that shows a single grey power-limit bar ("jail bar") on the cluster. The probe runs on a Windows
laptop (Python), talks to the car through a Vgate vLinker MC+ Bluetooth OBD adapter, reads the fault
memory and the battery/inverter quantities that drive the limiter, and writes them to CSV so the bar
can be explained with measurements instead of guesses.

It never writes to the vehicle: no fault clearing, no configuration changes, no routines.

---

## 1. The short answer about the bar

The grey bars at the right end of the power gauge are power the car is withholding, and bars from
different limiters add up. Owner measurements on 2021–2024 cars (sources in `docs/`) give, for a
**single bar with no wrench or warning**, this ranking:

| Rank | Cause | Evidence | How to test without any tool |
|---|---|---|---|
| 1 | Displayed state of charge at or below ~74 % | One bar appears there and stays until you charge past it | Charge above 80 % and look again |
| 2 | Battery pack below ~15 °C / 60 °F | Typical after a night outdoors at 10–15 °C; the bar lasts all day | Set a departure time (warms the pack), check right after |
| 3 | Stale limiter state | Random single bar, clears on restart | Power off, lock, wait 3 minutes, restart |
| 4 | A real fault (contactors / HV junction box, BECM state-of-health error) | Shows **many** bars, a wrench or turtle, and stores DTCs | If the bar survives tests 1–3, run `diagnose` below |

Those thresholds are community-measured, not Ford specifications. The tool exists to measure.

---

## 2. What you need

* Windows 10/11 laptop with Bluetooth (classic Bluetooth, not BLE-only) and Python 3.10 or newer
  (`winget install Python.Python.3.12` or python.org).
* Vgate vLinker MC+ (Bluetooth). Other ELM327/STN adapters that expose a COM port should also work.
* The car in **Ready** (foot on brake, press Start). In accessory mode the battery modules sleep.
* Optional but recommended: FORScan (free licence is enough for reading) as a second opinion.

---

## 3. Install

```powershell
git clone https://github.com/eszsonic/OBD-Mach-E.git
cd OBD-Mach-E
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest -q          # offline self-test: decodes 2,508 real Mach-E responses; takes ~15 s
```

`pip install -e .` creates the `mache-obd` command. `python -m mache_obd` is equivalent.

---

## 4. Pair the adapter and find the COM port

1. Plug the adapter into the OBD socket (under the dash, left of the steering column). Put the car
   in Ready.
2. Windows *Settings → Bluetooth & devices → Add device → Bluetooth*. Choose **`vLinker MC-Android`**
   (not the BLE name), PIN **1234**.
3. *Bluetooth & devices → Devices → More Bluetooth settings → COM Ports*. Note the **Outgoing**
   port, e.g. `COM5`. Or run:

```powershell
mache-obd ports
COM5     Standard Serial over Bluetooth link (COM5)  [BTHENUM\...]
```

4. Check the link:

```powershell
mache-obd --port COM5 info
ATI      ELM327 v2.3
AT@1     OBDII to RS232 Interpreter
STI      STN2255 v5.x.x
voltage  14.2V
```

With the car in Ready the voltage should read 13.5–15 V (DC-DC converter running). About 12.4 V
means the car is not actually in Ready.

Full adapter notes and a troubleshooting table: `docs/04_adapter_vlinker_mcplus_windows.md`.

---

## 5. Commands

All commands take the global options `--port COMx`, `--baud` (ignored over Bluetooth),
`--addressing 11|29`, `--sim FILE` (run against recorded data instead of a car), `-v`/`-vv` (log
adapter traffic).

### `scan` — which modules answer

```powershell
mache-obd --port COM5 scan
  BECM    7E4 answers   Battery Energy Control Module (HV battery BMS)
  SOBDMC  7E6 answers   Secondary OBD Control Module C (rear/primary motor inverter, thermal)
  SOBDMB  7E7 answers   Secondary OBD Control Module B (front/secondary motor inverter)
  PCM     7E0 answers   Powertrain Control Module
  BCM     726 answers   Body Control Module
  IPC     720 -         Instrument Panel Cluster
  ...
```

Modules marked `-` either sleep, sit on the other diagnostic CAN pair (cluster, SYNC), or use a
different address on this model year. **If the BECM shows `-` on the 2025 car**, run in order:

```powershell
mache-obd --port COM5 scan --range 700-7F7        # brute-force every 11-bit id (~1 min)
mache-obd --port COM5 --addressing 29 scan        # 29-bit addressing
mache-obd --port COM5 sweep --module BECM         # which DIDs the module answers
```

and confirm with FORScan, which knows Ford's current module table. Then edit `data/modules.json`.

### `dtc` — fault memory

```powershell
mache-obd --port COM5 dtc
BECM    availability mask 0x8F: 0 DTC(s)
SOBDMC  availability mask 0x8F: 1 DTC(s)
         P0ADE-00 status=0x09 [testFailed, confirmedDTC]
PCM     availability mask 0x8F: 0 DTC(s)
...
```

Reads UDS service `19 02` from BECM, SOBDMC, SOBDMB, PCM, SOBDM, GWM, DCDC, BCM, OBCC, BECMB.
`--module BECM --module PCM` limits the set; `--mask 09` shows only currently failed/confirmed
codes. Status words: `testFailed` = failing right now, `confirmedDTC` = stored as real,
`pendingDTC` = seen once, `testNotCompleted…` = not yet evaluated this drive.

Any `testFailed`/`confirmedDTC` entry in BECM/SOBDMC/PCM makes "fault" the leading explanation;
take the code list to the dealer. Codes are not cleared by this tool.

### `snapshot` — one reading of the power-limit set

```powershell
mache-obd --port COM5 snapshot
  7E4 4845 HV battery SOC displayed                MACHE_HVBAT_SOC_DISP=71   [8E]
  7E4 4808 HV battery temperature max/min/range/avg MACHE_T_RANGE_MAX=14, MACHE_T_RANGE_MIN=12, ...
  7E4 4815 Maximum discharge power limit (BECM)    MACHE_MAX_DISCH_PWR_LIM=63   [FC]
  7E4 48FB HV battery charge power limit           MACHE_HVBAT_CHG_PWR_LIM=119.1   [04A7]
  7E4 4840 Minimum cell/module voltage             MACHE_HVBAT_MIN_MOD_V=3.676   [0E5C]
  7E6 4824 Primary (rear) inverter temperature     MACHE_PRI_MOTOR_INV_T=19   [0013]
  7E6 48E0 HV battery thermal operation mode       MACHE_HVBAT_THERMAL_OP_MODE=HEAT   [0F]
  726 402A 12 V battery voltage                    MACHE_12V_V=14.3   [A6]
  ...
```

The bracketed hex is the raw payload, kept so a wrong scale can be re-decoded later. Lines ending
in `-- NO DATA` or `-- NRC 0x31 (requestOutOfRange)` mean the module does not serve that DID on
this car; that is information, not an error. The full list of what is read is
`POWER_LIMIT_SET` in `src/mache_obd/probe.py`; the meaning of each DID is in
`docs/02_vehicle_network_and_dids.md`.

### `diagnose` — DTCs + snapshot + assessment

```powershell
mache-obd --port COM5 diagnose
== DTCs
  BECM    0 DTC(s)
  SOBDMC  0 DTC(s)
  ...
== Snapshot
  (as above)
== Assessment (heuristic, community thresholds)
  * No DTCs in powertrain/HV modules -> the bar is most likely a normal operating limiter, not a fault.
  * SOC 71 % <= ~74 % -> ONE limiter bar is expected from state of charge alone (community threshold).
  * Pack min temperature 12 C (< ~15 C / 60 F) -> ONE bar is commonly reported from pack temperature alone.
  * BECM maximum discharge power limit DID 4815 = 63.00 ...
  * Cell/module voltage: min 3.676 V, avg 3.681 V, delta 5 mV -> balanced.
```

The assessment ranks hypotheses; it does not prove them. Two matching explanations (as above)
mean the bar is over-determined and only the logging protocol can tell which one is active.

### `log` — record to CSV while you drive

```powershell
mache-obd --port COM5 log --out logs\2026-11-12_cold_soak.csv --period 1
```

One row per second (one column per decoded signal, `t_unix` and `t_iso` first). Stop with Ctrl-C
or `--duration 1800`. Over Bluetooth a full set takes 2–3 s; if you need true 1 Hz, shorten
`POWER_LIMIT_SET`. Film the cluster with the laptop clock in frame so bar counts can be aligned
with rows. Suggested runs (details in `docs/03_software_plan.md` §5):

1. SOC sweep with a warm pack (start >85 % after a preconditioned departure).
2. Cold soak at >80 % SOC, no preconditioning.
3. Same conditions as 2 but with a preconditioned departure.
4. Key-cycle test whenever a bar is present at >74 % SOC and pack >15 °C.

Plot `MACHE_MAX_DISCH_PWR_LIM`, `MACHE_HVBAT_SOC_DISP`, `MACHE_T_RANGE_MIN` against the bar count.

### `sweep` — discover DIDs

```powershell
mache-obd --port COM5 sweep --module BECM --range 4800-49FF
  4800 len=  1 43  MACHE_HVBAT_T
  4801 len=  2 BC16  MACHE_HVBAT_SOC
  4802 len=  4 A1000000
  ...
```

Lists every DID the module answers in the given hex ranges, with the known signal name where the
table has one. Use it when the car disagrees with the table (model-year change) or to look for new
limiter-related values. A full `0000-FFFF` sweep takes about two hours over Bluetooth.

### Offline mode

```powershell
mache-obd --sim tests\fixtures_obdb.json --sim-year 2024 diagnose
```

Runs the whole pipeline against responses recorded from a 2024 car. Use it to learn the output
format, or to test changes without the car. `--sim-year 2025` reproduces the one 2025 capture in
which the BECM did not answer.

---

## 6. Reading the data: what each quantity tells you

| Signal | Source | Why it matters |
|---|---|---|
| `MACHE_HVBAT_SOC_DISP`, `MACHE_HVBAT_SOC` | BECM 4845 / 4801 | SOC limiter steps (~74, 64, 36, 23, 15 %) |
| `MACHE_T_RANGE_MIN/MAX/AVG`, `MACHE_HVBAT_T` | BECM 4808 / 4800 | Cold (<15 °C) and hot (>45 °C) limiters act on the coldest/hottest module |
| `MACHE_MAX_DISCH_PWR_LIM` | BECM 4815 | The BECM's own discharge cap; should fall when bars appear. Scale unverified on 2024–25 |
| `MACHE_HVBAT_CHG_PWR_LIM` | BECM 48FB | Charge cap; moves with temperature and SOC, a cross-check |
| `MACHE_HVBAT_MIN_MOD_V`, `MACHE_HVBAT_AVG_MOD_V`, `MACHE_HVB_SOC_VARIATION` | BECM 4840 / 4841 / 483E | Cell imbalance; a weak group caps power |
| `MACHE_CONTACTOR_V_POS/NEG`, `MACHE_HVBAT_V` | BECM 4805 / 4806 / 480D | Contactor and junction-box health (the known hard-fault cause) |
| `MACHE_HVBAT_SOH`, `MACHE_BAT_CAP`, `MACHE_HVBAT_AGE` | BECM 490C / 485C / 4810 | Health; a 2025 car should be near 100 % |
| `MACHE_PRI/SEC_MOTOR_INV_T`, `..._COIL_T` | SOBDMC 4824 / 481F, SOBDMB 481E / 4820 | Drive-unit thermal derate |
| `MACHE_HVBAT_THERMAL_OP_MODE`, `MACHE_COOLANT_HTR_*` | SOBDMC 48E0 / 48DF / 48DE | Whether the car is heating or cooling the pack right now |
| `MACHE_12V_V/SOC/A` | BCM 402A / 4028 / 402B | A weak 12 V system causes spurious module behaviour |
| `MACHE_VSS_HD`, `MACHE_ACC_POS` | PCM 1505 / 032B | Speed limiter steps start at ~73 mph; pedal for the 5-second cap |

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ports` shows nothing | Paired the BLE name, or no SPP profile | Remove the device, pair `vLinker MC-Android`; try *Devices and Printers → Add a device* |
| `info` hangs or `did not return OK` | Another program holds the port; adapter asleep | Close FORScan/Car Scanner; unplug and replug the adapter |
| `scan` finds nothing but `info` is fine | Car not in Ready | Press Start with the brake pressed; re-run |
| BECM silent, others answer | Model-year addressing (seen in one 2025 capture) | `scan --range 700-7F7`, `--addressing 29`, FORScan; edit `data/modules.json` |
| `CAN ERROR` on every request | Wrong protocol or bus | Run with `-vv` and check `ATSP6` was accepted; try `--addressing 29` |
| Values freeze, `STOPPED`, `BUFFER FULL` | Bluetooth back-pressure | Larger `--period`, shorter `POWER_LIMIT_SET`, keep the laptop near the port |
| Decoded value looks absurd | Scale unverified for this year | Compare the raw hex with FORScan's value for the same PID and correct the CSV row |

---

## 8. Repository map

| Path | Content |
|---|---|
| `docs/01_power_limit_findings.md` | What the bar means, cause catalogue with thresholds, ranked hypotheses, owner questions |
| `docs/02_vehicle_network_and_dids.md` | OBD pins, gateway, module addresses, DID table, ELM command sequence, 2025 caveat |
| `docs/03_software_plan.md` | Alternatives considered, architecture, work plan, experimental protocol, risks |
| `docs/04_adapter_vlinker_mcplus_windows.md` | Pairing, COM port, verification, adapter troubleshooting |
| `docs/sources.md` | Everything consulted |
| `data/mache_signals.csv` | 188 decoded signals (OBDb, CC BY-SA 4.0) |
| `data/modules.json` | 45 module addresses and buses (mme-record, MIT) |
| `src/mache_obd/` | Driver, UDS/DTC parsing, decoder, probe/diagnose, simulator, CLI |
| `tests/` | 2,508 real-car response fixtures and protocol/pipeline tests |
| `CLAUDE.md` | Conventions for AI-assisted development in this repo |

---

## 9. Status and limitations

* Decoder, protocol layer and CLI are tested offline against real responses from 2021–2026 cars.
  **Nothing has yet been run against a physical car or the vLinker MC+**; sections 4–5 describe
  the first on-car steps.
* The BECM discharge-limit scaling (DID 4815) is unverified for 2024–25 cars.
* Limiter thresholds come from owner forums, not Ford.
* Only the diagnostic (HS) CAN pair is used; cluster and SYNC data would need MS-CAN switching,
  which is unverified on this adapter and not needed here.

## 10. Safety and licences

Read-only by construction (no UDS services 0x14, 0x2E, 0x31, 0x27, 0x10 03). Do not operate the
laptop while driving; log from the passenger seat or while parked. Code is MIT; `data/mache_signals.csv`
and `tests/fixtures_obdb.json` derive from the OBDb project and stay CC BY-SA 4.0
(`data/ATTRIBUTION.md`).
