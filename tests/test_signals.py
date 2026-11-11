"""Decode every real-car response captured in the OBDb Mach-E repository and compare with its expected values."""
import json
import math
from pathlib import Path

import pytest

from mache_obd.elm327 import Elm327, Target, isotp_join
from mache_obd.sim import SimTransport
from mache_obd.signals import decode_signal, group_by_command, load_signals
from mache_obd.uds import parse_read_did

HERE = Path(__file__).parent
FIX = json.load(open(HERE / "fixtures_obdb.json"))
SIGS = group_by_command(load_signals())


ELM = Elm327(SimTransport())


def _message(lines: list[str], hdr: str, rax: str) -> bytes:
    """Reassemble exactly as the driver does on the car (frames echoed with header + PCI)."""
    return ELM.reassemble(lines, Target(int(hdr, 16), int(rax, 16)), expect=None)


def _message_for_did(lines: list[str], hdr: str, rax: str, did: int) -> bytes:
    from mache_obd.elm327 import expected_prefix
    from mache_obd.uds import build_read_did
    return ELM.reassemble(lines, Target(int(hdr, 16), int(rax, 16)), expected_prefix(build_read_did(did)))


@pytest.mark.parametrize("fx", FIX, ids=lambda f: f"{f['year']}-{f['hdr']}-{f['did']}-{f['response'][0][:14]}")
def test_obdb_fixture(fx):
    key = (fx["hdr"].upper(), int(fx["did"], 16))
    sigs = SIGS.get(key)
    if not sigs:
        pytest.skip("no signal definition for this command")
    msg = _message_for_did(fx["response"], fx["hdr"], fx["rax"], int(fx["did"], 16))
    payload = parse_read_did(msg, int(fx["did"], 16))
    for s in sigs:
        if s.id not in fx["expected"]:
            continue
        got = decode_signal(s, payload)
        exp = fx["expected"][s.id]
        if exp is None:
            assert got is None, (s.id, got, exp, payload.hex())
        elif isinstance(exp, str):
            assert str(got).upper() == exp.upper(), (s.id, got, exp)
        else:
            assert isinstance(got, (int, float)), (s.id, got, exp)
            assert math.isclose(got, exp, rel_tol=1e-6, abs_tol=1e-3), (s.id, got, exp, payload.hex())


def test_fixture_coverage_has_power_limit_dids():
    dids = {(f["hdr"], f["did"]) for f in FIX}
    for want in (("7E4", "4815"), ("7E4", "4808"), ("7E4", "4845"), ("7E6", "4824"), ("7E4", "48FB")):
        assert want in dids
