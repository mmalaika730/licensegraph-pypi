#!/usr/bin/env python3
"""
fetch_pypi.py  |  LicenseGraph-PyPI, AI-3001 Iteration 1

Sandbox-friendly substitute for Dataset/deps_dev/01_extract_deps_dev.sql.
Resolves real dependency trees for the seed packages straight from PyPI with pip's own resolver
and writes the same two CSVs build_kg.py reads (node_versions.csv, direct_edges.csv).

How it works
  1. For each seed:  pip install --dry-run --ignore-installed --report X.json <seed>
     (resolves what a fresh install would pick on this Python/OS; nothing is installed).
  2. Nodes = every resolved distribution (name, version) and its PyPI metadata.
  3. Direct edges: for each node, take its own Requires-Dist entries, keep those whose
     environment marker is true for this interpreter (no extras), and link to the resolved
     distribution of that name.
  4. License = first of: SPDX license_expression  >  short license text we can map  >
     trove classifiers. The source used is written to license_audit.csv.

Usage
  python3 fetch_pypi.py --out-dir . [--seeds seeds.txt] [--workers 4]
Requires: Python 3.9+, pip 23.1+ (for --report), packaging, network access to pypi.org.
Why not deps.dev: the build sandbox could not reach BigQuery or api.deps.dev. If you can run
01_extract_deps_dev.sql, build_kg.py accepts that output unchanged.
"""
import argparse
import csv
import json
import platform
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

DEFAULT_SEEDS = [
    "requests", "flask", "django", "fastapi", "uvicorn", "jinja2", "click", "sqlalchemy", "pydantic",
    "httpx", "celery", "redis", "boto3", "pytest", "black", "numpy", "pandas", "scipy", "matplotlib",
    "scikit-learn", "pillow", "lxml", "beautifulsoup4", "selenium", "openpyxl", "pyyaml",
    "cryptography", "paramiko", "docker", "psycopg2-binary", "pylint", "ansible-core",
    "mutagen", "unidecode", "pyinstaller",
    # added so that copyleft packages also sit several hops below permissive ones
    "beets", "fabric", "ansible", "ldap3", "psycopg", "python-slugify", "sphinx", "scrapy",
    "pytest-pylint", "mysql-connector-python",
]
# mysqlclient was dropped: it ships source only, so pip cannot resolve it without a C toolchain.

CLASSIFIER_TO_SPDX = {
    "MIT License": ("MIT", ""),
    "MIT No Attribution License (MIT-0)": ("MIT-0", ""),
    "BSD License": ("BSD-3-Clause", "ambiguous: BSD 2- or 3-clause"),
    "Apache Software License": ("Apache-2.0", "assumed version 2.0"),
    "ISC License (ISCL)": ("ISC", ""),
    "Python Software Foundation License": ("PSF-2.0", ""),
    "zlib/libpng License": ("Zlib", ""),
    "Boost Software License 1.0 (BSL-1.0)": ("BSL-1.0", ""),
    "The Unlicense (Unlicense)": ("Unlicense", ""),
    "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": ("CC0-1.0", ""),
    "Public Domain": ("LicenseRef-Public-Domain", ""),
    "Mozilla Public License 1.1 (MPL 1.1)": ("MPL-1.1", ""),
    "Mozilla Public License 2.0 (MPL 2.0)": ("MPL-2.0", ""),
    "Eclipse Public License 1.0 (EPL-1.0)": ("EPL-1.0", ""),
    "Eclipse Public License 2.0 (EPL-2.0)": ("EPL-2.0", ""),
    "Common Development and Distribution License 1.0 (CDDL-1.0)": ("CDDL-1.0", ""),
    "Artistic License": ("Artistic-2.0", "ambiguous: Artistic 1.0 or 2.0"),
    "GNU General Public License (GPL)": ("GPL-2.0-or-later", "ambiguous version"),
    "GNU General Public License v2 (GPLv2)": ("GPL-2.0-only", ""),
    "GNU General Public License v2 or later (GPLv2+)": ("GPL-2.0-or-later", ""),
    "GNU General Public License v3 (GPLv3)": ("GPL-3.0-only", ""),
    "GNU General Public License v3 or later (GPLv3+)": ("GPL-3.0-or-later", ""),
    "GNU Library or Lesser General Public License (LGPL)": ("LGPL-2.1-or-later", "ambiguous version"),
    "GNU Lesser General Public License v2 (LGPLv2)": ("LGPL-2.0-only", ""),
    "GNU Lesser General Public License v2 or later (LGPLv2+)": ("LGPL-2.0-or-later", ""),
    "GNU Lesser General Public License v3 (LGPLv3)": ("LGPL-3.0-only", ""),
    "GNU Lesser General Public License v3 or later (LGPLv3+)": ("LGPL-3.0-or-later", ""),
    "GNU Affero General Public License v3": ("AGPL-3.0-only", ""),
    "GNU Affero General Public License v3 or later (AGPLv3+)": ("AGPL-3.0-or-later", ""),
    "Other/Proprietary License": ("LicenseRef-Other-Proprietary", ""),
}

