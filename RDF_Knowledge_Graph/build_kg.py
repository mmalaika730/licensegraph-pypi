#!/usr/bin/env python3
"""
build_kg.py  |  LicenseGraph-PyPI, AI-3001 Iteration 1

Turns the deps.dev CSV exports into RDF instance data (the A-Box).

Inputs
  --versions    node_versions.csv        name,version,licenses,is_seed
  --edges       direct_edges.csv         name,version,dep_name,dep_version
  --spdx        SPDX licenses.json       (spdx/license-list-data, json/licenses.json)
  --categories  license_categories.csv   spdx_id,category,note   (curated)
  --projects    projects.csv (optional)  project,license,depends_on  ("name==version;...")
  --ontology    one or more ontology/rule .ttl files (optional), only used to report merged triple counts
Outputs (in --out-dir)
  instances.ttl, build_report.txt

Requires: Python 3.9+ and rdflib  (pip install rdflib)
Run:      python3 build_kg.py --help
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace

BASE = "http://example.org/licensegraph/"          # must match the ontology file
LG = Namespace("http://example.org/licensegraph#")
PKG, VER, LIC, PRJ = (Namespace(BASE + p + "/") for p in ("pkg", "ver", "license", "project"))

CATEGORY_CLASS = {
    "Permissive": LG.PermissiveLicense,
    "PublicDomain": LG.PublicDomainLicense,
    "WeakCopyleft": LG.WeakCopyleftLicense,
    "StrongCopyleft": LG.StrongCopyleftLicense,
    "NetworkCopyleft": LG.NetworkCopyleftLicense,
    "Proprietary": LG.ProprietaryLicense,
    "Unknown": LG.UnknownLicense,
}

NO_LICENSE = "NOASSERTION"
SPLIT_AND_OR = re.compile(r"\s+(?:OR|AND)\s+", re.I)
SPLIT_WITH = re.compile(r"\s+WITH\s+", re.I)


# ----------------------------------------------------------------------------
# URI helpers (see uri_design.md)
# ----------------------------------------------------------------------------
def norm_name(name: str) -> str:
    """PEP 503 normalisation: lower-case, runs of - _ . become a single -."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def seg(text: str) -> str:
    """Percent-encode one URI path segment (keeps - . _ ~)."""
    return quote(text.strip(), safe="-._~")


def pkg_uri(name):          return PKG[seg(norm_name(name))]
def ver_uri(name, version): return VER[f"{seg(norm_name(name))}/{seg(version)}"]
def lic_uri(spdx_id):       return LIC[seg(spdx_id)]
def prj_uri(name):          return PRJ[seg(norm_name(name))]


# ----------------------------------------------------------------------------
# Cleaning helpers
# ----------------------------------------------------------------------------
def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def truthy(text):
    return text.strip().lower() in {"true", "t", "1", "yes", "y"}


