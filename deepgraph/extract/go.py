"""Go extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_go
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

GO_LANG = Language(tree_sitter_go.language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


class GoExtractor(Extractor):
    @property
    def name(self) -> str:
        return "go"

    @property
    def supported_extensions(self) -> set[str]:
        return {".go"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        parser = Parser(GO_LANG)
        result = ExtractionResult()

        for file in files:
            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)
            rel = str(file)

            pkg_id = _extract_package(tree, src, result, rel)
            module_id = pkg_id or f"module:{file.with_suffix('').name}"

            _extract_go_imports(tree, src, module_id, result, rel)
            _extract_go_decls(tree.root_node, src, module_id, result, rel)

        return result


def _extract_package(tree, src: bytes, result: ExtractionResult, rel: str) -> str | None:
    root = tree.root_node
    for child in root.children:
        if child.type == "package_clause":
            name_node = child.child_by_field_name("name")
            if name_node:
                name = _text(src, name_node)
                module_id = f"module:{name}"
                result.nodes.append(TypedNode(
                    id=module_id, type=NodeType.MODULE, label=name,
                    source_location=rel,
                ))
                return module_id
    return None


def _extract_go_imports(tree, src: bytes, module_id: str, result: ExtractionResult, rel: str):
    root = tree.root_node
    for child in root.children:
        if child.type != "import_declaration":
            continue
        for c in child.named_children:
            if c.type == "import_spec":
                path_node = c.child_by_field_name("path")
                if path_node:
                    target = _text(src, path_node).strip("\"")
                    result.edges.append(TypedEdge(
                        source_id=module_id, target_id=f"module:{target}",
                        type=EdgeType.DEPENDS_ON,
                        evidence=[Evidence(file=rel, line=c.start_point[0] + 1)],
                    ))


def _extract_go_decls(node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
    for child in node.children:
        if child.type == "function_declaration":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
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
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

        elif child.type == "method_declaration":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            receiver = child.child_by_field_name("receiver")
            if receiver:
                rx_name = _find_go_type_name(src, receiver)
                if rx_name:
                    m_scope = f"{scope_id}.{rx_name}"
                    m_id = f"{m_scope}.{name}"
                    result.nodes.append(TypedNode(
                        id=m_id, type=NodeType.METHOD, label=name,
                        properties={"class": m_scope},
                        source_location=rel,
                    ))
                    add_missing_node(result, m_scope, NodeType.CLASS, rx_name, rel)
                    result.edges.append(TypedEdge(
                        source_id=m_scope, target_id=m_id,
                        type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                        evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                    ))
            else:
                fn_id = f"{scope_id}.{name}"
                result.nodes.append(TypedNode(
                    id=fn_id, type=NodeType.FUNCTION, label=name,
                    properties={"module": scope_id},
                    source_location=rel,
                ))
                result.edges.append(TypedEdge(
                    source_id=scope_id, target_id=fn_id,
                    type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                    evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                ))

        elif child.type == "type_declaration":
            for ts in child.named_children:
                if ts.type == "type_spec":
                    name_node = ts.child_by_field_name("name")
                    if not name_node:
                        continue
                    name = _text(src, name_node)
                    type_body = ts.child_by_field_name("type")
                    if not type_body:
                        continue

                    ntype = NodeType.CLASS
                    if type_body.type == "interface_type":
                        ntype = NodeType.INTERFACE
                    elif type_body.type == "struct_type":
                        ntype = NodeType.CLASS

                    type_id = f"{scope_id}.{name}"
                    result.nodes.append(TypedNode(
                        id=type_id, type=ntype, label=name,
                        properties={"module": scope_id},
                        source_location=rel,
                    ))
                    result.edges.append(TypedEdge(
                        source_id=scope_id, target_id=type_id,
                        type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                        evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                    ))

                    if type_body.type == "struct_type":
                        for field in type_body.named_children:
                            _extract_go_field(field, src, type_id, result, rel)
                    elif type_body.type == "interface_type":
                        for field in type_body.named_children:
                            _extract_go_iface_method(field, src, type_id, result, rel)


def _find_go_type_name(src: bytes, node: Node) -> str | None:
    """Extract type name from a Go type expression."""
    if node.type in ("type_identifier",):
        return _text(src, node)
    if node.type == "pointer_type":
        # Go pointer_type has no named field for the inner type
        inner = node.child_by_field_name("type") or (node.named_children[0] if node.named_children else None)
        if inner:
            return _find_go_type_name(src, inner)
    if node.type == "qualified_type":
        name_node = node.child_by_field_name("name")
        if name_node:
            return _text(src, name_node)
    if node.type == "parameter_declaration":
        type_node = node.child_by_field_name("type")
        if type_node:
            return _find_go_type_name(src, type_node)
    if node.type == "parameter_list":
        for c in node.named_children:
            result = _find_go_type_name(src, c)
            if result:
                return result
    return None


def add_missing_node(result: ExtractionResult, node_id: str, ntype: NodeType, label: str, rel: str):
    """Add a node if it doesn't already exist."""
    for n in result.nodes:
        if n.id == node_id:
            return
    result.nodes.append(TypedNode(
        id=node_id, type=ntype, label=label,
        source_location=rel,
    ))


def _extract_go_field(field: Node, src: bytes, type_id: str, result: ExtractionResult, rel: str):
    if field.type != "field_declaration_list":
        for child in field.children:
            if child.type == "field_declaration_list":
                field = child
                break

    if field.type == "field_declaration_list":
        for item in field.named_children:
            _extract_go_field(item, src, type_id, result, rel)
        return

    if field.type != "field_declaration":
        return

    name_node = field.child_by_field_name("name")
    if not name_node:
        return
    name = _text(src, name_node)
    f_id = f"{type_id}.{name}"
    result.nodes.append(TypedNode(
        id=f_id, type=NodeType.FIELD, label=name,
        properties={"class": type_id},
        source_location=rel,
    ))
    result.edges.append(TypedEdge(
        source_id=type_id, target_id=f_id,
        type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
        evidence=[Evidence(file=rel, line=field.start_point[0] + 1)],
    ))


def _extract_go_iface_method(method: Node, src: bytes, iface_id: str, result: ExtractionResult, rel: str):
    if method.type == "method_spec":
        name_node = method.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        m_id = f"{iface_id}.{name}"
        result.nodes.append(TypedNode(
            id=m_id, type=NodeType.METHOD, label=name,
            properties={"interface": iface_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=iface_id, target_id=m_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=method.start_point[0] + 1)],
        ))
