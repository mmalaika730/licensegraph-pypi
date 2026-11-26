# Explainability and provenance examples

Legend: EXPLICIT = stored triple; INFERRED = derived by OWL 2 RL schema reasoning or by the conflict rule; PREDICTION = TransE link prediction; GENERATED TEXT = the LLM's natural-language answer, which may only restate the facts above.

## E1. Why is mutagen flagged for acme-mit-app?
*What it shows: multi-hop chain + rule-derived conflict.*  Intent: `conflicts`  Status: `answered`

**Retrieval:** `INSERT rule 00_infer_conflicts.ru then SELECT ?c a lg:LicenseConflict ; lg:conflictProject ?proj ; lg:conflictRule ?rule ; lg:conflictVerdict ?verdict`

| id | knowledge type | fact | derived by | provenance |
|---|---|---|---|---|
| F1 | INFERRED (derived by schema or rule) | acme-mit-app conflicts with mutagen/1.48.1 (license GPL-2.0-or-later): verdict Incompatible by rule R1 (cited). Rule rationale: A permissive project that incorporates strong-copyleft code becomes a derivative work that must be distributed under the GPL, which conflicts with keeping the permissive license (Apache page: GPLv3 software cannot be included in Apache projects). | conflict rule over lg:CompatibilityRule individuals + license categories (SPARQL INSERT) | sources: https://www.apache.org/licenses/GPL-compatibility; https://www.fsf.org/blogs/licensing/licensing-and-compliance-lab-the-most-frequently-asked-frequently-asked-questions |
| F2 | EXPLICIT (stored in the graph) | Chain (3 hops) that brings mutagen/1.48.1 into acme-mit-app: acme-mit-app -> beets/2.14.1 -> mediafile/0.17.0 -> mutagen/1.48.1. | each arrow is a stored lg:directlyDependsOn edge | pip resolver output |

**GENERATED TEXT (LLM answer):** Mutagen is flagged because it brings GPL‑2.0‑or‑later code into **acme‑mit‑app**, and under rule R1 this creates an incompatibility: a permissive project that incorporates strong‑copyleft code must be distributed under the GPL, which conflicts with the app’s permissive license [F1 (inferred)]. The GPL‑licensed mutagen version reaches the app through a three‑hop dependency chain (acme‑mit‑app → beets 2.14.1 → mediafile 0.17.0 → mutagen 1.48.1) [F2 (explicit)]. This incompatibility is why mutagen is flagged.

**Facts cited by the answer:** F1, F2

## E2. Can an Apache-2.0 project depend on a GPL-2.0-only package?
*What it shows: license-level fact and its symmetric inference + category rule.*  Intent: `license_pair`  Status: `answered`

**Retrieval:** `?rule a lg:CompatibilityRule ; lg:projectCategory ?pc ; lg:dependencyCategory ?dc ; lg:verdict ?v  (categories of the two licenses)  +  ?a lg:incompatibleWith ?b  (license-level, symmetric)`

| id | knowledge type | fact | derived by | provenance |
|---|---|---|---|---|
| F1 | EXPLICIT (stored in the graph) | Apache-2.0 belongs to category PermissiveLicense. | stored rdf:type of the license | license_categories.csv (our own table) |
| F2 | EXPLICIT (stored in the graph) | GPL-2.0-only belongs to category StrongCopyleftLicense. | stored rdf:type of the license | license_categories.csv (our own table) |
| F3 | INFERRED (derived by schema or rule) | Apache-2.0 is stated to be incompatible with GPL-2.0-only at license level. | lg:incompatibleWith is symmetric | Apache Software Foundation, GPL compatibility page |
| F4 | EXPLICIT (stored in the graph) | Assuming the project is under Apache-2.0 and the dependency under GPL-2.0-only: rule R1 gives verdict Incompatible for (PermissiveLicense, StrongCopyleftLicense). Rationale: A permissive project that incorporates strong-copyleft code becomes a derivative work that must be distributed under the GPL, which conflicts with keeping the permissive license (Apache page: GPLv3 software cannot be included in Apache projects). | stored rule individual (cited) | sources: https://www.apache.org/licenses/GPL-compatibility; https://www.fsf.org/blogs/licensing/licensing-and-compliance-lab-the-most-frequently-asked-frequently-asked-questions |

