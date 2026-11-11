"""A tiny ELM327 emulator so the whole pipeline can run and be tested without a car."""
from __future__ import annotations

import json
from pathlib import Path

from .elm327 import Transport


class SimTransport(Transport):
    """Keys: (request_id_hex, request_payload_hex) -> list of response lines (header+PCI+data)."""

    def __init__(self, table: dict[tuple[str, str], list[str]] | None = None, ext: bool = False):
        self.table = table or {}
        self.ext = ext
        self.sh = "7DF"
        self.cra = None
        self._pending = ""
        self.sent: list[str] = []

    @classmethod
    def from_fixture_json(cls, path: str | Path, year: int | None = None, prefer_latest: bool = True):
        rows = json.load(open(path))
        table: dict[tuple[str, str], list[str]] = {}
        for r in rows:
            if year is not None and r["year"] != year:
                continue
            key = (r["hdr"].upper(), "22" + r["did"].upper())
            if key in table and not prefer_latest:
                continue
            table[key] = list(r["response"]) if isinstance(r["response"], list) else [r["response"]]
        return cls(table)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii").strip().upper()
        self.sent.append(cmd)
        if cmd == "ATZ":
            self._pending = "\r\rELM327 v1.5\r\r>"
        elif cmd.startswith("ATSH"):
            self.sh = cmd[4:]
            self._pending = "OK\r\r>"
        elif cmd.startswith("ATCRA"):
            self.cra = cmd[5:]
            self._pending = "OK\r\r>"
        elif cmd == "ATI":
            self._pending = "ELM327 v1.5\r\r>"
        elif cmd == "AT@1":
            self._pending = "vLinker MC+ simulator\r\r>"
        elif cmd in ("STI", "STDI"):
            self._pending = "STN2120 v5.6.x (sim)\r\r>"
        elif cmd == "ATRV":
            self._pending = "12.6V\r\r>"
        elif cmd.startswith("AT"):
            self._pending = "OK\r\r>"
        else:
            lines = self.table.get((self.sh, cmd))
            if lines is None and cmd == "3E00" and any(k[0] == self.sh for k in self.table):
                resp = f"{int(self.sh, 16) + 8:03X}" if not self.ext else self.cra
                lines = [f"{resp}027E00"]
            if lines is None and cmd.startswith("1902") and any(k[0] == self.sh for k in self.table):
                resp = f"{int(self.sh, 16) + 8:03X}"
                lines = [f"{resp}0359028F"]       # no DTCs stored
            if lines is None:
                self._pending = "NO DATA\r\r>"
            else:
                self._pending = "\r".join(lines) + "\r\r>"

    def read_until_prompt(self, timeout: float) -> str:
        out, self._pending = self._pending, ""
        return out