# short free-text license fields we are willing to map (checked in order, on the lower-cased text)
TEXT_RULES = [
    (r"^(the )?mit( license)?$", "MIT"),
    (r"^apache(-| )?2(\.0)?( license)?$|^apache license,? version 2\.0$|^apache software license$", "Apache-2.0"),
    (r"^bsd[- ]?3[- ]?clause( license)?$|^3-clause bsd( license)?$|^new bsd( license)?$", "BSD-3-Clause"),
    (r"^bsd[- ]?2[- ]?clause( license)?$|^simplified bsd( license)?$", "BSD-2-Clause"),
    (r"^gpl-?3(\.0)?(\+|-only|-or-later)?$|^gplv3\+?$|^gnu gpl v3", "GPL-3.0-or-later"),
    (r"^gpl-?2(\.0)?(\+|-only|-or-later)?$|^gplv2\+?$", "GPL-2.0-or-later"),
    (r"^lgpl-?2\.1(\+|-only|-or-later)?$|^lgplv2\.1\+?$", "LGPL-2.1-or-later"),
    (r"^lgpl-?3(\.0)?(\+|-only|-or-later)?$|^lgplv3\+?$", "LGPL-3.0-or-later"),
    (r"^mpl-?2\.0$|^mozilla public license 2\.0", "MPL-2.0"),
    (r"^isc( license)?$", "ISC"),
    (r"^psf(-2\.0)?$|^python software foundation license", "PSF-2.0"),
    (r"^unlicense$", "Unlicense"),
]


# Manual overrides, each justified by the raw metadata shown in license_audit.csv.
OVERRIDES = {
    "pysocks": ("BSD-3-Clause", "license field is just 'BSD' and there is no classifier; 3-clause assumed"),
    "pyinstaller": ("GPL-2.0-or-later WITH Bootloader-exception",
                    "license text: 'GPLv2-or-later with a special exception'; the classifier says GPLv2 only"),
}


def pick_license(meta):
    """Return (spdx string joined by ';', source, note)."""
    ov = OVERRIDES.get(canonicalize_name(meta.get("name", "")))
    if ov:
        return ov[0], "manual_override", ov[1]
    expr = (meta.get("license_expression") or "").strip()
    if expr:
        return expr, "license_expression", ""
    text = (meta.get("license") or "").strip()
    if text and len(text) <= 80 and "\n" not in text:
        low = re.sub(r"\s+", " ", text.lower())
        for pattern, spdx in TEXT_RULES:
            if re.search(pattern, low):
                return spdx, "license_text", f"mapped from '{text}'"
    found, notes = [], []
    for c in meta.get("classifier", []) or []:
        if not c.startswith("License ::"):
            continue
        key = c.split("::")[-1].strip()
        if key == "OSI Approved":
            continue
        if key in CLASSIFIER_TO_SPDX:
            spdx, note = CLASSIFIER_TO_SPDX[key]
            if spdx not in found:
                found.append(spdx)
                notes.append(note or f"classifier '{key}'")
        else:
            notes.append(f"unmapped classifier '{key}'")
    if found:
        return " OR ".join(found), "classifier", "; ".join(n for n in notes if n)
    return "", "none", (f"free text not mapped: {text[:60]!r}" if text else "")


