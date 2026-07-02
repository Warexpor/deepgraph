"""Rust extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_rust
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

RUST_LANG = Language(tree_sitter_rust.language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


class RustExtractor(Extractor):
    @property
    def name(self) -> str:
        return "rust"

    @property
    def supported_extensions(self) -> set[str]:
        return {".rs"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        parser = Parser(RUST_LANG)
        result = ExtractionResult()

        for file in files:
            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)
            rel = str(file)
            module_id = f"module:{file.with_suffix('')}"

            result.nodes.append(TypedNode(
                id=module_id, type=NodeType.MODULE, label=file.name,
                source_location=rel,
            ))

            _extract_rust_uses(tree, src, module_id, result, rel)
            _extract_rust_items(tree.root_node, src, module_id, result, rel)

        return result


def _extract_rust_uses(tree, src: bytes, module_id: str, result: ExtractionResult, rel: str):
    root = tree.root_node
    for child in root.children:
        if child.type == "use_declaration":
            arg = child.child_by_field_name("argument")
            if arg:
                target = _text(src, arg)
                result.edges.append(TypedEdge(
                    source_id=module_id, target_id=f"module:{target}",
                    type=EdgeType.DEPENDS_ON,
                    evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                ))


def _extract_rust_items(node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str,
                        is_impl_for: str | None = None):
    for child in node.children:
        if child.type == "struct_item":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            item_id = f"{scope_id}.{name}"
            result.nodes.append(TypedNode(
                id=item_id, type=NodeType.CLASS, label=name,
                properties={"module": scope_id},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=item_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))
            body = child.child_by_field_name("body")
            if body:
                for field in body.named_children:
                    if field.type == "field_declaration":
                        field_name = field.child_by_field_name("name")
                        if not field_name:
                            continue
                        fname = _text(src, field_name)
                        fid = f"{item_id}.{fname}"
                        result.nodes.append(TypedNode(
                            id=fid, type=NodeType.FIELD, label=fname,
                            properties={"struct": item_id},
                            source_location=rel,
                        ))
                        result.edges.append(TypedEdge(
                            source_id=item_id, target_id=fid,
                            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                            evidence=[Evidence(file=rel, line=field.start_point[0] + 1)],
                        ))

        elif child.type == "enum_item":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            item_id = f"{scope_id}.{name}"
            result.nodes.append(TypedNode(
                id=item_id, type=NodeType.ENUM, label=name,
                properties={"module": scope_id},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=item_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

        elif child.type == "trait_item":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            item_id = f"{scope_id}.{name}"
            result.nodes.append(TypedNode(
                id=item_id, type=NodeType.INTERFACE, label=name,
                properties={"module": scope_id},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=item_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

        elif child.type == "function_item":
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

        elif child.type == "impl_item":
            type_node = child.child_by_field_name("type")
            trait_node = child.child_by_field_name("trait")
            if not type_node:
                continue
            impl_for = _text(src, type_node)
            impl_scope = f"{scope_id}.{impl_for}"

            # Add the type as a node if not already present (placeholder)
            _ensure_node(result, impl_scope, NodeType.CLASS, impl_for, rel)
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=impl_scope,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

            if trait_node:
                trait_name = _text(src, trait_node)
                result.edges.append(TypedEdge(
                    source_id=impl_scope, target_id=f"interface:{trait_name}",
                    type=EdgeType.IMPLEMENTS,
                    evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                ))

            body = child.child_by_field_name("body")
            if body:
                _extract_rust_impl_items(body, src, impl_scope, result, rel)


def _extract_rust_impl_items(body: Node, src: bytes, impl_scope: str, result: ExtractionResult, rel: str):
    for child in body.named_children:
        if child.type == "function_item":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            m_id = f"{impl_scope}.{name}"
            result.nodes.append(TypedNode(
                id=m_id, type=NodeType.METHOD, label=name,
                properties={"class": impl_scope},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=impl_scope, target_id=m_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))


def _ensure_node(result: ExtractionResult, node_id: str, ntype: NodeType, label: str, rel: str):
    for n in result.nodes:
        if n.id == node_id:
            return
    result.nodes.append(TypedNode(
        id=node_id, type=ntype, label=label,
        source_location=rel,
    ))
