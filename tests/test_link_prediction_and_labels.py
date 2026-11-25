"""Tests for the link-prediction component and for keeping predictions apart from facts."""
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


def test_predictions_are_labelled_and_not_facts(qa):
    if qa.predictor is None:
        pytest.skip("model not trained")
    a = qa.ask("Predict the license of websocket-client")
    preds = [f for f in a.facts if f.kind == "prediction"]
    assert preds and all("not a confirmed fact" in f.text for f in preds)


def test_predictions_file_never_uses_hasLicense():
    t = (ROOT / "kg_reasoning/predictions.ttl").read_text(encoding="utf-8")
    body = "\n".join(l for l in t.splitlines() if not l.startswith("#"))
    assert "lg:hasLicense" not in body and "lg:predictedLicense" in body


def test_filtered_rank_skips_other_true_licenses():
    from kg_reasoning.link_prediction import rank_of
    scores = {1: 0.9, 2: 0.8, 3: 0.7, 4: 0.1}
    assert rank_of(scores, 3, set()) == 3
    assert rank_of(scores, 3, {1}) == 2          # license 1 is also a true license of this version, so it is not an error


def test_split_hides_only_license_links_and_is_disjoint():
    import numpy as np
    from kg_reasoning.data import Index, load_triples
    from kg_reasoning.link_prediction import split
    tr, lics, vers = load_triples(ROOT)
    idx = Index(tr)
    X = idx.encode(tr)
    train, test = split(X, idx.rel["hasLicense"], 0.2, np.random.default_rng(0))
    assert set(test[:, 1]) == {idx.rel["hasLicense"]}
    assert not ({tuple(r) for r in train} & {tuple(r) for r in test})
    assert len(train) + len(test) == len(X)


def test_demo_projects_are_not_used_as_observed_data():
    from kg_reasoning.data import load_triples
    tr, _, _ = load_triples(ROOT)
    assert not any("/project/" in h for h, _, _ in tr)


def test_transe_learns_a_toy_graph():
    import numpy as np
    from kg_reasoning.transe import TransE
    X = np.array([[0, 0, 4], [1, 0, 4], [2, 0, 5], [3, 0, 5], [0, 1, 1], [2, 1, 3]])
    m = TransE(6, 2, dim=8, margin=1.0, seed=0).fit(X, epochs=200)
    assert m.score(np.array([0]), 0, np.array([4]))[0] > m.score(np.array([0]), 0, np.array([5]))[0]
