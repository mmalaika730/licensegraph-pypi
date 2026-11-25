#!/usr/bin/env python3
"""
evaluate.py | the 10-question comparison: (A) LLM only vs (B) LLM + knowledge graph, same LLM and same settings.

  python evaluation/evaluate.py --retrieval-only    # no LLM needed: checks that the graph retrieval contains the expected facts
  python evaluation/evaluate.py                     # needs the LLM configured in .env; writes raw answers and the comparison table
  python evaluation/evaluate.py --from-raw          # no LLM call: rebuilds the table from the saved raw answers and evaluation/manual_review.csv

Correctness is checked in two ways, and the human review always wins:
  1. automatic: every key term of the expected answer (evaluation/cq_questions.json) appears in the answer;
  2. manual: evaluation/manual_review.csv (columns id, correct_A, correct_B, unsupported_claims_A, unsupported_claims_B, comment).
     Read each answer and fill this file in; the table and the totals use it where present.
The expected answers come from the Iteration 1 SPARQL results (Results/*.csv), not from the application's own retrieval code.
"""
import argparse
import csv
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kg_qa.cli import build_qa  # noqa: E402


def auto_correct(answer: str, keys) -> bool:
    a = answer.lower()
    return all(k.lower() in a for k in keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--from-raw", action="store_true", help="rebuild the table from raw_answers.json without calling the LLM again")
    ap.add_argument("--out", default=str(ROOT / "results_iter2/evaluation"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    qs = json.loads((ROOT / "evaluation/cq_questions.json").read_text(encoding="utf-8"))
    qa = build_qa(with_llm=not (a.retrieval_only or a.from_raw))

    if a.retrieval_only:
        rows, ok = [], 0
        for q in qs:
            r, ent, ret = qa.retrieve(q["question"])
            text = " ".join(f.text for f in ret.facts) if ret else ""
            hit = bool(ret) and auto_correct(text, q["keys"])
            ok += hit
            rows.append({"id": q["id"], "cq": q["cq"], "intent": r.intent, "facts": len(ret.facts) if ret else 0,
                         "retrieved_context_contains_expected_terms": hit})
        with open(out / "retrieval_check.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        for r in rows:
            print(r)
        print(f"\nretrieval contains all expected terms for {ok}/{len(qs)} questions (no LLM involved)")
        return

    if a.from_raw:
        saved = json.loads((out / "raw_answers.json").read_text(encoding="utf-8"))
        meta, raw = saved["meta"], saved["results"]
    else:
        if qa.llm is None:
            sys.exit("No LLM configured. Copy .env.example to .env and fill in LLM_BASE_URL, LLM_MODEL, LLM_API_KEY.")
        raw = []
        for q in qs:
            print(f"[{q['id']}/10] {q['question']}")
            plain = qa.ask_llm_only(q["question"])
            ans = qa.ask(q["question"])
            raw.append({"id": q["id"], "cq": q["cq"], "question": q["question"], "expected": q["expected"],
                        "llm_only": plain, "kg_grounded": ans.answer, "kg_status": ans.status, "intent": ans.intent,
                        "retrieved_fact_ids": [f.id for f in ans.facts], "cited_ids": ans.cited_ids,
                        "facts": [{"id": f.id, "kind": f.kind, "text": f.text} for f in ans.facts],
                        "prompt_sent_to_llm": ans.prompt})
        meta = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"), "llm": qa.llm.name, "temperature": qa.llm.temperature}
        (out / "raw_answers.json").write_text(json.dumps({"meta": meta, "results": raw}, indent=2, ensure_ascii=False), encoding="utf-8")

    manual = {}
    mf = ROOT / "evaluation/manual_review.csv"
    if mf.exists():
        for r in csv.DictReader(open(mf, encoding="utf-8")):
            manual[int(r["id"])] = r
    keys = {q["id"]: q["keys"] for q in qs}
    lines = [f"LLM: {meta['llm']}   temperature: {meta['temperature']}   run: {meta['timestamp']}", "",
             "| CQ / question | Expected answer | LLM only (A) | KG-grounded (B) | Correct? A / B | Evidence available? A / B |",
             "|---|---|---|---|---|---|"]
    tot = {"A": 0, "B": 0}
    ev = {"A": 0, "B": 0}
    for r in raw:
        m = manual.get(r["id"])
        ca = (m["correct_A"].strip().lower() == "yes") if m else auto_correct(r["llm_only"], keys[r["id"]])
        cb = (m["correct_B"].strip().lower() == "yes") if m else auto_correct(r["kg_grounded"], keys[r["id"]])
        eb = bool(r["cited_ids"]) and r["kg_status"] == "answered"
        tot["A"] += ca
        tot["B"] += cb
        ev["B"] += eb
        tag = "" if m else " (auto)"
        lines.append(f"| {r['cq']}: {r['question']} | {r['expected']} | {r['llm_only'].replace(chr(10), ' ')} | {r['kg_grounded'].replace(chr(10), ' ')} | "
                     f"{'Yes' if ca else 'No'} / {'Yes' if cb else 'No'}{tag} | No / {'Yes' if eb else 'No'} |")
    lines += ["", f"Correct (out of 10): LLM only {tot['A']}, KG-grounded {tot['B']}.",
              f"Answers with graph evidence (cited facts): LLM only 0, KG-grounded {ev['B']}.",
              "Correctness marked '(auto)' is a key-term match and must be confirmed by reading the answers (see evaluation/manual_review.csv)."]
    (out / "comparison_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-4:]))
    print(f"wrote {out / 'raw_answers.json'} and {out / 'comparison_table.md'}")


if __name__ == "__main__":
    main()
