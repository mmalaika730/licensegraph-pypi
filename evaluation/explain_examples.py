#!/usr/bin/env python3
"""
explain_examples.py | Section 5 of the brief: explainability and provenance for several answers.
For each question it writes: the question, the retrieved graph facts (each labelled explicit / inferred / prediction),
the final answer (generated text, only when an LLM is configured) and the supporting evidence.
Output: results_iter2/explainability/explainability_examples.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kg_qa.cli import build_qa  # noqa: E402

QUESTIONS = [
    ("E1", "Why is mutagen flagged for acme-mit-app?", "multi-hop chain + rule-derived conflict"),
    ("E2", "Can an Apache-2.0 project depend on a GPL-2.0-only package?", "license-level fact and its symmetric inference + category rule"),
    ("E3", "Which package versions have a copyleft dependency three or more hops below them?", "multi-hop inference"),
    ("E4", "Predict the license of websocket-client", "link-prediction output kept apart from facts"),
    ("E5", "Which license will django 6.0 use?", "insufficient evidence handled without guessing"),
]
LABEL = {"explicit": "EXPLICIT (stored in the graph)", "inferred": "INFERRED (derived by schema or rule)", "prediction": "PREDICTION (model guess, not a fact)"}


def main():
    qa = build_qa(with_llm=True)
    out = ["# Explainability and provenance examples", "",
           "Legend: EXPLICIT = stored triple; INFERRED = derived by OWL 2 RL schema reasoning or by the conflict rule; PREDICTION = TransE link prediction; "
           "GENERATED TEXT = the LLM's natural-language answer, which may only restate the facts above.", ""]
    for qid, q, why in QUESTIONS:
        a = qa.ask(q)
        out += [f"## {qid}. {q}", f"*What it shows: {why}.*  Intent: `{a.intent}`  Status: `{a.status}`", ""]
        if a.queries:
            out += ["**Retrieval:** " + "; ".join(f"`{x}`" for x in a.queries), ""]
        if a.facts:
            out += ["| id | knowledge type | fact | derived by | provenance |", "|---|---|---|---|---|"]
            for f in a.facts:
                out.append(f"| {f.id} | {LABEL[f.kind]} | {f.text} | {f.via or '-'} | {f.source or '-'} |")
            out.append("")
        if a.retrieval_note:
            out += [f"**Retrieval note:** {a.retrieval_note}", ""]
        gen = a.answer if a.status != "llm_unavailable" else "(not generated: no LLM configured when this file was written; run again with the LLM set in .env)"
        out += [f"**GENERATED TEXT (LLM answer):** {gen}", ""]
        if a.cited_ids:
            out += [f"**Facts cited by the answer:** {', '.join(a.cited_ids)}", ""]
        if a.route_note:
            out += [f"**Why no answer:** {a.route_note}", ""]
    d = ROOT / "results_iter2/explainability"
    d.mkdir(parents=True, exist_ok=True)
    (d / "explainability_examples.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
