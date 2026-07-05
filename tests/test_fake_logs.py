"""The fake-log generator produces bundles the pipeline parses correctly.

Keeps the synthetic fixtures honest: if the generator or the parsers drift apart,
this fails. Regenerates into a tmp dir (no dependency on committed samples).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from aidbg.logs import BundleKind, load_evidence, load_log_configs

CONFIG_DIR = Path(__file__).parent.parent / "configs" / "logs"
GEN = Path(__file__).parent.parent / "scripts" / "gen_fake_logs.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_fake_logs", GEN)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_fake_logs"] = mod  # dataclass field resolution needs this
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def evidence(tmp_path: Path):
    gen = _load_generator()
    gen.generate(tmp_path)
    return load_evidence(tmp_path, load_log_configs(CONFIG_DIR))


def test_generator_makes_expected_bundles(evidence):
    kinds = {(b.kind, b.index) for b in evidence.bundles}
    assert (BundleKind.BOOT, 0) in kinds
    assert (BundleKind.RUNTIME, 0) in kinds
    assert len(evidence.boots()) == 4


def test_all_boot_bundles_have_three_sources(evidence):
    for b in evidence.boots():
        assert b.get("uboot") is not None
        assert b.get("panic") is not None
        assert b.get("cbblog") is not None
        assert b.unrouted == []


def test_clock_jump_visible_across_panic_records(evidence):
    # First panic record is the 1970 default; last is real time — same file.
    panic = evidence.boots()[0].get("panic").records
    assert panic[0].timestamp.value.year == 1970
    assert panic[-1].timestamp.value.year == 2026


def test_uboot_relative_ms_parsed(evidence):
    u = evidence.boots()[0].get("uboot").records
    assert u[0].timestamp.rel_ms == 0
    assert all(r.timestamp is not None and r.timestamp.rel_ms is not None for r in u)


def test_multiboot_bundle_has_two_nesoft_or_hang(evidence):
    # CBBLOG1 spans a failed boot (stuck, no nesoft end) + a successful one.
    b1 = next(b for b in evidence.boots() if b.index == 1)
    lines = [r.message for r in b1.get("cbblog").records]
    # The successful boot's final process appears; the failed one hangs earlier.
    assert any("nesoft" in m for m in lines)
    assert any("no progress" in m for m in lines)


def test_runtime_bundle_has_no_uboot(evidence):
    rt = evidence.runtime()[0]
    assert rt.get("uboot") is None  # runtime dumps aren't a fresh boot
    assert rt.get("cbblog") is not None
