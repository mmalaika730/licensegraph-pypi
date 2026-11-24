# GraphDB and Protégé: setup and verification steps

These are the steps we followed to load the ontology and graph in Protégé and GraphDB and to verify the results. Screenshots are in `Visualization/`.

## Protégé (ontology)
1. File > Open `Ontology/licensegraph_ontology.ttl`; then File > Open again and choose "Open in the same window" (merge) for `Ontology/compatibility_rules.ttl`.
2. Check the tabs: **Classes** (17 classes, license hierarchy under `License`), **Object properties** (look at `dependsOn`: Transitive, with `directlyDependsOn` as sub-property; `treeContainsLicense` has a property chain), **Data properties**.
3. Run a reasoner (Reasoner menu: HermiT) and confirm it reports the ontology as consistent. An independent check with an OWL 2 RL reasoner in Python also found no inconsistencies.
4. Talking points: T-Box = this file; A-Box = `instances.ttl`; `lg:Package` and `lg:PackageVersion` are separate; `packageName` has no domain on purpose (Project is a PackageVersion, and Package is disjoint from PackageVersion).

## GraphDB (graph and queries)
1. Create a repository with the **OWL2-RL** ruleset (the OWL-Horst ruleset does not support property chains). Name it `licensegraph`.
2. Import `Ontology/licensegraph_ontology.ttl`, `Ontology/compatibility_rules.ttl` and `RDF_Knowledge_Graph/instances.ttl` (Import > RDF > Upload).
3. Check the import: `SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }` (stored triples: 2,748; GraphDB will report more after inference). Explore > Visual graph and start from `http://example.org/licensegraph/project/acme-mit-app`.
4. SPARQL > Update tab: run `SPARQL_Queries/00_infer_conflicts.ru` **once**.
5. SPARQL tab: run `Q01` to `Q14` and compare with `Results/*.csv`. Counts should match; small differences in the ordering are fine.
6. Show that facts are inferred: run `Q09` as written, then add `FROM <http://www.ontotext.com/explicit>` above `WHERE` and show 0 rows. Use `FROM <http://www.ontotext.com/implicit>` to show only inferred statements.
7. Screenshots of the visual graph and the query results are saved in `Visualization/`.