def parse_licenses(raw):
    """
    deps.dev gives an array of SPDX expressions, flattened with ';'.
    Returns (license_ids, notes). 'A OR B' and 'A AND B' are split into ids;
    'X WITH exception' keeps the base id X and records a note.
    """
    ids, notes = [], []
    for item in (x.strip() for x in raw.split(";")):
        if not item:
            continue
        for tok in SPLIT_AND_OR.split(item.strip("() ")):
            tok = tok.strip("() ")
            if SPLIT_WITH.search(tok):
                notes.append(f"exception dropped: {tok}")
                tok = SPLIT_WITH.split(tok)[0].strip("() ")
            if tok and tok not in ids:
                ids.append(tok)
    return ids, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--versions", required=True)
    ap.add_argument("--edges", required=True)
    ap.add_argument("--spdx", required=True)
    ap.add_argument("--categories", required=True)
    ap.add_argument("--projects")
    ap.add_argument("--ontology", nargs="*", default=[], help="ontology/rule .ttl files (only used for the triple report)")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spdx = {l["licenseId"]: l for l in json.load(open(args.spdx, encoding="utf-8"))["licenses"]}
    cat_map = {}
    for r in read_csv(args.categories):
        if r["category"] not in CATEGORY_CLASS:
            sys.exit(f"license_categories.csv: unknown category '{r['category']}' for {r['spdx_id']}")
        cat_map[r["spdx_id"]] = r["category"]

    g = Graph()
    for prefix, ns in (("lg", LG), ("pkg", PKG), ("ver", VER), ("license", LIC), ("project", PRJ),
                       ("rdfs", RDFS), ("xsd", XSD)):
        g.bind(prefix, ns)

    stats = Counter()
    unmapped, not_in_spdx, exception_notes, or_expressions = set(), set(), [], []
    license_use = Counter()
    seen_licenses = set()

    def add_license(lid):
        uri = lic_uri(lid)
        if lid in seen_licenses:
            return uri
        seen_licenses.add(lid)
        cat = cat_map.get(lid)
        if cat is None:
            unmapped.add(lid)
            cat = "Unknown"
        g.add((uri, RDF.type, CATEGORY_CLASS[cat]))
        g.add((uri, LG.spdxId, Literal(lid)))
        s = spdx.get(lid)
        if s:
            g.add((uri, RDFS.label, Literal(s["name"])))
            g.add((uri, LG.isOsiApproved, Literal(bool(s.get("isOsiApproved", False)))))
            if "isFsfLibre" in s:
                g.add((uri, LG.isFsfLibre, Literal(bool(s["isFsfLibre"]))))
        else:
            not_in_spdx.add(lid)
            g.add((uri, RDFS.label, Literal(lid)))
        return uri

    # ---- package versions ---------------------------------------------------
    nodes = {}
    for r in read_csv(args.versions):
        name, version = norm_name(r.get("name", "")), r.get("version", "")
        if not name or not version:
            stats["version rows dropped (empty name/version)"] += 1
            continue
        if (name, version) in nodes:
            stats["duplicate version rows merged"] += 1
            continue
        nodes[(name, version)] = r

        p, v = pkg_uri(name), ver_uri(name, version)
        g.add((p, RDF.type, LG.Package))
        g.add((p, LG.packageName, Literal(name)))
        g.add((p, LG.hasVersion, v))
        g.add((v, RDF.type, LG.PackageVersion))
        g.add((v, LG.versionString, Literal(version)))
        g.add((v, LG.isSeedRoot, Literal(truthy(r.get("is_seed", "")))))

        raw = r.get("licenses", "")
        ids, notes = parse_licenses(raw)
        if raw:
            g.add((v, LG.declaredLicenseString, Literal(raw)))
            if re.search(r"\sOR\s", raw, re.I) and "WITH" not in raw.upper():
                or_expressions.append(f"{name}=={version}: {raw}")
        exception_notes += [f"{name}=={version}: {n}" for n in notes]
        if not ids:
            ids = [NO_LICENSE]
            stats["versions with no license recorded (set to NOASSERTION)"] += 1
        g.add((v, LG.hasMultipleDeclaredLicenses, Literal(len(ids) > 1)))
        g.add((v, LG.isDisjunctiveLicense, Literal(bool(re.search(r"\sOR\s", raw, re.I)))))
        if r.get("license_source"):
            g.add((v, LG.licenseSource, Literal(r["license_source"])))
        for lid in ids:
            g.add((v, LG.hasLicense, add_license(lid)))
            license_use[lid] += 1

    # ---- direct dependency edges -------------------------------------------
    edges = set()
    dangling = []
    for r in read_csv(args.edges):
        a = (norm_name(r.get("name", "")), r.get("version", ""))
        b = (norm_name(r.get("dep_name", "")), r.get("dep_version", ""))
        if a == b:
            stats["self-loop edges dropped"] += 1
        elif a not in nodes or b not in nodes:
            stats["edges dropped (endpoint not in node table)"] += 1
            dangling.append(f"{a[0]}=={a[1]} -> {b[0]}=={b[1]}")
        elif (a, b) in edges:
            stats["duplicate edges merged"] += 1
        else:
            edges.add((a, b))
            g.add((ver_uri(*a), LG.directlyDependsOn, ver_uri(*b)))

    # ---- user projects (optional) -------------------------------------------
    project_problems = []
    seed_versions = {}
    for (n, v), row in nodes.items():
        if truthy(row.get("is_seed", "")):
            seed_versions.setdefault(n, []).append(v)
    if args.projects:
        for r in read_csv(args.projects):
            pu = prj_uri(r["project"])
            g.add((pu, RDF.type, LG.Project))
            g.add((pu, LG.projectName, Literal(norm_name(r["project"]))))
            g.add((pu, LG.packageName, Literal(norm_name(r["project"]))))
            g.add((pu, LG.hasLicense, add_license(r["license"])))
            license_use[r["license"]] += 1
            for dep in (d.strip() for d in r.get("depends_on", "").split(";") if d.strip()):
                if "==" in dep:
                    n, v = dep.split("==", 1)
                    key = (norm_name(n), v.strip())
                else:  # bare name: use that package's seed version (must be unique)
                    versions = seed_versions.get(norm_name(dep), [])
                    if len(versions) != 1:
                        project_problems.append(
                            f"{r['project']}: '{dep}' has no unique seed version; write name==version")
                        continue
                    key = (norm_name(dep), versions[0])
                if key not in nodes:
                    project_problems.append(f"{r['project']}: {key[0]}=={key[1]} is not in the node table")
                    continue
                g.add((pu, LG.directlyDependsOn, ver_uri(*key)))
            stats["projects loaded"] += 1

    # ---- write -------------------------------------------------------------
    inst_path = out_dir / "instances.ttl"
    g.serialize(destination=str(inst_path), format="turtle")

    merged_note = ""
    if args.ontology:
        onto = Graph()
        for path in args.ontology:
            onto.parse(path, format="turtle")
        merged = Graph()
        for t in onto:
            merged.add(t)
        for t in g:
            merged.add(t)
        merged_note = (f"T-Box (ontology) triples : {len(onto)}\n"
                       f"Merged (T-Box + A-Box)    : {len(merged)}\n")

    cat_counts = Counter()
    for lid, n in license_use.items():
        cat_counts[cat_map.get(lid, "Unknown")] += n

    lines = [
        "LicenseGraph-PyPI build report",
        "==============================",
        f"Package versions (nodes)  : {len(nodes)}",
        f"Packages (distinct names) : {len({n for n, _ in nodes})}",
        f"Direct dependency edges   : {len(edges)}",
        f"Distinct licenses used    : {len(seen_licenses)}",
        f"A-Box triples (instances) : {len(g)}",
        merged_note.rstrip(),
        "",
        "Cleaning actions",
        *(f"  {k}: {v}" for k, v in sorted(stats.items())),
        "",
        "License usage by category (node-license links)",
        *(f"  {k}: {v}" for k, v in cat_counts.most_common()),
        "",
        "Most frequent licenses",
        *(f"  {k}: {v}" for k, v in license_use.most_common(10)),
        "",
        f"NEEDS CURATION: SPDX ids with no category in license_categories.csv (typed UnknownLicense): "
        f"{sorted(unmapped) or 'none'}",
        f"Ids not found in the SPDX list (no OSI/FSF flags): {sorted(not_in_spdx) or 'none'}",
        f"OR-expressions (dual licensing: every option is currently linked as a license): {or_expressions or 'none'}",
        f"WITH-exceptions (exception dropped, base license kept): {exception_notes or 'none'}",
        f"Dropped edges (first 10): {dangling[:10] or 'none'}",
        f"Project problems: {project_problems or 'none'}",
    ]
    report = "\n".join(l for l in lines if l is not None)
    (out_dir / "build_report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nWrote {inst_path}")


if __name__ == "__main__":
    main()
