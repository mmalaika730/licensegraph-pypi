"""Unit tests. The stub LLM below exists ONLY to test the pipeline's plumbing; it is never used for the reported evaluation."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kg_qa.kg import KG  # noqa: E402
from kg_qa.qa import QA  # noqa: E402
from kg_qa.router import route  # noqa: E402


class StubLLM:
    name = "stub (tests only)"

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, system, user):
        self.calls.append((system, user))
        return self.reply


@pytest.fixture(scope="module")
def kg():
    return KG(ROOT)


@pytest.fixture(scope="module")
def qa(kg):
    try:
        from kg_reasoning.predictor import Predictor
        pred = Predictor(ROOT / "kg_reasoning/model")
    except Exception:
        pred = None
    return QA(kg, None, pred, ROOT)


@pytest.mark.parametrize("q", ["What is the capital of France?", "Will my company get sued if I ship acme-mit-app?",
                               "Does the package nonexistent-lib have license conflicts?", "Which license will django 6.0 use?"])
def test_insufficient_evidence_never_calls_llm(kg, q):
    llm = StubLLM("SHOULD NOT BE USED")
    a = QA(kg, llm, None, ROOT).ask(q)
    assert a.status == "insufficient_evidence" and a.answer.startswith("Insufficient evidence")
    assert llm.calls == []


def test_grounded_prompt_contains_only_retrieved_facts(kg):
    llm = StubLLM("mutagen conflicts [F1].")
    a = QA(kg, llm, None, ROOT).ask("Why is mutagen flagged for acme-mit-app?")
    system, user = llm.calls[0]
    assert "ONLY the facts given" in system and "F1 [" in user and "mutagen" in user
    assert a.cited_ids == ["F1"] and not a.uncited_warning


def test_uncited_answer_is_flagged(kg):
    a = QA(kg, StubLLM("It is incompatible."), None, ROOT).ask("Why is mutagen flagged for acme-mit-app?")
    assert a.uncited_warning


def test_no_secrets_in_repo():
    import re
    rx = re.compile(r"sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|gsk_[A-Za-z0-9]{20,}|Bearer [A-Za-z0-9._-]{20,}")
    assert not (ROOT / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".md", ".txt", ".json", ".example", ".toml", ".ttl", ".csv"} and not ({".git", ".venv", "venv", "__pycache__", "node_modules"} & set(p.parts)):
            assert not rx.search(p.read_text(encoding="utf-8", errors="ignore")), p
