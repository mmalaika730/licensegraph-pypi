#!/usr/bin/env python3
"""make_graph_images.py | draws the knowledge graph from instances.ttl.
Outputs: dependency_tree_acme-mit-app.png (one project's tree, labelled) and graph_overview.png (all packages).
Colour = license category of the package version (explicit type on the license node).
Usage: python3 make_graph_images.py --instances ../RDF_Knowledge_Graph/instances.ttl --project acme-mit-app --out-dir ."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
from rdflib import RDF, Graph, Namespace, URIRef

LG = Namespace("http://example.org/licensegraph#")
B = "http://example.org/licensegraph/"
CATS = [("NetworkCopyleftLicense", "Network copyleft", "#7a1f5c"), ("StrongCopyleftLicense", "Strong copyleft (GPL)", "#c0392b"),
        ("WeakCopyleftLicense", "Weak copyleft (LGPL/MPL)", "#e08a1e"), ("ProprietaryLicense", "Proprietary", "#222222"),
        ("UnknownLicense", "Unknown", "#888888"), ("PermissiveLicense", "Permissive", "#4a78b5"),
        ("PublicDomainLicense", "Public domain only", "#2a9d8f")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", required=True); ap.add_argument("--project", default="acme-mit-app")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    g = Graph().parse(a.instances, format="turtle")
    cat_of_lic = {}
    for lic in g.subjects(LG.spdxId, None):
        for name, _, _ in CATS:
            if (lic, RDF.type, LG[name]) in g:
                cat_of_lic[lic] = name; break
    rank = {n: i for i, (n, _, _) in enumerate(CATS)}
    def node_cat(n):
        cs = [cat_of_lic[l] for l in g.objects(n, LG.hasLicense) if l in cat_of_lic]
        return min(cs, key=rank.get) if cs else "UnknownLicense"
    colour = {n: c for n, _, c in CATS}
    label = lambda n: str(n).split("/ver/")[-1] if "/ver/" in str(n) else str(n).split("/project/")[-1]
    G = nx.DiGraph()
    for s, o in g.subject_objects(LG.directlyDependsOn):
        G.add_edge(s, o)
    handles = [Line2D([0], [0], marker="o", ls="", color=c, label=l, markersize=9) for _, l, c in CATS]
    out = Path(a.out_dir)

    # 1) one project's tree, layered by shortest depth
    root = URIRef(B + "project/" + a.project)
    T = G.subgraph(nx.descendants(G, root) | {root}).copy()
    depth = nx.single_source_shortest_path_length(T, root)
    for n, d in depth.items(): T.nodes[n]["layer"] = d
    pos = nx.multipartite_layout(T, subset_key="layer", align="vertical")
    fig, ax = plt.subplots(figsize=(15, 11))
    nx.draw_networkx_edges(T, pos, ax=ax, arrowsize=8, edge_color="#999", alpha=.6, width=.8, node_size=300)
    nx.draw_networkx_nodes(T, pos, ax=ax, node_color=[colour[node_cat(n)] for n in T], node_size=[900 if n == root else 330 for n in T],
                           edgecolors=["black" if node_cat(n) not in ("PermissiveLicense", "PublicDomainLicense") else "white" for n in T], linewidths=1.2)
    lp = {n: (pos[n][0] + 0.015, pos[n][1]) for n in T}
    nx.draw_networkx_labels(T, lp, {n: label(n) for n in T}, ax=ax, font_size=6.5, horizontalalignment="left",
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    ax.set_title(f"Dependency tree of '{a.project}' ({T.number_of_nodes()} package versions, {T.number_of_edges()} edges), coloured by license category", fontsize=12)
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True); ax.axis("off")
    fig.tight_layout(); fig.savefig(out / f"dependency_tree_{a.project}.png", dpi=160); plt.close(fig)

    # 2) whole graph overview
    fig, ax = plt.subplots(figsize=(15, 11))
    pos = nx.spring_layout(G, k=.35, seed=7, iterations=120)
    cop = {"NetworkCopyleftLicense", "StrongCopyleftLicense", "WeakCopyleftLicense"}
    nx.draw_networkx_edges(G, pos, ax=ax, arrowsize=5, edge_color="#bbb", alpha=.5, width=.5, node_size=60)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=[colour[node_cat(n)] for n in G], node_size=[110 if node_cat(n) in cop or str(n).count("/project/") else 45 for n in G], linewidths=0)
    nx.draw_networkx_labels(G, pos, {n: label(n) for n in G if node_cat(n) in cop or "/project/" in str(n)}, ax=ax, font_size=6.5)
    ax.set_title(f"LicenseGraph-PyPI: all {G.number_of_nodes()} package versions and {G.number_of_edges()} dependency edges (copyleft packages and projects labelled)", fontsize=12)
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True); ax.axis("off")
    fig.tight_layout(); fig.savefig(out / "graph_overview.png", dpi=160); plt.close(fig)
    print("tree nodes/edges:", T.number_of_nodes(), T.number_of_edges(), "| overview:", G.number_of_nodes(), G.number_of_edges())


if __name__ == "__main__":
    main()
