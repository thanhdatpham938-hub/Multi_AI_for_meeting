"""Offline tests for the Mission 3 metrics and the run_eval suites / estimate / rescore (no API)."""

import json
from pathlib import Path

import pytest

from eval import run_eval
from eval.metrics import (
    aggregate_detail,
    evaluate_case,
    format_metric,
)
from meeting_extractor.conflicts import conflict_pairs
from meeting_extractor.models import Item, RunResult, Status, Topic, Utterance

UTTS = [
    Utterance(id="u001", time="00:01", speaker="Hùng", text="Chốt dùng AWS nhé."),
    Utterance(id="u002", time="00:02", speaker="Lan", text="Để anh hỏi sếp đã."),
    Utterance(id="u003", time="00:03", speaker="Nam", text="Sandbox hết hạn sau 15 phút."),
]


def mk(item_id: str = "d01", type_: str = "decision", **kw) -> Item:
    base = dict(item_id=item_id, type=type_, topic_id="t01", topic="T", content="x", evidence=["u001"], confidence=0.8)
    base.update(kw)
    return Item(**base)


def result(items: list[Item], source: str = "tests/fixtures/tc1.txt") -> RunResult:
    return RunResult(run_id="r1", source_file=source, model_light="l", model_strong="s", prompt_versions={},
                     utterances=UTTS, topics=[Topic(topic_id="t01", title="T", utterance_ids=["u001", "u002", "u003"])],
                     items=items)


def counts(items: list[Item], answer: dict | None = None):
    rep = evaluate_case(result(items), answer or {"case": "X", "items": []})
    return rep, aggregate_detail([rep])


def test_no_samples_is_not_applicable():
    _, m = counts([])
    for name in ("unresolved_status_accuracy", "quote_validity", "field_provenance",
                 "knowledge_scope_accuracy", "unflagged_conflicts", "expected_flags_met"):
        assert m[name][0] is None, name
    assert "không áp dụng" in format_metric("quote_validity", None, 0)


def test_small_sample_marked_reference():
    assert "(tham khảo)" in format_metric("quote_validity", 1.0, 9)
    assert "(tham khảo)" not in format_metric("quote_validity", 1.0, 10)
    assert format_metric("unflagged_conflicts", 2.0, 12).startswith("2 ")


def test_unresolved_status_accuracy():
    answer = {"case": "X", "items": [
        {"type": "decision", "status": "deferred", "accept_statuses": ["deferred", "open"], "content": "a", "evidence": ["u002"]},
        {"type": "decision", "status": "confirmed", "content": "b", "evidence": ["u001"]},
    ]}
    ok = mk("d01", status="open", evidence=["u002"])
    _, m = counts([ok, mk("d02", status="confirmed", topic_id="t02")], answer)
    assert m["unresolved_status_accuracy"] == (1.0, 1)
    bad = mk("d01", status="confirmed", evidence=["u002"])
    _, m = counts([bad], answer)
    assert m["unresolved_status_accuracy"] == (0.0, 1)


def test_quote_validity_ignores_old_items_and_checks_substring():
    good = mk("d01", evidence_quotes={"u001": "  chốt DÙNG   aws "})
    bad = mk("d02", evidence_quotes={"u001": "dùng Azure"})
    _, m = counts([good, bad, mk("d03")])
    assert m["quote_validity"] == (0.5, 2)  # the item without quotes is not counted


def test_quote_validity_with_stub_items():
    class Stub:
        def __init__(self, quotes):
            self.evidence_quotes = quotes

    from eval.metrics import invalid_quotes
    texts = {u.id: u.text for u in UTTS}
    assert invalid_quotes(Stub({"u001": "chốt dùng aws"}), texts) == []
    assert invalid_quotes(Stub({"u001": "azure", "u009": "x", "u002": ""}), texts) == ["u001", "u009", "u002"]
    assert invalid_quotes(mk(), texts) == []  # field absent / empty


def test_field_provenance_counts_owner_and_deadline():
    it = mk("a01", "action", owner="Nam", deadline="thứ Sáu")
    _, m = counts([it])
    assert m["field_provenance"] == (0.0, 2)  # old items have no field_evidence


def test_field_provenance_with_stub_attribute():
    class Stub:
        pass

    from eval import metrics
    rep = metrics.CaseReport("X", False, [], [])
    rep.counts = {k: 0 for k in metrics.M3_COUNT_KEYS}
    it = mk("a01", "action", owner="Nam", deadline="mai")
    object.__setattr__(it, "field_evidence", {"owner": ["u001"]})  # simulate the M2 field
    metrics._collect_m3_counts(rep, result([it]), {}, [it])
    assert (rep.counts["prov_ok"], rep.counts["prov_total"]) == (1, 2)


