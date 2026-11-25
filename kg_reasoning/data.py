"""
data.py | turns the RDF knowledge graph into integer triples for the link-prediction experiment.

Only structural relations are used, so nothing in the training data can reveal a hidden license:
  directlyDependsOn   package version -> package version   (pip resolver output)
  hasLicense          package version -> license           (the relation we hide and try to recover)
  inCategory          license         -> license category  (rdf:type of the license, e.g. PermissiveLicense)
  hasVersion          package         -> package version
Literal properties such as lg:declaredLicenseString or lg:licenseSource are NOT used (they would leak the answer).
Demo projects (acme-*) are excluded from evaluation: their licenses are chosen by us, not observed.
"""
from __future__ import annotations

from pathlib import Path

from rdflib import RDF, Graph, URIRef

LG = "http://example.org/licensegraph#"
LIC = "http://example.org/licensegraph/license/"
VER = "http://example.org/licensegraph/ver/"
PROJ = "http://example.org/licensegraph/project/"
CATEGORIES = ["PermissiveLicense", "PublicDomainLicense", "WeakCopyleftLicense", "StrongCopyleftLicense",
              "NetworkCopyleftLicense", "ProprietaryLicense", "UnknownLicense"]
REL_NAMES = ["directlyDependsOn", "hasLicense", "inCategory", "hasVersion"]


def load_triples(root: Path):
    """Returns (triples as (h, r, t) IRI-string tuples, license IRIs, version IRIs)."""
    g = Graph()
    g.parse(root / "RDF_Knowledge_Graph/instances.ttl", format="turtle")
    triples = []
    for rel in ("directlyDependsOn", "hasLicense", "hasVersion"):
        for s, _, o in g.triples((None, URIRef(LG + rel), None)):
            if str(s).startswith(PROJ):
                continue          # demo projects are not observed data
            triples.append((str(s), rel, str(o)))
    licenses = sorted({str(s) for s in g.subjects(RDF.type, None) if str(s).startswith(LIC)})
    for lic in licenses:
        for cat in CATEGORIES:
            if (URIRef(lic), RDF.type, URIRef(LG + cat)) in g:
                triples.append((lic, "inCategory", LG + cat))
    versions = sorted({h for h, r, t in triples if r == "hasLicense"})
    return sorted(set(triples)), licenses, versions


class Index:
    """Maps IRIs and relation names to integer ids."""

    def __init__(self, triples):
        ents = sorted({x for h, r, t in triples for x in (h, t)})
        self.ent = {e: i for i, e in enumerate(ents)}
        self.ents = ents
        self.rel = {r: i for i, r in enumerate(REL_NAMES)}

    def encode(self, triples):
        import numpy as np
        return np.array([(self.ent[h], self.rel[r], self.ent[t]) for h, r, t in triples], dtype=np.int64)
