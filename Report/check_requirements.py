#!/usr/bin/env python3
"""check_requirements.py | counts what the submitted files actually contain against the Iteration 1 brief.
Usage: python3 check_requirements.py --root .. --out requirements_check.md   (run from Report/)"""
import argparse
import re
from pathlib import Path
from rdflib import OWL, RDF, RDFS, Graph, Namespace

LG = Namespace("http://example.org/licensegraph#")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--root", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); R = Path(a.root)
    onto = Graph().parse(R / "Ontology/licensegraph_ontology.ttl", format="turtle")
    rules = Graph().parse(R / "Ontology/compatibility_rules.ttl", format="turtle")
    inst = Graph().parse(R / "RDF_Knowledge_Graph/instances.ttl", format="turtle")
    classes = {c for c in onto.subjects(RDF.type, OWL.Class)}
    objp = set(onto.subjects(RDF.type, OWL.ObjectProperty)); datp = set(onto.subjects(RDF.type, OWL.DatatypeProperty))
    constructs = {
        "transitive property": any(onto.subjects(RDF.type, OWL.TransitiveProperty)),
        "symmetric property": any(onto.subjects(RDF.type, OWL.SymmetricProperty)),
        "inverse properties": any(onto.subject_objects(OWL.inverseOf)),
        "property chain axiom": any(onto.subject_objects(OWL.propertyChainAxiom)),
        "subproperty hierarchy": any(onto.subject_objects(RDFS.subPropertyOf)),
        "subclass hierarchy": any(onto.subject_objects(RDFS.subClassOf)),
        "disjoint classes": any(onto.subject_objects(OWL.disjointWith)),
        "functional properties": any(onto.subjects(RDF.type, OWL.FunctionalProperty)),
    }
    qs = sorted((R / "SPARQL_Queries").glob("Q*.rq"))
    text = {q.name: q.read_text(encoding="utf-8") for q in qs}
    def uses(pat): return sorted(n.split("_")[0] for n, t in text.items() if re.search(pat, re.sub(r"(?m)^\s*#.*$", "", t)))
    feats = {"basic graph pattern": [n.split("_")[0] for n in text], "FILTER": uses(r"\bFILTER\b"), "OPTIONAL": uses(r"\bOPTIONAL\b"),
             "UNION": uses(r"\bUNION\b"), "aggregation": uses(r"\b(COUNT|GROUP BY|GROUP_CONCAT)\b"),
             "property path (+ or *)": uses(r"lg:\w+\)?[+*]"), "multi-hop traversal": uses(r"lg:\w+\)?\+|directlyDependsOn\s*\?n2|directlyDependsOn/")}
    inference_q = sorted(n.split("_")[0] for n, t in text.items() if re.search(r"(?m)^#\s*inference:\s*required", t))
    ex = (R / "Results/inference_examples.md").read_text(encoding="utf-8").count("## Example ")
    cq = (R / "Report/competency_questions.md").read_text(encoding="utf-8")
    cq_n = len(re.findall(r"(?m)^\| CQ\d+ \| [^|]+\| [^|]+\|$", cq))
    n_rules = len(set(rules.subjects(RDF.type, LG.CompatibilityRule)))
    csvs = sorted(p.name for p in (R / "Results").glob("Q*.csv"))
    ok = lambda c: "PASS" if c else "FAIL"
    rows = [("Competency questions 12-15", cq_n, 12 <= cq_n <= 15),
            ("Classes >= 10", len(classes), len(classes) >= 10),
            ("Properties >= 8 (object + datatype)", f"{len(objp)} + {len(datp)}", len(objp) + len(datp) >= 8),
            ("Reasoning-enabling constructs >= 3", f"{sum(constructs.values())} ({', '.join(k for k, v in constructs.items() if v)})", sum(constructs.values()) >= 3),
            ("RDF triples >= 500 (instance data)", len(inst), len(inst) >= 500),
            ("SPARQL queries >= 8", len(qs), len(qs) >= 8),
            ("Result file for every query", f"{len(csvs)} of {len(qs)}", len(csvs) >= len(qs)),
            ("Inference-dependent query (marked)", ", ".join(inference_q), len(inference_q) >= 1),
            ("Inferred-fact examples >= 3", ex, ex >= 3),
            ("Curated compatibility rules (assignment idea: 20-30)", n_rules, 20 <= n_rules <= 30)]
    out = ["# Requirements check (generated from the submitted files)", "",
           "| Requirement | Found | Status |", "|---|---|---|"]
    out += [f"| {r} | {f} | {ok(c)} |" for r, f, c in rows]
    out += ["", "## SPARQL feature coverage (query ids that use each feature)", "", "| Feature | Queries |", "|---|---|"]
    out += [f"| {k} | {', '.join(v) or 'NONE'} |" for k, v in feats.items()]
    out += ["", "## Not checkable by script (do these by hand)", "",
            "- Ontology opened in Protégé; graph loaded in GraphDB with the OWL2-RL ruleset; GraphDB screenshots.",
            "- Per-member contributions in the progress report; team name in the ZIP file name."]
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8"); print("\n".join(out))


if __name__ == "__main__":
    main()
