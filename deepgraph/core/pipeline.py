"""Pipeline orchestrator: detect → extract → build → analyze."""

from __future__ import annotations
from pathlib import Path
from deepgraph.core.types import ExtractionResult, AnalysisResult
from deepgraph.core.graph import TypedMultiGraph
from deepgraph.extract import registry
from deepgraph.analyze import analyze as analyze_graph


def analyze(root: Path) -> tuple[TypedMultiGraph, ExtractionResult, AnalysisResult]:
    """Run the full analysis pipeline on a directory."""
    files = registry.detect_files(root)
    if not files:
        print(f"No supported files found in {root}")
        return TypedMultiGraph(), ExtractionResult(), AnalysisResult()

    print(f"Found {len(files)} files")
    extractor = registry.for_files(files)
    extraction = extractor.extract(files)
    print(f"Extracted: {len(extraction.nodes)} nodes, {len(extraction.edges)} edges")

    graph = TypedMultiGraph()
    graph.build(extraction)
    print(f"Graph: {graph.node_count()} nodes, {graph.edge_count()} edges")

    analysis = analyze_graph(graph)
    if analysis.communities:
        print(f"Communities: {len(analysis.communities)}")
    if analysis.god_nodes:
        print(f"God nodes: {len(analysis.god_nodes)}")
    if analysis.surprises:
        print(f"Surprises: {len(analysis.surprises)}")

    return graph, extraction, analysis
