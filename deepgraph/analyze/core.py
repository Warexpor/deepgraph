"""Graph analysis: community detection, centrality, god nodes."""

from __future__ import annotations
from collections import Counter
from deepgraph.core.types import AnalysisResult
from deepgraph.core.graph import TypedMultiGraph

import networkx as nx


def analyze(graph: TypedMultiGraph) -> AnalysisResult:
    """Run all analysis passes on a graph and return the results."""
    g = graph.graph
    result = AnalysisResult()

    if g.number_of_nodes() == 0:
        return result

    _detect_communities(g, result)
    _compute_cohesion(g, result)
    _find_god_nodes(g, result)
    _find_surprises(g, result)

    return result


def _detect_communities(g: nx.MultiDiGraph, result: AnalysisResult):
    """Detect communities using greedy modularity maximization."""
    community_gen = nx.community.greedy_modularity_communities(g.to_undirected())
    for i, community in enumerate(community_gen):
        node_list = sorted(community)
        if len(node_list) < 2:
            continue
        result.communities[i] = node_list
        # Label community by most common type
        types = [g.nodes[n].get("type", None) for n in node_list]
        type_counts = Counter(t.name if hasattr(t, "name") else str(t) for t in types if t)
        top_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
        result.labels[i] = f"{top_type} cluster ({len(node_list)} nodes)"


def _compute_cohesion(g: nx.MultiDiGraph, result: AnalysisResult):
    """Compute intra-community vs inter-community edge ratio per community."""
    if not result.communities:
        return

    node_to_community = {}
    for cid, nodes in result.communities.items():
        for n in nodes:
            node_to_community[n] = cid

    for cid, nodes in result.communities.items():
        community_set = set(nodes)
        intra = 0
        inter = 0
        for u, v in g.edges():
            in_cu = u in community_set
            in_cv = v in community_set
            if in_cu and in_cv:
                intra += 1
            elif in_cu != in_cv:
                inter += 1
        total = intra + inter
        result.cohesion[cid] = intra / total if total > 0 else 0.0


def _find_god_nodes(g: nx.MultiDiGraph, result: AnalysisResult):
    """Find nodes with significantly higher degree than average."""
    if g.number_of_nodes() < 5:
        return

    degrees = [d for _, d in g.degree()]
    if not degrees:
        return

    mean = sum(degrees) / len(degrees)
    variance = sum((d - mean) ** 2 for d in degrees) / len(degrees)
    std = variance ** 0.5
    threshold = mean + 2 * std if std > 0 else float("inf")

    for node, degree in g.degree():
        if degree > threshold:
            ndata = g.nodes[node]
            result.god_nodes.append({
                "node": ndata.get("label", node),
                "id": node,
                "degree": degree,
                "threshold": round(threshold, 2),
                "type": ndata.get("type").name.lower() if ndata.get("type") else "unknown",
            })

    result.god_nodes.sort(key=lambda x: x["degree"], reverse=True)


def _find_surprises(g: nx.MultiDiGraph, result: AnalysisResult):
    """Flag possibly-surprising structural patterns."""
    for node, degree in g.degree():
        ndata = g.nodes[node]
        node_type = ndata.get("type")
        if not node_type:
            continue

        in_deg = g.in_degree(node)
        out_deg = g.out_degree(node)

        # High in-degree but never referenced as source in any edge (sink)
        if in_deg >= 5 and out_deg == 0:
            result.surprises.append({
                "node": ndata.get("label", node),
                "type": node_type.name.lower(),
                "reason": f"High in-degree ({in_deg}) but zero out-degree - pure sink?",
                "in_degree": in_deg,
                "out_degree": out_deg,
            })

        # High out-degree but never referenced by others (orphan caller)
        if out_deg >= 5 and in_deg == 0:
            result.surprises.append({
                "node": ndata.get("label", node),
                "type": node_type.name.lower(),
                "reason": f"High out-degree ({out_deg}) but zero in-degree - orphan caller?",
                "in_degree": in_deg,
                "out_degree": out_deg,
            })

    # Disconnected components
    undirected = g.to_undirected()
    components = list(nx.connected_components(undirected))
    if len(components) > 2:
        isolated = [c for c in components if len(c) == 1]
        for iso in isolated:
            n = next(iter(iso))
            ndata = g.nodes[n]
            result.surprises.append({
                "node": ndata.get("label", n),
                "type": ndata.get("type").name.lower() if ndata.get("type") else "unknown",
                "reason": "Isolated node — no connections to any other node",
                "in_degree": g.in_degree(n),
                "out_degree": g.out_degree(n),
            })
