# References and how they informed the implementation

All sources below were consulted for Iteration 2 (links checked on 22 November 2026). In-text citations in the other documents use these numbers.

## Reference list

1. A. Bordes, N. Usunier, A. Garcia-Duran, J. Weston, O. Yakhnenko. "Translating Embeddings for Modeling Multi-relational Data." Advances in Neural Information Processing Systems 26 (NIPS 2013). https://proceedings.neurips.cc/paper/2013/file/1cecc7a77928ca8133fa24680a88d2f9-Paper.pdf
2. A. Rossi, D. Barbosa, D. Firmani, A. Matinata, P. Merialdo. "Knowledge Graph Embedding for Link Prediction: A Comparative Analysis." ACM Transactions on Knowledge Discovery from Data 15(2), 2021. https://arxiv.org/abs/2002.00819 (DOI 10.1145/3424672)
3. P. Lewis et al. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." NeurIPS 2020. https://arxiv.org/abs/2005.11401
4. D. Edge et al. "From Local to Global: A Graph RAG Approach to Query-Focused Summarization." Microsoft Research, 2024. https://arxiv.org/abs/2404.16130
5. S. Pan, L. Luo, Y. Wang, C. Chen, J. Wang, X. Wu. "Unifying Large Language Models and Knowledge Graphs: A Roadmap." IEEE Transactions on Knowledge and Data Engineering 36(7), 2024. https://arxiv.org/abs/2306.08302 (DOI 10.1109/TKDE.2024.3352100)
6. Z. Ji et al. "Survey of Hallucination in Natural Language Generation." ACM Computing Surveys 55(12), 2023. https://arxiv.org/abs/2202.03629 (DOI 10.1145/3571730)
7. A. Hogan et al. "Knowledge Graphs." ACM Computing Surveys 54(4), 2021. https://arxiv.org/abs/2003.02320 (DOI 10.1145/3447772)
8. W3C. "OWL 2 Web Ontology Language Profiles (OWL 2 RL)." https://www.w3.org/TR/owl2-profiles/#OWL_2_RL
9. W3C. "SPARQL 1.1 Query Language." https://www.w3.org/TR/sparql11-query/
10. RDFLib and OWL-RL documentation and source. https://rdflib.readthedocs.io and https://github.com/RDFLib/OWL-RL
11. Ontotext. "GraphDB documentation" (repositories, rulesets, named graphs, explicit/implicit graphs). https://graphdb.ontotext.com/documentation/
12. Streamlit documentation. https://docs.streamlit.io
13. The documentation of the LLM provider that was used for the evaluation (endpoint, model name and rate limits): see `.env.example` and fill in the provider's page in the final report.

Iteration 1 sources for the compatibility rules (Apache GPL-compatibility page, FSF licensing post, Qt LGPL obligations, MPL 2.0 FAQ, Kemitchell AGPL guide) are listed in `Dataset/curated/compatibility_sources.csv`.

## How each key reference informed the work

| Ref | What we took from it | Where it shows up |
|---|---|---|
| [1] | The TransE idea: relations as translations (h + r is close to t), margin ranking loss, negative sampling by corrupting head or tail, unit-length entity vectors | `kg_reasoning/transe.py` (our own NumPy implementation) |
| [2] | How to evaluate link prediction fairly: filtered ranking, MRR and Hits@k, and comparison against simple baselines; the warning that embeddings often need tuning and can be matched by simple methods | `kg_reasoning/link_prediction.py` (filtered ranks, baselines, several splits) |
| [3] | The retrieve-then-generate pattern: fetch relevant evidence at query time and give it to the generator instead of relying on the model's memory | `kg_qa/qa.py`, `prompts/grounded_*.txt` |
| [4] | Background on graph-based RAG; we do not implement its community summarisation, we retrieve exact facts and paths with graph queries instead, which suits version-pinned dependency trees | `docs/application_architecture.md` |
| [5] | The three ways KGs and LLMs combine; our system is the "KG-enhanced LLM at inference time" pattern, and the survey motivates showing provenance | `kg_qa/`, explainability examples |
| [6] | Why a plain LLM invents plausible but unsupported claims (hallucination) and why answers must be checked against sources | LLM-only vs KG-grounded evaluation; the "insufficient evidence" behaviour |
| [7] | Terminology for the KG, for the distinction between stored and derived knowledge, and for open-world versus closed-world reading of the graph | report sections on design and limitations |
| [8] | The OWL 2 RL rule set that gives transitivity, symmetry, subclass typing and property chains; this is what the `inferred` label means | `kg_qa/kg.py` (owlrl closure), GraphDB ruleset OWL2-RL |
| [9] | Property paths, aggregation, named graphs (`GRAPH`) used in the retrieval queries and Q15 | `SPARQL_Queries/`, `kg_qa/retrievers.py` |
| [10] | The libraries used to load, reason over and query the graph without GraphDB | `kg_qa/kg.py` |
| [11] | Loading the predictions into a separate named graph; checking explicit versus implicit statements | `docs/GraphDB_Iteration2.md` |
| [12] | The web demo | `kg_qa/app_streamlit.py` |

## Reading checklist for the viva
Each member should have read at least the papers behind their own component (see the team plan): the link-prediction member [1] and [2]; the retrieval member [7], [8], [9]; the LLM-application member [3], [5], [6]. Everyone should be able to say in one sentence what [4] adds beyond [3].
