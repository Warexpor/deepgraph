"""Query interface for typed knowledge graphs."""
from deepgraph.query.graph_query import find_nodes, find_neighbors, find_paths, graph_stats

__all__ = ["find_nodes", "find_neighbors", "find_paths", "graph_stats"]
