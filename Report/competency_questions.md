# LicenseGraph-PyPI: Competency Questions and CQ-to-KG Mapping

AI-3001 | Iteration 1 | Prefixes: `lg:` ontology, `pkg:` package, `ver:` package version, `license:` license, `rule:` compatibility rule.
Queries are in `SPARQL_Queries/` (primary set `Q01`-`Q14`, extra set in `supplementary/`); outputs are in `Results/`.
Project names used in the queries (`acme-mit-app` etc.) are demo projects defined in `Dataset/curated/projects.csv`.

## Competency questions (15)

| # | Competency question | Type |
|---|---------------------|------|
| CQ1 | Which package versions does project X depend on directly? | Basic |
| CQ2 | What licenses do the direct dependencies of X use? | Basic (OPTIONAL) |
| CQ3 | Which transitive dependencies of X are copyleft, and through which dependency chain? | Multi-hop, property path |
| CQ4 | Which projects and packages are exposed to package Z (for example a GPL package) anywhere below them? | Multi-hop (reverse path) |
| CQ5 | Which licenses in the graph are not confirmed OSI-approved, and how many package versions use them? | Aggregation / filtering |
| CQ6 | For each direct dependency of X, which copyleft licenses appear somewhere beneath it? | Multi-hop + grouping |
| CQ7 | Which package versions have a copyleft dependency at depth 3 or more? | Multi-hop, hard for an LLM |
| CQ8 | Is a project under MIT compatible with every license in the dependency tree of Y? | Inference |
| CQ9 | Which dependencies of X are copyleft, using the license class hierarchy rather than stored categories? | Inference |
| CQ10 | If I ship X under a proprietary or other license, which dependencies conflict, and which curated rule triggers each one? | Inference (rule) |
| CQ11 | Which conflicts are firm, and which could be avoided by choosing another option of a dual-licensed dependency? | Inference + aggregation |
| CQ12 | Which licenses appear most often across all package versions in the graph? | Aggregation |
| CQ13 | For each seed package, how large is its dependency tree and how many of those dependencies are copyleft? | Aggregation |
| CQ14 | Which license values lack an OSI flag or are non-SPDX (unknown, public-domain-style, proprietary)? | Filtering (OPTIONAL) |
| CQ15 | For the exact resolved version of package X, what is the exact chain that introduces each copyleft license? | Multi-hop, hard for an LLM |

Brief's minimums: 4 multi-hop (we have CQ3, CQ4, CQ6, CQ7, CQ15 = 5), 2 inference (CQ8, CQ9, CQ10, CQ11 = 4), 2 aggregation/filtering (CQ5, CQ12, CQ13, CQ14 = 4), 2 LLM-hard (CQ7, CQ15).
Why CQ7 and CQ15 are hard for an LLM: the answer depends on the real, version-pinned resolved dependency tree, which an LLM cannot see and tends to guess.

## CQ-to-KG mapping table

| CQ | Classes | Properties | SPARQL features | Inference needed | Query | Result on the real graph |
|----|---------|------------|-----------------|------------------|-------|--------------------------|
| CQ1 | Project, PackageVersion | `lg:directlyDependsOn`, `lg:packageName`, `lg:versionString` | BGP | No | Q01 | 4 direct dependencies of `acme-mit-app` |
| CQ2 | PackageVersion, License | `lg:hasLicense`, `lg:spdxId`, `lg:isOsiApproved` | BGP, OPTIONAL | No | Q01 | licenses alongside each dependency |
| CQ3 | PackageVersion, CopyleftLicense | `lg:directlyDependsOn+`, `lg:hasLicense` | property path `+`, `a/rdfs:subClassOf*` | Yes (subclass typing) | Q03, Q04 | 5 copyleft dependencies; 7 exact chains |
| CQ4 | PackageVersion, Project | `lg:directlyDependsOn+` towards the dependent | property path, COALESCE | Yes (transitivity) | Q07 | `mutagen` is reached by `acme-mit-app`, `beets`, `mediafile` |
| CQ5 | License | `lg:isOsiApproved` | FILTER, OPTIONAL, aggregation | No | Q02 | 5 license values without a confirmed OSI flag |
| CQ6 | PackageVersion, CopyleftLicense | `lg:directlyDependsOn`, `lg:hasLicense` | property path, GROUP BY, GROUP_CONCAT | Yes (transitivity) | Q08 | one row per direct dependency with copyleft below |
| CQ7 | PackageVersion, CopyleftLicense | `lg:directlyDependsOn` (fixed 3 hops then `*`) | path sequence `/`, FILTER | No (path written out) | Q13 | 2 rows (MPL-2.0 `certifi` below `beets` and `scrapy`) |
| CQ8 | Project, License, CompatibilityRule | `lg:treeContainsLicense`, `lg:conflictProject` | ASK, FILTER NOT EXISTS | Yes (property chain, rule) | Q10, Q12 | Q10 lists every license in the tree; Q12 answers false for `acme-mit-app` |
| CQ9 | License, CopyleftLicense | `rdf:type`, `rdfs:subClassOf` | inference-only pattern | Yes (subclass) | Q09 | 5 copyleft dependencies; 0 rows without reasoning |
| CQ10 | LicenseConflict, CompatibilityRule | `lg:conflictProject`, `lg:conflictDependency`, `lg:conflictRule`, `lg:conflictVerdict` | SELECT over derived individuals | Yes (rule R01) | Q11 | 16 conflicts: 5 Incompatible, 11 Conditional |
| CQ11 | LicenseConflict | `lg:isDisjunctiveLicense`, `lg:conflictVerdict` | COUNT, GROUP BY, IF | Yes (rule R01) | Q14 | 7 rows splitting firm and avoidable conflicts per project |
| CQ12 | License | `lg:hasLicense`, `lg:spdxId` | COUNT, GROUP BY, ORDER BY | No | Q05 | MIT 66, BSD-3-Clause 60, Apache-2.0 27 |
| CQ13 | PackageVersion | `lg:directlyDependsOn+`, `lg:hasLicense` | COUNT DISTINCT, property path | Yes (transitivity) | Q06 | for example `beets`: 19 transitive dependencies, 3 copyleft |
| CQ14 | License | `lg:isOsiApproved`, `lg:spdxId` | OPTIONAL, FILTER `!BOUND` | No | Q02 | same query as CQ5 |
| CQ15 | Package, PackageVersion | `lg:hasVersion`, `lg:versionString`, `lg:directlyDependsOn` | UNION per depth, CONCAT | Yes (typing) | Q04 | e.g. `acme-mit-app -> beets/2.14.1 -> mediafile/0.17.0 -> mutagen/1.48.1` |

Supplementary queries (`SPARQL_Queries/supplementary/`) cover the same questions with different formulations (for example Q12 for incompatible license pairs in one tree, which returns 0 rows on this data because no dependency tree here contains both sides of the one stored pair).

## Inference examples

See `Results/inference_examples.md`: four examples, each verified by script as absent from the stored graph and present after reasoning.
