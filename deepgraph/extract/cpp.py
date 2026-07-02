"""C/C++ extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_cpp
import tree_sitter_c
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

CPP_LANG = Language(tree_sitter_cpp.language())
C_LANG = Language(tree_sitter_c.language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


def _find_declarator_name(src: bytes, node: Node) -> str | None:
    """Find the identifier name from a declarator chain."""
    if node.type in ("identifier", "field_identifier"):
        return _text(src, node)
    if node.type in ("function_declarator", "pointer_declarator",
                      "qualified_identifier", "reference_declarator"):
        child = node.child_by_field_name("declarator") or node.child_by_field_name("name")
        if child:
            return _find_declarator_name(src, child)
        for c in node.children:
            if c.type in ("identifier", "field_identifier"):
                return _text(src, c)
    return None


class CppExtractor(Extractor):
    @property
    def name(self) -> str:
        return "cpp"

    @property
    def supported_extensions(self) -> set[str]:
        return {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".c"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        result = ExtractionResult()

        for file in files:
            lang = C_LANG if file.suffix == ".c" else CPP_LANG
            parser = Parser(lang)
            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)
            rel = str(file)
            module_id = f"module:{file.with_suffix('').name}"

            result.nodes.append(TypedNode(
                id=module_id, type=NodeType.MODULE, label=file.name,
                source_location=rel,
            ))

            _extract_includes(tree, src, module_id, result, rel)
            _extract_cpp_decls(tree.root_node, src, module_id, result, rel)

        return result


def _extract_includes(tree, src: bytes, module_id: str, result: ExtractionResult, rel: str):
    root = tree.root_node
    for child in root.children:
        if child.type == "preproc_include":
            path_node = child.child_by_field_name("path")
            if path_node:
                target = _text(src, path_node).strip("\"<>")
                result.edges.append(TypedEdge(
                    source_id=module_id, target_id=f"module:{target}",
                    type=EdgeType.DEPENDS_ON,
                    evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
                ))


def _extract_cpp_decls(node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
    for child in node.children:
        if child.type == "class_specifier":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
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
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

            # Base classes
            bases = child.child_by_field_name("bases")
            if bases:
                for base in bases.children:
                    if base.type == "base_class_clause":
                        type_node = base.child_by_field_name("type")
                        if type_node:
                            bc_name = _text(src, type_node)
                            result.edges.append(TypedEdge(
                                source_id=class_id, target_id=f"class:{bc_name}",
                                type=EdgeType.EXTENDS,
                                evidence=[Evidence(file=rel, line=base.start_point[0] + 1)],
                            ))

            # Body members
            body = child.child_by_field_name("body")
            if body:
                for member in body.named_children:
                    _extract_cpp_member(member, src, class_id, result, rel)

        elif child.type in ("struct_specifier",):
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            struct_id = f"{scope_id}.{name}"
            result.nodes.append(TypedNode(
                id=struct_id, type=NodeType.CLASS, label=name,
                properties={"module": scope_id},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=struct_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))
            body = child.child_by_field_name("body")
            if body:
                for member in body.named_children:
                    _extract_cpp_member(member, src, struct_id, result, rel)

        elif child.type == "enum_specifier":
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            enum_id = f"{scope_id}.{name}"
            result.nodes.append(TypedNode(
                id=enum_id, type=NodeType.ENUM, label=name,
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=scope_id, target_id=enum_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=child.start_point[0] + 1)],
            ))

        elif child.type == "function_definition":
            decl_node = child.child_by_field_name("declarator")
            if not decl_node:
                continue
            name = _find_declarator_name(src, decl_node)
            if not name:
                continue
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


def _extract_cpp_member(member: Node, src: bytes, class_id: str, result: ExtractionResult, rel: str):
    if member.type == "function_definition":
        decl_node = member.child_by_field_name("declarator")
        if not decl_node:
            return
        name = _find_declarator_name(src, decl_node)
        if not name:
            return
        m_id = f"{class_id}.{name}"
        result.nodes.append(TypedNode(
            id=m_id, type=NodeType.METHOD, label=name,
            properties={"class": class_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=class_id, target_id=m_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=member.start_point[0] + 1)],
        ))
    elif member.type == "field_declaration":
        decl = member.child_by_field_name("declarator")
        if not decl:
            return
        name = _find_declarator_name(src, decl)
        if not name:
            return
        f_id = f"{class_id}.{name}"
        result.nodes.append(TypedNode(
            id=f_id, type=NodeType.FIELD, label=name,
            properties={"class": class_id},
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=class_id, target_id=f_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=member.start_point[0] + 1)],
        ))
