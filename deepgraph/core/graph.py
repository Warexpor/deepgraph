"""Multi-resolution typed multigraph builder."""

from __future__ import annotations
import networkx as nx
from deepgraph.core.types import TypedNode, TypedEdge, ExtractionResult, NodeType, EdgeType, Confidence, Cardinality


class TypedMultiGraph:
    """A NetworkX-based multi-digraph with typed nodes and edges."""

    def __init__(self):
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    @property
    def graph(self) -> nx.MultiDiGraph:
        return self._g

    def build(self, result: ExtractionResult):
        for node in result.nodes:
            self._g.add_node(
                node.id,
                type=node.type,
                label=node.label,
                properties=node.properties,
                source_location=node.source_location,
                confidence=node.confidence,
            )
        for edge in result.edges:
            if not self._g.has_node(edge.source_id) or not self._g.has_node(edge.target_id):
                continue  # skip dangling edges
            self._g.add_edge(
                edge.source_id,
                edge.target_id,
                key=f"{edge.type.name}::{edge.label or edge.type.name}",
                type=edge.type,
                label=edge.label,
                cardinality=edge.cardinality,
                weight=edge.weight,
                confidence=edge.confidence,
                evidence=[e.to_dict() for e in edge.evidence],
                properties=edge.properties,
            )

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def typed_nodes(self, node_type: NodeType) -> list[str]:
        return [n for n, d in self._g.nodes(data=True) if d.get("type") == node_type]

    def typed_edges(self, edge_type: EdgeType) -> list[tuple[str, str]]:
        return [(u, v) for u, v, k, d in self._g.edges(data=True, keys=True) if d.get("type") == edge_type]

    def to_json_dict(self) -> dict:
        nodes = []
        for n, d in self._g.nodes(data=True):
            nodes.append({
                "id": n,
                "type": d.get("type").name.lower() if d.get("type") else "unknown",
                "label": d.get("label", n),
                "properties": d.get("properties", {}),
                "source_location": d.get("source_location"),
                "confidence": d.get("confidence").name.lower() if d.get("confidence") else "unknown",
            })
        edges = []
        for u, v, k, d in self._g.edges(data=True, keys=True):
            edges.append({
                "source_id": u,
                "target_id": v,
                "key": k,
                "type": d.get("type").name.lower() if d.get("type") else "unknown",
                "label": d.get("label", ""),
                "cardinality": d.get("cardinality").value if d.get("cardinality") else None,
                "weight": d.get("weight", 1.0),
                "confidence": d.get("confidence").name.lower() if d.get("confidence") else "unknown",
                "evidence": d.get("evidence", []),
                "properties": d.get("properties", {}),
            })
        return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_json_dict(cls, data: dict) -> TypedMultiGraph:
        """Reconstruct a graph from a JSON dict (inverse of to_json_dict)."""
        graph = cls()
        for n in data.get("nodes", []):
            graph._g.add_node(
                n["id"],
                type=n.get("type", "unknown"),
                label=n.get("label", n["id"]),
                properties=n.get("properties", {}),
                source_location=n.get("source_location"),
                confidence=n.get("confidence", "unknown"),
            )
        for e in data.get("edges", []):
            graph._g.add_edge(
                e["source_id"], e["target_id"],
                key=e.get("key", f"{e.get('type', 'edge')}::{e.get('label', '')}"),
                type=e.get("type", "unknown"),
                label=e.get("label", ""),
                cardinality=e.get("cardinality"),
                weight=e.get("weight", 1.0),
                confidence=e.get("confidence", "unknown"),
                evidence=e.get("evidence", []),
                properties=e.get("properties", {}),
            )
        return graph
