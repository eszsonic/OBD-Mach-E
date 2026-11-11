"""High-level probing: module scan, DTC readout, power-limit snapshot, diagnosis heuristics, logging."""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .elm327 import Elm327, ElmError
from .signals import DATA_DIR, Signal, decode_payload, group_by_command, load_signals
from .uds import Dtc, NegativeResponse, UdsError, build_read_dtc_by_status, build_tester_present, check_positive, parse_dtc_by_status

log = logging.getLogger(__name__)

MODULES_JSON = DATA_DIR / "modules.json"


def load_modules(path: str | Path | None = None) -> dict[str, dict]:
    data = json.load(open(path or MODULES_JSON))
    return {m["name"]: m for m in data["modules"]}


# (request id, DID) pairs that bear on "why is power limited", in priority order.
POWER_LIMIT_SET: list[tuple[str, int, str]] = [
    ("7E4", 0x4845, "HV battery SOC displayed"),
    ("7E4", 0x4801, "HV battery SOC (0.002 % resolution)"),
    ("7E4", 0x4800, "HV battery temperature"),
    ("7E4", 0x4808, "HV battery temperature max/min/range/avg"),
    ("7E4", 0x4846, "HV battery coolant inlet temperature"),
    ("7E4", 0x4815, "Maximum discharge power limit (BECM)"),
    ("7E4", 0x4852, "Battery discharge power limit (BECM, unverified)"),
    ("7E4", 0x48FB, "HV battery charge power limit"),
    ("7E4", 0x480D, "HV battery voltage"),
    ("7E4", 0x48F9, "HV battery current"),
    ("7E4", 0x4840, "Minimum cell/module voltage"),
    ("7E4", 0x4841, "Average cell/module voltage"),
    ("7E4", 0x483E, "SOC spread across modules"),
    ("7E4", 0x4805, "Contactor voltage positive"),
    ("7E4", 0x4806, "Contactor voltage negative"),
    ("7E4", 0x490C, "HV battery state of health"),
    ("7E4", 0x485C, "Battery capacity (Ah)"),
    ("7E4", 0x4810, "HV battery age"),
    ("7E6", 0x4824, "Primary (rear) inverter temperature"),
    ("7E6", 0x481F, "Primary (rear) motor coil temperature"),
    ("7E6", 0x1E2C, "Primary motor speed"),
    ("7E6", 0x481C, "Primary motor torque"),
    ("7E6", 0x48E0, "HV battery thermal operation mode"),
    ("7E6", 0x48DF, "Coolant heater mode"),
    ("7E6", 0x48DE, "Coolant heater power"),
    ("7E6", 0xDD05, "Outside temperature"),
    ("7E7", 0x481E, "Secondary (front) inverter temperature"),
    ("7E7", 0x4820, "Secondary (front) motor coil temperature"),
    ("7E7", 0x4821, "Secondary motor speed"),
    ("7E7", 0x481A, "Secondary motor torque"),
    ("726", 0x4028, "12 V battery SOC"),
    ("726", 0x402A, "12 V battery voltage"),
    ("726", 0x402B, "12 V battery current"),
    ("746", 0x483D, "DC-DC converter enabled"),
    ("7E0", 0x1505, "Vehicle speed (high resolution)"),
    ("7E0", 0x032B, "Accelerator pedal position"),
]

# Modules whose DTCs can explain reduced motive power.
DTC_MODULES = ["BECM", "SOBDMC", "SOBDMB", "PCM", "SOBDM", "GWM", "DCDC", "BCM", "OBCC", "BECMB"]


