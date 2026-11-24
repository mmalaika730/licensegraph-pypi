"""
kg.py | loads the LicenseGraph-PyPI knowledge graph for the question-answering application.

Two graphs are kept side by side:
  explicit  = ontology + compatibility rules + instance data, exactly as stored in the Turtle files
  reasoned  = explicit + OWL 2 RL closure + the conflict rule (SPARQL_Queries/00_infer_conflicts.ru)

A fact is labelled "explicit" when its triple is in `explicit`, and "inferred" when it is only in
`reasoned`. This is how the application separates stored knowledge from derived knowledge.
"""
from __future__ import annotations

import re
from pathlib import Path

import owlrl
from rdflib import RDF, Graph, Literal, Namespace, URIRef

LG = Namespace("http://example.org/licensegraph#")
PKG = "http://example.org/licensegraph/pkg/"
VER = "http://example.org/licensegraph/ver/"
LIC = "http://example.org/licensegraph/license/"
PROJ = "http://example.org/licensegraph/project/"
RULE = "http://example.org/licensegraph/rule/"

PREFIXES = """PREFIX lg:   <http://example.org/licensegraph#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""

CATEGORY_CLASSES = ["PermissiveLicense", "PublicDomainLicense", "WeakCopyleftLicense", "StrongCopyleftLicense",
                    "NetworkCopyleftLicense", "ProprietaryLicense", "UnknownLicense"]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def short(iri) -> str:
    """Readable label for an IRI: ver/beets/2.14.1 -> beets/2.14.1, license/MIT -> MIT."""
    s = str(iri)
    for base in (VER, LIC, PROJ, PKG, RULE):
        if s.startswith(base):
            return s[len(base):]
    return s.rsplit("#", 1)[-1] if "#" in s else s


def norm_name(name: str) -> str:
    """PEP 503 normalisation, so 'Typing_Extensions' and 'typing-extensions' are the same name."""
    return re.sub(r"[-_.]+", "-", name).lower()


class KG:
    def __init__(self, root: Path | None = None, materialise: bool = True):
        self.root = Path(root) if root else repo_root()
        self.explicit = Graph()
        for rel in ("Ontology/licensegraph_ontology.ttl", "Ontology/compatibility_rules.ttl",
                    "RDF_Knowledge_Graph/instances.ttl"):
            self.explicit.parse(self.root / rel, format="turtle")
        self.reasoned = Graph()
        for t in self.explicit:
            self.reasoned.add(t)
        self.rule_text = (self.root / "SPARQL_Queries/00_infer_conflicts.ru").read_text(encoding="utf-8")
        if materialise:
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, rdfs_closure=False,
                                   axiomatic_triples=False, datatype_axioms=False).expand(self.reasoned)
            self.reasoned.update(self.rule_text)
        self._index()

    # ------------------------------------------------------------------ lookups
    def _index(self):
        self.projects = {}          # normalised name -> IRI
        for p in self.explicit.subjects(RDF.type, LG.Project):
            name = str(self.explicit.value(p, LG.projectName) or short(p))
            self.projects[norm_name(name)] = p
        self.packages = {}          # normalised name -> [version IRIs]
        for pk in self.explicit.subjects(RDF.type, LG.Package):
            name = str(self.explicit.value(pk, LG.packageName) or short(pk))
            self.packages[norm_name(name)] = sorted(self.explicit.objects(pk, LG.hasVersion), key=str)
        self.licenses = {}          # lower-case spdx id -> IRI
        for lic in self.explicit.subjects(RDF.type, None):
            if str(lic).startswith(LIC):
                sid = self.explicit.value(lic, LG.spdxId)
                if sid:
                    self.licenses[str(sid).lower()] = lic
        self.rules = {short(r).lower(): r for r in self.explicit.subjects(RDF.type, LG.CompatibilityRule)}
        self.seed_versions = set(self.explicit.subjects(LG.isSeedRoot, Literal(True)))

    def node_label(self, iri) -> str:
        s = str(iri)
        if s.startswith(PROJ):
            return s[len(PROJ):]
        return short(iri)

    def nodes_for(self, name: str):
        """Project IRI or all version IRIs for a package name."""
        n = norm_name(name)
        if n in self.projects:
            return [self.projects[n]]
        return list(self.packages.get(n, []))

    # --------------------------------------------------------------- provenance
    def is_explicit(self, s, p, o) -> bool:
        return (s, p, o) in self.explicit

    def kind(self, s, p, o) -> str:
        if self.is_explicit(s, p, o):
            return "explicit"
        return "inferred" if (s, p, o) in self.reasoned else "unknown"

    # ------------------------------------------------------------------ queries
    def select(self, sparql: str, graph: str = "reasoned", **bindings):
        g = self.reasoned if graph == "reasoned" else self.explicit
        res = g.query(PREFIXES + sparql, initBindings={k: v for k, v in bindings.items()})
        return [{str(v): row[i] for i, v in enumerate(res.vars)} for row in res]

    def category_of(self, lic) -> str:
        """Most specific license category stored for a license (explicit type)."""
        for cls in CATEGORY_CLASSES:
            if (lic, RDF.type, LG[cls]) in self.explicit:
                return cls
        return "License"

    def is_copyleft(self, lic) -> bool:
        return (lic, RDF.type, LG.CopyleftLicense) in self.reasoned

    def spdx(self, lic) -> str:
        return str(self.explicit.value(lic, LG.spdxId) or short(lic))

    def direct_deps(self, node):
        return sorted(self.explicit.objects(node, LG.directlyDependsOn), key=str)

    def license_of(self, node):
        return sorted(self.explicit.objects(node, LG.hasLicense), key=str)

    def reachable(self, node):
        """All nodes reachable through directlyDependsOn (the transitive closure from this node)."""
        seen, stack = set(), [node]
        while stack:
            n = stack.pop()
            for d in self.explicit.objects(n, LG.directlyDependsOn):
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        return seen

    def all_paths(self, start, targets, limit: int = 50):
        """All simple dependency paths from start to any node in targets (the graph is a DAG)."""
        targets = set(targets)
        out = []

        def walk(n, path):
            if len(out) >= limit:
                return
            for d in sorted(self.explicit.objects(n, LG.directlyDependsOn), key=str):
                if d in path:
                    continue
                p2 = path + [d]
                if d in targets:
                    out.append(p2)
                walk(d, p2)

        walk(start, [start])
        return out
