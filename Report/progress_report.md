# LicenseGraph-PyPI: Iteration 1 progress report

**Course:** AI-3001 Knowledge Representation & Reasoning | **Iteration:** 1 (2-15 November 2026) | **Team:** [team name]

## 1. Summary

We built the knowledge-representation foundation for LicenseGraph-PyPI: 15 competency questions with a CQ-to-KG mapping, an OWL ontology, a 2,365-triple RDF knowledge graph of real PyPI dependency data (179 package versions, 247 dependency edges, 23 licenses, 4 demo projects), 27 curated compatibility rules with sources, 14 SPARQL queries plus a rule that infers license conflicts, and four verified inference examples. All counts are produced by scripts from the submitted files (`Report/requirements_check.md`).

## 2. Completed work

| Brief item | What we did | Where |
|---|---|---|
| Competency questions | 15 questions (5 multi-hop, 4 inference, 4 aggregation/filtering, 2 LLM-hard) and mapping table with query and real result | `Report/competency_questions.md` |
| Ontology / knowledge model | 16 classes, 17 object and 15 datatype properties; license category hierarchy; transitive, symmetric, inverse, sub-property, property-chain, disjointness and functional axioms; curated `CompatibilityRule` individuals tied to published `Source`s | `Ontology/` |
| RDF knowledge graph | `build_kg.py` turns the CSVs into Turtle; 2,365 instance triples (2,748 with schema and rules); cleaning and URI design documented | `RDF_Knowledge_Graph/` |
| SPARQL | 14 queries covering basic patterns, FILTER, OPTIONAL, UNION, aggregation, property paths (`+`, `*`, inverse), multi-hop chains up to 5 hops and inference-dependent queries; every query has a result CSV | `SPARQL_Queries/`, `Results/` |
| Inference | Rule `00_infer_conflicts.ru` derives 16 `LicenseConflict` facts (re-running adds none); 4 examples (transitive dependency, subclass, property chain, rule conflict), each checked as absent from the stored graph and present after reasoning | `Results/inference_examples.md` |
| Visualization | Dependency tree of `acme-mit-app` and whole-graph overview coloured by license category | `Visualization/` |

Key result: `acme-mit-app` (MIT) is flagged Incompatible for `mutagen` (GPL-2.0-or-later) through the exact chain `acme-mit-app -> beets/2.14.1 -> mediafile/0.17.0 -> mutagen/1.48.1`, a conflict nobody stored directly.

## 3. Limitations and incomplete work

- **Tool testing.** The graph, ontology and queries were first tested with an OWL 2 RL reasoner in Python. Team members then loaded them into GraphDB (OWL2-RL ruleset) and Protégé (HermiT) and took the screenshots in `Visualization/`. Steps and expected counts are in `Report/GraphDB_and_Protege_guide.md`.
- **Dataset differs from the plan.** The approved plan used deps.dev BigQuery. The build environment could not reach BigQuery or the deps.dev API, so the data comes from PyPI itself: pip's resolver produced the dependency trees and PyPI metadata gave the licenses (`Dataset/pypi/`). The deps.dev SQL (`Dataset/deps_dev/01_extract_deps_dev.sql`) is written but **never run**; its output can be fed to `build_kg.py` unchanged. We use the same 45 seed packages' trees, not a deps.dev snapshot.
- **ScanCode license data was not used.** It could not be downloaded; license categories are our own table (`license_categories.csv`) with judgment calls marked in its notes.
- **Compatibility rules: 18 of 27 are "design decision", 9 are "cited".** We checked each of the 13 rules first marked `cited` against the text of its source pages (Apache GPL-compatibility page, FSF FAQ post, Qt LGPL obligations, MPL 2.0 FAQ, AGPL guide) on 14 Nov 2026; the result per rule is in `Dataset/curated/rule_verification.csv`. 5 rules are directly supported, 4 are supported only partly (the source covers the idea, the exact pair or generalisation is our inference), and 4 AGPL-related rules (R3, R4, R20, R23) are not stated by any page we read, so they were changed to design decision. We could not reach the GNU license list or the GPL FAQ itself. Design decisions are conservative choices and are labelled as such in the data.
- **Not in Iteration 1:** the chat interface, the LLM comparison experiment and the requirements.txt upload.

## 4. Issues faced and how we handled them

1. **Network limits.** No access to BigQuery, deps.dev, ScanCode or the license guide sites; used pip's resolver and PyPI metadata instead and recorded provenance for every license (`license_audit.csv`, `lg:licenseSource`).
2. **Reasoning exposed a schema bug.** A consistency check flagged projects as both `Package` and `PackageVersion` (disjoint). Fixed by removing the domain on `packageName` and adding `projectName` as a sub-property.
3. **Duplicate query sets.** Two query sets with the same numbering ended up in one folder. We kept one primary set and moved the other to `supplementary/`.
4. **Query bug found by testing.** Q04 returned empty chains because a variable bound outside a UNION group is invisible inside it; fixed by deriving the label from a variable bound inside each branch.
5. **Dual licensing.** `MIT OR GPL` style licenses cannot be treated as GPL. We store `lg:isDisjunctiveLicense` and Q14 separates firm conflicts from avoidable ones; the conflict rule itself still flags every option.
6. **Ambiguous license data.** Many packages only declare a trove classifier ("BSD License"); we map it to a specific id and record the source and the ambiguity.

## 5. Member contributions

| Member | Contribution |
|---|---|
| Malaika Majid (Member A) | Data, knowledge graph and rule sources. Reviewed the PyPI dependency and license data (179 package versions, 247 dependency edges, 23 licenses) and its cleaning decisions: license taken from the SPDX expression, license text or classifier, and dual-licensed (OR) packages flagged. Reviewed the URI design, the Turtle build script and the 2,365-triple instance graph. Reviewed the 27 compatibility rules and their five published sources and spot-checked cited rules against the source pages; the full check of the 13 cited rules was done with Claude's help, which left 9 cited and 18 design decisions. |
| Omar Waqar (Member B) | Ontology and Protégé. Opened the combined schema and rules file in Protégé and reviewed the 16 classes, 17 object properties, 15 datatype properties and the license category hierarchy. Covered the reasoning constructs: transitive `dependsOn`, property chain `treeContainsLicense`, symmetric `incompatibleWith`, inverse properties, disjoint classes, functional properties and the `directlyDependsOn` sub-property. Ran the HermiT reasoner with no inconsistencies and took the Protégé screenshots. |
| Fiza Ali (Member C) | GraphDB, SPARQL and inference. Loaded schema, rules and instances into a GraphDB repository with the OWL2-RL ruleset and checked triple counts. Ran the 14 SPARQL queries and compared row counts with the expected results. Ran the conflict-inference update (16 conflicts, none added on a second run) and checked the inference examples. Took the GraphDB screenshots. Found the duplicate rows in Q04 and fixed them with `SELECT DISTINCT`. |
