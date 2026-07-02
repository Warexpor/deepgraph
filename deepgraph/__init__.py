"""DeepGraph: Multi-language typed knowledge graph builder."""
from deepgraph.core.types import TypedNode, TypedEdge, ExtractionResult, AnalysisResult, NodeType, EdgeType
from deepgraph.core.graph import TypedMultiGraph
from deepgraph.core.pipeline import analyze
from deepgraph.extract.base import Extractor
from deepgraph.extract.registry import register, for_files, detect_files
from deepgraph.extract.python import PythonExtractor
from deepgraph.extract.java import JavaExtractor
from deepgraph.extract.javascript import JavaScriptExtractor, TypeScriptExtractor
from deepgraph.extract.cpp import CppExtractor
from deepgraph.extract.csharp import CSharpExtractor
from deepgraph.extract.go import GoExtractor
from deepgraph.extract.rust import RustExtractor
from deepgraph.export.obsidian import export_obsidian
from deepgraph.viz import export_html
from deepgraph.query import find_nodes, find_neighbors, find_paths, graph_stats

__all__ = [
    "TypedNode", "TypedEdge", "ExtractionResult", "AnalysisResult",
    "NodeType", "EdgeType",
    "TypedMultiGraph",
    "analyze", "export_html",
    "Extractor", "register", "for_files", "detect_files",
    "PythonExtractor", "JavaExtractor",
    "JavaScriptExtractor", "TypeScriptExtractor",
    "CppExtractor", "CSharpExtractor", "GoExtractor", "RustExtractor",
    "export_obsidian",
    "find_nodes", "find_neighbors", "find_paths", "graph_stats",
]