def test_knowledge_scope_accuracy():
    answer = {"case": "X", "items": [
        {"type": "knowledge", "content": "sandbox", "evidence": ["u003"], "knowledge_scope": "reusable"},
        {"type": "knowledge", "content": "no label", "evidence": ["u001"]},
    ]}
    it = mk("k01", "knowledge", evidence=["u003"])
    object.__setattr__(it, "knowledge_scope", "reusable")
    _, m = counts([it], answer)
    assert m["knowledge_scope_accuracy"] == (1.0, 1)
    wrong = mk("k01", "knowledge", evidence=["u003"])
    _, m = counts([wrong], answer)
    assert m["knowledge_scope_accuracy"] == (0.0, 1)


def test_conflicts_unflagged_vs_flagged_vs_superseded():
    conf, live = mk("d01", status="confirmed"), mk("d02", status="proposed")
    assert len(conflict_pairs([conf, live])) == 1
    assert conflict_pairs([conf, mk("d02", status="superseded")]) == []
    _, m = counts([conf, live])
    assert m["unflagged_conflicts"] == (1.0, 2)
    flagged = mk("d02", status="proposed", flags=["conflicting_decision"])
    _, m = counts([conf, flagged])
    assert m["unflagged_conflicts"] == (0.0, 2)


def test_expect_no_conflicts_and_expect_flags_any():
    conf, live = mk("d01", status="confirmed"), mk("d02", status="proposed")
    rep, _ = counts([conf, live], {"case": "X", "items": [], "expect_no_conflicts": True})
    assert any("mâu thuẫn" in e for e in rep.errors)
    rep, m = counts([conf], {"case": "X", "items": [], "expect_flags_any": ["unresolved_reference"]})
    assert any("unresolved_reference" in e for e in rep.errors) and m["expected_flags_met"] == (0.0, 1)
    conf.flags = ["unresolved_reference"]
    rep, m = counts([conf], {"case": "X", "items": [], "expect_flags_any": ["unresolved_reference"]})
    assert not any("mang cờ" in e for e in rep.errors) and m["expected_flags_met"] == (1.0, 1)


# ------------------------------------------------------------------ run_eval: estimate, --yes, rescore


