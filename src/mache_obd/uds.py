"""Minimal ISO 14229 (UDS) request builders / response parsers used by the probe."""
from __future__ import annotations

from dataclasses import dataclass

SID_READ_DID = 0x22
SID_READ_DTC = 0x19
SID_TESTER_PRESENT = 0x3E
SID_SESSION = 0x10

NRC = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceededNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x78: "requestCorrectlyReceived-ResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}

DTC_STATUS_BITS = [
    (0x01, "testFailed"),
    (0x02, "testFailedThisOperationCycle"),
    (0x04, "pendingDTC"),
    (0x08, "confirmedDTC"),
    (0x10, "testNotCompletedSinceLastClear"),
    (0x20, "testFailedSinceLastClear"),
    (0x40, "testNotCompletedThisOperationCycle"),
    (0x80, "warningIndicatorRequested"),
]


class UdsError(Exception):
    pass


class NegativeResponse(UdsError):
    def __init__(self, sid: int, nrc: int):
        self.sid, self.nrc = sid, nrc
        super().__init__(f"NRC 0x{nrc:02X} ({NRC.get(nrc, 'unknown')}) to SID 0x{sid:02X}")

    @property
    def pending(self) -> bool:
        return self.nrc == 0x78


def build_read_did(did: int) -> bytes:
    return bytes([SID_READ_DID, (did >> 8) & 0xFF, did & 0xFF])


def build_read_dtc_by_status(mask: int = 0xFF) -> bytes:
    return bytes([SID_READ_DTC, 0x02, mask & 0xFF])


def build_tester_present() -> bytes:
    return bytes([SID_TESTER_PRESENT, 0x00])


def check_positive(data: bytes, sid: int) -> bytes:
    """Validate a UDS response for `sid`; return the bytes after the response SID."""
    if not data:
        raise UdsError("empty response")
    if data[0] == 0x7F:
        if len(data) < 3:
            raise UdsError(f"malformed negative response {data.hex()}")
        raise NegativeResponse(data[1], data[2])
    if data[0] != sid + 0x40:
        raise UdsError(f"unexpected SID 0x{data[0]:02X} (wanted 0x{sid + 0x40:02X}) in {data.hex()}")
    return data[1:]


def parse_read_did(data: bytes, did: int) -> bytes:
    body = check_positive(data, SID_READ_DID)
    if len(body) < 2 or ((body[0] << 8) | body[1]) != did:
        raise UdsError(f"DID mismatch: wanted {did:04X}, got {body[:2].hex()}")
    return body[2:]


@dataclass(frozen=True)
class Dtc:
    code: str          # e.g. "P0ADE-00"
    status: int
    raw: bytes

    @property
    def status_names(self) -> list[str]:
        return [n for bit, n in DTC_STATUS_BITS if self.status & bit]

    @property
    def active(self) -> bool:
        return bool(self.status & 0x09)   # testFailed or confirmed

    def __str__(self) -> str:
        return f"{self.code} status=0x{self.status:02X} [{', '.join(self.status_names)}]"


def dtc_bytes_to_string(b1: int, b2: int, b3: int) -> str:
    """SAE J2012 / ISO 15031-6 3-byte DTC -> 'P0ADE-00' style (Ford shows the 3rd byte as failure type)."""
    letter = "PCBU"[(b1 >> 6) & 0x3]
    return f"{letter}{(b1 >> 4) & 0x3}{b1 & 0xF:X}{b2:02X}-{b3:02X}"


def parse_dtc_by_status(data: bytes) -> tuple[int, list[Dtc]]:
    body = check_positive(data, SID_READ_DTC)
    if len(body) < 2 or body[0] != 0x02:
        raise UdsError(f"unexpected 0x19 sub-function response {body.hex()}")
    avail_mask = body[1]
    recs = body[2:]
    dtcs = []
    for i in range(0, len(recs) - len(recs) % 4, 4):
        b1, b2, b3, st = recs[i : i + 4]
        dtcs.append(Dtc(dtc_bytes_to_string(b1, b2, b3), st, bytes(recs[i : i + 4])))
    return avail_mask, dtcs
