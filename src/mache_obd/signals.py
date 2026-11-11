"""Signal definitions (OBDb-derived CSV) and raw-payload decoding."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_SIGNALS_CSV = DATA_DIR / "mache_signals.csv"


@dataclass(frozen=True)
class Signal:
    hdr: str          # request CAN id, hex string e.g. "7E4"
    rax: str          # response CAN id, hex string e.g. "7EC"
    did: int          # UDS data identifier
    id: str           # OBDb signal id, e.g. MACHE_HVBAT_T
    name: str
    bix: int          # bit offset from start of DID payload, MSB-first
    length: int       # bit length
    mul: float
    div: float
    add: float
    signed: bool
    unit: str
    vmin: float | None
    vmax: float | None
    nullmin: float | None   # decoded value <= nullmin  -> not available (None)
    nullmax: float | None   # decoded value >= nullmax  -> not available (None)
    enum: dict[int, str] | None
    enum_desc: dict[int, str] | None
    dbg: bool
    year_filter: dict
    desc: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.hdr.upper(), self.did)

    @property
    def verified_for_2025(self) -> bool | None:
        """None = unknown, False = a 2025 car was probed and did NOT answer, True = listed as supported."""
        yrs = self.year_filter.get("years")
        if yrs and 2025 in yrs:
            return False
        return None


def _f(x: str) -> float | None:
    x = (x or "").strip()
    if x == "":
        return None
    return float(x)


def load_signals(path: str | Path | None = None) -> list[Signal]:
    path = Path(path) if path else DEFAULT_SIGNALS_CSV
    out: list[Signal] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            enum = json.loads(row["map"]) if row.get("map") else None
            enum_desc = json.loads(row["map_desc"]) if row.get("map_desc") else None
            out.append(
                Signal(
                    hdr=row["hdr"].upper(),
                    rax=row["rax"].upper(),
                    did=int(row["did"], 16),
                    id=row["id"],
                    name=row["name"],
                    bix=int(row["bix"] or 0),
                    length=int(row["len"]),
                    mul=float(row["mul"] or 1),
                    div=float(row["div"] or 1),
                    add=float(row["add"] or 0),
                    signed=row["signed"] in ("1", "True", "true"),
                    unit=row["unit"],
                    vmin=_f(row.get("min", "")),
                    vmax=_f(row.get("max", "")),
                    nullmin=_f(row.get("nullmin", "")),
                    nullmax=_f(row.get("nullmax", "")),
                    enum={int(k): v for k, v in enum.items()} if enum else None,
                    enum_desc={int(k): v for k, v in enum_desc.items()} if enum_desc else None,
                    dbg=row.get("dbg") in ("1", "True", "true"),
                    year_filter=json.loads(row["filter"]) if row.get("filter") else {},
                    desc=row.get("desc", ""),
                )
            )
    return out


def group_by_command(signals: Iterable[Signal]) -> dict[tuple[str, int], list[Signal]]:
    groups: dict[tuple[str, int], list[Signal]] = {}
    for s in signals:
        groups.setdefault(s.key, []).append(s)
    return groups


def extract_bits(payload: bytes, bix: int, length: int) -> int:
    total = len(payload) * 8
    if bix + length > total:
        raise ValueError(f"payload too short: need {bix + length} bits, have {total}")
    val = int.from_bytes(payload, "big")
    return (val >> (total - bix - length)) & ((1 << length) - 1)


def decode_signal(sig: Signal, payload: bytes, clamp: bool = True):
    """Decode one signal from the DID payload (bytes after `62 DID_hi DID_lo`).

    Follows OBDb semantics: enum lookup; two's-complement when signed; value = raw*mul/div+add;
    None when the value reaches a declared null sentinel (nullmin/nullmax); otherwise clamped to
    [min, max] (pass clamp=False to see the unclamped number, e.g. when validating a scale).
    """
    raw = extract_bits(payload, sig.bix, sig.length)
    if sig.enum is not None:
        return sig.enum.get(raw, f"UNKNOWN({raw})")
    if sig.signed and raw & (1 << (sig.length - 1)):
        raw -= 1 << sig.length
    value = raw * sig.mul / sig.div + sig.add
    if sig.nullmin is not None and value <= sig.nullmin:
        return None
    if sig.nullmax is not None and value >= sig.nullmax:
        return None
    if clamp:
        if sig.vmin is not None and value < sig.vmin:
            value = sig.vmin
        if sig.vmax is not None and value > sig.vmax:
            value = sig.vmax
    return value


def decode_payload(sigs: Iterable[Signal], payload: bytes) -> dict[str, object]:
    out = {}
    for s in sigs:
        try:
            out[s.id] = decode_signal(s, payload)
        except ValueError as exc:
            out[s.id] = f"ERR {exc}"
    return out