@dataclass
class Reading:
    hdr: str
    did: int
    label: str
    ok: bool
    raw_hex: str = ""
    values: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class Session:
    elm: Elm327
    signals: list[Signal] = field(default_factory=load_signals)
    modules: dict[str, dict] = field(default_factory=load_modules)

    def __post_init__(self):
        self.by_cmd = group_by_command(self.signals)

    # ---- module presence ---------------------------------------------------------------
    def ping(self, req_id: int, resp_id: int | None = None) -> bool:
        try:
            self.elm.set_target(req_id, resp_id)
            data = self.elm.send_receive(build_tester_present(), timeout=1.0)
            check_positive(data, 0x3E)
            return True
        except NegativeResponse:
            return True      # it answered, even if it dislikes 3E 00
        except (ElmError, UdsError):
            return False

    def scan_known_modules(self, names: list[str] | None = None) -> dict[str, bool]:
        out = {}
        for name, m in self.modules.items():
            if names and name not in names:
                continue
            out[name] = self.ping(int(m["request_id"], 16), int(m["response_id"], 16))
        return out

    def scan_address_range(self, start: int = 0x700, stop: int = 0x7F7) -> list[int]:
        """Brute-force tester-present over an 11-bit range (response assumed req+8)."""
        found = []
        for req in range(start, stop + 1):
            if self.ping(req):
                found.append(req)
        return found

    # ---- DTCs ------------------------------------------------------------------------------
    def read_dtcs(self, module: str, mask: int = 0xFF) -> tuple[int | None, list[Dtc], str]:
        m = self.modules[module]
        try:
            self.elm.set_target(int(m["request_id"], 16), int(m["response_id"], 16))
            data = self.elm.send_receive(build_read_dtc_by_status(mask))
            avail, dtcs = parse_dtc_by_status(data)
            return avail, dtcs, ""
        except (ElmError, UdsError) as exc:
            return None, [], str(exc)

    def read_all_dtcs(self, modules: list[str] | None = None) -> dict[str, tuple]:
        return {name: self.read_dtcs(name) for name in (modules or DTC_MODULES) if name in self.modules}

    # ---- DIDs --------------------------------------------------------------------------------
    def read(self, hdr: str, did: int, label: str = "") -> Reading:
        sigs = self.by_cmd.get((hdr.upper(), did), [])
        rax = int(sigs[0].rax, 16) if sigs and sigs[0].rax else None
        try:
            payload = self.elm.read_did(int(hdr, 16), did, rax)
        except (ElmError, UdsError) as exc:
            return Reading(hdr, did, label, False, error=str(exc))
        return Reading(hdr, did, label, True, payload.hex().upper(), decode_payload(sigs, payload) if sigs else {"raw": payload.hex()})

    def snapshot(self, items: list[tuple[str, int, str]] | None = None) -> list[Reading]:
        return [self.read(h, d, lbl) for h, d, lbl in (items or POWER_LIMIT_SET)]

    def sweep(self, module: str, ranges: list[tuple[int, int]]) -> list[tuple[int, str]]:
        """Which DIDs does a module answer? Returns (did, payload hex)."""
        m = self.modules[module]
        req, rax = int(m["request_id"], 16), int(m["response_id"], 16)
        hits = []
        for lo, hi in ranges:
            for did in range(lo, hi + 1):
                try:
                    payload = self.elm.read_did(req, did, rax, retries=0)
                    hits.append((did, payload.hex().upper()))
                except (ElmError, UdsError):
                    continue
        return hits

    # ---- logging -----------------------------------------------------------------------------------
    def log_csv(self, path: str | Path, items: list[tuple[str, int, str]] | None = None, period: float = 1.0,
                duration: float | None = None, on_row=None) -> int:
        items = items or POWER_LIMIT_SET
        cols = ["t_unix", "t_iso"]
        for h, d, _ in items:
            cols += [s.id for s in self.by_cmd.get((h, d), [])] or [f"{h}_{d:04X}_raw"]
        n = 0
        t0 = time.time()
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if fh.tell() == 0:
                w.writerow(cols)
            while duration is None or time.time() - t0 < duration:
                tick = time.time()
                row: dict = {"t_unix": f"{tick:.3f}", "t_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(tick))}
                for r in self.snapshot(items):
                    if r.ok:
                        row.update(r.values if r.values and "raw" not in r.values else {f"{r.hdr}_{r.did:04X}_raw": r.raw_hex})
                w.writerow([row.get(c, "") for c in cols])
                fh.flush()
                n += 1
                if on_row:
                    on_row(row)
                time.sleep(max(0.0, period - (time.time() - tick)))
        return n


# ---------------------------------------------------------------------------------------------------
# Diagnosis heuristics. Thresholds are *community-observed* (macheforum "performance limiters" thread),
# not Ford specifications; they are here to rank hypotheses, not to prove them.
# ---------------------------------------------------------------------------------------------------
def diagnose(readings: list[Reading], dtcs: dict[str, tuple] | None = None) -> list[str]:
    v: dict[str, object] = {}
    for r in readings:
        if r.ok:
            v.update(r.values)
    out: list[str] = []

    if dtcs:
        active = [(m, d) for m, (avail, lst, err) in dtcs.items() for d in lst if d.active]
        stored = [(m, d) for m, (avail, lst, err) in dtcs.items() for d in lst if not d.active]
        unreachable = [m for m, (avail, lst, err) in dtcs.items() if avail is None]
        if active:
            out.append("FAULT: active/confirmed DTCs present -> a component or HV-system fault is the leading hypothesis: "
                       + "; ".join(f"{m}:{d.code}" for m, d in active))
        if stored:
            out.append("Note: stored/history DTCs (not currently failing): " + "; ".join(f"{m}:{d.code}" for m, d in stored))
        if unreachable:
            out.append("Could not read DTCs from: " + ", ".join(unreachable) + " (module asleep, different address on this model year, or bus not reachable)")
        if not active and not stored and not unreachable:
            out.append("No DTCs in powertrain/HV modules -> the bar is most likely a normal operating limiter, not a fault.")

    soc = v.get("MACHE_HVBAT_SOC_DISP")
    if isinstance(soc, (int, float)):
        if soc <= 23:
            out.append(f"SOC {soc:.0f} % -> 'low battery' derate (community: ~12 bars at <=23 %, 13 at <=15 %).")
        elif soc <= 36:
            out.append(f"SOC {soc:.0f} % -> expect ~3 limiter bars from state of charge alone.")
        elif soc <= 64:
            out.append(f"SOC {soc:.0f} % -> expect ~2 limiter bars from state of charge alone.")
        elif soc <= 74:
            out.append(f"SOC {soc:.0f} % <= ~74 % -> ONE limiter bar is expected from state of charge alone (community threshold).")
        else:
            out.append(f"SOC {soc:.0f} % > 74 % -> state of charge should not produce a bar.")

    tmin = v.get("MACHE_T_RANGE_MIN", v.get("MACHE_HVBAT_T"))
    tmax = v.get("MACHE_T_RANGE_MAX")
    if isinstance(tmin, (int, float)):
        if tmin < 0:
            out.append(f"Pack min temperature {tmin:.0f} C -> cold derate (multiple bars expected).")
        elif tmin < 15:
            out.append(f"Pack min temperature {tmin:.0f} C (< ~15 C / 60 F) -> ONE bar is commonly reported from pack temperature alone.")
        else:
            out.append(f"Pack min temperature {tmin:.0f} C -> not cold enough to explain a bar by itself.")
    if isinstance(tmax, (int, float)) and tmax >= 45:
        out.append(f"Pack max temperature {tmax:.0f} C -> hot-pack derate plausible (post-DCFC / sustained high load).")
    if isinstance(tmin, (int, float)) and isinstance(tmax, (int, float)) and tmax - tmin >= 6:
        out.append(f"Pack temperature spread {tmax - tmin:.0f} C is large -> thermal management/sensor issue worth logging over time.")

    for key, label, lim in (("MACHE_PRI_MOTOR_INV_T", "rear inverter", 70), ("MACHE_SEC_MOTOR_INV_T", "front inverter", 70),
                            ("MACHE_PRI_MOTOR_COIL_T", "rear motor coil", 120), ("MACHE_SEC_MOTOR_COIL_T", "front motor coil", 120)):
        t = v.get(key)
        if isinstance(t, (int, float)) and t >= lim:
            out.append(f"{label} temperature {t:.0f} C is high -> drive-unit thermal derate plausible.")

    pl = v.get("MACHE_MAX_DISCH_PWR_LIM")
    if isinstance(pl, (int, float)):
        out.append(f"BECM maximum discharge power limit DID 4815 = {pl:.2f} (scale per OBDb: raw*0.25 kW, saturates at 63.75). "
                   "Log this against bar count: it should drop as bars appear if the limit originates in the BECM.")
    pl2 = v.get("MACHE_BAT_DCHG_POWER_LIM")
    if isinstance(pl2, (int, float)):
        out.append(f"BECM battery discharge power limit DID 4852 = {pl2:.0f} kW (unverified scaling).")

    vmin, vavg = v.get("MACHE_HVBAT_MIN_MOD_V"), v.get("MACHE_HVBAT_AVG_MOD_V")
    if isinstance(vmin, (int, float)) and isinstance(vavg, (int, float)):
        d = (vavg - vmin) * 1000
        out.append(f"Cell/module voltage: min {vmin:.3f} V, avg {vavg:.3f} V, delta {d:.0f} mV"
                   + (" -> imbalance is significant; a weak cell group would cap discharge power." if d > 50 else " -> balanced."))
    spread = v.get("MACHE_HVB_SOC_VARIATION")
    if isinstance(spread, (int, float)) and spread > 2:
        out.append(f"SOC spread across modules {spread:.2f} % -> imbalance; compare with SOH.")
    soh = v.get("MACHE_HVBAT_SOH")
    if isinstance(soh, (int, float)):
        out.append(f"BECM state of health {soh:.1f} %" + (" (unusually low for a 2025 car -> check recall 26S68 / BECM SOH init)" if soh < 90 else "."))

    v12 = v.get("MACHE_12V_V")
    if isinstance(v12, (int, float)) and v12 < 12.2:
        out.append(f"12 V battery {v12:.2f} V is low; weak 12 V supply is a known cause of spurious module behaviour on this platform.")

    cp, cn = v.get("MACHE_CONTACTOR_V_POS"), v.get("MACHE_CONTACTOR_V_NEG")
    hv = v.get("MACHE_HVBAT_V")
    if isinstance(cp, (int, float)) and isinstance(hv, (int, float)) and hv > 100 and abs(hv - cp) > 5:
        out.append(f"Pack {hv:.1f} V vs contactor-positive {cp:.1f} V differ -> read during drive; a persistent gap suggests HVBJB/contactor trouble.")

    if not out:
        out.append("No decoded values available; check adapter connection, that the car is in Ready (not accessory), and module reachability (scan).")
    return out
