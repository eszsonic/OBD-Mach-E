# Mach-E diagnostic network, modules and data identifiers

## 1. What the OBD-II connector gives you

* Pins 6/14 ("Diag1", conventionally HS-CAN) and pins 3/11 ("Diag2", conventionally MS-CAN) are the
  only two CAN pairs on the connector. **Both run at 500 kbit/s** and **both terminate at the
  Gateway Module (GWM)**, which routes diagnostic requests to the seven internal buses
  (HS1–HS4, MS, CAN-FD, powertrain) and point-to-point Ethernet links
  ([pinout thread][pinout], [PID thread, page 2][pids2]).
* Consequence: there is **no broadcast traffic to sniff**. Everything is request/response UDS
  (ISO 14229 over ISO-TP 15765-2). An ELM327-class adapter is therefore adequate; a passive CAN
  logger is not useful here.
* Modules relevant to power limitation all answer on the pins-6/14 side with 11-bit identifiers
  (request `0x7xx`, response `request + 8`). MS-CAN (pins 3/11) is only needed for the cluster
  (IPC `720`) and SYNC (APIM `7D0`), which this project does not require.

## 2. Modules that matter for "why is power limited"

| Module | Req → Resp | Role | Why it matters |
|---|---|---|---|
| BECM | `7E4 → 7EC` | Battery Energy Control Module (pack BMS) | Owns SOC, pack temperatures, cell voltages, contactor voltages, **discharge/charge power limits**, SOH |
| SOBDMC | `7E6 → 7EE` | Secondary OBD module C (rear/primary drive unit) | Inverter and motor-coil temperature, torque, rpm, pack thermal mode, coolant heater |
| SOBDMB | `7E7 → 7EF` | Secondary OBD module B (front/secondary drive unit) | Same for the front motor (AWD) |
| PCM | `7E0 → 7E8` | Powertrain Control Module | Torque arbitration, speed, pedal; standard OBD mode 01 lives here |
| SOBDM | `7E2 → 7EA` | On-board AC charger | Charger status; shares HV current/voltage DIDs |
| OBCC | `6F5 → 6FD` | DC fast-charge control | DCFC limits |
| DCDC | `746 → 74E` | 12 V DC-DC converter | 12 V supply health |
| BCM | `726 → 72E` | Body Control Module | 12 V battery SOC/voltage/current (12 V problems create spurious limits) |
| GWM | `716 → 71E` | Gateway | Routing; VIN |

Full list of 45 module addresses: `data/modules.json` (from mme-record, which was validated on a
2022 car).

## 3. Data identifiers (UDS service `0x22`)

`data/mache_signals.csv` holds 188 signals from the community-maintained OBDb Mach-E signal set
(real-car captures, CC BY-SA 4.0). The subset used by the `snapshot`/`log`/`diagnose` commands:

| Req | DID | Signal | Decode (payload after `62 DID`) | Notes |
|---|---|---|---|---|
| 7E4 | 4845 | SOC displayed | `A / 2` % | What the cluster shows |
| 7E4 | 4801 | SOC high-res | `AB / 500` % | |
| 7E4 | 4800 | Pack temperature | `A − 50` °C | |
| 7E4 | 4808 | Pack T max / min / range / avg | `A−50, B−50, C−50, D−50` °C | **Min** is the limiter-relevant one |
| 7E4 | 4846 | Coolant inlet T | `A − 50` °C | |
| 7E4 | **4815** | **Maximum discharge power limit** | `A × 0.25` kW (saturates at 63.75) | Captured 61–63 on 2024 cars; scaling marked "to 2023 / from 2025" by OBDb, i.e. unverified on 2024–25 → first thing to validate |
| 7E4 | 4852 | Battery discharge power limit | `A` kW | OBDb "debug" (unverified) |
| 7E4 | 48FB | Charge power limit | `AB / 10` kW | Known to move with temperature/SOC; useful cross-check of the limiter logic |
| 7E4 | 480D / 48F9 | Pack voltage / current | `AB/100` V, `signed AB/10` A | Power = V·I |
| 7E4 | 4840 / 4841 | Min / avg module voltage | `AB / 1000` V | Spread = imbalance |
| 7E4 | 483E | SOC spread across modules | `AB / 1000` % | |
| 7E4 | 4805 / 4806 | Contactor voltage + / − | `AB/100`, `AB/10` V | Contactor (HVBJB) health |
| 7E4 | 490C | State of health | `A / 2` % | `FF` = not available |
| 7E4 | 485C / 4810 | Capacity (Ah) / age (h) | `AB/10`, `AB×3.6` | |
| 7E6 | 4824 / 481F | Rear inverter / coil T | `signed AB` °C | |
| 7E6 | 1E2C / 481C | Rear motor rpm / torque | `signed AB`, `signed AB/10` N·m | |
| 7E6 | 48E0 | Pack thermal mode | enum: Off, Equalize, Coolant flow, fan, moderate, maximum, Heat | Tells you whether the car *thinks* the pack needs heating/cooling |
| 7E6 | 48DF / 48DE | Coolant heater mode / power | enum / `AB/1000` kW | |
| 7E7 | 481E / 4820 / 4821 / 481A | Front inverter T / coil T / rpm / torque | as above | |
| 726 | 4028 / 402A / 402B | 12 V SOC / V / A | `A` %, `A/20+6` V, `A−127` A | |
| 7E0 | 1505 / 032B | Speed / pedal | `AB/128` km/h, `A/2` % | |

