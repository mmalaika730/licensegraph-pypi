"""
transe.py | TransE knowledge-graph embedding in plain NumPy (Bordes et al., 2013).

Idea: every entity and relation is a vector. A true triple (h, r, t) should satisfy  h + r ~= t,
so the plausibility score is  score(h, r, t) = -|| h + r - t ||^2  (higher = more plausible).
Training pushes true triples to a smaller distance than corrupted ones (a random wrong head or tail) by at least `margin`:
    loss = max(0, margin + d(h, r, t) - d(h', r, t'))
Entity vectors are re-normalised to length 1 after each epoch, as in the original paper.
"""
from __future__ import annotations

import numpy as np


class TransE:
    def __init__(self, n_ent: int, n_rel: int, dim: int = 32, margin: float = 1.0, lr: float = 0.05,
                 neg: int = 4, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        bound = 6.0 / np.sqrt(dim)
        self.E = self.rng.uniform(-bound, bound, (n_ent, dim))
        self.R = self.rng.uniform(-bound, bound, (n_rel, dim))
        self.R /= np.linalg.norm(self.R, axis=1, keepdims=True)
        self.margin, self.lr, self.neg = margin, lr, neg
        self._normalise()

    def _normalise(self):
        self.E /= np.maximum(np.linalg.norm(self.E, axis=1, keepdims=True), 1e-9)

    def score(self, h, r, t):
        d = self.E[h] + self.R[r] - self.E[t]
        return -np.sum(d * d, axis=-1)

    def fit(self, triples: np.ndarray, epochs: int = 300, batch: int = 64, verbose: bool = False):
        # type-constrained corruption: a corrupted head/tail is drawn from the entities seen in that slot for that relation
        heads = {r: np.unique(triples[triples[:, 1] == r, 0]) for r in np.unique(triples[:, 1])}
        tails = {r: np.unique(triples[triples[:, 1] == r, 2]) for r in np.unique(triples[:, 1])}
        n = len(triples)
        for ep in range(epochs):
            perm = self.rng.permutation(n)
            total = 0.0
            for i in range(0, n, batch):
                b = triples[perm[i:i + batch]]
                for _ in range(self.neg):
                    h, r, t = b[:, 0], b[:, 1], b[:, 2]
                    h2, t2 = h.copy(), t.copy()
                    flip = self.rng.random(len(b)) < 0.5
                    for j in range(len(b)):
                        if flip[j]:
                            h2[j] = self.rng.choice(heads[r[j]])
                        else:
                            t2[j] = self.rng.choice(tails[r[j]])
                    pos = self.E[h] + self.R[r] - self.E[t]
                    negd = self.E[h2] + self.R[r] - self.E[t2]
                    viol = (self.margin + np.sum(pos * pos, 1) - np.sum(negd * negd, 1)) > 0
                    total += float(np.sum(np.maximum(0, self.margin + np.sum(pos * pos, 1) - np.sum(negd * negd, 1))))
                    if not viol.any():
                        continue
                    g_pos, g_neg = 2 * pos[viol], 2 * negd[viol]
                    hv, rv, tv, h2v, t2v = h[viol], r[viol], t[viol], h2[viol], t2[viol]
                    lr = self.lr
                    np.add.at(self.E, hv, -lr * g_pos)
                    np.add.at(self.E, tv, lr * g_pos)
                    np.add.at(self.R, rv, -lr * g_pos)
                    np.add.at(self.E, h2v, lr * g_neg)
                    np.add.at(self.E, t2v, -lr * g_neg)
                    np.add.at(self.R, rv, lr * g_neg)
            self._normalise()
            if verbose and (ep + 1) % 50 == 0:
                print(f"  epoch {ep + 1:4d}  loss {total / n:.4f}")
        return self
