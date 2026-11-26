# Modern KG reasoning: link prediction with TransE (Option A)

## What we chose and why
We implemented **Option A, link prediction / KG completion**. The task fits our domain: a package version's license is the most important fact in the graph, and for real PyPI data it is sometimes missing or ambiguous (many packages only declare a trove classifier such as "BSD License"). A model that suggests the most plausible license from the graph structure is a realistic completion task. Predictions are only suggestions: they are stored apart from the facts, labelled as predictions, and never used by the conflict rule.

## How TransE works (in our own words)
TransE [1] represents every entity in our graph (a package version, a license, a license category) and every relation (`directlyDependsOn`, `hasLicense`, `hasVersion`, `inCategory`) as a short vector of numbers; after tuning we used 16 numbers per vector. The core idea is that a relation behaves like a step: if a fact (head, relation, tail) is true, then starting at the head's vector and adding the relation's vector should land close to the tail's vector, so **h + r ≈ t**. For example, `packaging/26.3 + hasLicense` should end up near `Apache-2.0`. A triple's score is minus the squared distance between h + r and t, so a score near zero means the fact looks believable and a large negative score means it does not. To train, we take each true triple and create a fake one by swapping its head or its tail for another entity that has appeared in that position for the same relation (for example, another license in place of the true one), then nudge the vectors so the true triple ends up closer than the fake one by at least a fixed margin. After every pass over the data (epoch), all entity vectors are rescaled to length 1, otherwise the model could reduce the loss just by making vectors bigger instead of learning anything. To predict a missing license, we score (version, hasLicense, L) for all 23 licenses L, sort them from best to worst, and treat the top one as the model's guess.

Why this suits our graph: TransE handles many-to-one relations like `hasLicense` only approximately (many versions point to MIT), which [2] also points out, so we expected modest results and compare against simple baselines.

## Data and protocol
* Graph used for training (644 triples): `directlyDependsOn` (247), `hasLicense` (195), `hasVersion` (179), and `inCategory` for each license (23). Demo projects are excluded because their licenses are chosen by us, not observed. Literal properties such as `declaredLicenseString` are not used, because they would reveal the answer.
* **Hidden links:** 20% of the 195 `hasLicense` links (39 links) are removed before training; the model must recover them. Five random splits (seeds 0 to 4) are run.
* **Metrics** [2]: filtered MRR, Hits@1, Hits@3, Hits@10. "Filtered" means that if a version really has two licenses, the second true license is not counted as an error when the first is evaluated. With only 23 candidate licenses Hits@10 is weak evidence.
* **Hyper-parameters** (dimension 16 or 32, margin 0.5 or 1.0, 100 or 300 epochs) were chosen on a validation split taken inside the training data of seed 0, never on the test links.
* **Baselines:** random (expected value), *most frequent license* (always guess MIT, BSD-3-Clause, ...), and *neighbour vote* (the licenses of the direct dependencies and dependents of the version).

## Results (mean ± std over 5 splits; produced by `python kg_reasoning/link_prediction.py`)
| Method | MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---|---|---|---|
| TransE | 0.556 ± 0.058 | 0.410 ± 0.061 | 0.621 ± 0.094 | 0.877 ± 0.025 |
| Most frequent license | 0.563 ± 0.044 | 0.318 ± 0.048 | 0.764 ± 0.052 | 0.944 ± 0.025 |
| Neighbour vote | 0.616 ± 0.023 | 0.441 ± 0.034 | 0.749 ± 0.041 | 0.944 ± 0.025 |
| Random (expected) | 0.162 | 0.043 | 0.130 | 0.435 |

**Reading the results honestly.** TransE is far better than random and gets the exact license first for about 41% of hidden links, more often than the most-frequent baseline (32%). But it does **not** clearly beat the simple neighbour-vote baseline (44%), and its MRR is about the same as always guessing the common license. The reason is that in this graph a license says little about structure: most packages are MIT, BSD or Apache, and licenses do not follow dependency edges strongly. So the model is a weak signal and is presented as such. This matches the warning in [2] that simple methods can rival embeddings on small graphs. Reproducing it with a different seed gives different numbers within the standard deviation shown.

## Predictions versus facts
* `kg_reasoning/predictions.ttl` holds the model's top-3 guesses for the 39 hidden links as `lg:LicensePrediction` individuals with `lg:predictedLicense`, rank, score, method and `lg:predictionStatus "prediction, not a verified fact"`. `lg:predictedLicense` is deliberately **not** a sub-property of `lg:hasLicense`, so no reasoner or rule treats it as a fact.
* In GraphDB it is loaded into its own named graph (see `GraphDB_Iteration2.md`); query `Q15` compares guess and stored license.
* In the application, a prediction is printed as "PREDICTION (not a confirmed fact)" and says whether the link was hidden during training (a genuine test) or not.

## Limitations
Small graph (179 versions, 23 licenses); one relation of interest; no hyper-parameter search beyond a tiny grid; no use of text such as the license classifier (which would help but is kept out on purpose to avoid leaking the answer); TransE scores are distances, not probabilities.

## Explicit, inferred and predicted knowledge in this project
| Kind | Example | How obtained |
|---|---|---|
| Explicit | `beets/2.14.1 directlyDependsOn mediafile/0.17.0` | stored triple |
| Inferred | `acme-mit-app dependsOn mutagen/1.48.1` | OWL 2 RL transitivity; conflict rule |
| Predicted | "websocket-client is probably Apache-2.0" | TransE, never stored as a fact |

## Extra experiment: margin 2.0
We added margin 2.0 to the hyper-parameter grid (dimension 16 or 32, margin 0.5, 1.0 or 2.0, 100 or 300 epochs: 12 settings instead of 8) and re-ran the experiment in a separate copy of the repository, so the committed model and results above are unchanged. Margin 2.0 won on validation (dimension 32, margin 2.0, 300 epochs: validation MRR 0.547 against 0.544 for the original choice), and on the held-out links TransE improved from MRR 0.556 to 0.593, Hits@1 from 0.410 to 0.431 and Hits@3 from 0.621 to 0.723, which brings it close to the neighbour-vote baseline (MRR 0.616, Hits@1 0.441) but still not above it. We think the larger margin helps because it forces the true license of a version to score clearly better than the wrong ones, which matters when most versions share a few common licenses, and the larger dimension gives the model more room to separate them. The gain is smaller than one standard deviation (0.056 for MRR) and margin 2.0 was chosen by a validation gap of only 0.002 on 23 links, so it is a small improvement that may not hold on other data.
