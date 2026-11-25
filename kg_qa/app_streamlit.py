"""Streamlit demo UI:  streamlit run kg_qa/app_streamlit.py"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kg_qa.cli import build_qa  # noqa: E402

BADGE = {"explicit": ":green[EXPLICIT]", "inferred": ":orange[INFERRED]", "prediction": ":red[PREDICTION, not a fact]"}
EXAMPLES = ["", "Why is mutagen flagged for acme-mit-app?", "Which packages are exposed to mutagen anywhere below them?",
            "Is acme-mit-app compatible with every license in its dependency tree?", "Can an Apache-2.0 project depend on a GPL-2.0-only package?",
            "Predict the license of websocket-client", "Which license will django 6.0 use?", "What is the capital of France?"]

st.set_page_config(page_title="LicenseGraph-PyPI", layout="wide")


@st.cache_resource(show_spinner="Loading the knowledge graph and running reasoning ...")
def load():
    return build_qa()


qa = load()
st.title("LicenseGraph-PyPI: license conflict question answering")
st.caption("Pipeline: question, KG retrieval and reasoning, retrieved context, LLM, grounded answer with evidence.")
with st.sidebar:
    st.subheader("System")
    st.write("LLM: " + (qa.llm.name if qa.llm else "not configured (evidence only)"))
    st.write("Link-prediction model: " + ("loaded" if qa.predictor else "not found"))
    st.write(f"Stored triples: {len(qa.kg.explicit)}; after reasoning: {len(qa.kg.reasoned)}")
    st.markdown("**Legend**\n\n- :green[EXPLICIT]: stored in the graph\n- :orange[INFERRED]: derived by schema or rule\n- :red[PREDICTION]: model guess, never a fact\n- Generated text: the LLM's wording of the facts")
pick = st.selectbox("Example questions", EXAMPLES)
q = st.text_input("Ask a question about the dependency graph", value=pick)
if q.strip():
    with st.spinner("Retrieving evidence and generating the answer ..."):
        a = qa.ask(q)
    st.subheader("Answer (generated text)")
    (st.warning if a.status != "answered" else st.success)(a.answer)
    if a.uncited_warning:
        st.error("This answer cites no graph facts; treat it as ungrounded.")
    st.caption(f"intent: {a.intent} | status: {a.status} | entities: {a.entities}")
    if a.facts:
        st.subheader("Supporting evidence from the graph")
        for f in a.facts:
            cited = " (cited)" if f.id in a.cited_ids else ""
            st.markdown(f"**{f.id}**{cited} {BADGE[f.kind]}: {f.text}")
            st.caption(f"derived by: {f.via or '-'} | provenance: {f.source or '-'}")
    if a.retrieval_note:
        st.info(a.retrieval_note)
    if a.route_note:
        st.info(a.route_note)
    with st.expander("How the graph was queried"):
        st.code("\n".join(a.queries) or "-")
    if a.prompt:
        with st.expander("Context and prompt sent to the LLM"):
            st.code(a.prompt)
