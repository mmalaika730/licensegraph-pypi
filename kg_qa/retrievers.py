"""
retrievers.py | the KG retrieval layer. Each retriever takes resolved entities, queries the graph and
returns a Retrieval: a list of numbered Facts, each tagged explicit / inferred / prediction, plus the
SPARQL or procedure that produced it.

Nothing here calls an LLM. The LLM only sees what these functions return.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rdflib import RDF, Literal

from .kg import KG, LG, RULE, short

EXPLICIT, INFERRED, PREDICTION = "explicit", "inferred", "prediction"


@dataclass
class Fact:
    text: str                       # one readable sentence
    kind: str                       # explicit | inferred | prediction
    via: str = ""                   # how it was derived (rule id, property chain, model name ...)
    source: str = ""                # provenance: where the underlying data or rule comes from
    id: str = ""                    # F1, F2 ... assigned later


@dataclass
class Retrieval:
    intent: str
    description: str
    facts: list = field(default_factory=list)
    queries: list = field(default_factory=list)     # SPARQL or procedure text shown to the user
    note: str = ""                                    # for example "no copyleft dependencies found"

    def number(self):
        for i, f in enumerate(self.facts, 1):
            f.id = f"F{i}"
        return self


def _lic_text(kg: KG, lic) -> str:
    return f"{kg.spdx(lic)} ({kg.category_of(lic)})"


def _data_source(kg: KG, node) -> str:
    src = kg.explicit.value(node, LG.licenseSource)
    return f"PyPI metadata, license value from '{src}'" if src else "curated demo project (Dataset/curated/projects.csv)"


# ---------------------------------------------------------------------------------------------
def license_of(kg: KG, nodes, **_):
    r = Retrieval("license_of", "Declared license(s) of a package version or project")
    r.queries.append("?node lg:hasLicense ?lic . ?lic lg:spdxId ?id . ?lic a ?category  (explicit triples)")
    for n in nodes:
        for lic in kg.license_of(n):
            r.facts.append(Fact(f"{kg.node_label(n)} has license {_lic_text(kg, lic)}.", EXPLICIT,
                                "stored triple lg:hasLicense", _data_source(kg, n)))
            if kg.explicit.value(n, LG.isDisjunctiveLicense) == Literal(True):
                decl = kg.explicit.value(n, LG.declaredLicenseString)
                r.facts.append(Fact(f"{kg.node_label(n)} is dual-licensed; declared as \"{decl}\" (the user may choose one option).",
                                    EXPLICIT, "stored triple lg:isDisjunctiveLicense", _data_source(kg, n)))
    return r


def direct_deps(kg: KG, nodes, **_):
    r = Retrieval("direct_deps", "Direct dependencies of a package version or project")
    r.queries.append("?node lg:directlyDependsOn ?dep . OPTIONAL { ?dep lg:hasLicense ?lic }")
    for n in nodes:
        for d in kg.direct_deps(n):
            lic = ", ".join(kg.spdx(x) for x in kg.license_of(d)) or "no license recorded"
            r.facts.append(Fact(f"{kg.node_label(n)} directly depends on {short(d)} (license {lic}).", EXPLICIT,
                                "stored triple lg:directlyDependsOn", "pip resolver output, Dataset/pypi/direct_edges.csv"))
    return r


def _tree(kg: KG, n):
    return sorted(kg.reachable(n), key=str)


def tree_licenses(kg: KG, nodes, **_):
    r = Retrieval("tree_licenses", "All licenses that appear anywhere in the dependency tree")
    r.queries.append("?node lg:directlyDependsOn+ ?dep . ?dep lg:hasLicense ?lic . GROUP BY ?lic   "
                     "(same result as the property chain lg:treeContainsLicense)")
    for n in nodes:
        counts = {}
        for d in _tree(kg, n):
            for lic in kg.license_of(d):
                counts.setdefault(lic, []).append(short(d))
        if not counts:
            r.note = "The graph records no dependencies for this node."
        for lic, who in sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            ex = ", ".join(who[:4]) + (" ..." if len(who) > 4 else "")
            r.facts.append(Fact(f"The dependency tree of {kg.node_label(n)} contains license {_lic_text(kg, lic)} "
                                f"in {len(who)} package version(s), for example {ex}.", INFERRED,
                                "transitive closure of lg:directlyDependsOn + lg:hasLicense (property chain lg:treeContainsLicense)",
                                "derived from PyPI dependency data"))
    return r


def copyleft_chains(kg: KG, nodes, **_):
    r = Retrieval("copyleft_chains", "Copyleft licenses in the dependency tree with the exact chain that introduces each")
    r.queries.append("?node lg:directlyDependsOn+ ?dep . ?dep lg:hasLicense/a/rdfs:subClassOf* lg:CopyleftLicense ; "
                     "then every directlyDependsOn path from ?node to ?dep is listed")
    for n in nodes:
        tree = _tree(kg, n)
        cl = {d: [l for l in kg.license_of(d) if kg.is_copyleft(l)] for d in tree}
        cl = {d: ls for d, ls in cl.items() if ls}
        if not cl:
            r.note = f"No copyleft license was found anywhere below {kg.node_label(n)} in the graph."
        for d, ls in sorted(cl.items(), key=lambda kv: str(kv[0])):
            for lic in ls:
                r.facts.append(Fact(f"{kg.node_label(n)} depends (transitively) on {short(d)}, which has copyleft license "
                                    f"{_lic_text(kg, lic)}.", INFERRED,
                                    "transitivity of lg:dependsOn; copyleft membership through rdfs:subClassOf",
                                    "derived from PyPI dependency data"))
        for path in kg.all_paths(n, cl.keys()):
            end = path[-1]
            lics = ", ".join(kg.spdx(x) for x in cl[end])
            r.facts.append(Fact(f"Chain ({len(path) - 1} hops, introduces {lics}): "
                                + " -> ".join(kg.node_label(x) for x in path) + ".", EXPLICIT,
                                "each arrow is a stored lg:directlyDependsOn edge", "pip resolver output"))
    return r


def dependency_chains(kg: KG, nodes, targets=(), **_):
    r = Retrieval("dependency_chains", "Exact dependency chain(s) from a node to a target package")
    r.queries.append("every lg:directlyDependsOn path from ?node to ?target (graph traversal over stored edges)")
    tgt = [v for t in targets for v in t]
    for n in nodes:
        paths = kg.all_paths(n, tgt)
        if not paths:
            r.note = f"No dependency path from {kg.node_label(n)} to the target was found in the graph."
        for p in paths:
            lic = ", ".join(kg.spdx(x) for x in kg.license_of(p[-1]))
            r.facts.append(Fact(f"{kg.node_label(n)} reaches {short(p[-1])} (license {lic}) through the chain "
                                + " -> ".join(kg.node_label(x) for x in p) + ".", EXPLICIT,
                                "each arrow is a stored lg:directlyDependsOn edge", "pip resolver output"))
        if paths:
            r.facts.append(Fact(f"{kg.node_label(n)} lg:dependsOn {short(paths[0][-1])} holds, although it is not stored "
                                f"directly (transitive dependency).", INFERRED, "transitivity of lg:dependsOn", ""))
    return r


def dependents(kg: KG, targets=(), **_):
    r = Retrieval("dependents", "Which projects and packages reach the target package anywhere below them")
    r.queries.append("?x lg:directlyDependsOn+ ?target   (reverse transitive path)")
    tgt = {v for t in targets for v in t}
    reached = []
    for x in sorted(set(kg.explicit.subjects(LG.directlyDependsOn, None)), key=str):
        if kg.reachable(x) & tgt:
            reached.append(x)
    if not reached:
        r.note = "No package or project in the graph depends on the target."
    for x in reached:
        paths = kg.all_paths(x, tgt, limit=1)
        via = " -> ".join(kg.node_label(y) for y in paths[0]) if paths else ""
        r.facts.append(Fact(f"{kg.node_label(x)} depends (transitively) on {', '.join(short(t) for t in sorted(tgt, key=str))}"
                            f"; one chain: {via}.", INFERRED, "transitivity of lg:dependsOn", "derived from PyPI dependency data"))
    return r


def deep_copyleft(kg: KG, min_depth: int = 3, **_):
    r = Retrieval("deep_copyleft", f"Package versions with a copyleft dependency at least {min_depth} hops below them")
    r.queries.append("?v lg:isSeedRoot true . ?v lg:directlyDependsOn/lg:directlyDependsOn/lg:directlyDependsOn/lg:directlyDependsOn* ?dv "
                     ". ?dv lg:hasLicense/a/rdfs:subClassOf* lg:CopyleftLicense   (the same pattern as Iteration 1 query Q13)")
    for v in sorted(kg.seed_versions, key=str):
        # lengths of all paths from v: depth-first over the DAG, collecting nodes reached by a path of >= min_depth edges
        found = set()

        def walk(n, depth):
            for d in kg.explicit.objects(n, LG.directlyDependsOn):
                if depth + 1 >= min_depth:
                    found.add(d)
                walk(d, depth + 1)

        walk(v, 0)
        for d in sorted(found, key=str):
            for lic in kg.license_of(d):
                if kg.is_copyleft(lic):
                    r.facts.append(Fact(f"{short(v)} has copyleft dependency {short(d)} ({kg.spdx(lic)}) at depth {min_depth} or more.",
                                        INFERRED, f"directlyDependsOn path of {min_depth}+ hops; copyleft through rdfs:subClassOf",
                                        "derived from PyPI dependency data"))
    if not r.facts:
        r.note = f"No copyleft dependency at depth {min_depth} or more was found."
    return r


def _conflict_rows(kg: KG, proj):
    return kg.select("""
        SELECT ?c ?dep ?lic ?rule ?verdict WHERE {
          ?c a lg:LicenseConflict ; lg:conflictProject ?proj ; lg:conflictDependency ?dep ;
             lg:conflictLicense ?lic ; lg:conflictRule ?rule ; lg:conflictVerdict ?verdict . }
        ORDER BY ?verdict ?dep""", proj=proj)


def _rule_fact_parts(kg: KG, rule):
    status = kg.explicit.value(rule, LG.ruleStatus)
    comment = kg.explicit.value(rule, rdfs_comment())
    srcs = [str(kg.explicit.value(s, LG.sourceUrl)) for s in kg.explicit.objects(rule, LG.ruleSource)]
    return str(status), str(comment), srcs


def rdfs_comment():
    from rdflib.namespace import RDFS
    return RDFS.comment


def _focus(route):
    """Version IRIs of packages named in the question next to a project (e.g. 'why is mutagen flagged for acme-mit-app'); empty = no focus."""
    if route is None or not route.entities.projects:
        return set()
    return {v for _, vs in route.entities.packages for v in vs}


def conflicts(kg: KG, nodes, route=None, **_):
    r = Retrieval("conflicts", "License conflicts of a project, with the compatibility rule that triggered each one")
    r.queries.append("INSERT rule 00_infer_conflicts.ru then SELECT ?c a lg:LicenseConflict ; lg:conflictProject ?proj ; "
                     "lg:conflictRule ?rule ; lg:conflictVerdict ?verdict")
    for n in nodes:
        rows = _conflict_rows(kg, n)
        focus = _focus(route)
        if focus:
            rows = [x for x in rows if x["dep"] in focus]
            if not rows:
                r.note = f"No license conflict was derived between {kg.node_label(n)} and the named package."
        if not rows and not r.note:
            r.note = f"No license conflict was derived for {kg.node_label(n)}."
        for row in rows:
            status, comment, srcs = _rule_fact_parts(kg, row["rule"])
            via = f"rule {short(row['rule'])} ({status})"
            r.facts.append(Fact(
                f"{kg.node_label(n)} conflicts with {short(row['dep'])} (license {kg.spdx(row['lic'])}): "
                f"verdict {short(row['verdict'])} by {via}. Rule rationale: {comment}",
                INFERRED, "conflict rule over lg:CompatibilityRule individuals + license categories (SPARQL INSERT)",
                ("sources: " + "; ".join(srcs)) if srcs else "no published source; our own design decision"))
            for path in kg.all_paths(n, [row["dep"]], limit=2):
                r.facts.append(Fact(f"Chain ({len(path) - 1} hops) that brings {short(row['dep'])} into {kg.node_label(n)}: "
                                    + " -> ".join(kg.node_label(x) for x in path) + ".", EXPLICIT,
                                    "each arrow is a stored lg:directlyDependsOn edge", "pip resolver output"))
    return r


def compatibility(kg: KG, nodes, **_):
    r = Retrieval("compatibility", "Whether a project is compatible with every license in its tree")
    r.queries.append("ASK { ?proj a lg:Project . FILTER NOT EXISTS { ?c a lg:LicenseConflict ; lg:conflictProject ?proj } }")
    for n in nodes:
        rows = _conflict_rows(kg, n)
        inc = [x for x in rows if short(x["verdict"]) == "Incompatible"]
        con = [x for x in rows if short(x["verdict"]) == "Conditional"]
        if not rows:
            r.facts.append(Fact(f"No conflict was derived for {kg.node_label(n)}; every license in its tree is Compatible with its own license "
                                f"according to the curated rules.", INFERRED, "conflict rule (no match)", ""))
        else:
            r.facts.append(Fact(f"{kg.node_label(n)} is NOT fully compatible: {len(inc)} Incompatible and {len(con)} Conditional conflict(s) were derived.",
                                INFERRED, "conflict rule over lg:CompatibilityRule", ""))
            for x in inc + con:
                status, _c, _s = _rule_fact_parts(kg, x["rule"])
                r.facts.append(Fact(f"{short(x['verdict'])}: {short(x['dep'])} ({kg.spdx(x['lic'])}) by rule {short(x['rule'])} ({status}).",
                                    INFERRED, "conflict rule", ""))
    return r


def firm_vs_avoidable(kg: KG, nodes, **_):
    r = Retrieval("firm_vs_avoidable", "Conflicts that are firm versus those avoidable through a dual-licence option")
    r.queries.append("conflict rows joined with lg:isDisjunctiveLicense of the conflicting dependency")
    for n in nodes:
        rows = _conflict_rows(kg, n)
        firm = [x for x in rows if kg.explicit.value(x["dep"], LG.isDisjunctiveLicense) != Literal(True)]
        avoid = [x for x in rows if kg.explicit.value(x["dep"], LG.isDisjunctiveLicense) == Literal(True)]
        r.facts.append(Fact(f"{kg.node_label(n)} has {len(firm)} firm and {len(avoid)} potentially avoidable conflict(s) "
                            f"({len(rows)} in total).", INFERRED, "conflict rule + lg:isDisjunctiveLicense", ""))
        for x in firm:
            r.facts.append(Fact(f"Firm: {short(x['dep'])} ({kg.spdx(x['lic'])}), {short(x['verdict'])}, rule {short(x['rule'])}.",
                                INFERRED, "conflict rule", ""))
        for x in avoid:
            decl = kg.explicit.value(x["dep"], LG.declaredLicenseString)
            r.facts.append(Fact(f"Avoidable: {short(x['dep'])} is dual-licensed (\"{decl}\"); choosing another option could remove the "
                                f"{short(x['verdict'])} conflict on {kg.spdx(x['lic'])}.", INFERRED, "conflict rule + lg:isDisjunctiveLicense", ""))
    return r


def license_pair(kg: KG, route=None, **_):
    """Rule-level answer for 'can a project under license A depend on a dependency under license B?'.
    The first license or family named is taken as the project's license, the second as the dependency's."""
    r = Retrieval("license_pair", "Compatibility verdict for a project license category versus a dependency license category")
    r.queries.append("?rule a lg:CompatibilityRule ; lg:projectCategory ?pc ; lg:dependencyCategory ?dc ; lg:verdict ?v  (categories of the two licenses)  "
                     "+  ?a lg:incompatibleWith ?b  (license-level, symmetric)")
    ent = route.entities
    slots = [("license", iri) for _, iri in ent.licenses] + [("category", c) for c in ent.categories]
    if len(slots) < 2:
        r.note = "Two licenses or license families are needed."
        return r
    (k1, a), (k2, b) = slots[0], slots[1]

    def cat(kind, x):
        return kg.category_of(x) if kind == "license" else x

    def name(kind, x):
        return kg.spdx(x) if kind == "license" else x.replace("License", " license")
    ca, cb = cat(k1, a), cat(k2, b)
    for kind, x in ((k1, a), (k2, b)):
        if kind == "license":
            r.facts.append(Fact(f"{kg.spdx(x)} belongs to category {kg.category_of(x)}.", EXPLICIT, "stored rdf:type of the license", "license_categories.csv (our own table)"))
    if k1 == "license" and k2 == "license":
        if (a, LG.incompatibleWith, b) in kg.reasoned:
            kind = "explicit" if kg.is_explicit(a, LG.incompatibleWith, b) else INFERRED
            r.facts.append(Fact(f"{kg.spdx(a)} is stated to be incompatible with {kg.spdx(b)} at license level.", kind,
                                "lg:incompatibleWith is symmetric" if kind == INFERRED else "stored triple lg:incompatibleWith",
                                "Apache Software Foundation, GPL compatibility page"))
    rules = kg.select("""SELECT ?rule ?v ?status WHERE { ?rule a lg:CompatibilityRule ; lg:projectCategory ?pc ; lg:dependencyCategory ?dc ; lg:verdict ?v ; lg:ruleStatus ?status }""",
                      graph="explicit", pc=LG[ca], dc=LG[cb])
    if not rules:
        r.note = f"No curated rule covers a project in category {ca} with a dependency in category {cb}."
    for row in rules:
        status, comment, srcs = _rule_fact_parts(kg, row["rule"])
        r.facts.append(Fact(f"Assuming the project is under {name(k1, a)} and the dependency under {name(k2, b)}: rule {short(row['rule'])} gives verdict "
                            f"{short(row['v'])} for ({ca}, {cb}). Rationale: {comment}", EXPLICIT, f"stored rule individual ({status})",
                            ("sources: " + "; ".join(srcs)) if srcs else "no published source; our own design decision"))
    return r


def graph_stats(kg: KG, **_):
    r = Retrieval("graph_stats", "Size of the knowledge graph")
    r.queries.append("COUNT of lg:Package, lg:PackageVersion, lg:License, lg:directlyDependsOn triples and all stored triples")
    n_pkg = len(set(kg.explicit.subjects(RDF.type, LG.Package)))
    n_ver = len({v for v in kg.explicit.subjects(RDF.type, LG.PackageVersion) if (v, RDF.type, LG.Project) not in kg.explicit})
    n_lic = len(kg.licenses)
    n_edge = len(list(kg.explicit.triples((None, LG.directlyDependsOn, None))))
    for txt in (f"The graph stores {n_pkg} packages and {n_ver} resolved package versions (plus {len(kg.projects)} demo projects).",
                f"It stores {n_edge} direct dependency edges and {n_lic} licenses; {len(kg.explicit)} triples are stored in total (ontology, rules and data).",
                f"{len(kg.reasoned)} triples exist after OWL 2 RL reasoning and the conflict rule."):
        r.facts.append(Fact(txt, EXPLICIT if "after OWL" not in txt else INFERRED, "COUNT over stored triples" if "after OWL" not in txt else "OWL 2 RL closure + conflict rule", "RDF_Knowledge_Graph/instances.ttl"))
    return r


def license_frequency(kg: KG, top: int = 5, **_):
    r = Retrieval("license_frequency", "Most frequent licenses across all package versions")
    r.queries.append("SELECT ?id (COUNT(?v) AS ?n) WHERE { ?v lg:hasLicense ?l . ?l lg:spdxId ?id } GROUP BY ?id ORDER BY DESC(?n)")
    rows = kg.select("""SELECT ?id (COUNT(DISTINCT ?v) AS ?n) WHERE {
        ?v a lg:PackageVersion ; lg:hasLicense ?l . FILTER NOT EXISTS { ?v a lg:Project } ?l lg:spdxId ?id }
        GROUP BY ?id ORDER BY DESC(?n) ?id""", graph="explicit")
    for row in rows[:top]:
        r.facts.append(Fact(f"License {row['id']} is used by {int(row['n'])} package version(s).", INFERRED,
                            "COUNT aggregation over stored lg:hasLicense triples", "PyPI metadata"))
    return r


def non_osi(kg: KG, **_):
    r = Retrieval("non_osi", "Licenses without a confirmed OSI-approved flag")
    r.queries.append("?l lg:spdxId ?id . OPTIONAL { ?l lg:isOsiApproved ?osi } FILTER(!BOUND(?osi) || ?osi = false)  + COUNT of versions")
    rows = kg.select("""SELECT ?id ?osi (COUNT(DISTINCT ?v) AS ?n) WHERE {
        ?l lg:spdxId ?id . OPTIONAL { ?l lg:isOsiApproved ?osi } FILTER(!BOUND(?osi) || ?osi = false)
        OPTIONAL { ?v lg:hasLicense ?l . FILTER NOT EXISTS { ?v a lg:Project } } }
        GROUP BY ?id ?osi ORDER BY DESC(?n) ?id""", graph="explicit")
    for row in rows:
        flag = "marked not OSI-approved" if row["osi"] is not None else "has no OSI flag in the SPDX list"
        r.facts.append(Fact(f"License {row['id']} {flag}; used by {int(row['n'])} package version(s).", EXPLICIT,
                            "lg:isOsiApproved from the SPDX License List", "SPDX License List v8791eda"))
    return r


def tree_size(kg: KG, nodes, **_):
    r = Retrieval("tree_size", "Size of the dependency tree and number of copyleft dependencies")
    r.queries.append("COUNT(DISTINCT ?d) over ?node lg:directlyDependsOn+ ?d, and the copyleft subset")
    for n in nodes:
        tree = _tree(kg, n)
        cl = [d for d in tree if any(kg.is_copyleft(l) for l in kg.license_of(d))]
        r.facts.append(Fact(f"{kg.node_label(n)} has {len(tree)} transitive dependencies, of which {len(cl)} have a copyleft license"
                            + (": " + ", ".join(short(d) for d in cl) if cl else "") + ".", INFERRED,
                            "transitive closure of lg:directlyDependsOn; copyleft through rdfs:subClassOf", "derived from PyPI dependency data"))
    return r


def predict_license(kg: KG, nodes, predictor=None, **_):
    r = Retrieval("predict_license", "Embedding-model prediction of a license; never used to derive conflicts")
    r.queries.append("kg_reasoning/predictor.py: TransE ranks all License entities for (node, lg:hasLicense, ?) by score -||h + r - t||^2")
    if predictor is None:
        r.note = "The link-prediction model is not available (train it with: python kg_reasoning/link_prediction.py)."
        return r
    for n in nodes:
        stored = ", ".join(kg.spdx(x) for x in kg.license_of(n))
        if stored:
            r.facts.append(Fact(f"The stored (verified) license of {kg.node_label(n)} is {stored}.", EXPLICIT, "stored triple lg:hasLicense", _data_source(kg, n)))
        held = predictor.was_held_out(n)
        why = ("this license link was hidden from the model during training, so this is a genuine prediction" if held else
               "this license link was part of the training data, so agreement with the stored license is NOT evidence of predictive skill")
        for rank, (lic, score) in enumerate(predictor.top_licenses(n, k=3), 1):
            r.facts.append(Fact(f"PREDICTION (not a confirmed fact): rank {rank} license for {kg.node_label(n)} is {lic} (model score {score:.3f}); {why}.",
                                PREDICTION, f"{predictor.model_name} link prediction (held-out MRR about 0.56, see results_iter2/link_prediction)", "kg_reasoning"))
    return r


RETRIEVERS = {
    "license_of": license_of, "direct_deps": direct_deps, "tree_licenses": tree_licenses,
    "copyleft_chains": copyleft_chains, "dependency_chains": dependency_chains, "dependents": dependents,
    "deep_copyleft": deep_copyleft, "conflicts": conflicts, "compatibility": compatibility,
    "firm_vs_avoidable": firm_vs_avoidable, "license_frequency": license_frequency, "non_osi": non_osi,
    "tree_size": tree_size, "predict_license": predict_license, "license_pair": license_pair, "graph_stats": graph_stats,
}