def resolve(seed, tmp):
    out = Path(tmp) / f"{seed}.json"
    cmd = [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
           "--disable-pip-version-check", "--report", str(out), seed]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.exists():
        return seed, None, (r.stderr or r.stdout).strip()[-300:]
    return seed, json.loads(out.read_text()), ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seeds", help="text file, one package per line (default: built-in list)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds = ([s.strip() for s in open(args.seeds) if s.strip() and not s.startswith("#")]
             if args.seeds else DEFAULT_SEEDS)

    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(lambda s: resolve(s, tmp), seeds))

    failed = [(s, e) for s, d, e in results if d is None]
    nodes = {}      # (name, version) -> dict
    seed_nodes = set()
    for seed, rep, _ in results:
        if rep is None:
            continue
        for item in rep["install"]:
            m = item["metadata"]
            key = (canonicalize_name(m["name"]), m["version"])
            if key not in nodes:
                nodes[key] = m
            if item.get("requested"):
                seed_nodes.add(key)

    edges = set()
    for seed, rep, _ in results:
        if rep is None:
            continue
        # name -> version resolved in THIS seed's tree, so every edge matches one real resolution
        resolved = {canonicalize_name(i["metadata"]["name"]): i["metadata"]["version"] for i in rep["install"]}
        for item in rep["install"]:
            m = item["metadata"]
            a = (canonicalize_name(m["name"]), m["version"])
            for line in m.get("requires_dist") or []:
                try:
                    req = Requirement(line)
                except Exception:
                    continue
                if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                    continue
                dep = canonicalize_name(req.name)
                if dep in resolved and (dep, resolved[dep]) != a:
                    edges.add((a, (dep, resolved[dep])))
    ambiguous = []

    with open(out_dir / "node_versions.csv", "w", newline="", encoding="utf-8") as f, \
         open(out_dir / "license_audit.csv", "w", newline="", encoding="utf-8") as fa:
        w, wa = csv.writer(f), csv.writer(fa)
        w.writerow(["name", "version", "licenses", "is_seed", "license_source"])
        wa.writerow(["name", "version", "licenses", "license_source", "note", "raw_license_field",
                     "raw_classifiers"])
        for key in sorted(nodes):
            m = nodes[key]
            lic, src, note = pick_license(m)
            w.writerow([key[0], key[1], lic, str(key in seed_nodes).lower(), src])
            raw = (m.get("license") or "").strip().replace("\n", " ")[:120]
            cls = " | ".join(c.split("::", 1)[1].strip() for c in (m.get("classifier") or [])
                             if c.startswith("License ::"))
            wa.writerow([key[0], key[1], lic, src, note, raw, cls])
    with open(out_dir / "direct_edges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "version", "dep_name", "dep_version"])
        for a, b in sorted(edges):
            w.writerow([a[0], a[1], b[0], b[1]])

    src_counts = {}
    for m in nodes.values():
        s = pick_license(m)[1]
        src_counts[s] = src_counts.get(s, 0) + 1
    manifest = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(), "platform": platform.platform(),
        "pip": subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True,
                              text=True).stdout.strip(),
        "seeds_requested": len(seeds), "seeds_resolved": len(seeds) - len(failed),
        "seeds_failed": failed, "nodes": len(nodes), "edges": len(edges),
        "seed_nodes": len(seed_nodes), "license_source_counts": src_counts,
        "ambiguous_edges_all_versions_linked": ambiguous,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "ambiguous_edges_all_versions_linked"}, indent=2))
    print("ambiguous edges:", len(ambiguous))


if __name__ == "__main__":
    main()
