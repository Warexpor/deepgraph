# deepgraph

**Multi-language typed knowledge graph builder.**  
Parse source code into a directed graph of typed nodes and edges, then visualize it as an interactive force-directed graph or an Obsidian vault with wiki-links.

---

## Features

- **8 language extractors** — Python, Java, JavaScript, TypeScript, C, C++, Go, Rust, C#
- **Typed graph** — nodes have types (class, interface, enum, method, field, function, ...) and edges have types (extends, implements, contains, references, depends_on, ...)
- **Cardinality detection** — `List<Wheel>` → 1:N, `Engine engine` → 1:1, `Map<String, Part>` → N:N
- **Community detection** — Louvain-style modularity clustering via NetworkX
- **God node detection** — nodes with statistically significant degree
- **3 output formats**:
  - **Interactive HTML** — D3.js force-directed graph with search, filters, theme toggle (dark/light), edge labels, tooltips
  - **Obsidian vault** — 1 `.md` file per node with `[[wiki-links]]` for every relationship, community pages, god nodes index
  - **JSON** — full graph data for programmatic use

---

## Installation

```bash
pip install deepgraph
```

Or install from source:

```bash
git clone https://github.com/your-username/deepgraph
cd deepgraph
pip install -e .
```

### Language support

Core install only includes the Python extractor. Add languages as needed:

```bash
# All languages
pip install "deepgraph[all]"

# Or pick specific ones
pip install "deepgraph[java,javascript,cpp,go,rust,csharp]"
```

---

## Quick start

```bash
# Analyze a codebase, print JSON to stdout
deepgraph analyze /path/to/project

# Export to JSON file
deepgraph analyze /path/to/project --output graph.json

# Export interactive HTML visualization
deepgraph analyze /path/to/project --html graph.html

# Export Obsidian vault
deepgraph analyze /path/to/project --obsidian vault/

# Do it all at once
deepgraph analyze /path/to/project --output graph.json --obsidian vault/ --html graph.html
```

### HTML visualization

Open `graph.html` in a browser. You'll see:

- A force-directed graph with nodes colored by type
- Edge labels showing relationship type and cardinality
- Sidebar with node/edge type filters and search
- Dark/light theme toggle
- Drag to reposition, scroll to zoom, hover for details

### Obsidian vault

Open the vault folder in Obsidian (`Open folder as vault`). Hit `Ctrl+G` (or click **Open graph view**) to see the full codebase graph. Each node is a markdown file with `[[wiki-links]]` connecting related code.

---

## CLI reference

| Command | Description |
|---------|-------------|
| `analyze <path>` | Analyze a codebase and build the knowledge graph |
| `info <path>` | Show graph statistics for a codebase |
| `visualize <graph.json>` | Generate HTML from a saved JSON file |

### analyze options

| Option | Description |
|--------|-------------|
| `-o, --output FILE` | Save graph as JSON |
| `--pretty / --no-pretty` | Pretty-print JSON (default: pretty) |
| `--obsidian DIRECTORY` | Export Obsidian vault |
| `--html FILE` | Export interactive HTML graph |
| `--json-only` | Skip analysis phase (extract + build only) |

---

## Python API

```python
from pathlib import Path
from deepgraph import (
    analyze, TypedMultiGraph,
    PythonExtractor, JavaExtractor,
    export_obsidian, export_html,
    find_nodes, find_neighbors, find_paths, graph_stats,
    NodeType, EdgeType,
)

# Run the pipeline
graph, extraction, analysis = analyze(Path("./my_project"))
# graph: TypedMultiGraph (NetworkX-backed)
# extraction: ExtractionResult (raw nodes + edges from parsers)
# analysis: AnalysisResult (communities, god nodes, surprises)

# Query the graph
classes = find_nodes(graph, node_type="class")
neighbors = find_neighbors(graph, "module:com.example.Foo")
stats = graph_stats(graph)
print(f"{stats['nodes']} nodes, {stats['edges']} edges")

# Export
export_obsidian(graph, analysis, Path("./vault/"))
export_html(graph, Path("./graph.html"), title="My Project")

# Build from saved JSON
from deepgraph import TypedMultiGraph
import json
data = json.loads(Path("graph.json").read_text())
graph = TypedMultiGraph.from_json_dict(data)
```

