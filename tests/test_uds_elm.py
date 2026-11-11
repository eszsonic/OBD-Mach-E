import pytest

from mache_obd.elm327 import Elm327, ElmError, Target, isotp_join
from mache_obd.probe import Session, diagnose
from mache_obd.sim import SimTransport
from mache_obd.uds import NegativeResponse, build_read_dtc_by_status, dtc_bytes_to_string, parse_dtc_by_status, parse_read_did


def test_dtc_string_formats():
    assert dtc_bytes_to_string(0x0A, 0xDE, 0x00) == "P0ADE-00"
    assert dtc_bytes_to_string(0x1A, 0x10, 0x00) == "P1A10-00"
    assert dtc_bytes_to_string(0x05, 0x63, 0x16) == "P0563-16"
    assert dtc_bytes_to_string(0xC1, 0x00, 0x87) == "U0100-87"
    assert dtc_bytes_to_string(0x90, 0x6E, 0x00) == "B106E-00"
    assert dtc_bytes_to_string(0x40, 0x01, 0x00) == "C0001-00"


def test_parse_dtc_by_status():
    data = bytes.fromhex("59028F" "0ADE0009" "1A100008" "0563162F")
    avail, dtcs = parse_dtc_by_status(data)
    assert avail == 0x8F
    assert [d.code for d in dtcs] == ["P0ADE-00", "P1A10-00", "P0563-16"]
    assert dtcs[0].active and "confirmedDTC" in dtcs[0].status_names
    assert build_read_dtc_by_status(0x09) == b"\x19\x02\x09"


def test_negative_response():
    with pytest.raises(NegativeResponse) as ei:
        parse_read_did(bytes.fromhex("7F2231"), 0x4800)
    assert ei.value.nrc == 0x31 and not ei.value.pending


def test_isotp_multiframe_from_forum_capture():
    # APIM GPS DID 8012 capture posted on macheforum (7D0 -> 7D8), 18-byte response.
    frames = [bytes.fromhex("1012628012010F00"), bytes.fromhex("21000A11FFFFEE16"), bytes.fromhex("2204000E01430000")]
    msg = isotp_join(frames)
    assert len(msg) == 0x12
    payload = parse_read_did(msg, 0x8012)
    assert payload.hex().upper() == "010F00000A11FFFFEE1604000E0143"
    lat = int.from_bytes(payload[2:6], "big", signed=True) / 60
    lon = int.from_bytes(payload[6:10], "big", signed=True) / 60
    assert round(lat, 4) == 42.95 and round(lon, 4) == -76.4333


def test_elm_reassemble_ignores_noise_and_other_ids():
    elm = Elm327(SimTransport())
    tgt = Target(0x7E4, 0x7EC)
    lines = ["SEARCHING...", "7E8037F2231", "7EC056248FB04A7", ">"]
    assert elm.reassemble(lines, tgt).hex().upper() == "6248FB04A7"
    with pytest.raises(ElmError):
        elm.reassemble(["NO DATA"], tgt)


def test_full_pipeline_on_simulator():
    table = {
        ("7E4", "224845"): ["7EC04624845" + "8C"],          # 70 %
        ("7E4", "224808"): ["7EC0762480844433244"],         # 18/17/0/18 C
        ("7E4", "224815"): ["7EC04624815F4"],               # 61 kW
        ("7E4", "224840"): ["7EC056248400E5C"],
        ("7E4", "224841"): ["7EC056248410E6A"],
        ("7E6", "224824"): ["7EE056248240035"],
        ("7E4", "1902FF"): ["7EC07590289" + "0ADE0009"],    # one active P0ADE
    }
    elm = Elm327(SimTransport(table))
    elm.initialize()
    s = Session(elm)
    assert s.scan_known_modules(["BECM", "SOBDMC", "IPC"]) == {"BECM": True, "SOBDMC": True, "IPC": False}
    rs = s.snapshot()
    got = {k: v for r in rs if r.ok for k, v in r.values.items()}
    assert got["MACHE_HVBAT_SOC_DISP"] == 70 and got["MACHE_T_RANGE_MIN"] == 17 and got["MACHE_MAX_DISCH_PWR_LIM"] == 61
    dt = s.read_all_dtcs(["BECM", "SOBDMC"])
    assert [d.code for d in dt["BECM"][1]] == ["P0ADE-00"]
    assert dt["SOBDMC"][1] == []
    report = diagnose(rs, dt)
    assert any("FAULT" in line and "P0ADE" in line for line in report)
    assert any("ONE limiter bar" in line for line in report)          # SOC 70 % branch


def test_sim_from_fixture_json_runs_diagnose(tmp_path):
    import json
    from pathlib import Path
    fx = Path(__file__).parent / "fixtures_obdb.json"
    elm = Elm327(SimTransport.from_fixture_json(fx, year=2024))
    elm.initialize()
    s = Session(elm)
    rs = s.snapshot()
    assert sum(r.ok for r in rs) >= 15
    assert diagnose(rs, s.read_all_dtcs(["BECM", "SOBDMC", "PCM"]))
