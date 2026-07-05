#!/usr/bin/env python3
"""Generate FAKE board logs to exercise the parse pipeline + debug sub-agents.

The real logs live on the company intranet; these are synthetic stand-ins that
model the domain we established (see CLAUDE.md / memory):

- Bundles ``CBBLOG0..N`` (boot, index 0 newest) + ``CBBLOGDUMP0..M`` (runtime).
- Three logs per bundle: ``UBOOT`` (``[<ms>ms]`` since power-on), ``panic``
  (kernel dmesg, ``[YYYYMMDDHHMMSS]`` wall clock that boots at 1970, is bumped to
  1990, then set to real time), ``CBBLOG`` (BSP_DRV user-space,
  ``[YYYY-MM-DD:HH:MM:SS]`` linux time, 1970 until the clock is set).
- Boot paths: normal→soft (主控 sys_clk_init→cpldload→boot→SGC→nesoft; 单板
  initrd→boot→bdsoft); reset-storm→bios (initrd→nebios).
- ``vBSP_init`` begin/end landmarks per process; SGC = serial→parallel point.
- One bundle may span several boots (a failed boot is dumped by the next boot).

NOTE: the CBBLOG *line* format here is an ASSUMPTION (real private layout TBD):
``[YYYY-MM-DD:HH:MM:SS] [pid=<pid> tid=<tid>] [P<process_id>] [<LEVEL>] <msg>``
Only the leading timestamp is what the current parser reads; the rest is so the
lines look realistic and the future CBBLOG field parser has something to chew on.

Run:  uv run python scripts/gen_fake_logs.py [output_dir]
Default output: samples/fake_evidence/
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# process_id catalogue (category label, not launch order / not unique).
PID_NESOFT = 0  # 主控 final process (dumps + clears reserved mem)
PID_BDSOFT = 1  # 单板 final process
PID_BOOT = 3  # sets the real time
PID_INITRD = 4
PID_NEBIOS = 5  # recovery / bios 态
PID_GENERIC = 6  # sys_clk_init / cpldload / SGC / business procs share this


@dataclass
class Stage:
    """One process in a boot sequence."""

    name: str
    process_id: int
    linux_pid: int


# Normal boot sequences (→ soft 态).
MAIN_NORMAL = [
    Stage("sys_clk_init", PID_GENERIC, 120),
    Stage("cpldload", PID_GENERIC, 135),
    Stage("boot", PID_BOOT, 150),
    Stage("SGC", PID_GENERIC, 210),  # serial→parallel transition
    Stage("nesoft", PID_NESOFT, 240),
]
LINE_NORMAL = [
    Stage("initrd", PID_INITRD, 90),
    Stage("boot", PID_BOOT, 150),
    Stage("bdsoft", PID_BDSOFT, 230),
]
# Recovery boot (reset-storm → bios 态).
RECOVERY = [
    Stage("initrd", PID_INITRD, 90),
    Stage("nebios", PID_NEBIOS, 160),
]


# --- wall-clock model --------------------------------------------------------
# The kernel starts at 1970, is bumped to 1990 mid-boot, then set to real time
# by the `boot` process (PID_BOOT). We model that by tracking "seconds since
# kernel start" and mapping to whichever epoch is active at that moment.

_EPOCH_1970 = datetime(1970, 1, 1)
_EPOCH_1990 = datetime(1990, 1, 1)


@dataclass
class Clock:
    """Maps 'seconds since kernel start' → the wall clock visible at that time."""

    real_start: datetime  # real time the kernel came up (for the REAL phase)
    bump_1990_at: float = 8.0  # secs after kernel start when time := 1990
    set_real_at: float = 18.0  # secs after kernel start when `boot` sets real time

    def at(self, secs: float) -> datetime:
        if secs < self.bump_1990_at:
            return _EPOCH_1970 + timedelta(seconds=secs)
        if secs < self.set_real_at:
            return _EPOCH_1990 + timedelta(seconds=secs - self.bump_1990_at)
        return self.real_start + timedelta(seconds=secs)

    def panic_ts(self, secs: float) -> str:
        return self.at(secs).strftime("[%Y%m%d%H%M%S]")

    def cbblog_ts(self, secs: float) -> str:
        return self.at(secs).strftime("[%Y-%m-%d:%H:%M:%S]")


@dataclass
class BootLogs:
    """Accumulates the three log streams for one simulated boot."""

    uboot: list[str] = field(default_factory=list)
    panic: list[str] = field(default_factory=list)
    cbblog: list[str] = field(default_factory=list)

    def cbb(self, clock: Clock, secs: float, st: Stage, level: str, msg: str) -> None:
        ts = clock.cbblog_ts(secs)
        self.cbblog.append(
            f"{ts} [pid={st.linux_pid} tid={st.linux_pid}] [P{st.process_id}] [{level}] {msg}"
        )


# --- one boot simulation -----------------------------------------------------


def simulate_boot(
    real_start: datetime,
    stages: list[Stage],
    *,
    stop_after: int | None = None,
    hang_in_last: bool = False,
    into: BootLogs | None = None,
) -> BootLogs:
    """Simulate one boot into ``into`` (a fresh :class:`BootLogs` if omitted).

    ``stop_after`` truncates the boot after N stages (a failed boot that never
    reached the final process). ``hang_in_last`` prints a ``vBSP_init begin`` for
    the last reached stage but no matching ``end`` (stuck in that process).
    """
    lb = into or BootLogs()
    clock = Clock(real_start=real_start)

    # Bootloader: relative-ms timestamps, ends by handing off to the kernel.
    lb.uboot.append("[0ms] UBOOT: power-on reset")
    lb.uboot.append("[45ms] UBOOT: DDR init done")
    lb.uboot.append("[120ms] UBOOT: loading kernel image")
    lb.uboot.append("[260ms] UBOOT: Starting kernel ...")

    # Kernel (panic log): epoch time = kernel-start + uptime.
    lb.panic.append(f"{clock.panic_ts(0.2)} Linux version 5.10 booting")
    lb.panic.append(f"{clock.panic_ts(1.5)} SoC clock tree initialised")
    lb.panic.append(f"{clock.panic_ts(3.0)} eth0: MAC driver probe ok")
    lb.panic.append(f"{clock.panic_ts(9.0)} rtc: system time bumped to 1990 default")
    lb.panic.append(f"{clock.panic_ts(20.0)} userspace: init handoff")

    reached = stages if stop_after is None else stages[:stop_after]
    base = 22.0  # secs after kernel start when user-space starts coming up
    for i, st in enumerate(reached):
        t = base + i * 4.0
        lb.cbb(clock, t, st, "INFO", f"vBSP_init begin process={st.name}")
        last = i == len(reached) - 1
        if last and hang_in_last:
            lb.cbb(clock, t + 1.0, st, "WARN", f"{st.name}: waiting on resource, no progress")
            break  # no matching end → hung
        if st.name == "boot":
            lb.cbb(clock, t + 0.5, st, "INFO", "boot: system time set to real time")
        lb.cbb(clock, t + 1.5, st, "INFO", f"vBSP_init end process={st.name}")
    return lb


def runtime_dump(real_start: datetime) -> BootLogs:
    """A runtime (CBBLOGDUMP) snapshot: board already in soft 态, then a fault.

    Runtime dumps don't clear reserved memory; here we show a link-flap issue
    that surfaces hours after boot (the class of problem CBBLOGDUMP is for).
    """
    lb = BootLogs()
    clock = Clock(real_start=real_start, bump_1990_at=-1, set_real_at=-1)  # already real time
    sg = Stage("nesoft", PID_NESOFT, 240)
    biz = Stage("ethmgr", PID_GENERIC, 512)
    lb.cbb(clock, 0.0, sg, "INFO", "runtime: heartbeat ok")
    lb.panic.append(f"{clock.panic_ts(3600.0)} eth0: PHY link down (autoneg lost)")
    lb.cbb(clock, 3600.5, biz, "ERROR", "eth0 link flap detected, carrier lost")
    lb.panic.append(f"{clock.panic_ts(3603.0)} eth0: PHY link up, 1000Mbps full-duplex")
    lb.cbb(clock, 3603.5, biz, "WARN", "eth0 recovered after 3s outage")
    return lb


# --- scenarios → bundle folders ----------------------------------------------


def _write_bundle(root: Path, name: str, lb: BootLogs) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    if lb.uboot:
        (d / "UBOOT").write_text("\n".join(lb.uboot) + "\n", encoding="utf-8")
    if lb.panic:
        (d / "panic").write_text("\n".join(lb.panic) + "\n", encoding="utf-8")
    if lb.cbblog:
        (d / "CBBLOG").write_text("\n".join(lb.cbblog) + "\n", encoding="utf-8")


def generate(out: Path) -> list[str]:
    """Build the sample evidence tree. Returns the list of bundle names made."""
    t0 = datetime(2026, 7, 4, 10, 20, 0)
    made: list[str] = []

    # CBBLOG0: healthy 主控 boot → soft 态 (the baseline good case).
    _write_bundle(out, "CBBLOG0", simulate_boot(t0, MAIN_NORMAL))
    made.append("CBBLOG0")

    # CBBLOG1: ONE bundle spanning TWO boots — first failed (stuck in SGC, never
    # reached nesoft, so not dumped that boot), second succeeded and dumped both.
    span = simulate_boot(t0 - timedelta(minutes=5), MAIN_NORMAL, stop_after=4, hang_in_last=True)
    simulate_boot(t0 - timedelta(minutes=3), MAIN_NORMAL, into=span)  # 2nd boot, appended
    _write_bundle(out, "CBBLOG1", span)
    made.append("CBBLOG1")

    # CBBLOG2: reset-storm → recovery/bios 态 (initrd→nebios).
    _write_bundle(out, "CBBLOG2", simulate_boot(t0 - timedelta(minutes=10), RECOVERY))
    made.append("CBBLOG2")

    # CBBLOG3: healthy 单板 boot → soft 态.
    _write_bundle(out, "CBBLOG3", simulate_boot(t0 - timedelta(minutes=20), LINE_NORMAL))
    made.append("CBBLOG3")

    # CBBLOGDUMP0: runtime link-flap (surfaces hours after boot).
    _write_bundle(out, "CBBLOGDUMP0", runtime_dump(t0))
    made.append("CBBLOGDUMP0")
    return made


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/fake_evidence")
    out.mkdir(parents=True, exist_ok=True)
    made = generate(out)
    print(f"wrote {len(made)} fake bundles to {out}/:")
    for name in made:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
