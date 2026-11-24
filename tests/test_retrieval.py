"""Routing and retrieval tests (no LLM involved)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kg_qa.kg import KG  # noqa: E402
from kg_qa.qa import QA  # noqa: E402
from kg_qa.router import route  # noqa: E402


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


def test_inference_is_not_stored(kg):
    from kg_qa.kg import LG
    from rdflib import URIRef
    proj = URIRef("http://example.org/licensegraph/project/acme-mit-app")
    mut = next(iter(kg.packages["mutagen"]))
    assert (proj, LG.dependsOn, mut) in kg.reasoned and (proj, LG.dependsOn, mut) not in kg.explicit
    assert kg.kind(proj, LG.dependsOn, mut) == "inferred"


def test_conflict_counts_match_iteration1(qa):
    a = qa.ask("Which licenses conflict with acme-mit-app?")
    kinds = " ".join(f.text for f in a.facts)
    assert "mutagen" in kinds and "pylint" in kinds and "unidecode" in kinds and "Incompatible" in kinds
    assert all(f.kind in ("explicit", "inferred") for f in a.facts)


def test_exact_chain(qa):
    a = qa.ask("Through which exact dependency chain does acme-mit-app end up depending on mutagen?")
    assert any("acme-mit-app -> beets/2.14.1 -> mediafile/0.17.0 -> mutagen/1.48.1" in f.text for f in a.facts)


def test_license_pair_uses_symmetric_inference(qa):
    a = qa.ask("Can an Apache-2.0 project depend on a GPL-2.0-only package?")
    assert any("incompatible with" in f.text for f in a.facts)
    assert any(f.kind == "inferred" for f in a.facts if "incompatible with" in f.text)   # stored as GPL -> Apache, asked as Apache -> GPL


def test_all_eval_questions_route(kg):
    for q in json.loads((ROOT / "evaluation/cq_questions.json").read_text(encoding="utf-8")):
        assert route(kg, q["question"]).status == "ok", q["question"]
