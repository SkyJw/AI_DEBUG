"""Evidence-package (Bundle) layer: name parsing, folder/tgz loading, routing.

Structural only — asserts loading/routing/ordering, never boot segmentation
(a bundle may span several boots by design; splitting it is a later layer).
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from aidbg.logs import (
    Bundle,
    BundleKind,
    Evidence,
    load_evidence,
    load_log_configs,
    parse_bundle_name,
)

CONFIG_DIR = Path(__file__).parent.parent / "configs" / "logs"


@pytest.fixture
def configs():
    return load_log_configs(CONFIG_DIR)


# --- name parsing ------------------------------------------------------------


def test_parse_boot_bundle_name():
    assert parse_bundle_name("CBBLOG0") == (BundleKind.BOOT, 0)
    assert parse_bundle_name("CBBLOG11.TGZ") == (BundleKind.BOOT, 11)


def test_parse_runtime_bundle_name_not_confused_with_boot():
    # CBBLOGDUMP has CBBLOG as a prefix — must not misclassify as BOOT.
    assert parse_bundle_name("CBBLOGDUMP0") == (BundleKind.RUNTIME, 0)
    assert parse_bundle_name("CBBLOGDUMP2.tar.gz") == (BundleKind.RUNTIME, 2)


def test_parse_unknown_name_is_tolerant():
    assert parse_bundle_name("random.txt") == (BundleKind.UNKNOWN, -1)


# --- folder loading ----------------------------------------------------------


def _write_boot_folder(root: Path, name: str = "CBBLOG0") -> Path:
    d = root / name
    d.mkdir()
    (d / "UBOOT").write_text("[100ms] boot start\n[200ms] Starting kernel\n")
    (d / "panic").write_text("[19700101000012] soc probe\n[20260630102045] clock set\n")
    (d / "CBBLOG").write_text("[2026-07-04:15:12:30] vBSP_init begin nesoft\n")
    (d / "misc.dat").write_text("nobody routes me\n")
    return d


def test_bundle_load_from_folder_routes_all_sources(tmp_path: Path, configs):
    d = _write_boot_folder(tmp_path)
    b = Bundle.load(d, configs)
    assert b.kind is BundleKind.BOOT
    assert b.index == 0
    assert set(b.logs) == {"uboot", "panic", "cbblog"}
    assert b.get("uboot") is not None
    assert b.unrouted == ["misc.dat"]


def test_bundle_load_filter_off_is_lossless(tmp_path: Path, configs):
    d = _write_boot_folder(tmp_path)
    b = Bundle.load(d, configs)
    # Shipped configs ship filters disabled → every line kept.
    assert len(b.get("uboot")) == 2
    assert len(b.get("panic")) == 2
    assert len(b.get("cbblog")) == 1


def test_bundle_hiboot_alias_routes_to_uboot(tmp_path: Path, configs):
    d = tmp_path / "CBBLOG1"
    d.mkdir()
    (d / "hiboot_bootinfo").write_text("[50ms] hi\n")
    b = Bundle.load(d, configs)
    assert b.get("uboot") is not None
    assert b.index == 1


def test_bundle_missing_source_is_none(tmp_path: Path, configs):
    d = tmp_path / "CBBLOG2"
    d.mkdir()
    (d / "panic").write_text("[19700101000001] only panic here\n")
    b = Bundle.load(d, configs)
    assert b.get("panic") is not None
    assert b.get("uboot") is None  # retention windows differ; missing is normal
    assert b.get("cbblog") is None


# --- tarball loading ---------------------------------------------------------


def test_bundle_load_from_tgz(tmp_path: Path, configs):
    # Build a real .tgz with the three logs inside.
    src = tmp_path / "stage"
    src.mkdir()
    (src / "UBOOT").write_text("[10ms] a\n")
    (src / "panic").write_text("[19700101000005] b\n")
    (src / "CBBLOG").write_text("[2026-07-04:00:00:01] c\n")
    tgz = tmp_path / "CBBLOG3.TGZ"
    with tarfile.open(tgz, "w:gz") as tar:
        for f in src.iterdir():
            tar.add(f, arcname=f.name)

    b = Bundle.load(tgz, configs)
    assert b.kind is BundleKind.BOOT
    assert b.index == 3
    assert set(b.logs) == {"uboot", "panic", "cbblog"}


# --- evidence discovery ------------------------------------------------------


def test_load_evidence_discovers_and_orders(tmp_path: Path, configs):
    _write_boot_folder(tmp_path, "CBBLOG0")
    _write_boot_folder(tmp_path, "CBBLOG2")
    dump = tmp_path / "CBBLOGDUMP0"
    dump.mkdir()
    (dump / "CBBLOG").write_text("[2026-07-04:16:00:00] runtime line\n")
    (tmp_path / "not_a_bundle").mkdir()  # ignored

    ev = load_evidence(tmp_path, configs)
    assert isinstance(ev, Evidence)
    assert [(b.kind, b.index) for b in ev.boots()] == [(BundleKind.BOOT, 0), (BundleKind.BOOT, 2)]
    assert [(b.kind, b.index) for b in ev.runtime()] == [(BundleKind.RUNTIME, 0)]


def test_load_evidence_missing_root_is_empty(tmp_path: Path, configs):
    ev = load_evidence(tmp_path / "nope", configs)
    assert ev.bundles == []