**GENERATED TEXT (LLM answer):** No. An Apache‑2.0 project cannot depend on a GPL‑2.0‑only package because the two licenses are incompatible — Apache‑2.0 is a permissive license while GPL‑2.0‑only is a strong‑copyleft license, and the knowledge graph records an incompatibility verdict for that combination [F1][F2][F3][F4]. This reflects a legal risk.

**Facts cited by the answer:** F1, F2, F3, F4

## E3. Which package versions have a copyleft dependency three or more hops below them?
*What it shows: multi-hop inference.*  Intent: `deep_copyleft`  Status: `answered`

**Retrieval:** `?v lg:isSeedRoot true . ?v lg:directlyDependsOn/lg:directlyDependsOn/lg:directlyDependsOn/lg:directlyDependsOn* ?dv . ?dv lg:hasLicense/a/rdfs:subClassOf* lg:CopyleftLicense   (the same pattern as Iteration 1 query Q13)`

| id | knowledge type | fact | derived by | provenance |
|---|---|---|---|---|
| F1 | INFERRED (derived by schema or rule) | beets/2.14.1 has copyleft dependency certifi/2026.10.23 (MPL-2.0) at depth 3 or more. | directlyDependsOn path of 3+ hops; copyleft through rdfs:subClassOf | derived from PyPI dependency data |
| F2 | INFERRED (derived by schema or rule) | scrapy/2.19.0 has copyleft dependency certifi/2026.10.23 (MPL-2.0) at depth 3 or more. | directlyDependsOn path of 3+ hops; copyleft through rdfs:subClassOf | derived from PyPI dependency data |

**GENERATED TEXT (LLM answer):** - beets 2.14.1 has a copyleft dependency three or more hops below it [inferred F1]  
- scrapy 2.19.0 has a copyleft dependency three or more hops below it [inferred F2]

**Facts cited by the answer:** F1, F2

## E4. Predict the license of websocket-client
*What it shows: link-prediction output kept apart from facts.*  Intent: `predict_license`  Status: `answered`

**Retrieval:** `kg_reasoning/predictor.py: TransE ranks all License entities for (node, lg:hasLicense, ?) by score -||h + r - t||^2`

| id | knowledge type | fact | derived by | provenance |
|---|---|---|---|---|
| F1 | EXPLICIT (stored in the graph) | The stored (verified) license of websocket-client/1.9.2 is Apache-2.0. | stored triple lg:hasLicense | PyPI metadata, license value from 'license_text' |
| F2 | PREDICTION (model guess, not a fact) | PREDICTION (not a confirmed fact): rank 1 license for websocket-client/1.9.2 is Apache-2.0 (model score -1.934); this license link was hidden from the model during training, so this is a genuine prediction. | TransE link prediction (held-out MRR about 0.56, see results_iter2/link_prediction) | kg_reasoning |
| F3 | PREDICTION (model guess, not a fact) | PREDICTION (not a confirmed fact): rank 2 license for websocket-client/1.9.2 is 0BSD (model score -2.030); this license link was hidden from the model during training, so this is a genuine prediction. | TransE link prediction (held-out MRR about 0.56, see results_iter2/link_prediction) | kg_reasoning |
| F4 | PREDICTION (model guess, not a fact) | PREDICTION (not a confirmed fact): rank 3 license for websocket-client/1.9.2 is LGPL-2.1-or-later (model score -2.267); this license link was hidden from the model during training, so this is a genuine prediction. | TransE link prediction (held-out MRR about 0.56, see results_iter2/link_prediction) | kg_reasoning |

**GENERATED TEXT (LLM answer):** The model’s top prediction for the license of websocket‑client 1.9.2 is **Apache‑2.0** (predicted, not verified) [F2]. The knowledge graph also contains an explicit, verified record that the stored license for this package version is **Apache‑2.0** [F1].

**Facts cited by the answer:** F1, F2

## E5. Which license will django 6.0 use?
*What it shows: insufficient evidence handled without guessing.*  Intent: `license_of`  Status: `insufficient_evidence`

**GENERATED TEXT (LLM answer):** Insufficient evidence in the knowledge graph. The graph does not contain django version 6.0; it only holds django 6.1.3.

**Why no answer:** The graph does not contain django version 6.0; it only holds django 6.1.3.