---

## Supported languages

| Language | Extractor | Extensions | Dependencies |
|----------|-----------|------------|--------------|
| Python | `PythonExtractor` | `.py` | core |
| Java | `JavaExtractor` | `.java` | `tree-sitter-java` |
| JavaScript | `JavaScriptExtractor` | `.js`, `.jsx`, `.mjs`, `.cjs` | `tree-sitter-javascript` |
| TypeScript | `TypeScriptExtractor` | `.ts`, `.tsx` | `tree-sitter-typescript` |
| C/C++ | `CppExtractor` | `.cpp`, `.cc`, `.h`, `.hpp`, `.c` | `tree-sitter-cpp`, `tree-sitter-c` |
| Go | `GoExtractor` | `.go` | `tree-sitter-go` |
| Rust | `RustExtractor` | `.rs` | `tree-sitter-rust` |
| C# | `CSharpExtractor` | `.cs` | `tree-sitter-c-sharp` |

Multiple extractors are auto-detected and run in parallel on a single directory. Just point `deepgraph analyze` at your project root.

---

## Output formats

### Interactive HTML

A self-contained `.html` file (no server needed) with:

- D3.js force-directed graph
- Node colors by type (class=orange, interface=purple, enum=lavender, etc.)
- Edge labels with type and cardinality (`extends`, `contains 1:N`, `references 1:1`)
- Sidebar controls for filtering by node/edge type, searching by name
- Dark/light theme toggle
- Tooltip on hover showing node details or edge relationships
- Drag, zoom, pan

### Obsidian vault

A full Obsidian vault with:

- One `.md` file per node with YAML frontmatter (type, confidence, tags)
- `[[wiki-links]]` for every relationship
- Community index pages
- God nodes and surprises summary pages
- Source file location in frontmatter

Open in Obsidian → graph view gives you a clickable codebase map.

### JSON

The raw graph data with `{ "nodes": [...], "edges": [...] }`. Each node has `id`, `type`, `label`, `properties`, `source_location`, `confidence`. Each edge has `source_id`, `target_id`, `type`, `cardinality`, `weight`, `evidence`.

---

## Architecture

```
source code → [extract] → typed nodes + edges → [build] → NetworkX MultiDiGraph
                                                              ↓
                                              [analyze] → communities, god nodes
                                                              ↓
                                          ┌──────┬──────┬──────────┐
                                          ↓      ↓      ↓          ↓
                                        JSON  Obsidian  HTML    Query API
```

- **Extract** — tree-sitter parsers produce typed ASTs per file, converted to `TypedNode` + `TypedEdge` lists
- **Build** — loads nodes/edges into a NetworkX `MultiDiGraph` with typed metadata
- **Analyze** — community detection (greedy modularity), centrality, god nodes, structural surprises
- **Export** — JSON dump, Obsidian vault with wiki-links, self-contained D3.js HTML

---

## Project structure

```
deepgraph/
├── core/
│   ├── types.py        # TypedNode, TypedEdge, NodeType, EdgeType, Cardinality
│   ├── graph.py        # TypedMultiGraph (NetworkX-backed, JSON import/export)
│   └── pipeline.py     # detect → extract → build → analyze orchestrator
├── extract/
│   ├── base.py         # Extractor ABC
│   ├── registry.py     # plugin registry + file detection
│   ├── python.py       # Python extractor
│   ├── java.py         # Java extractor (classes, interfaces, fields, inheritance)
│   ├── javascript.py   # JavaScript + TypeScript extractors
│   ├── cpp.py          # C/C++ extractor
│   ├── go.py           # Go extractor
│   ├── rust.py         # Rust extractor
│   └── csharp.py       # C# extractor
├── analyze/
│   └── core.py         # community detection, god nodes, surprises
├── export/
│   └── obsidian.py     # Obsidian vault export
├── viz/
│   └── html_graph.py   # D3.js HTML graph generator
├── query/
│   └── graph_query.py  # find_nodes, find_neighbors, find_paths
└── cli.py              # Click CLI (analyze, info, visualize)
```

---

## License

MIT
