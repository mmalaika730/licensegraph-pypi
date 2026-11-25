"""
predictor.py | loads the trained TransE model and ranks licenses for a package version.
Everything returned here is a PREDICTION: it is never written to the stored graph and never used by the conflict rule.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

LIC = "http://example.org/licensegraph/license/"


class Predictor:
    model_name = "TransE"

    def __init__(self, model_dir: Path):
        z = np.load(Path(model_dir) / "transe_model.npz", allow_pickle=False)
        meta = json.loads((Path(model_dir) / "transe_meta.json").read_text(encoding="utf-8"))
        self.E, self.R = z["E"], z["R"]
        self.ent = {e: i for i, e in enumerate(meta["entities"])}
        self.rel = {r: i for i, r in enumerate(meta["relations"])}
        self.licenses = meta["licenses"]
        self.held_out = {(h, t) for h, t in meta["held_out_links"]}
        self.meta = meta

    def was_held_out(self, node) -> bool:
        return any(h == str(node) for h, _ in self.held_out)

    def top_licenses(self, node, k: int = 3):
        h = self.ent.get(str(node))
        if h is None:
            return []
        L = np.array([self.ent[l] for l in self.licenses])
        d = self.E[h] + self.R[self.rel["hasLicense"]] - self.E[L]
        s = -np.sum(d * d, axis=1)
        order = np.argsort(-s)[:k]
        return [(self.licenses[i][len(LIC):], float(s[i])) for i in order]
