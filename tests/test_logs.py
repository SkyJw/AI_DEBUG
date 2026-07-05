"""Log-modelling layer: records, whitelist filter, per-type parsing, YAML config.

Pure modelling only — these assert structure and losslessness, never boot/stage
interpretation (that layer does not exist yet by design).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aidbg.logs import (
    CbblogRecord,
    LogConfigSet,
    PanicRecord,
    Target,
    TargetSet,
    UbootRecord,
    load_log_configs,
    log_type,
)
from aidbg.logs.base import LOG_TYPES
from aidbg.logs.cbblog import CbblogLog
from aidbg.logs.panic import PanicLog
from aidbg.logs.uboot import UbootLog


# --- registry ----------------------------------------------------------------


def test_three_log_types_registered():
    assert set(LOG_TYPES) == {"uboot", "panic", "cbblog"}
    assert log_type("uboot") is UbootLog
    assert log_type("panic") is PanicLog
    assert log_type("cbblog") is CbblogLog


# --- UBOOT parsing ------------------------------------------------------------


def test_uboot_relative_ms_timestamp():
    lf = UbootLog.parse("UBOOT", "[100ms] hello uboot")
    (rec,) = lf.records
    assert isinstance(rec, UbootRecord)
    assert rec.timestamp is not None
    assert rec.timestamp.rel_ms == 100
    assert rec.timestamp.value is None
    assert rec.message == "hello uboot"
    assert rec.line_no == 0


def test_uboot_unparsed_line_kept_lossless():
    lf = UbootLog.parse("UBOOT", "no timestamp here")
    (rec,) = lf.records
    assert rec.timestamp is None
    assert rec.message == "no timestamp here"
    assert rec.raw == "no timestamp here"


# --- panic parsing ------------------------------------------------------------


def test_panic_wallclock_timestamp():
    lf = PanicLog.parse("panic", "[20260630102045] soc probe done")
    (rec,) = lf.records
    assert isinstance(rec, PanicRecord)
    assert rec.timestamp is not None
    assert rec.timestamp.value == datetime(2026, 6, 30, 10, 20, 45)
    assert rec.message == "soc probe done"


def test_panic_1970_default_is_just_a_value_no_era_judgement():
    lf = PanicLog.parse("panic", "[19700101000012] early boot")
    (rec,) = lf.records
    # Layer converts digits to a datetime; it does not label it "1970 era".
    assert rec.timestamp is not None
    assert rec.timestamp.value == datetime(1970, 1, 1, 0, 0, 12)


def test_panic_continuation_line_has_no_timestamp():
    text = "[19700101000012] Unable to handle kernel NULL pointer\nsome_func+0x1c/0x40"
    lf = PanicLog.parse("panic", text)
    header, cont = lf.records
    assert header.timestamp is not None
    assert cont.timestamp is None  # continuation: no stamp of its own
    assert cont.message == "some_func+0x1c/0x40"
    assert cont.line_no == 1


def test_panic_invalid_date_keeps_raw_drops_value():
    lf = PanicLog.parse("panic", "[20261332250000] bogus date")
    (rec,) = lf.records
    assert rec.timestamp is not None
    assert rec.timestamp.raw == "[20261332250000]"
    assert rec.timestamp.value is None  # not a real date


# --- CBBLOG parsing -----------------------------------------------------------


def test_cbblog_timestamp_and_deferred_fields():
    lf = CbblogLog.parse("CBBLOG", "[2026-07-04:15:12:30] vBSP_init begin nesoft")
    (rec,) = lf.records
    assert isinstance(rec, CbblogRecord)
    assert rec.timestamp is not None
    assert rec.timestamp.value == datetime(2026, 7, 4, 15, 12, 30)
    # Field extraction deferred: structured fields unset, remainder in message.
    assert rec.process_id is None
    assert rec.pid is None
    assert rec.message == "vBSP_init begin nesoft"


# --- losslessness -------------------------------------------------------------


def test_parse_is_lossless_line_count_matches():
    text = "[100ms] a\ngarbage\n[200ms] b"
    lf = UbootLog.parse("UBOOT", text)
    assert len(lf) == 3
    assert [r.line_no for r in lf.records] == [0, 1, 2]


# --- target set ---------------------------------------------------------------


def test_targets_disabled_keeps_everything():
    t = TargetSet(targets=(Target("x", "keep it", "keep"),), enabled=False)
    assert t.keep("anything")


def test_targets_whitelist_keeps_only_matches():
    t = TargetSet(
        targets=(
            Target("errs", "error line", r"(?i)error", match="regex"),
            Target("init", "startup landmark", "vBSP_init", match="substring"),
        ),
        enabled=True,
    )
    assert t.keep("ERROR: boom")
    assert t.keep("vBSP_init begin")
    assert not t.keep("routine heartbeat tick")


def test_targets_select_preserves_original_line_numbers():
    t = TargetSet(targets=(Target("keep2", "kept", "KEEP", match="substring"),), enabled=True)
    lines = ["drop", "KEEP one", "drop", "KEEP two"]
    assert list(t.select(lines)) == [(1, "KEEP one"), (3, "KEEP two")]


def test_disabled_target_never_matches():
    t = TargetSet(targets=(Target("off", "m", "x", enabled=False),), enabled=True)
    # Only target is disabled → no line qualifies for the whitelist.
    assert not t.keep("xxx")


def test_annotate_returns_matched_targets_when_enabled():
    t = TargetSet(
        targets=(
            Target("stall", "stage stalled", "no progress", match="substring", problem="sgc-stall"),
            Target("bios", "recovery", "nebios", match="substring", problem="reset-storm"),
        ),
        enabled=True,
    )
    hits = t.annotate("SGC: waiting on resource, no progress")
    assert [h.id for h in hits] == ["stall"]
    assert hits[0].meaning == "stage stalled"
    assert hits[0].problem == "sgc-stall"


def test_annotate_empty_when_disabled():
    # Annotation only exists in targeted mode — the switch stays meaningful.
    t = TargetSet(targets=(Target("stall", "m", "no progress", match="substring"),), enabled=False)
    assert t.annotate("no progress here") == []


def test_bad_regex_rejected_at_construction():
    import pytest

    with pytest.raises(Exception):
        Target("bad", "m", "(", match="regex")


def test_bad_match_kind_rejected():
    import pytest

    with pytest.raises(ValueError):
        Target("bad", "m", "x", match="glob")


# --- parse with targets applied -----------------------------------------------


def test_logfile_parse_applies_targets_and_keeps_line_no():
    t = TargetSet(targets=(Target("ms200", "m", "200ms", match="substring"),), enabled=True)
    lf = UbootLog.parse("UBOOT", "[100ms] a\n[200ms] b\n[300ms] c", targets=t)
    (rec,) = lf.records
    assert rec.message == "b"
    assert rec.line_no == 1  # original position preserved despite dropping line 0


# --- YAML config --------------------------------------------------------------


def test_load_shipped_configs_route_filenames():
    cfgset = load_log_configs(Path(__file__).parent.parent / "configs" / "logs")
    assert set(cfgset.configs) == {"uboot", "panic", "cbblog"}
    # UBOOT/hiboot_bootinfo aliasing lives in config, not the class.
    assert cfgset.resolve("UBOOT").log_cls is UbootLog
    assert cfgset.resolve("hiboot_bootinfo").log_cls is UbootLog
    assert cfgset.resolve("panic").log_cls is PanicLog
    assert cfgset.resolve("CBBLOG").log_cls is CbblogLog
    assert cfgset.resolve("unknown_file") is None


def test_shipped_targets_default_off():
    cfgset = load_log_configs(Path(__file__).parent.parent / "configs" / "logs")
    # Lossless by default: shipped target sets are disabled.
    for cfg in cfgset.configs.values():
        assert cfg.target_set.enabled is False


def test_global_switch_neutralises_targets(tmp_path: Path):
    (tmp_path / "uboot.yaml").write_text(
        "type: uboot\n"
        "filenames: [UBOOT]\n"
        "target:\n"
        "  enabled: true\n"
        "  entries:\n"
        "    - id: only-errors\n"
        "      meaning: only errors\n"
        "      match: substring\n"
        "      pattern: ERROR\n"
    )
    on = load_log_configs(tmp_path, targets_enabled=True)
    assert on.resolve("UBOOT").target_set.keep("boring") is False  # targeting active
    off = load_log_configs(tmp_path, targets_enabled=False)
    assert off.resolve("UBOOT").target_set.keep("boring") is True  # master switch off


def test_config_from_yaml_builds_targets(tmp_path: Path):
    (tmp_path / "panic.yaml").write_text(
        "type: panic\n"
        "filenames: [panic]\n"
        "target:\n"
        "  enabled: true\n"
        "  entries:\n"
        "    - id: oops\n"
        "      meaning: kernel oops\n"
        "      match: regex\n"
        "      pattern: Oops\n"
        "      problem: kernel-oops\n"
    )
    cfgset = load_log_configs(tmp_path)
    ts = cfgset.resolve("panic").target_set
    assert ts.enabled
    assert ts.keep("Oops: bad")
    assert not ts.keep("all fine")
    # target carries its problem link + meaning
    (tgt,) = ts.targets
    assert tgt.problem == "kernel-oops"
    assert tgt.meaning == "kernel oops"


def test_missing_config_dir_yields_empty_set(tmp_path: Path):
    cfgset = load_log_configs(tmp_path / "nope")
    assert isinstance(cfgset, LogConfigSet)
    assert cfgset.configs == {}
    assert cfgset.resolve("UBOOT") is None
