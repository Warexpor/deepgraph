"""TypeScript/JavaScript extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_javascript
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

JS_LANG = Language(tree_sitter_javascript.language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


try:
    import tree_sitter_typescript
    TS_LANG = Language(tree_sitter_typescript.language_typescript())
    TSX_LANG = Language(tree_sitter_typescript.language_tsx())
    _HAS_TS = True
except ImportError:
    TS_LANG = TSX_LANG = None
    _HAS_TS = False


class JavaScriptExtractor(Extractor):
    @property
    def name(self) -> str:
        return "javascript"

    @property
    def supported_extensions(self) -> set[str]:
        return {".js", ".jsx", ".mjs", ".cjs"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        return _extract_js_ts(files, JS_LANG)


class TypeScriptExtractor(Extractor):
    @property
    def name(self) -> str:
        return "typescript"

    @property
    def supported_extensions(self) -> set[str]:
        exts = {".ts"}
        if _HAS_TS:
            exts.add(".tsx")
        return exts

    def extract(self, files: list[Path]) -> ExtractionResult:
        result = ExtractionResult()
        if not _HAS_TS:
            return result
        ts_files = [f for f in files if f.suffix != ".tsx"]
        tsx_files = [f for f in files if f.suffix == ".tsx"]
        if ts_files:
            result = result.merge(_extract_js_ts(ts_files, TS_LANG))
        if tsx_files:
            result = result.merge(_extract_js_ts(tsx_files, TSX_LANG))
        return result


def _extract_js_ts(files: list[Path], lang: Language) -> ExtractionResult:
    parser = Parser(lang)
    result = ExtractionResult()

    for file in files:
        source_text = file.read_text(encoding="utf-8", errors="replace")
        src = source_text.encode("utf-8")
        tree = parser.parse(src)
        module_id = f"module:{file.with_suffix('').name}"
        rel = str(file)

        result.nodes.append(TypedNode(
            id=module_id, type=NodeType.MODULE, label=file.name,
            source_location=rel,
        ))

        _extract_imports(tree, src, module_id, result, rel)
        _extract_exports(tree, src, module_id, result, rel)
        _extract_decls(tree.root_node, src, module_id, result, rel)

    return result


def _extract_imports(tree, src: bytes, module_id: str, result: ExtractionResult, rel: str):
    root = tree.root_node
    for child in root.children:
        if child.type == "import_statement":
            source_node = child.child_by_field_name("source")
            if source_node:
                target = _text(src, source_node).strip("\"'")
                result.edges.append(TypedEdge(
                    source_id=module_id, target_id=f"module:{target}",
                    type=EdgeType.DEPENDS_ON,
                    evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                ))


def _extract_exports(tree, src: bytes, module_id: str, result: ExtractionResult, rel: str):
    root = tree.root_node
    for child in root.children:
        if child.type == "export_statement":
            decl = child.child_by_field_name("declaration")
            if decl:
                _extract_decl(decl, src, module_id, result, rel, module_id)


def _extract_decls(node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str, parent_id: str | None = None):
    for child in node.children:
        _extract_decl(child, src, scope_id, result, rel, parent_id)


def _extract_decl(node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str, parent_id: str | None = None):
    if node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        class_id = f"{scope_id}.{name}"
        result.nodes.append(TypedNode(
            id=class_id, type=NodeType.CLASS, label=name,
            properties={"module": scope_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=class_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

        # Superclass
        superclass = node.child_by_field_name("superclass")
        if superclass:
            sc_name = _text(src, superclass).strip()
            result.edges.append(TypedEdge(
                source_id=class_id, target_id=f"class:{sc_name}",
                type=EdgeType.EXTENDS,
                evidence=[Evidence(file=rel, line=superclass.start_point[0] + 1)],
            ))

        # Body
        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                _extract_class_member(member, src, class_id, result, rel)

    elif node.type == "function_declaration":
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        fn_id = f"{scope_id}.{name}"
        result.nodes.append(TypedNode(
            id=fn_id, type=NodeType.FUNCTION, label=name,
            properties={"module": scope_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=fn_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

    elif node.type == "interface_declaration":
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        iface_id = f"{scope_id}.{name}"
        result.nodes.append(TypedNode(
            id=iface_id, type=NodeType.INTERFACE, label=name,
            properties={"module": scope_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=iface_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

    elif node.type == "enum_declaration":
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        enum_id = f"{scope_id}.{name}"
        result.nodes.append(TypedNode(
            id=enum_id, type=NodeType.ENUM, label=name,
            properties={"module": scope_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=enum_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

    # Recurse into class/object/namespace bodies
    for child in node.children:
        if hasattr(child, "type") and child.type in ("class_body", "object", "namespace_body", "statement_block"):
            _extract_decls(child, src, scope_id, result, rel)


def _extract_class_member(node: Node, src: bytes, class_id: str, result: ExtractionResult, rel: str):
    if node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        m_id = f"{class_id}.{name}"
        result.nodes.append(TypedNode(
            id=m_id, type=NodeType.METHOD, label=name,
            properties={"class": class_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=class_id, target_id=m_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))
    elif node.type in ("field_definition", "public_field_definition"):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        f_id = f"{class_id}.{name}"
        result.nodes.append(TypedNode(
            id=f_id, type=NodeType.FIELD, label=name,
            properties={"class": class_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=class_id, target_id=f_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))
