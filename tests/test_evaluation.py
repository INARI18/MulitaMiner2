"""Evaluation subsystem: scorers, field mapping, alignment, orchestration."""
import pytest

from mulitaminer.evaluation.scorers import SCORERS, pair_score, render_text, text_scorers


# --- scorers -----------------------------------------------------------------


def test_scorers_exact_numeric_and_text():
    exact = SCORERS["exact"].fn
    assert exact(8019, "8019.0") == 1.0
    assert exact("TCP", "tcp") == 1.0
    assert exact(7.5, 7.6) == 0.0
    assert exact("high", "low") == 0.0


def test_scorers_set_f1_known_value():
    set_f1 = SCORERS["set_f1"].fn
    # 1 common item, |a|=2, |b|=3 -> P=0.5, R=1/3, F1=0.4
    a = ["CVE-2021-1234", "CVE-2020-0001"]
    b = ["cve-2021-1234", "CVE-2019-9999", "CVE-2018-8888"]
    assert set_f1(a, b) == pytest.approx(0.4)
    assert set_f1(a, a) == 1.0
    assert set_f1(a, ["CVE-0000-0000"]) == 0.0


def test_scorers_token_f1_known_value():
    token_f1 = SCORERS["token_f1"].fn
    # tokens a: [the, server, is, vulnerable], b: [the, server, responded]
    # common=2, P=2/4, R=2/3 -> F1 = 4/7
    assert token_f1("The server is vulnerable", "the server responded") == pytest.approx(4 / 7)
    assert token_f1("same text", "same text") == 1.0


def test_scorers_rouge_l_known_value():
    rouge_l = SCORERS["rouge_l"].fn
    # a: [a, b, c, d], b: [a, c, d, e] -> LCS [a, c, d] = 3, P=R=3/4, F1=0.75
    assert rouge_l("a b c d", "a c d e") == pytest.approx(0.75)
    # Order matters for LCS (unlike token_f1): reversed sequence scores lower.
    assert rouge_l("a b c", "c b a") == pytest.approx(1 / 3)


def test_scorers_pair_rules_vacuous_and_presence():
    token_f1 = SCORERS["token_f1"]
    assert pair_score(token_f1, [], "") == (1.0, True)
    assert pair_score(token_f1, None, []) == (1.0, True)
    assert pair_score(token_f1, "something", "") == (0.0, False)
    assert pair_score(token_f1, [], "something") == (0.0, False)
    score, vacuous = pair_score(token_f1, "same text", "same text")
    assert score == 1.0 and vacuous is False


def test_scorers_render_text_joins_and_strips():
    assert render_text(["a", None, "b"]) == "a\nb"
    assert render_text({"family": "Web", "empty": None}) == "family: Web"
    assert render_text(None) == ""
    assert render_text("  x  ") == "x"


def test_scorers_bertscore_unavailable_is_safe():
    bert = SCORERS["bertscore"]
    if bert.available:
        pytest.skip("bert-score installed in this environment")
    assert "uv sync --group eval" in bert.hint
    with pytest.raises(RuntimeError, match="eval"):
        bert.fn("a", "b")


def test_scorers_kinds_split():
    assert {s.name for s in text_scorers()} == {"token_f1", "rouge_l", "bertscore"}
    assert SCORERS["exact"].kind == "structural"
    assert SCORERS["set_f1"].kind == "structural"
