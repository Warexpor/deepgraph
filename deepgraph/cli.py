"""DeepGraph CLI."""

from __future__ import annotations
import json
from pathlib import Path
import click
from deepgraph.core import pipeline
from deepgraph.extract import registry
from deepgraph.extract.python import PythonExtractor
from deepgraph.extract.java import JavaExtractor
from deepgraph.extract.javascript import JavaScriptExtractor, TypeScriptExtractor
from deepgraph.extract.cpp import CppExtractor
from deepgraph.extract.csharp import CSharpExtractor
from deepgraph.extract.go import GoExtractor
from deepgraph.extract.rust import RustExtractor
from deepgraph.export.obsidian import export_obsidian
from deepgraph.viz import export_html
from deepgraph.core.graph import TypedMultiGraph
from deepgraph.query import graph_stats


def _register_all():
    registry.register(PythonExtractor())
    registry.register(JavaExtractor())
    registry.register(JavaScriptExtractor())
    registry.register(TypeScriptExtractor())
    registry.register(CppExtractor())
    registry.register(CSharpExtractor())
    registry.register(GoExtractor())
    registry.register(RustExtractor())


@click.group()
def cli():
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Output JSON file")
@click.option("--pretty/--no-pretty", default=True, help="Pretty-print JSON output")
@click.option("--obsidian", type=click.Path(file_okay=False), help="Output Obsidian vault directory")
@click.option("--html", type=click.Path(dir_okay=False), help="Output HTML visualization file")
@click.option("--json-only", is_flag=True, default=False, help="Skip analysis phase (extract + build only)")
def analyze(path: str, output: str | None, pretty: bool, obsidian: str | None, html: str | None, json_only: bool):
    """Analyze a codebase and build a typed knowledge graph."""
    _register_all()

    graph, extraction, analysis = pipeline.analyze(Path(path))

    if not json_only and analysis:
        if analysis.god_nodes:
            click.echo(f"God nodes: {len(analysis.god_nodes)}")
        if analysis.surprises:
            click.echo(f"Surprises: {len(analysis.surprises)}")
        if analysis.communities:
            click.echo(f"Communities: {len(analysis.communities)}")

    data = graph.to_json_dict()
    if output:
        out_path = Path(output)
        out_path.write_text(
            json.dumps(data, indent=2 if pretty else None, default=str),
            encoding="utf-8",
        )
        click.echo(f"Wrote {out_path}")

    if obsidian:
        vault_path = Path(obsidian)
        export_obsidian(graph, analysis, vault_path)
        click.echo(f"Obsidian vault: {vault_path.resolve()}")

    if html:
        html_path = Path(html)
        export_html(graph, html_path, title=Path(path).name)
        click.echo(f"HTML graph: {html_path.resolve()}")

    if not output and not obsidian and not html:
        click.echo(json.dumps(data, indent=2 if pretty else None, default=str))


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
def info(path: str):
    """Show graph statistics for a codebase."""
    _register_all()

    graph, extraction, analysis = pipeline.analyze(Path(path))
    stats = graph_stats(graph)

    click.echo(f"Nodes: {stats['nodes']}")
    click.echo(f"Edges: {stats['edges']}")
    click.echo(f"Density: {stats['density']}")
    click.echo("")
    click.echo("Node types:")
    for tname, count in stats["node_types"].items():
        click.echo(f"  {tname}: {count}")

    if analysis:
        if analysis.communities:
            click.echo(f"\nCommunities: {len(analysis.communities)}")
            for cid, members in sorted(analysis.communities.items()):
                label = analysis.labels.get(cid, f"Community {cid}")
                cohesion = analysis.cohesion.get(cid, 0.0)
                click.echo(f"  [{cid}] {label} — {len(members)} nodes, cohesion={cohesion:.2f}")
        if analysis.god_nodes:
            click.echo(f"\nGod nodes ({len(analysis.god_nodes)}):")
            for gn in analysis.god_nodes[:10]:
                click.echo(f"  {gn['node']} (deg={gn['degree']})")
        if analysis.surprises:
            click.echo(f"\nSurprises ({len(analysis.surprises)}):")
            for s in analysis.surprises[:10]:
                click.echo(f"  {s['node']}: {s['reason']}")


@cli.command()
@click.argument("json_file", type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.option("-o", "--output", default="graph.html", show_default=True, help="Output HTML file")
@click.option("--title", default="Codebase Graph", help="Graph title")
@click.option("--all-nodes", is_flag=True, default=False, help="Show all nodes including fields/methods")
def visualize(json_file: str, output: str, title: str, all_nodes: bool):
    """Generate an HTML visualization from a saved graph.json."""
    data = json.loads(Path(json_file).read_text(encoding="utf-8"))
    graph = TypedMultiGraph.from_json_dict(data)
    out_path = Path(output)
    export_html(graph, out_path, title=title, show_all_nodes=all_nodes)
    click.echo(f"Wrote {out_path.resolve()}")
