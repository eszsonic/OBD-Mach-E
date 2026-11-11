"""Command-line interface.

Examples (Windows PowerShell):
  python -m mache_obd ports
  python -m mache_obd --port COM5 info
  python -m mache_obd --port COM5 scan
  python -m mache_obd --port COM5 dtc
  python -m mache_obd --port COM5 snapshot
  python -m mache_obd --port COM5 diagnose
  python -m mache_obd --port COM5 log --period 1 --out drive1.csv
  python -m mache_obd --port COM5 sweep --module BECM --range 4800-49FF
  python -m mache_obd --sim tests/fixtures_obdb.json diagnose      # offline dry run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .elm327 import Elm327, SerialTransport
from .probe import DTC_MODULES, POWER_LIMIT_SET, Session, diagnose


def _ports() -> None:
    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial not installed: pip install pyserial")
        return
    found = False
    for p in list_ports.comports():
        found = True
        print(f"{p.device:8s} {p.description}  [{p.hwid}]")
    if not found:
        print("No serial ports. Pair 'vLinker MC-Android' (PIN 1234) in Windows Bluetooth settings; "
              "an outgoing 'Standard Serial over Bluetooth' COM port then appears in Device Manager.")


def _open(args) -> Elm327:
    if args.sim:
        from .sim import SimTransport
        tr = SimTransport.from_fixture_json(args.sim, year=args.sim_year)
    else:
        if not args.port:
            sys.exit("--port COMx is required (or --sim fixtures.json)")
        tr = SerialTransport(args.port, args.baud)
    elm = Elm327(tr)
    ident = elm.initialize(addressing=args.addressing)
    logging.getLogger(__name__).info("adapter: %s", ident)
    return elm


def _parse_ranges(text: str) -> list[tuple[int, int]]:
    out = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        out.append((int(lo, 16), int(hi or lo, 16)))
    return out


def _print_readings(rs) -> None:
    for r in rs:
        if r.ok:
            vals = ", ".join(f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in r.values.items())
            print(f"  {r.hdr} {r.did:04X} {r.label:45s} {vals}   [{r.raw_hex}]")
        else:
            print(f"  {r.hdr} {r.did:04X} {r.label:45s} -- {r.error}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mache_obd", description="Read-only Mach-E UDS probe for power-limit diagnosis")
    ap.add_argument("--port", help="serial port of the Bluetooth adapter, e.g. COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--addressing", type=int, choices=(11, 29), default=11, help="CAN id size; try 29 if no module answers")
    ap.add_argument("--sim", help="run against a fixture JSON instead of hardware")
    ap.add_argument("--sim-year", type=int, default=None)
    ap.add_argument("-v", "--verbose", action="count", default=0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports", help="list serial ports")
    sub.add_parser("info", help="adapter identity and battery voltage")
    sp = sub.add_parser("scan", help="which modules answer tester-present")
    sp.add_argument("--range", help="brute-force 11-bit range, e.g. 700-7F7", default=None)
    dp = sub.add_parser("dtc", help="read DTCs (service 19 02)")
    dp.add_argument("--module", action="append", help="module name(s); default: powertrain/HV set")
    dp.add_argument("--mask", default="FF", help="status mask hex (FF=all, 09=failed/confirmed)")
    sub.add_parser("snapshot", help="read the power-limit DID set once")
    sub.add_parser("diagnose", help="DTCs + snapshot + ranked hypotheses")
    lp = sub.add_parser("log", help="log the power-limit DID set to CSV")
    lp.add_argument("--out", required=True)
    lp.add_argument("--period", type=float, default=1.0)
    lp.add_argument("--duration", type=float, default=None, help="seconds; default until Ctrl-C")
    wp = sub.add_parser("sweep", help="find which DIDs a module answers")
    wp.add_argument("--module", required=True)
    wp.add_argument("--range", default="4800-49FF,0100-07FF,F100-F1FF,DD00-DD10")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING - 10 * min(args.verbose, 2), format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "ports":
        _ports()
        return 0

    elm = _open(args)
    s = Session(elm)
    try:
        if args.cmd == "info":
            for k, v in elm.identity.items():
                print(f"{k:8s} {v}")
        elif args.cmd == "scan":
            if args.range:
                lo, _, hi = args.range.partition("-")
                for req in s.scan_address_range(int(lo, 16), int(hi, 16)):
                    name = next((n for n, m in s.modules.items() if int(m["request_id"], 16) == req), "?")
                    print(f"  {req:03X} -> {req + 8:03X}  {name}")
            else:
                for name, ok in s.scan_known_modules().items():
                    m = s.modules[name]
                    print(f"  {name:7s} {m['request_id']} {'answers' if ok else '-'}   {m['description']}")
        elif args.cmd == "dtc":
            res = s.read_all_dtcs(args.module or DTC_MODULES)
            for name, (avail, dtcs, err) in res.items():
                if avail is None:
                    print(f"{name:7s} unreachable: {err}")
                    continue
                print(f"{name:7s} availability mask 0x{avail:02X}: {len(dtcs)} DTC(s)")
                for d in dtcs:
                    print(f"         {d}")
        elif args.cmd == "snapshot":
            _print_readings(s.snapshot())
        elif args.cmd == "diagnose":
            print("== DTCs")
            dt = s.read_all_dtcs()
            for name, (avail, dtcs, err) in dt.items():
                print(f"  {name:7s} " + (f"unreachable ({err})" if avail is None else f"{len(dtcs)} DTC(s) " + "; ".join(d.code for d in dtcs)))
            print("== Snapshot")
            rs = s.snapshot()
            _print_readings(rs)
            print("== Assessment (heuristic, community thresholds)")
            for line in diagnose(rs, dt):
                print("  * " + line)
        elif args.cmd == "log":
            print(f"logging to {args.out}; Ctrl-C to stop")
            try:
                n = s.log_csv(args.out, POWER_LIMIT_SET, args.period, args.duration,
                              on_row=lambda row: print(row.get("t_iso"), {k: row[k] for k in ("MACHE_HVBAT_SOC_DISP", "MACHE_T_RANGE_MIN", "MACHE_MAX_DISCH_PWR_LIM") if k in row}))
            except KeyboardInterrupt:
                n = -1
            print("done", n)
        elif args.cmd == "sweep":
            for did, payload in s.sweep(args.module, _parse_ranges(args.range)):
                known = [sig.id for sig in s.by_cmd.get((s.modules[args.module]["request_id"], did), [])]
                print(f"  {did:04X} len={len(payload)//2:3d} {payload}  {','.join(known)}")
    finally:
        elm.transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