### Model-year caveat that drives the software design

In the OBDb capture set, 2024 and 2026 cars answer every BECM (`7E4`) and SOBDM (`7E2`) DID above,
but the **one 2025 car in the set answered none of them** (all marked unsupported), while still
answering PCM, SOBDMC, SOBDMB, BCM and ABS. The likely explanations are (a) the capture was taken
with the car not in Ready so the BECM was asleep, or (b) a 2025-specific addressing change. The
tool therefore (1) pings every known module first, (2) can brute-force the 11-bit range, (3) can
switch to 29-bit addressing (`18DA xx F1`), and (4) can sweep DID ranges on any module. If the BECM
still does not answer, FORScan (which carries Ford's own module database) is the fastest way to
learn where the 2025 BECM lives, and the result can be fed back into `data/modules.json`.

## 4. Services used, and the ones deliberately not used

* `22 xx xx` ReadDataByIdentifier — all live values.
* `19 02 FF` ReadDTCInformation / reportDTCByStatusMask — fault memory with status byte
  (`testFailed`, `confirmedDTC`, `pendingDTC`, …). DTC bytes decode to Ford's `P0ADE-00` style.
* `3E 00` TesterPresent — module discovery.
* **Not used**: `14` ClearDiagnosticInformation, `2E` WriteDataByIdentifier, `31` RoutineControl,
  `10 03`/`27` extended session & security access. The tool is read-only by construction.

## 5. ELM327 command sequence (what the driver sends)

```
ATZ  ATE0  ATL0  ATS0  ATH1  ATCAF1  ATAT1  ATST64  ATSP6      # 11-bit 500 kbit, headers on, ISO-TP on
ATSH7E4  ATCRA7EC  ATFCSH7E4  ATFCSD300000  ATFCSM1            # talk to BECM, accept 7EC, FC frames
224808                                                         # read pack temperature DID
-> 7EC0762480844433244                                         # 7EC | PCI 07 | 62 48 08 | 44 43 32 44
```
Multi-frame answers arrive as `7EC10xx…`, `7EC21…`, `7EC22…` lines and are reassembled in software
(`elm327.isotp_join`). For 29-bit: `ATSP7`, `ATCP18`, `ATSHDA xx F1`, `ATCRA18DAF1xx`.

## 6. MS-CAN (only if you later want IPC/APIM data)

OBDLink adapters switch with STN commands `STP53` + `STPBR500000` and back with `STP33`
([PID thread][pids2]). The vLinker MC+ advertises MS-CAN support and STN-command compatibility, but
one reseller states it has no HS/MS switch and relies on app-side switching; whether `STP53` works
on it is **unverified**. Not needed for the power-limit question.

[pinout]: https://www.macheforum.com/site/threads/odbii-connector-schematic-pinout.11857/
[pids2]: https://www.macheforum.com/site/threads/ford-mustang-mach-e-extended-pids-for-torque-project.7427/page-2
