#!/usr/bin/env python3
"""
run_queries.py  |  LicenseGraph-PyPI, AI-3001 Iteration 1

Local stand-in for GraphDB: loads the ontology and instance data, materialises the OWL 2 RL
closure, applies the conflict rule R01, runs every Q*.rq query and saves each result as CSV.
For the review, run the same queries in GraphDB (OWL2-RL ruleset) and regenerate the results
from there; this script is for fast checking and for a reproducible record.

Usage
  pip install rdflib owlrl
  python3 run_queries.py --ontology ../Ontology/licensegraph_ontology.ttl ../Ontology/compatibility_rules.ttl \
                         --instances ../RDF_Knowledge_Graph/instances.ttl \
                         --results-dir ../Results

For the inference queries it also runs them on the explicit-only graph (no reasoning) and prints
that row count, which shows the answers are derived, not stored.
"""
import argparse
import csv
import time
from pathlib import Path

import owlrl
from rdflib import RDF, Graph, Namespace

LG = Namespace("http://example.org/licensegraph#")
INFERENCE_QUERIES = ("Q08", "Q09", "Q12")


def conflicts(g):
    return len(set(g.subjects(RDF.type, LG.LicenseConflict)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ontology", required=True, nargs="+", help="schema .ttl plus rules .ttl")
    ap.add_argument("--instances", required=True)
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--queries-dir", default=str(Path(__file__).parent))
    ap.add_argument("--rule-file", default="00_infer_conflicts.ru", help="conflict rule inside --queries-dir")
    args = ap.parse_args()

    qdir, out = Path(args.queries_dir), Path(args.results_dir)
    out.mkdir(parents=True, exist_ok=True)

    explicit = Graph()
    for path in args.ontology:
        explicit.parse(path, format="turtle")
    explicit.parse(args.instances, format="turtle")

    reasoned = Graph()
    for t in explicit:
        reasoned.add(t)
    t0 = time.time()
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, rdfs_closure=False,
                           axiomatic_triples=False, datatype_axioms=False).expand(reasoned)
    errors = [str(o) for _, p, o in reasoned if str(p).endswith("agent-ont#error")]
    print(f"explicit triples: {len(explicit)}   after OWL-RL closure: {len(reasoned)}   "
          f"({time.time() - t0:.1f}s)   consistency errors: {len(errors)}")
    for e in errors[:5]:
        print("  INCONSISTENT:", e)

    rule = (qdir / args.rule_file).read_text(encoding="utf-8")
    before = conflicts(reasoned)
    reasoned.update(rule)
    after = conflicts(reasoned)
    reasoned.update(rule)
    again = conflicts(reasoned)
    print(f"{args.rule_file} conflicts: before rule {before}, after rule {after}, after running it again {again}\n")

    print(f"{'query':<46}{'rows':>6}{'secs':>7}   explicit-only rows")
    for path in sorted(qdir.glob("Q*.rq")):
        text = path.read_text(encoding="utf-8")
        t = time.time()
        res = reasoned.query(text)
        if res.type == "ASK":
            rows, header = [[bool(res.askAnswer)]], ["result"]
        else:
            header = [str(v) for v in res.vars]
            rows = [["" if v is None else str(v) for v in r] for r in res]
        with open(out / f"{path.stem}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        note = ""
        if path.stem.split("_")[0] in INFERENCE_QUERIES:
            note = str(len(list(explicit.query(text))))
        print(f"{path.stem:<46}{len(rows):>6}{time.time() - t:>7.2f}   {note}")
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
