"""Problem catalogue + bidirectional target↔problem link consistency.

The shipped configs/logs/*.yaml (targets) and configs/problems.yaml (problems)
must stay in sync: every target→problem link resolves, and every problem→target
back-reference resolves. This test guards that invariant.
"""

from __future__ import annotations

from pathlib import Path

from aidbg.logs import (
    Problem,
    ProblemCatalog,
    check_links,
    load_log_configs,
    load_problems,
)

ROOT = Path(__file__).parent.parent
LOGS_DIR = ROOT / "configs" / "logs"
PROBLEMS_FILE = ROOT / "configs" / "problems.yaml"


def test_load_problem_catalogue():
    cat = load_problems(PROBLEMS_FILE)
    assert isinstance(cat, ProblemCatalog)
    assert len(cat) >= 5
    p = cat.get("sgc-stall")
    assert isinstance(p, Problem)
    assert p.title
    assert p.likely_causes
    assert p.verify_steps
    assert "cbblog-stage-stall" in p.targets  # back-reference to its signature


def test_missing_problems_file_is_empty():
    cat = load_problems(ROOT / "configs" / "nope.yaml")
    assert len(cat) == 0
    assert cat.get("anything") is None


def test_shipped_target_problem_links_are_consistent():
    cfgset = load_log_configs(LOGS_DIR)
    cat = load_problems(PROBLEMS_FILE)
    targets = cfgset.all_targets()
    target_ids = {t.id for t in targets}
    problem_refs = {t.problem for t in targets if t.problem}

    issues = check_links(cat, target_ids, problem_refs)
    assert issues == [], f"link inconsistencies: {issues}"


def test_bidirectional_links_mirror_each_other():
    # Every target→problem link should be mirrored by problem→target, and vice versa.
    cfgset = load_log_configs(LOGS_DIR)
    cat = load_problems(PROBLEMS_FILE)
    targets = cfgset.all_targets()

    for t in targets:
        if not t.problem:
            continue
        prob = cat.get(t.problem)
        assert prob is not None, f"target {t.id} → missing problem {t.problem}"
        assert t.id in prob.targets, (
            f"target {t.id} links problem {t.problem}, but problem does not list it back"
        )

    by_id = {t.id: t for t in targets}
    for prob in cat.problems.values():
        for tid in prob.targets:
            assert tid in by_id, f"problem {prob.id} → unknown target {tid}"
            assert by_id[tid].problem == prob.id, (
                f"problem {prob.id} lists target {tid}, but target links {by_id[tid].problem!r}"
            )


def test_check_links_flags_unknown_problem():
    cat = load_problems(PROBLEMS_FILE)
    issues = check_links(cat, target_ids={"t1"}, target_problem_refs={"does-not-exist"})
    assert any("does-not-exist" in i for i in issues)
