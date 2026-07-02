"""Export knowledge graph as an Obsidian vault with markdown notes + wiki-links."""

from __future__ import annotations
from pathlib import Path
from deepgraph.core.graph import TypedMultiGraph
from deepgraph.core.types import AnalysisResult


def _sanitize(name: str) -> str:
    """Turn a node ID into a safe filename."""
    return name.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")


def _node_file(node_id: str) -> str:
    return _sanitize(node_id) + ".md"


def _link(node_id: str) -> str:
    return f"[[{_sanitize(node_id)}]]"


def export_obsidian(graph: TypedMultiGraph,
                    analysis: AnalysisResult | None,
                    output_dir: Path,
                    title: str = "Codebase Graph") -> Path:
    """Export a graph as an Obsidian vault.

    Each node becomes a .md file with YAML frontmatter and [[wiki-links]].
    Additional index and community pages organize the structure.
    """
    g = graph.graph
    nodes_dir = output_dir / "Nodes"
    communities_dir = output_dir / "Communities"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    communities_dir.mkdir(parents=True, exist_ok=True)

    # Incoming/outgoing edge index per node
    outgoing: dict[str, list[tuple[str, str, str, int]]] = {}  # node_id -> [(target_id, edge_type, label, weight)]
    incoming: dict[str, list[tuple[str, str, str, int]]] = {}  # node_id -> [(source_id, edge_type, label, weight)]

    for u, v, k, d in g.edges(data=True, keys=True):
        outgoing.setdefault(u, []).append((v, d.get("type").name.lower() if d.get("type") else "edge",
                                           d.get("label", ""), int(d.get("weight", 1))))
        incoming.setdefault(v, []).append((u, d.get("type").name.lower() if d.get("type") else "edge",
                                           d.get("label", ""), int(d.get("weight", 1))))

    community_map: dict[str, int] = {}
    if analysis:
        for cid, members in analysis.communities.items():
            for m in members:
                community_map[m] = cid

    # Write a node file for every graph node
    for node_id, ndata in g.nodes(data=True):
        props = ndata.get("properties", {})
        node_type = ndata.get("type")
        ntype = node_type.name.lower() if node_type else "unknown"
        label = ndata.get("label", node_id)
        src = ndata.get("source_location", "")
        confidence = ndata.get("confidence")

        tags = {ntype, f"type/{ntype}"}
        community_id = community_map.get(node_id)
        if community_id is not None:
            tags.add(f"community/{community_id}")

        lines = ["---"]
        lines.append(f'type: {ntype}')
        lines.append(f'label: "{label.replace(chr(34), chr(39))}"')
        if src:
            lines.append(f'source: "{escape_yaml(src)}"')
        if confidence:
            lines.append(f'confidence: {confidence.name.lower()}')
        lines.append("tags: [" + ", ".join(sorted(tags)) + "]")
        lines.append("---")
        lines.append("")
        lines.append(f"# {label}")
        lines.append("")
        lines.append(f"**Type:** {ntype}")
        if src:
            lines.append(f"**Source:** {src}")
        lines.append("")

        # Relationships section
        has_relationships = False
        out_links = outgoing.get(node_id, [])
        in_links = incoming.get(node_id, [])

        if in_links:
            has_relationships = True
            lines.append("## Incoming")
            for src_id, etype, elabel, w in sorted(in_links, key=lambda x: (-x[3], x[0])):
                link_text = _link(src_id)
                lines.append(f"- {link_text} `{etype}`")
        if out_links:
            has_relationships = True
            lines.append("## Outgoing")
            for tgt_id, etype, elabel, w in sorted(out_links, key=lambda x: (-x[3], x[0])):
                link_text = _link(tgt_id)
                lines.append(f"- {link_text} `{etype}`")

        if not has_relationships:
            lines.append("*No relationships*")

        # Properties section
        if props and isinstance(props, dict):
            lines.append("")
            lines.append("## Properties")
            for k, v in sorted(props.items()):
                lines.append(f"- {k}: {v}")

        (nodes_dir / _node_file(node_id)).write_text("\n".join(lines), encoding="utf-8")

    # Community summary pages
    if analysis and analysis.communities:
        for cid, members in sorted(analysis.communities.items()):
            community_set = set(members)
            label = analysis.labels.get(cid, f"Community {cid}")
            cohesion = analysis.cohesion.get(cid, 0.0)

            # Find intra-community edges
            intra_edges = []
            for u, v, k, d in g.edges(data=True, keys=True):
                if u in community_set and v in community_set:
                    intra_edges.append((u, v, d.get("type").name.lower() if d.get("type") else "edge"))

            lines = ["---"]
            lines.append(f'cluster: {cid}')
            lines.append(f'label: "{label}"')
            lines.append(f'cohesion: {cohesion:.2f}')
            lines.append(f'size: {len(members)}')
            lines.append("tags: [community]")
            lines.append("---")
            lines.append("")
            lines.append(f"# Community {cid}: {label}")
            lines.append("")
            lines.append(f"- Cohesion: {cohesion:.2f}")
            lines.append(f"- Size: {len(members)} nodes")
            lines.append("")
            lines.append("## Members")
            for m in sorted(members):
                ndata = g.nodes[m]
                mtype = ndata.get("type")
                mtype_name = mtype.name.lower() if mtype else "?"
                lines.append(f"- {_link(m)} `{mtype_name}`")
            if intra_edges:
                lines.append("")
                lines.append("## Internal Edges")
                for u, v, etype in sorted(intra_edges):
                    lines.append(f"- {_link(u)} --{etype}--> {_link(v)}")

            (communities_dir / f"Community_{cid}.md").write_text("\n".join(lines), encoding="utf-8")

    # God nodes page
    if analysis and analysis.god_nodes:
        lines = ["---", "tags: [god-nodes]", "---", "",
                 "# God Nodes", "",
                 "Nodes with significantly higher degree than average.", ""]
        for gn in analysis.god_nodes:
            nid = gn["id"]
            lines.append(f"- {_link(nid)} — degree={gn['degree']}, type={gn['type']}")
        (output_dir / "God_Nodes.md").write_text("\n".join(lines), encoding="utf-8")

    # Surprises page
    if analysis and analysis.surprises:
        lines = ["---", "tags: [surprises]", "---", "",
                 "# Surprises", "",
                 "Structural patterns that may be worth investigating.", ""]
        for s in analysis.surprises:
            nid = s.get("node", "")
            lines.append(f"- {nid}: {s['reason']}")
        (output_dir / "Surprises.md").write_text("\n".join(lines), encoding="utf-8")

    # Root index page
    total_nodes = g.number_of_nodes()
    total_edges = g.number_of_edges()

    # Count by type
    type_counts = {}
    for _, d in g.nodes(data=True):
        t = d.get("type")
        tn = t.name.lower() if t else "unknown"
        type_counts[tn] = type_counts.get(tn, 0) + 1

    lines = ["---",
             f'title: "{title}"',
             f'total_nodes: {total_nodes}',
             f'total_edges: {total_edges}',
             "tags: [index]",
             "---",
             "",
             f"# {title}",
             "",
             f"- **Total nodes:** {total_nodes}",
             f"- **Total edges:** {total_edges}",
             "",
             "## Node Types",
             ""]
    for tname, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {tname}: {count}")
    lines.append("")

    if analysis and analysis.communities:
        lines.extend(["", "## Communities", ""])
        for cid in sorted(analysis.communities):
            label = analysis.labels.get(cid, f"Community {cid}")
            lines.append(f"- [[Communities/Community_{cid}|{label}]]")

    if analysis and analysis.god_nodes:
        lines.extend(["", "## Notable", ""])
        lines.append("- [[God_Nodes|God Nodes]]")
    if analysis and analysis.surprises:
        lines.append("- [[Surprises|Surprises]]")

    (output_dir / "Index.md").write_text("\n".join(lines), encoding="utf-8")

    return output_dir


def escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
