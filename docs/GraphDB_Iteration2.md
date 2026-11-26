# GraphDB and Protégé for Iteration 2

## Protégé
1. Open `Ontology/licensegraph_with_rules.owl` (ontology plus compatibility rules; regenerated for Iteration 2 with the prediction classes and properties).
2. New in Iteration 2: class `License prediction` (disjoint from Package, Package version, License, Compatibility rule); object properties `predictionFor`, `predictedLicense` (not a sub-property of `hasLicense`); data properties `predictionRank`, `predictionScore`, `predictionMethod`, `predictionStatus`, `heldOutLink`. Duplicate declarations of `conflictLicense` and `conflictVerdict` that existed in Iteration 1 were removed.
3. Reasoner > HermiT > Start reasoner: no inconsistencies. Screenshot the class hierarchy and the new class.

## GraphDB
1. Repository `licensegraph` with ruleset **OWL2-RL** (as in Iteration 1). Import `Ontology/licensegraph_ontology.ttl`, `Ontology/compatibility_rules.ttl`, `RDF_Knowledge_Graph/instances.ttl` into the default graph.
2. Import `kg_reasoning/predictions.ttl` into a **named graph**: Import > Upload RDF files > choose the file > in the import settings set "Target graphs: named graph" = `http://example.org/licensegraph/predictions`.
3. Check the import with `SELECT (COUNT(*) AS ?n) FROM <http://www.ontotext.com/explicit> WHERE { ?s ?p ?o }`. In our run (GraphDB 11.5.2) this returned **3,714** explicit triples: the 3 files in the default graph added 2,778 (`instances.ttl` 2,365 + `licensegraph_ontology.ttl` 212 + `compatibility_rules.ttl` 201, as shown on the Import page), and `predictions.ttl` added 936 in the named graph. GraphDB 11 counts the named graph in this total, so 3,714 = 2,778 + 936.
4. Run `SPARQL_Queries/00_infer_conflicts.ru` once (SPARQL > Update tab), then re-run `Q01` to `Q14` and `Q15`.
5. Expected: `Q11` returns 16 conflicts; `Q15` returns 36 rows, 15 of them with `agrees = yes` (`Results/Q15_predictions_vs_stored_licenses.csv`).
6. Show that predictions are not facts: `SELECT * WHERE { ?pv lg:hasLicense ?l }` never returns a `lg:LicensePrediction` object, and the conflict rule's results are identical with and without the predictions graph.
7. Show three inferred facts for the viva: transitive `dependsOn` (Q09/Q10 with the `FROM <http://www.ontotext.com/explicit>` comparison), the property chain `treeContainsLicense`, and a rule-derived `LicenseConflict` (Q11).
