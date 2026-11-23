#!/usr/bin/env python3
"""
inference_examples.py | proves that selected facts are INFERRED, not stored, and writes
Results/inference_examples.md in the required form: Explicit Facts -> Rule/Schema Knowledge -> Inferred Fact.

For each example it checks three things programmatically:
  1. every explicit fact is in the stored graph (ontology + instances),
  2. the inferred triple is NOT in the stored graph,
  3. the inferred triple IS in the graph after OWL 2 RL reasoning (+ conflict rule for example 4).

Usage: python3 inference_examples.py --ontology schema.ttl rules.ttl --instances instances.ttl \
         --rule 00_infer_conflicts.ru --out ../Results/inference_examples.md
"""
import argparse
from rdflib import RDF, RDFS, Graph, Namespace, URIRef
import owlrl

LG = Namespace("http://example.org/licensegraph#")
B = "http://example.org/licensegraph/"


def short(u):
    s = str(u)
    for p, n in ((B + "ver/", "ver:"), (B + "project/", "project:"), (B + "license/", "license:"),
                 (B + "rule/", "rule:"), (str(LG), "lg:"), (str(RDFS), "rdfs:"), (str(RDF), "rdf:")):
        if s.startswith(p):
            return n + s[len(p):]
    return s


def fmt(t):
    return f"`{short(t[0])} {short(t[1])} {short(t[2])}`"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ontology", nargs="+", required=True)
    ap.add_argument("--instances", required=True)
    ap.add_argument("--rule", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    stored = Graph()
    for p in a.ontology:
        stored.parse(p, format="turtle")
    stored.parse(a.instances, format="turtle")
    closed = Graph()
    for t in stored:
        closed.add(t)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, rdfs_closure=False, axiomatic_triples=False,
                           datatype_axioms=False).expand(closed)
    after_rule = Graph()
    for t in closed:
        after_rule.add(t)
    after_rule.update(open(a.rule, encoding="utf-8").read())

    proj = URIRef(B + "project/acme-mit-app")
    mutagen = next(s for s in stored.subjects(RDF.type, LG.PackageVersion)
                   if str(s).startswith(B + "ver/mutagen/"))
    gpl = URIRef(B + "license/GPL-2.0-or-later")
    chain, node = [proj], proj
    # follow the stored directlyDependsOn edges breadth-first to find one chain proj -> mutagen
    from collections import deque
    prev, dq, seen = {}, deque([proj]), {proj}
    while dq:
        n = dq.popleft()
        if n == mutagen:
            break
        for m in stored.objects(n, LG.directlyDependsOn):
            if m not in seen:
                seen.add(m); prev[m] = n; dq.append(m)
    chain = [mutagen]
    while chain[-1] != proj:
        chain.append(prev[chain[-1]])
    chain.reverse()
    chain_edges = [(chain[i], LG.directlyDependsOn, chain[i + 1]) for i in range(len(chain) - 1)]

    conflict = None
    for c in after_rule.subjects(RDF.type, LG.LicenseConflict):
        if (c, LG.conflictProject, proj) in after_rule and (c, LG.conflictDependency, mutagen) in after_rule:
            conflict = c
    assert conflict is not None, "no conflict derived for acme-mit-app/mutagen"
    rule = next(after_rule.objects(conflict, LG.conflictRule))
    verdict = next(after_rule.objects(conflict, LG.conflictVerdict))
    pc = next(after_rule.objects(rule, LG.projectCategory)); dc = next(after_rule.objects(rule, LG.dependencyCategory))
    proj_lic = next(stored.objects(proj, LG.hasLicense)); mut_lic = next(stored.objects(mutagen, LG.hasLicense))

    examples = [
        ("Transitive dependency (transitive property + subproperty)",
         chain_edges,
         ["`lg:directlyDependsOn rdfs:subPropertyOf lg:dependsOn`", "`lg:dependsOn a owl:TransitiveProperty`"],
         (proj, LG.dependsOn, mutagen), closed),
        ("License category (subclass reasoning)",
         [(gpl, RDF.type, LG.StrongCopyleftLicense)],
         ["`lg:StrongCopyleftLicense rdfs:subClassOf lg:CopyleftLicense`"],
         (gpl, RDF.type, LG.CopyleftLicense), closed),
        ("License anywhere in the tree (property chain)",
         chain_edges + [(mutagen, LG.hasLicense, gpl)],
         ["`lg:treeContainsLicense owl:propertyChainAxiom ( lg:dependsOn lg:hasLicense )`",
          "`lg:dependsOn a owl:TransitiveProperty`; `lg:directlyDependsOn rdfs:subPropertyOf lg:dependsOn`"],
         (proj, LG.treeContainsLicense, gpl), closed),
        ("License conflict (curated compatibility rule + rule R01)",
         chain_edges + [(proj, LG.hasLicense, proj_lic), (mutagen, LG.hasLicense, mut_lic),
                        (proj_lic, RDF.type, next(t for t in stored.objects(proj_lic, RDF.type) if t != URIRef("http://www.w3.org/2002/07/owl#NamedIndividual"))),
                        (mut_lic, RDF.type, next(t for t in stored.objects(mut_lic, RDF.type) if str(t).startswith(str(LG))))],
         [f"`{short(rule)} lg:projectCategory {short(pc)} ; lg:dependencyCategory {short(dc)} ; lg:verdict {short(verdict)}`",
          "Rule file `00_infer_conflicts.ru` (INSERT ... WHERE with `lg:dependsOn`-style path and `a/rdfs:subClassOf*`)"],
         (conflict, RDF.type, LG.LicenseConflict), after_rule),
    ]
    out = ["# Inference examples (Explicit facts -> Rule/Schema knowledge -> Inferred fact)", "",
           f"Computed on the real graph: {len(stored)} stored triples (schema + rules + data); "
           f"{len(closed)} after OWL 2 RL reasoning; conflict rule R01 applied on top.", "",
           "Each example was verified by script: explicit facts are in the stored graph, the inferred triple is "
           "**absent** from the stored graph and **present** after reasoning.", ""]
    for i, (title, facts, schema, inferred, graph) in enumerate(examples, 1):
        ok_exp = all(f in stored for f in facts)
        not_stored = inferred not in stored
        derived = inferred in graph
        assert ok_exp and not_stored and derived, (title, ok_exp, not_stored, derived)
        out += [f"## Example {i}: {title}", "", "**Explicit facts (stored)**", ""]
        out += [f"- {fmt(f)}" for f in facts]
        out += ["", "**Rule / schema knowledge**", ""] + [f"- {s}" for s in schema]
        out += ["", "**Inferred fact (never stored)**", "", f"- {fmt(inferred)}", ""]
        if i == 4:
            out += [f"  - rule: `{short(rule)}`, verdict: `{short(verdict)}`, dependency: `{short(mutagen)}`", ""]
        out += [f"Check: explicit facts stored = {ok_exp}; inferred triple stored = {not not_stored}; "
                f"inferred after reasoning = {derived}", ""]
    open(a.out, "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
