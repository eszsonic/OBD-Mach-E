"""ELM327 / STN11xx (vLinker MC+) serial driver with software ISO-TP reassembly.

The adapter is used in ISO 15765-4 CAN mode with headers ON and automatic formatting ON, so
the adapter sends flow-control frames for us while every received frame (header + PCI + data)
is echoed back as one text line. Reassembly is done here so that 11-bit and 29-bit
addressing, single/multi-frame answers and odd header pairs (e.g. 726/72E) all work the same way.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from .uds import NegativeResponse, UdsError, build_read_did, parse_read_did

log = logging.getLogger(__name__)

ERROR_TOKENS = ("NO DATA", "CAN ERROR", "BUS INIT", "BUS ERROR", "UNABLE TO CONNECT", "STOPPED",
                "DATA ERROR", "BUFFER FULL", "FB ERROR", "LV RESET", "ACT ALERT", "ERR")


class ElmError(Exception):
    pass


class Transport:
    """Byte transport (serial port or simulator)."""

    def write(self, data: bytes) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def read_until_prompt(self, timeout: float) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        pass


class SerialTransport(Transport):
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1):
        import serial  # lazy import so the simulator works without pyserial

        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout, write_timeout=2)

    def write(self, data: bytes) -> None:
        self.ser.reset_input_buffer()
        self.ser.write(data)
        self.ser.flush()

    def read_until_prompt(self, timeout: float) -> str:
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if buf.endswith(b">"):
                    break
        return buf.decode("ascii", errors="replace")

    def close(self) -> None:
        self.ser.close()


@dataclass
class Target:
    req_id: int
    resp_id: int
    ext: bool = False   # 29-bit addressing


@dataclass
class Elm327:
    transport: Transport
    cmd_timeout: float = 2.0
    uds_timeout: float = 3.0
    addressing: int = 11             # 11 or 29 bit
    identity: dict = field(default_factory=dict)
    _target: Target | None = None

    # ---- low level -------------------------------------------------------------------
    def raw(self, cmd: str, timeout: float | None = None) -> list[str]:
        """Send one command, return response lines without echo/prompt."""
        self.transport.write((cmd + "\r").encode("ascii"))
        text = self.transport.read_until_prompt(timeout or self.cmd_timeout)
        lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]
        lines = [ln for ln in lines if ln and ln != ">"]
        if lines and lines[0].upper() == cmd.upper():     # echo
            lines = lines[1:]
        lines = [ln.rstrip(">").strip() for ln in lines]
        log.debug("%s -> %s", cmd, lines)
        return [ln for ln in lines if ln]

    def at(self, cmd: str, expect_ok: bool = True, timeout: float | None = None) -> list[str]:
        lines = self.raw(cmd, timeout)
        if expect_ok and not any("OK" in ln for ln in lines):
            raise ElmError(f"{cmd!r} did not return OK: {lines}")
        return lines

    # ---- setup -----------------------------------------------------------------------
    def initialize(self, addressing: int = 11) -> dict:
        self.addressing = addressing
        self.raw("ATZ", timeout=4.0)
        time.sleep(0.5)
        self.at("ATE0")      # echo off
        self.at("ATL0")      # no linefeeds
        self.at("ATS0")      # no spaces
        self.at("ATH1")      # headers on (we need the CAN id + PCI byte)
        self.at("ATCAF1")    # ISO-TP formatting / automatic flow control
        self.at("ATAT1")     # adaptive timing
        self.at("ATST64")    # 400 ms max wait for a frame
        self.at("ATSP7" if addressing == 29 else "ATSP6")   # ISO 15765-4 CAN 500 kbit, 29 or 11 bit
        ident = {}
        for key, cmd in (("ATI", "ATI"), ("AT@1", "AT@1"), ("STI", "STI"), ("STDI", "STDI")):
            try:
                ident[key] = " ".join(self.raw(cmd))
            except Exception as exc:  # pragma: no cover
                ident[key] = f"n/a ({exc})"
        ident["voltage"] = " ".join(self.raw("ATRV"))
        self.identity = ident
        self._target = None
        return ident

    def set_target(self, req_id: int, resp_id: int | None = None) -> None:
        if resp_id is None:
            resp_id = req_id + 8 if self.addressing == 11 else (0x18DAF100 | ((req_id & 0xFF) ))
        tgt = Target(req_id, resp_id, self.addressing == 29)
        if self._target == tgt:
            return
        if self.addressing == 11:
            self.at(f"ATSH{req_id:03X}")
            self.at(f"ATCRA{resp_id:03X}")
            self.at(f"ATFCSH{req_id:03X}")
        else:
            # 29-bit physical addressing 18 DA <target> <tester F1>
            self.at(f"ATCP{(req_id >> 24) & 0xFF:02X}")
            self.at(f"ATSH{req_id & 0xFFFFFF:06X}")
            self.at(f"ATCRA{resp_id:08X}")
            self.at(f"ATFCSH{req_id & 0xFFFFFF:06X}")
        self.at("ATFCSD300000")   # flow control: continue, no block size, no separation time
        self.at("ATFCSM1")
        self._target = tgt

    # ---- transport-level UDS -----------------------------------------------------------
    def send_receive(self, payload: bytes, timeout: float | None = None) -> bytes:
        """Send a UDS payload to the current target and return the reassembled response."""
        if self._target is None:
            raise ElmError("no target set")
        lines = self.raw(payload.hex().upper(), timeout or self.uds_timeout)
        return self.reassemble(lines, self._target, expected_prefix(payload))

    def reassemble(self, lines: list[str], tgt: Target, expect: bytes | None = None) -> bytes:
        """Pick the frames from the target id (optionally only those answering `expect`) and join them.

        `expect` is the positive-response prefix (e.g. 62 48 00 for a DID read); frames that start a
        message for something else (a late answer to an earlier request, or a batched mode-01 reply)
        are discarded, as are their consecutive frames. Negative responses (7F sid ..) are kept.
        """
        hdr_len = 8 if tgt.ext else 3
        want = f"{tgt.resp_id:0{hdr_len}X}"
        frames: list[bytes] = []
        accepting = False
        for ln in lines:
            token = ln.replace(" ", "").upper()
            if any(tok in token.replace("CANERROR", "CAN ERROR") for tok in ("NODATA", "CAN ERROR")) or token in ("?",) \
                    or any(ln.upper().startswith(t) for t in ERROR_TOKENS):
                if not frames:
                    raise ElmError(ln)
                continue
            if token.startswith("SEARCHING"):
                continue
            if not re.fullmatch(r"[0-9A-F]+", token):
                continue
            if not token.startswith(want):
                log.debug("ignoring frame from other id: %s", ln)
                continue
            frame = bytes.fromhex(token[hdr_len:])
            pci = frame[0] >> 4 if frame else 0xF
            if pci in (0x0, 0x1):                       # start of a message: decide whether it is ours
                body = frame[1:] if pci == 0x0 else frame[2:]
                accepting = expect is None or body.startswith(expect) or (len(body) > 1 and body[0] == 0x7F)
                if accepting and frames and (frames[0][0] >> 4) in (0x0, 0x1):
                    frames = []                          # a newer matching message supersedes
            elif pci == 0x2 and not accepting:
                continue
            if accepting:
                frames.append(frame)
        if not frames:
            raise ElmError(f"no frames from {want}: {lines}")
        return isotp_join(frames)

    # ---- helpers -------------------------------------------------------------------------
    def read_did(self, req_id: int, did: int, resp_id: int | None = None, retries: int = 2) -> bytes:
        self.set_target(req_id, resp_id)
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                data = self.send_receive(build_read_did(did))
                return parse_read_did(data, did)
            except NegativeResponse as nr:
                if nr.pending and attempt < retries:
                    time.sleep(0.3)
                    last = nr
                    continue
                raise
            except ElmError as exc:
                last = exc
                if attempt < retries:
                    time.sleep(0.2)
                    continue
                raise
        raise UdsError(str(last))


def expected_prefix(request: bytes) -> bytes:
    """Positive-response prefix for a UDS request: SID+0x40 followed by the echoed identifier bytes."""
    sid = request[0]
    if sid == 0x22:
        return bytes([sid + 0x40]) + request[1:3]
    if sid in (0x19, 0x3E, 0x10, 0x31):
        return bytes([sid + 0x40]) + request[1:2]
    return bytes([sid + 0x40])


def isotp_join(frames: list[bytes]) -> bytes:
    """Join ELM-echoed frames (PCI byte included) into one UDS message."""
    first = frames[0]
    pci = first[0] >> 4
    if pci == 0x0:                                   # single frame
        n = first[0] & 0xF
        return bytes(first[1 : 1 + n])
    if pci == 0x1:                                   # first frame
        total = ((first[0] & 0xF) << 8) | first[1]
        buf = bytearray(first[2:])
        expected_sn = 1
        for fr in frames[1:]:
            if fr[0] >> 4 != 0x2:
                continue
            sn = fr[0] & 0xF
            if sn != expected_sn:
                log.warning("ISO-TP sequence gap: got %d expected %d", sn, expected_sn)
            expected_sn = (sn + 1) & 0xF
            buf += fr[1:]
        if len(buf) < total:
            raise ElmError(f"incomplete multi-frame response: {len(buf)}/{total} bytes")
        return bytes(buf[:total])
    # No PCI (adapter stripped it) -> treat as plain payload
    return bytes(b"".join(frames))
