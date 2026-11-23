# LicenseGraph-PyPI | AI-3001 Knowledge Representation & Reasoning (Iterations 1 and 2)

An open-source **license conflict reasoner for Python dependency trees**, built as a knowledge graph with OWL reasoning, SPARQL, a modern KG reasoning component (link prediction with TransE) and a knowledge-grounded LLM question-answering application.

Team: Malaika Majid, Omar Waqar, Fiza Ali. Instructor: Ms. Mehreen Javaid. Final submission commit: see the report (tag `iteration2-final`).

## What is in this repository

| Folder | Contents | Iteration |
|---|---|---|
| `Dataset/` | real PyPI dependency data (pip resolver + PyPI metadata), SPDX license list, curated license categories, 27 compatibility rules with sources and a check of the cited rules, deps.dev extraction SQL (not run) | 1 |
| `Ontology/` | OWL ontology (17 classes, 19 object and 20 datatype properties), generated rules file, merged file for Protégé | 1, extended in 2 |
| `RDF_Knowledge_Graph/` | `instances.ttl` (2,365 triples), build script, cleaning report, URI design | 1 |
| `SPARQL_Queries/` | `Q01` to `Q14` (Iteration 1) and `Q15` (predictions vs stored licenses), conflict inference rule, runner scripts | 1, 2 |
| `Results/` | one CSV per query, symbolic inference examples | 1, 2 |
| `Visualization/` | graph images and screenshots | 1, 2 |
| `Report/` | competency questions and CQ-to-KG mapping, progress report, requirements check | 1 |
| `kg_reasoning/` | **Iteration 2, modern KG reasoning:** TransE link prediction in NumPy, trained model, predictions as RDF | 2 |
| `kg_qa/` | **Iteration 2, application:** KG loader with reasoning, question router, retrieval, LLM client, pipeline, CLI, Streamlit UI | 2 |
| `prompts/` | the exact prompts sent to the LLM (grounded and LLM-only) | 2 |
| `evaluation/` | the 10 competency questions with expected answers, evaluation script, explainability script, manual review template | 2 |
| `results_iter2/` | link-prediction results, LLM-only vs KG-grounded comparison, explainability examples | 2 |
| `docs/` | method description, architecture, GraphDB/Protégé steps, references, statement on AI tools | 2 |
| `tests/` | automated tests | 2 |

## Prerequisites
* Python 3.10 or newer, `git`
* Java is only needed if you want to run the HermiT reasoner outside Protégé
* Optional for the demonstration: Protégé 5.x and GraphDB (Desktop or Free), see `docs/GraphDB_Iteration2.md`
* An LLM endpoint for the application and the evaluation (any OpenAI-compatible service, or a local Ollama server)

## Setup
```bash
git clone <repository URL>
cd <repository folder>
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # Windows: copy .env.example .env
# edit .env: LLM_BASE_URL, LLM_MODEL, LLM_API_KEY (see the examples inside the file). .env is git-ignored; never commit a key.
```
The data and the trained model are already in the repository, so nothing has to be downloaded to run the application.

## Run
```bash
python -m pytest -q tests                                  # 18 tests; no LLM or network needed

# the application
python -m kg_qa.cli "Why is mutagen flagged for acme-mit-app?"
python -m kg_qa.cli --no-llm "Which packages are exposed to mutagen anywhere below them?"   # evidence only
streamlit run kg_qa/app_streamlit.py                       # web interface

# modern KG reasoning (about 1 minute); rewrites kg_reasoning/model, kg_reasoning/predictions.ttl, results_iter2/link_prediction
python kg_reasoning/link_prediction.py

# evaluation: 10 competency questions, LLM only vs LLM + knowledge graph
python evaluation/evaluate.py --retrieval-only             # no LLM: checks the graph retrieval holds the expected facts
python evaluation/evaluate.py                              # needs the LLM; writes results_iter2/evaluation/
python evaluation/evaluate.py --from-raw                   # rebuilds the table from saved answers + manual_review.csv (no LLM call)
python evaluation/explain_examples.py                      # explainability examples -> results_iter2/explainability/
```
Correctness in `comparison_table.md` is first an automatic key-term check; fill in `evaluation/manual_review.csv` (template: `manual_review_TEMPLATE.csv`) after reading the answers, and re-run to use the manual judgement.

## Data preparation
The graph was built from real PyPI data (pip's dependency resolver and PyPI metadata for 45 seed packages, fetched on 2026-11-04). To rebuild it from scratch see "Reproduce Iteration 1" below. Large files are not involved: `instances.ttl` is about 400 KB.

## Configuration
`.env.example` is the sample configuration (no credentials). The same LLM client, model and temperature (0) are used for both conditions of the evaluation.

## Reproduce Iteration 1

```bash
# 1. data (needs internet to pypi.org)            -> Dataset/pypi/*.csv
python3 Dataset/pypi/fetch_pypi.py --out-dir Dataset/pypi
# 2. rules table -> Turtle
python3 Ontology/make_rules_ttl.py --rules Dataset/curated/compatibility_rules.csv --sources Dataset/curated/compatibility_sources.csv --out Ontology/compatibility_rules.ttl
# 3. knowledge graph                              -> RDF_Knowledge_Graph/instances.ttl
python3 RDF_Knowledge_Graph/build_kg.py --versions Dataset/pypi/node_versions.csv --edges Dataset/pypi/direct_edges.csv \
  --spdx Dataset/spdx/licenses.json --categories Dataset/curated/license_categories.csv --projects Dataset/curated/projects.csv \
  --ontology Ontology/licensegraph_ontology.ttl Ontology/compatibility_rules.ttl --out-dir RDF_Knowledge_Graph
# 4. run all queries locally with an OWL 2 RL reasoner (stand-in for GraphDB) -> Results/
python3 SPARQL_Queries/run_queries.py --ontology Ontology/licensegraph_ontology.ttl Ontology/compatibility_rules.ttl \
  --instances RDF_Knowledge_Graph/instances.ttl --results-dir Results
# 5. inference examples and graph images
python3 SPARQL_Queries/inference_examples.py --ontology Ontology/licensegraph_ontology.ttl Ontology/compatibility_rules.ttl \
  --instances RDF_Knowledge_Graph/instances.ttl --rule SPARQL_Queries/00_infer_conflicts.ru --out Results/inference_examples.md
python3 Visualization/make_graph_images.py --instances RDF_Knowledge_Graph/instances.ttl --project acme-mit-app --out-dir Visualization
```

Note: step 1 re-resolves current PyPI releases, so versions and counts will differ from the submitted snapshot (`Dataset/pypi/manifest.json` records the date). Skip it to reproduce exactly.

GraphDB loading and Protégé: see `Report/GraphDB_and_Protege_guide.md`.
