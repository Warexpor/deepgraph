"""Query interface for typed knowledge graphs."""

from __future__ import annotations
import fnmatch
import networkx as nx
from deepgraph.core.graph import TypedMultiGraph
from deepgraph.core.types import NodeType, EdgeType


def find_nodes(graph: TypedMultiGraph,
               *,
               node_type: NodeType | str | None = None,
               name_pattern: str | None = None,
               limit: int = 50) -> list[dict]:
    """Find nodes by type and/or name pattern.

    node_type can be a NodeType enum or its string name (case-insensitive).
    name_pattern is a glob pattern matched against node id and label.
    """
    g = graph.graph
    results = []

    # Resolve node type
    resolved_type = None
    if node_type is not None:
        if isinstance(node_type, NodeType):
            resolved_type = node_type
        else:
            for t in NodeType:
                if t.name.lower() == node_type.lower():
                    resolved_type = t
                    break
            if resolved_type is None:
                raise ValueError(f"Unknown node type: {node_type}")

    for node, ndata in g.nodes(data=True):
        if resolved_type is not None and ndata.get("type") != resolved_type:
            continue
        if name_pattern is not None:
            if not fnmatch.fnmatchcase(node, name_pattern) and not fnmatch.fnmatchcase(ndata.get("label", ""), name_pattern):
                continue
        results.append({
            "id": node,
            "type": ndata.get("type").name.lower() if ndata.get("type") else "unknown",
            "label": ndata.get("label", node),
            "source": ndata.get("source_location", ""),
        })
        if len(results) >= limit:
            break

    return results


def find_neighbors(graph: TypedMultiGraph,
                   node_id: str,
                   *,
                   direction: str = "both",
                   edge_type: EdgeType | str | None = None) -> dict:
    """Find neighbors of a node.

    direction: 'in', 'out', or 'both'
    """
    g = graph.graph
    if not g.has_node(node_id):
        raise KeyError(f"Node not found: {node_id}")

    resolved_etype = None
    if edge_type is not None:
        if isinstance(edge_type, EdgeType):
            resolved_etype = edge_type
        else:
            for e in EdgeType:
                if e.name.lower() == edge_type.lower():
                    resolved_etype = e
                    break
            if resolved_etype is None:
                raise ValueError(f"Unknown edge type: {edge_type}")

    incoming: list[dict] = []
    outgoing: list[dict] = []

    if direction in ("in", "both"):
        for u, v, k, d in g.in_edges(node_id, data=True, keys=True):
            if resolved_etype is not None and d.get("type") != resolved_etype:
                continue
            incoming.append({
                "source": u,
                "type": d.get("type").name.lower() if d.get("type") else "edge",
                "label": d.get("label", ""),
            })

    if direction in ("out", "both"):
        for u, v, k, d in g.out_edges(node_id, data=True, keys=True):
            if resolved_etype is not None and d.get("type") != resolved_etype:
                continue
            outgoing.append({
                "target": v,
                "type": d.get("type").name.lower() if d.get("type") else "edge",
                "label": d.get("label", ""),
            })

    return {"incoming": incoming, "outgoing": outgoing}


def find_paths(graph: TypedMultiGraph,
               source: str,
               target: str,
               max_depth: int = 5) -> list[list[dict]]:
    """Find all simple paths between two nodes up to max_depth."""
    g = graph.graph
    if not g.has_node(source):
        raise KeyError(f"Source node not found: {source}")
    if not g.has_node(target):
        raise KeyError(f"Target node not found: {target}")

    paths: list[list[dict]] = []
    try:
        raw_paths = nx.shortest_simple_paths(g, source, target)
        for i, path in enumerate(raw_paths):
            if i >= 10:
                break
            paths.append([{
                "id": n,
                "type": g.nodes[n].get("type").name.lower() if g.nodes[n].get("type") else "unknown",
                "label": g.nodes[n].get("label", n),
            } for n in path])
            if len(path) > max_depth + 1:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    return paths


def graph_stats(graph: TypedMultiGraph) -> dict:
    """Return summary statistics about the graph."""
    g = graph.graph
    if g.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0}

    type_counts = {}
    for _, d in g.nodes(data=True):
        t = d.get("type")
        tn = t.name.lower() if t else "unknown"
        type_counts[tn] = type_counts.get(tn, 0) + 1

    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "density": round(nx.density(g), 4),
        "node_types": dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        "is_directed": g.is_directed(),
        "has_multiple_edges": g.is_multigraph(),
    }
