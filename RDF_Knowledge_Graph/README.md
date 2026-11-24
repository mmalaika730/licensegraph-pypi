# RDF Knowledge Graph: how to build it

## Pipeline

```
deps.dev BigQuery --(01_extract_deps_dev.sql)--> node_versions.csv + direct_edges.csv
                                                              |
SPDX licenses.json + license_categories.csv -----------------+
projects.csv (optional: an additional project) --------------------+
                                                              v
                                                    build_kg.py  -->  instances.ttl + build_report.txt
                                                              |
                          licensegraph_ontology.ttl + instances.ttl  -->  GraphDB (OWL2-RL ruleset)
```

## Steps

1. **Extract.** Run the statements in `Dataset/deps_dev/01_extract_deps_dev.sql` in the BigQuery console (replace `YOUR_PROJECT`, do the dry run first, aim for 100 to 200 nodes). Save the two final queries as `Dataset/deps_dev/node_versions.csv` and `Dataset/deps_dev/direct_edges.csv`.
2. **Build.**
   ```bash
   pip install rdflib
   python3 RDF_Knowledge_Graph/build_kg.py \
     --versions Dataset/deps_dev/node_versions.csv \
     --edges    Dataset/deps_dev/direct_edges.csv \
     --spdx     Dataset/spdx/licenses.json \
     --categories Dataset/curated/license_categories.csv \
     --ontology Ontology/licensegraph_ontology.ttl \
     --out-dir  RDF_Knowledge_Graph
   ```
   Add `--projects projects.csv` (columns `project,license,depends_on`, with `depends_on` as `name==version;name==version`) to include an additional project, for example one licensed MIT and one `LicenseRef-Proprietary`.
3. **Read `build_report.txt`.** It lists triple counts (the requirement is at least 500 meaningful triples), every cleaning action, licenses that still need a category, and anything dropped.
4. **Load into GraphDB.** Create a repository with the **OWL2-RL** ruleset (it supports transitive, inverse, symmetric and property-chain axioms; the OWL-Horst ruleset does not support property chains). Import `Ontology/licensegraph_ontology.ttl` and `RDF_Knowledge_Graph/instances.ttl`.

`_fixture_test/` holds the output of running the script on **synthetic** data (`Dataset/fixture/`, fictional `demo-*` packages). It only proves the script works; do not submit it as the knowledge graph.

## Data cleaning and transformation (for the report)

| Step | What happens |
|------|--------------|
| Name normalisation | PEP 503 on every package name (see `uri_design.md`) |
| Row cleaning | Rows with an empty name or version are dropped; duplicate version rows and duplicate edges are merged; self-loops are dropped |
| Edge integrity | An edge is kept only if both endpoints are in the node table; dropped edges are listed in the report |
| License parsing | `;`-joined SPDX expressions are split; `A OR B` and `A AND B` become separate license links; `X WITH exception` keeps the base license X |
| Missing licenses | A version with no license gets `license/NOASSERTION` (typed `UnknownLicense`), so every node has a license link |
| License enrichment | SPDX name, OSI-approved and FSF-libre flags are added from the SPDX License List (`licenses.json`, version `8791eda`) |
| Categorisation | `Dataset/curated/license_categories.csv` maps each SPDX id to one category class. Unlisted ids become `UnknownLicense` and appear in the report |
| Typing | Each license gets its category class, so `rdfs:subClassOf` reasoning supplies the broader classes (for example AGPL is also StrongCopyleft and Copyleft) |

## Known limitations to decide as a team

- **Dual licensing.** Every id in an `A OR B` expression is currently linked with `lg:hasLicense`, so a dual-licensed `MIT OR GPL-2.0-only` package counts as a GPL risk. The fixture shows this: a MIT project is flagged for such a dependency. `lg:declaredLicenseString` and `lg:hasMultipleDeclaredLicenses` are kept so the application can warn "dual-licensed, verify", but the conflict rule does not yet treat OR as a choice.
- **License categories are our own judgment.** `license_categories.csv` was curated by hand. It was not cross-checked against ScanCode's license categories because that data could not be downloaded.
- **OSI flag.** `lg:isOsiApproved` is only present for ids found in the SPDX list. A query for non-OSI licenses should therefore also treat a missing flag as "not confirmed".
- **Per-root resolution.** If the same package version resolves to different children under different seed roots, `direct_edges` keeps the union.
