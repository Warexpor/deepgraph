"""C# extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
import tree_sitter_c_sharp as csharp
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

CS_LANG = Language(csharp.language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


class CSharpExtractor(Extractor):
    @property
    def name(self) -> str:
        return "csharp"

    @property
    def supported_extensions(self) -> set[str]:
        return {".cs"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        parser = Parser(CS_LANG)
        result = ExtractionResult()

        for file in files:
            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)
            rel = str(file)

            self._extract_file(tree, src, file, result, rel)

        return result

    def _extract_file(self, tree, src: bytes, file: Path, result: ExtractionResult, rel: str):
        module_id = f"module:{file.with_suffix('').name}"
        result.nodes.append(TypedNode(
            id=module_id, type=NodeType.MODULE, label=file.name,
            source_location=rel,
        ))

        root = tree.root_node
        for child in root.children:
            if child.type == "using_directive":
                self._extract_using(child, src, module_id, result, rel)
            elif child.type == "namespace_declaration":
                self._extract_namespace(child, src, module_id, result, rel)

    def _extract_using(self, node: Node, src: bytes, module_id: str, result: ExtractionResult, rel: str):
        # Simple: using System; -> first named child
        # Alias: using Foo = Bar; -> qualified_name child
        target = None
        for c in node.named_children:
            if c.type in ("identifier", "qualified_name"):
                target = _text(src, c)
                break
        if target:
            result.edges.append(TypedEdge(
                source_id=module_id, target_id=f"module:{target}",
                type=EdgeType.DEPENDS_ON,
                evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
            ))

    def _extract_namespace(self, node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        ns_id = f"{scope_id}.{name}"

        result.nodes.append(TypedNode(
            id=ns_id, type=NodeType.MODULE, label=name,
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=ns_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

        body = node.child_by_field_name("body")
        if body:
            self._extract_decls(body, src, ns_id, result, rel)

    def _extract_decls(self, node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
        for child in node.named_children:
            if child.type in ("class_declaration", "struct_declaration", "record_declaration"):
                self._extract_type(child, src, scope_id, result, rel)
            elif child.type == "interface_declaration":
                self._extract_interface(child, src, scope_id, result, rel)
            elif child.type == "enum_declaration":
                self._extract_enum(child, src, scope_id, result, rel)

    def _extract_type(self, node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        type_map = {"class_declaration": NodeType.CLASS, "struct_declaration": NodeType.CLASS,
                    "record_declaration": NodeType.RECORD}
        ntype = type_map.get(node.type, NodeType.CLASS)
        type_id = f"{scope_id}.{name}"

        result.nodes.append(TypedNode(
            id=type_id, type=ntype, label=name,
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=type_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

        # Inheritance (base_list has no field name in tree-sitter-c-sharp)
        base_list = next((c for c in node.children if c.type == "base_list"), None)
        if base_list:
            for base in base_list.named_children:
                base_name = _text(src, base)
                result.edges.append(TypedEdge(
                    source_id=type_id, target_id=f"class:{base_name}",
                    type=EdgeType.EXTENDS,
                    evidence=[Evidence(file=rel, line=base.start_point[0] + 1)],
                ))

        # Members
        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                self._extract_member(member, src, type_id, result, rel)

    def _extract_interface(self, node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        iface_id = f"{scope_id}.{name}"

        result.nodes.append(TypedNode(
            id=iface_id, type=NodeType.INTERFACE, label=name,
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=iface_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

        # Interface inheritance
        base_list = next((c for c in node.children if c.type == "base_list"), None)
        if base_list:
            for base in base_list.named_children:
                base_name = _text(src, base)
                result.edges.append(TypedEdge(
                    source_id=iface_id, target_id=f"interface:{base_name}",
                    type=EdgeType.EXTENDS,
                    evidence=[Evidence(file=rel, line=base.start_point[0] + 1)],
                ))

        body = node.child_by_field_name("body")
        if body:
            for member in body.named_children:
                self._extract_member(member, src, iface_id, result, rel)

    def _extract_enum(self, node: Node, src: bytes, scope_id: str, result: ExtractionResult, rel: str):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)
        enum_id = f"{scope_id}.{name}"

        result.nodes.append(TypedNode(
            id=enum_id, type=NodeType.ENUM, label=name,
            source_location=rel,
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=enum_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
        ))

    def _extract_member(self, node: Node, src: bytes, type_id: str, result: ExtractionResult, rel: str):
        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _text(src, name_node)
            m_id = f"{type_id}.{name}"
            result.nodes.append(TypedNode(
                id=m_id, type=NodeType.METHOD, label=name,
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=type_id, target_id=m_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
            ))
        elif node.type == "field_declaration":
            vd = node.child_by_field_name("declarator")
            if not vd:
                vd = next((c for c in node.children if c.type == "variable_declaration"), None)
            if vd:
                for vdecl in vd.named_children:
                    if vdecl.type == "variable_declarator":
                        vname = vdecl.child_by_field_name("name")
                        if not vname:
                            continue
                        f_name = _text(src, vname)
                        f_id = f"{type_id}.{f_name}"
                        result.nodes.append(TypedNode(
                            id=f_id, type=NodeType.FIELD, label=f_name,
                            source_location=rel,
                        ))
                        result.edges.append(TypedEdge(
                            source_id=type_id, target_id=f_id,
                            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                            evidence=[Evidence(file=rel, line=vdecl.start_point[0] + 1)],
                        ))
        elif node.type == "property_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = _text(src, name_node)
            p_id = f"{type_id}.{name}"
            result.nodes.append(TypedNode(
                id=p_id, type=NodeType.FIELD, label=name,
                properties={"kind": "property"},
                source_location=rel,
            ))
            result.edges.append(TypedEdge(
                source_id=type_id, target_id=p_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=rel, line=node.start_point[0] + 1)],
            ))
