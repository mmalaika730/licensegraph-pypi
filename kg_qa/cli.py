#!/usr/bin/env python3
"""Command-line interface:  python -m kg_qa.cli "Which licenses conflict with acme-mit-app?"   (or no argument for interactive mode)"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kg_qa.kg import KG, repo_root  # noqa: E402
from kg_qa.llm import LLM  # noqa: E402
from kg_qa.qa import QA  # noqa: E402


def build_qa(with_llm=True, with_predictor=True) -> QA:
    root = repo_root()
    predictor = None
    if with_predictor:
        try:
            from kg_reasoning.predictor import Predictor
            predictor = Predictor(root / "kg_reasoning/model")
        except Exception:
            predictor = None
    return QA(KG(root), LLM.from_env(root) if with_llm else None, predictor, root)


def show(a, verbose=False):
    print(f"\nQUESTION : {a.question}")
    print(f"INTENT   : {a.intent}   entities: {a.entities}")
    if a.queries:
        print("RETRIEVAL: " + " | ".join(a.queries))
    print("EVIDENCE :")
    for f in a.facts:
        print(f"  {f.id} [{f.kind}] {f.text}\n        via: {f.via or '-'}   source: {f.source or '-'}")
    if a.retrieval_note:
        print(f"  note: {a.retrieval_note}")
    if verbose and a.prompt:
        print("PROMPT   :\n" + a.prompt)
    print(f"STATUS   : {a.status}")
    print(f"ANSWER   : {a.answer}")
    if a.uncited_warning:
        print("WARNING  : the answer cites no fact ids; treat it as ungrounded.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--no-llm", action="store_true", help="retrieval and evidence only")
    ap.add_argument("--show-prompt", action="store_true")
    a = ap.parse_args()
    qa = build_qa(with_llm=not a.no_llm)
    if a.question:
        show(qa.ask(" ".join(a.question)), a.show_prompt)
        return
    print("LicenseGraph-PyPI question answering. Empty line to quit.")
    while True:
        try:
            q = input("\n> ").strip()
        except EOFError:
            break
        if not q:
            break
        show(qa.ask(q), a.show_prompt)


if __name__ == "__main__":
    main()
