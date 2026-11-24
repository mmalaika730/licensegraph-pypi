"""
qa.py | the question-answering pipeline.

  question -> route (entity linking + intent) -> KG retrieval (SPARQL / graph traversal) -> numbered facts
           -> prompt -> LLM -> answer -> citation check -> answer + evidence

If the graph cannot support an answer the LLM is NOT asked to improvise: the pipeline returns "insufficient evidence"
with the reason. The LLM-only baseline (`ask_llm_only`) exists only for the comparative evaluation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .kg import KG
from .retrievers import RETRIEVERS, Retrieval
from .router import Route, route as make_route

INSUFFICIENT = "Insufficient evidence in the knowledge graph."


@dataclass
class Answer:
    question: str
    status: str                       # answered | insufficient_evidence | llm_unavailable
    answer: str = ""
    intent: str | None = None
    route_note: str = ""
    entities: dict = field(default_factory=dict)
    facts: list = field(default_factory=list)
    queries: list = field(default_factory=list)
    retrieval_note: str = ""
    prompt: str = ""
    cited_ids: list = field(default_factory=list)
    uncited_warning: bool = False
    llm_name: str = ""

    def evidence_table(self):
        return [(f.id, f.kind, f.text, f.via, f.source) for f in self.facts]


class QA:
    def __init__(self, kg: KG, llm=None, predictor=None, root: Path | None = None, max_facts: int = 40):
        self.kg, self.llm, self.predictor = kg, llm, predictor
        self.root = Path(root) if root else Path(__file__).resolve().parent.parent
        self.max_facts = max_facts
        self.sys_grounded = (self.root / "prompts/grounded_system.txt").read_text(encoding="utf-8")
        self.usr_grounded = (self.root / "prompts/grounded_user.txt").read_text(encoding="utf-8")
        self.sys_plain = (self.root / "prompts/llm_only_system.txt").read_text(encoding="utf-8")
        self.usr_plain = (self.root / "prompts/llm_only_user.txt").read_text(encoding="utf-8")

    # ---------------------------------------------------------------- retrieval only
    def retrieve(self, question: str):
        r: Route = make_route(self.kg, question)
        ent = {"projects": [n for n, _ in r.entities.projects], "packages": [n for n, _ in r.entities.packages],
               "licenses": [n for n, _ in r.entities.licenses], "categories": r.entities.categories}
        if r.intent is None or r.status != "ok":
            return r, ent, None
        fn = RETRIEVERS[r.intent]
        ret: Retrieval = fn(self.kg, nodes=r.nodes, targets=r.targets, route=r, predictor=self.predictor)
        ret.number()
        return r, ent, ret

    def ask(self, question: str) -> Answer:
        r, ent, ret = self.retrieve(question)
        a = Answer(question=question, status="insufficient_evidence", intent=r.intent, entities=ent, route_note=r.reason)
        if ret is None or (not ret.facts and not ret.note):
            a.answer = INSUFFICIENT + " " + (r.reason or "The graph returned no facts for this question.")
            return a
        a.facts, a.queries, a.retrieval_note = ret.facts[: self.max_facts], ret.queries, ret.note
        if not ret.facts:                                  # e.g. "no copyleft dependency found": a graph statement, not an LLM guess
            a.answer = f"{ret.note} (This is based on the graph only; it contains the 179 package versions and 4 demo projects loaded from the PyPI snapshot.)"
            a.status = "answered"
            return a
        facts_txt = "\n".join(f"{f.id} [{f.kind}] {f.text}" for f in a.facts)
        if len(ret.facts) > self.max_facts:
            facts_txt += f"\n(Only the first {self.max_facts} of {len(ret.facts)} facts are shown.)"
        note = f"NOTE: {ret.note}\n\n" if ret.note else ""
        a.prompt = self.usr_grounded.format(question=question, facts=facts_txt, note=note)
        if self.llm is None:
            a.status, a.answer = "llm_unavailable", "(No LLM configured: showing the retrieved evidence only. Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in .env.)"
            return a
        a.llm_name = self.llm.name
        a.answer = self.llm.chat(self.sys_grounded, a.prompt)
        a.cited_ids = sorted(set(re.findall(r"F\d+", a.answer)), key=lambda x: int(x[1:]))
        refused = a.answer.strip().lower().startswith("insufficient evidence")
        a.status = "insufficient_evidence" if refused else "answered"
        a.uncited_warning = (not refused) and not a.cited_ids
        return a

    # ---------------------------------------------------------------- baseline for the evaluation
    def ask_llm_only(self, question: str) -> str:
        if self.llm is None:
            raise RuntimeError("No LLM configured")
        return self.llm.chat(self.sys_plain, self.usr_plain.format(question=question))
