#!/usr/bin/env python3
"""
link_prediction.py | Iteration 2, modern KG reasoning, Option A (link prediction / KG completion).

Task: hide 20% of the stored `lg:hasLicense` links of package versions, train a TransE embedding on everything else,
and rank all 23 licenses for each hidden link. Predictions are compared with the held-out truth.

Protocol
  * 5 random splits (seeds 0-4); each split hides 20% of hasLicense triples (test). Dependency edges, package-version
    links and license categories stay in training, so the model can use graph structure but never the hidden answer.
  * Filtered ranking: other licenses that are truly linked to the same version are not counted as errors.
  * Metrics: MRR, Hits@1, Hits@3 (Hits@10 is reported but weak evidence: there are only 23 candidates).
  * Hyper-parameters are chosen on a validation split inside the training data of seed 0, never on test links.
  * Baselines: random (expected value), most-frequent license, neighbour vote (licenses of direct dependencies and dependents).
Outputs go to results_iter2/link_prediction/ and kg_reasoning/model/ and kg_reasoning/predictions.ttl.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kg_reasoning.data import LG, LIC, Index, load_triples  # noqa: E402
from kg_reasoning.transe import TransE  # noqa: E402


def split(X, hl, frac, rng):
    ids = np.where(X[:, 1] == hl)[0]
    test = rng.choice(ids, max(1, int(round(frac * len(ids)))), replace=False)
    keep = np.setdiff1d(np.arange(len(X)), test)
    return X[keep], X[test]


def known_map(X):
    m = {}
    for h, r, t in X:
        m.setdefault((int(h), int(r)), set()).add(int(t))
    return m


def rank_of(scores, truth, other_true):
    """scores: dict license id -> score. Rank 1 = best; other true licenses of the same version are skipped (filtered ranking)."""
    mine = scores[truth]
    return 1 + sum(1 for l, s in scores.items() if l != truth and l not in other_true and s > mine)


def metrics(ranks):
    r = np.array(ranks, dtype=float)
    return {"MRR": float(np.mean(1 / r)), "Hits@1": float(np.mean(r <= 1)), "Hits@3": float(np.mean(r <= 3)),
            "Hits@10": float(np.mean(r <= 10)), "n": int(len(r))}


def eval_transe(model, T, L, known, rel_hl):
    ranks = []
    lid = list(L)
    for h, r, t in T:
        s = model.score(np.full(len(L), h), rel_hl, L)
        full = dict(zip(lid, s))
        ranks.append(rank_of(full, int(t), known[(int(h), int(r))] - {int(t)}))
    return ranks


def eval_scores(score_fn, T, L, known):
    ranks = []
    lid = list(L)
    for h, r, t in T:
        full = dict(zip(lid, score_fn(int(h))))
        ranks.append(rank_of(full, int(t), known[(int(h), int(r))] - {int(t)}))
    return ranks


def baselines(train, L, idx):
    hl, dep = idx.rel["hasLicense"], idx.rel["directlyDependsOn"]
    lic_of = {}
    for h, r, t in train:
        if r == hl:
            lic_of.setdefault(int(h), []).append(int(t))
    freq = {int(l): 0 for l in L}
    for lics in lic_of.values():
        for l in lics:
            freq[l] = freq.get(l, 0) + 1
    out_n, in_n = {}, {}
    for h, r, t in train:
        if r == dep:
            out_n.setdefault(int(h), []).append(int(t))
            in_n.setdefault(int(t), []).append(int(h))

    def most_frequent(h):
        return [freq[int(l)] for l in L]

    def neighbour_vote(h):
        c = {int(l): 0.0 for l in L}
        for n in out_n.get(h, []) + in_n.get(h, []):
            for l in lic_of.get(n, []):
                c[l] += 1.0
        return [c[int(l)] + 0.001 * freq[int(l)] for l in L]      # frequency only breaks ties
    return {"most_frequent_license": most_frequent, "neighbour_vote": neighbour_vote}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--quick", action="store_true", help="small grid, for tests")
    a = ap.parse_args()
    root = Path(a.root)
    triples, licenses, versions = load_triples(root)
    idx = Index(triples)
    X = idx.encode(triples)
    hl = idx.rel["hasLicense"]
    L = np.array([idx.ent[l] for l in licenses])
    out = root / "results_iter2/link_prediction"
    out.mkdir(parents=True, exist_ok=True)
    print(f"{len(triples)} training-graph triples, {len(licenses)} licenses, {int((X[:, 1] == hl).sum())} hasLicense links")

    # ---- 1. hyper-parameter selection on a validation split of the seed-0 training data
    rng = np.random.default_rng(0)
    train0, test0 = split(X, hl, 0.2, rng)
    tr_in, val = split(train0, hl, 0.15, np.random.default_rng(100))
    known_v = known_map(train0)
    grid = list(itertools.product([16, 32], [0.5, 1.0], [100, 300])) if not a.quick else [(16, 1.0, 50)]
    rows = []
    for dim, margin, epochs in grid:
        m = TransE(len(idx.ents), len(idx.rel), dim=dim, margin=margin, seed=0).fit(tr_in, epochs=epochs)
        rows.append({"dim": dim, "margin": margin, "epochs": epochs, **metrics(eval_transe(m, val, L, known_v, hl))})
    rows.sort(key=lambda r: -r["MRR"])
    best = rows[0]
    print("validation grid (best first):")
    for r in rows:
        print("  ", r)
    (out / "hyperparameter_validation.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    # ---- 2. evaluation on held-out test links, several random splits
    res = {"TransE": [], "most_frequent_license": [], "neighbour_vote": [], "random (expected)": []}
    detail = []
    final_model, final_test = None, None
    for seed in range(a.seeds):
        train, test = split(X, hl, 0.2, np.random.default_rng(seed))
        known = known_map(X)
        m = TransE(len(idx.ents), len(idx.rel), dim=best["dim"], margin=best["margin"], seed=seed).fit(train, epochs=best["epochs"])
        res["TransE"].append(metrics(eval_transe(m, test, L, known, hl)))
        for name, fn in baselines(train, L, idx).items():
            res[name].append(metrics(eval_scores(fn, test, L, known)))
        n = len(L)
        res["random (expected)"].append({"MRR": float(np.mean([1 / k for k in range(1, n + 1)])), "Hits@1": 1 / n, "Hits@3": 3 / n,
                                         "Hits@10": 10 / n, "n": len(test)})
        if seed == 0:
            final_model, final_test, final_train = m, test, train
    summary = []
    for name, lst in res.items():
        row = {"method": name}
        for k in ("MRR", "Hits@1", "Hits@3", "Hits@10"):
            v = np.array([x[k] for x in lst])
            row[k] = f"{v.mean():.3f} +- {v.std():.3f}"
        row["test links per split"] = lst[0]["n"]
        summary.append(row)
    print("\nheld-out results (mean +- std over", a.seeds, "splits):")
    for r in summary:
        print("  ", r)
    (out / "link_prediction_results.json").write_text(json.dumps({"best_hyperparameters": best, "summary": summary, "per_split": res}, indent=2), encoding="utf-8")
    import csv
    with open(out / "link_prediction_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    # ---- 3. the seed-0 model is the one the application uses; save it with its held-out links
    mdir = root / "kg_reasoning/model"
    mdir.mkdir(parents=True, exist_ok=True)
    held = [[idx.ents[int(h)], idx.ents[int(t)]] for h, r, t in final_test]
    np.savez(mdir / "transe_model.npz", E=final_model.E, R=final_model.R)
    (mdir / "transe_meta.json").write_text(json.dumps({
        "entities": idx.ents, "relations": list(idx.rel), "licenses": licenses, "held_out_links": held,
        "hyperparameters": best, "seed": 0, "split": "20% of hasLicense links held out"}), encoding="utf-8")

    # ---- 4. per-link predictions for the held-out links, as CSV and as RDF (clearly typed as predictions)
    known = known_map(X)
    lines = ["@prefix lg:  <http://example.org/licensegraph#> .", "@prefix lic: <http://example.org/licensegraph/license/> .",
             "@prefix pred: <http://example.org/licensegraph/prediction/> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
             "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", "",
             "# GENERATED by kg_reasoning/link_prediction.py. These are MODEL PREDICTIONS, not stored or inferred facts.",
             "# They use lg:predictedLicense, never lg:hasLicense, and must not be loaded into the graph that the conflict rule reads.", ""]
    rows_csv = []
    lid = list(L)
    for i, (h, r, t) in enumerate(final_test):
        s = final_model.score(np.full(len(L), h), hl, L)
        order = np.argsort(-s)
        truth_rank = rank_of(dict(zip(lid, s)), int(t), known[(int(h), int(r))] - {int(t)})
        for rank, j in enumerate(order[:3], 1):
            lic = licenses[j]
            rows_csv.append({"package_version": idx.ents[int(h)].split("/ver/")[-1], "hidden_true_license": idx.ents[int(t)].split("/license/")[-1],
                             "rank": rank, "predicted_license": lic.split("/license/")[-1], "score": f"{s[j]:.4f}",
                             "correct": lic == idx.ents[int(t)], "true_license_rank": truth_rank})
            lines.append(f"pred:{i}-{rank} a lg:LicensePrediction ; lg:predictionFor <{idx.ents[int(h)]}> ; lg:predictedLicense <{lic}> ; "
                         f"lg:predictionRank {rank} ; lg:predictionScore \"{s[j]:.4f}\"^^xsd:decimal ; lg:predictionMethod \"TransE\" ; "
                         f"lg:heldOutLink true ; lg:predictionStatus \"prediction, not a verified fact\" .")
    (root / "kg_reasoning/predictions.ttl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out / "heldout_predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
        w.writeheader()
        w.writerows(rows_csv)
    print(f"\nwrote {len(rows_csv)} prediction rows, model in kg_reasoning/model/, RDF in kg_reasoning/predictions.ttl")


if __name__ == "__main__":
    main()