@pytest.fixture
def no_api(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("API must not be called")

    monkeypatch.setattr(run_eval, "make_llm", boom)
    monkeypatch.setattr(run_eval, "run", boom)


def test_estimate_arithmetic():
    short = run_eval.Job("tc1", "short", Path("a"), Path("a"), None, 20, 2)
    long_ = run_eval.Job("c", "long", Path("b"), Path("b"), None, 140, 1)
    assert short.cost == pytest.approx(0.052)
    assert long_.cost == pytest.approx(0.364)
    base, total = run_eval.estimate_cost([short, long_], use_judge=True)
    assert base == pytest.approx(0.416) and total == pytest.approx(0.4576)
    assert run_eval.estimate_cost([short, long_], use_judge=False)[1] == pytest.approx(0.416)


def test_quick_suite_composition():
    jobs, _ = run_eval.collect_jobs("quick", set(), 1, 1)
    names = [j.name for j in jobs]
    assert names.count("case2_kho_du_lieu_khong_ro_rang") == 1
    assert sum(j.suite == "short" for j in jobs) >= 7
    assert all(j.suite == "short" or j.name == "case2_kho_du_lieu_khong_ro_rang" for j in jobs)


def test_exits_without_yes_and_never_calls_api(no_api, capsys):
    code = run_eval.main(["--suite", "quick"])
    out = capsys.readouterr().out
    assert code == run_eval.EXIT_NEED_YES
    assert "Ước tính chi phí" in out and "$" in out


def test_default_suite_is_short_and_also_needs_yes(no_api, capsys):
    assert run_eval.main([]) == run_eval.EXIT_NEED_YES
    assert "case2" not in capsys.readouterr().out


def write_run(runs_dir: Path, run_id: str, res: RunResult) -> Path:
    d = runs_dir / run_id
    d.mkdir(parents=True)
    (d / "result.json").write_text(res.model_dump_json(), encoding="utf-8")
    return d


def tc1_result(status: str) -> RunResult:
    utts = [Utterance(id=f"u{i:03d}", time="00:01", speaker="Hùng (PM)", text="t") for i in range(1, 25)]
    it = mk("d01", status=status, evidence=["u019"])
    res = result([it])
    return res.model_copy(update={"utterances": utts, "run_id": "20260101-tc1"})


def test_rescore_run_dir_by_fixture_name(no_api, tmp_path, capsys):
    d = write_run(tmp_path, "20260101-tc1", tc1_result("confirmed"))
    out_file = tmp_path / "out.md"
    code = run_eval.main(["--rescore", str(d), "--out", str(out_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Bộ ngắn" in out and "Tỷ lệ chốt nhầm | 0.0% (n=1)" in out
    assert out_file.read_text(encoding="utf-8").startswith("# Chấm lại offline")


def test_rescore_latest_json_uses_all_runs_for_stability(no_api, tmp_path, monkeypatch, capsys):
    write_run(tmp_path, "r_a", tc1_result("confirmed"))
    write_run(tmp_path, "r_b", tc1_result("open"))
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"run_ids": {"TC1": ["r_a", "r_b"]}}), encoding="utf-8")
    monkeypatch.setattr(run_eval, "load_settings", lambda: type("S", (), {"runs_dir": tmp_path})())
    assert run_eval.main(["--rescore", str(latest)]) == 0
    out = capsys.readouterr().out
    assert "100.0%" in out and "❌" in out  # stability 100% > 10%


def test_rescore_manual_answer_for_unnamed_run(no_api, tmp_path, capsys):
    res = tc1_result("confirmed").model_copy(update={"source_file": "transcript.txt", "run_id": "20260101-zzz"})
    d = write_run(tmp_path, "20260101-zzz", res)
    assert run_eval.main(["--rescore", str(d)]) == 1  # cannot guess the answer key
    assert "--answer" in capsys.readouterr().err
    answer = run_eval.FIXTURES / "tc1.expected.json"
    assert run_eval.main(["--rescore", str(d), "--answer", f"zzz={answer}"]) == 0
    assert "Chấm lại TC1" in capsys.readouterr().out


def test_rescore_missing_path_is_clean_error(no_api, tmp_path, capsys):
    assert run_eval.main(["--rescore", str(tmp_path / "nope")]) == 2


# ------------------------------------------------------------------ accept_owners


def _action_answer(**extra) -> dict:
    return {"case": "X", "items": [{"type": "action", "content": "a", "evidence": ["u001"], "owner": None, **extra}]}


def test_accept_owners_any_listed_owner_ok_and_not_fabricated():
    answer = _action_answer(accept_owners=["Nam", "lan"])
    for owner in ("Nam", "LAN"):
        rep, m = counts([mk("a01", "action", owner=owner)], answer)
        assert rep.errors == [] and m["fabricated_fields"][0] == 0.0, owner


def test_accept_owners_unlisted_owner_is_wrong_and_fabricated():
    rep, m = counts([mk("a01", "action", owner="Minh")], _action_answer(accept_owners=["Nam"]))
    assert any("Sai owner" in e for e in rep.errors) and m["fabricated_fields"][0] == 1.0


def test_accept_owners_null_in_list_accepts_no_owner():
    answer = _action_answer(accept_owners=["Nam", None])
    assert counts([mk("a01", "action")], answer)[0].errors == []
    rep, _ = counts([mk("a01", "action")], _action_answer(accept_owners=["Nam"]))
    assert any("Sai owner" in e for e in rep.errors)


# ------------------------------------------------------------------ exit code: stability and pipeline errors


class _Usage:
    def to_dict(self):
        return {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd_estimate": 0.0}


class _FakeLLM:
    usage = _Usage()


def patch_runner(monkeypatch, tmp_path, statuses: list):
    """Replace settings/LLM/pipeline so main(--yes) runs offline; `statuses` is consumed one per run
    (a string = TC1 decision with that status, an Exception instance = LLMError raised)."""
    settings = type("S", (), {"model_light": "l", "model_strong": "s", "runs_dir": tmp_path})()
    queue = list(statuses)

    def fake_run(path, meta, llm=None, settings=None):
        nxt = queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return tc1_result(nxt).model_copy(update={"run_id": f"run{len(queue)}"})

    monkeypatch.setattr(run_eval, "load_settings", lambda: settings)
    monkeypatch.setattr(run_eval, "make_llm", lambda s: _FakeLLM())
    monkeypatch.setattr(run_eval, "run", fake_run)
    monkeypatch.setattr(run_eval, "RESULTS", tmp_path / "results")


def test_repeat_with_changing_status_fails_exit_code(monkeypatch, tmp_path, capsys):
    patch_runner(monkeypatch, tmp_path, ["confirmed", "open"])
    code = run_eval.main(["--suite", "short", "--cases", "tc1", "--repeat", "2", "--no-llm-match", "--yes"])
    assert code == 1
    saved = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
    assert saved["metrics"]["stability_change_rate"] == 1.0


def test_repeat_with_stable_status_passes(monkeypatch, tmp_path, capsys):
    patch_runner(monkeypatch, tmp_path, ["confirmed", "confirmed"])
    assert run_eval.main(["--suite", "short", "--cases", "tc1", "--repeat", "2", "--no-llm-match", "--yes"]) == 0


def test_pipeline_error_makes_exit_code_nonzero(monkeypatch, tmp_path, capsys):
    patch_runner(monkeypatch, tmp_path, [run_eval.LLMError("boom")])
    code = run_eval.main(["--suite", "short", "--cases", "tc1", "--no-llm-match", "--yes"])
    assert code == 1
    assert "Pipeline lỗi" in capsys.readouterr().out


def test_failed_repeat_run_recorded_in_notes(monkeypatch, tmp_path, capsys):
    patch_runner(monkeypatch, tmp_path, ["confirmed", run_eval.LLMError("timeout")])
    run_eval.main(["--suite", "short", "--cases", "tc1", "--repeat", "2", "--no-llm-match", "--yes"])
    out = capsys.readouterr().out
    assert "Lần chạy 2 lỗi" in out and "timeout" in out
