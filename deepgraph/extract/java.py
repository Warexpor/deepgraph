"""Java extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
from tree_sitter_java import language as java_language
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

JAVA_LANG = Language(java_language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


def _normalize_package(src: bytes, node: Node) -> str:
    """Extract dotted package/import name, handling scoped_identifier chains."""
    parts = []
    n = node
    while n.type == "scoped_identifier":
        name_node = n.child_by_field_name("name")
        if name_node:
            parts.insert(0, _text(src, name_node))
        n = n.child_by_field_name("scope")
    if n.type in ("identifier",):
        parts.insert(0, _text(src, n))
    elif n.type == "scoped_type_identifier":
        name_node = n.child_by_field_name("name")
        if name_node:
            parts.insert(0, _text(src, name_node))
        n2 = n.child_by_field_name("scope")
        if n2:
            parts.insert(0, _text(src, n2.get_named_child(0) if n2.named_child_count else n2))
    return ".".join(parts)


class JavaExtractor(Extractor):
    @property
    def name(self) -> str:
        return "java"

    @property
    def supported_extensions(self) -> set[str]:
        return {".java"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        parser = Parser(JAVA_LANG)
        result = ExtractionResult()

        for file in files:
            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)

            pkg = self._extract_package(src, tree)
            module_id = f"module:{pkg}" if pkg else f"module:{file.with_suffix('').name}"

            result.nodes.append(TypedNode(
                id=module_id, type=NodeType.MODULE, label=pkg or file.name,
                source_location=str(file),
            ))

            self._extract_imports(src, tree, module_id, result)
            self._extract_types(src, tree, file, module_id, result)

        return result

    def _extract_package(self, src: bytes, tree) -> str | None:
        root = tree.root_node
        for child in root.children:
            if child.type == "package_declaration":
                for c in child.named_children:
                    if c.type == "scoped_identifier":
                        return _normalize_package(src, c)
        return None

    def _normalize_import(self, src: bytes, node: Node) -> str | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            for c in node.named_children:
                if c.type == "scoped_identifier":
                    name_node = c
                    break
        if not name_node:
            return None
        return _normalize_package(src, name_node)

    def _extract_imports(self, src: bytes, tree, module_id: str, result: ExtractionResult):
        root = tree.root_node
        for child in root.children:
            if child.type != "import_declaration":
                continue
            target = self._normalize_import(src, child)
            if target:
                result.edges.append(TypedEdge(
                    source_id=module_id, target_id=f"module:{target}",
                    type=EdgeType.DEPENDS_ON,
                    evidence=[Evidence(file="", line=child.start_point[0] + 1)],
                ))

    def _extract_types(self, src: bytes, tree, file: Path,
                       module_id: str, result: ExtractionResult):
        root = tree.root_node
        for child in root.children:
            if child.type in ("class_declaration", "interface_declaration",
                              "enum_declaration", "record_declaration"):
                self._extract_type_decl(child, src, file, module_id, result)

    def _extract_type_decl(self, node: Node, src: bytes, file: Path,
                           scope_id: str, result: ExtractionResult):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _text(src, name_node)

        type_map = {
            "class_declaration": NodeType.CLASS,
            "interface_declaration": NodeType.INTERFACE,
            "enum_declaration": NodeType.ENUM,
            "record_declaration": NodeType.RECORD,
        }
        node_type = type_map.get(node.type, NodeType.CLASS)
        type_id = f"{scope_id}.{name}"

        result.nodes.append(TypedNode(
            id=type_id, type=node_type, label=name,
            properties={"package": scope_id} if scope_id.startswith("module:") else {"parent": scope_id},
            source_location=str(file),
        ))
        result.edges.append(TypedEdge(
            source_id=scope_id, target_id=type_id,
            type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
            evidence=[Evidence(file=str(file), line=name_node.start_point[0] + 1)],
        ))

        # Inheritance: superclass
        superclass = node.child_by_field_name("superclass")
        if superclass:
            for tc in superclass.children:
                if tc.type == "type_identifier":
                    sc_name = _text(src, tc)
                    result.edges.append(TypedEdge(
                        source_id=type_id, target_id=f"class:{sc_name}",
                        type=EdgeType.EXTENDS,
                        evidence=[Evidence(file=str(file), line=superclass.start_point[0] + 1)],
                    ))
                    break

        # Inheritance: super_interfaces (field name "interfaces" in tree-sitter-java 0.23)
        super_interfaces = node.child_by_field_name("interfaces") or node.child_by_field_name("super_interfaces")
        if super_interfaces:
            for tc in super_interfaces.children:
                if tc.type == "type_list":
                    for type_item in tc.named_children:
                        iface_name = _text(src, type_item)
                        result.edges.append(TypedEdge(
                            source_id=type_id, target_id=f"interface:{iface_name}",
                            type=EdgeType.IMPLEMENTS,
                            evidence=[Evidence(file=str(file), line=type_item.start_point[0] + 1)],
                        ))

        # Body members
        body = node.child_by_field_name("body")
        if body:
            self._extract_members(body, src, file, type_id, result)

    def _extract_members(self, body: Node, src: bytes, file: Path,
                         type_id: str, result: ExtractionResult):
        for member in body.named_children:
            if member.type == "method_declaration":
                name_node = member.child_by_field_name("name")
                if not name_node:
                    continue
                m_name = _text(src, name_node)
                m_id = f"{type_id}.{m_name}"
                result.nodes.append(TypedNode(
                    id=m_id, type=NodeType.METHOD, label=m_name,
                    properties={"class": type_id},
                    source_location=str(file),
                ))
                result.edges.append(TypedEdge(
                    source_id=type_id, target_id=m_id,
                    type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                    evidence=[Evidence(file=str(file), line=name_node.start_point[0] + 1)],
                ))
            elif member.type == "constructor_declaration":
                name_node = member.child_by_field_name("name")
                if not name_node:
                    continue
                c_name = _text(src, name_node)
                c_id = f"{type_id}.{c_name}"
                result.nodes.append(TypedNode(
                    id=c_id, type=NodeType.CONSTRUCTOR, label=c_name,
                    properties={"class": type_id},
                    source_location=str(file),
                ))
                result.edges.append(TypedEdge(
                    source_id=type_id, target_id=c_id,
                    type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                    evidence=[Evidence(file=str(file), line=name_node.start_point[0] + 1)],
                ))
            elif member.type == "field_declaration":
                decl = member.child_by_field_name("declarator")
                if not decl:
                    continue
                v_node = decl.child_by_field_name("name")
                if not v_node:
                    continue
                f_name = _text(src, v_node)
                f_id = f"{type_id}.{f_name}"
                result.nodes.append(TypedNode(
                    id=f_id, type=NodeType.FIELD, label=f_name,
                    properties={"class": type_id},
                    source_location=str(file),
                ))
                result.edges.append(TypedEdge(
                    source_id=type_id, target_id=f_id,
                    type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                    evidence=[Evidence(file=str(file), line=v_node.start_point[0] + 1)],
                ))
                self._extract_field_refs(member, src, file, type_id, result)
            elif member.type in ("class_declaration", "interface_declaration",
                                 "enum_declaration", "record_declaration"):
                self._extract_type_decl(member, src, file, type_id, result)

    _COLLECTION_TYPES = frozenset({
        "List", "Set", "Collection", "Queue", "Deque", "Stack",
        "ArrayList", "LinkedList", "HashSet", "LinkedHashSet", "TreeSet",
        "Vector", "CopyOnWriteArrayList",
    })
    _MAP_TYPES = frozenset({"Map", "HashMap", "TreeMap", "LinkedHashMap", "ConcurrentHashMap", "Hashtable"})
    _CONTAINER_TYPES = frozenset({"Optional", "OptionalInt", "OptionalLong", "OptionalDouble"})
    _PRIMITIVES = frozenset({"int", "long", "float", "double", "boolean", "char", "byte", "short", "void"})
    _JDK_TYPES = frozenset({
        "String", "Integer", "Long", "Float", "Double", "Boolean", "Character", "Byte", "Short",
        "Object", "Class", "Enum", "Throwable", "Exception", "RuntimeException", "Error",
        "Thread", "Runnable", "Callable",
        "Iterator", "Iterable", "Comparable", "Comparator", "AutoCloseable", "Cloneable",
        "Arrays", "Collections", "Objects", "System", "Math", "StringBuilder", "StringBuffer",
    })

    def _extract_field_refs(self, member: Node, src: bytes, file: Path,
                            type_id: str, result: ExtractionResult):
        """Extract field type references and create REFERENCES edges with cardinality."""
        type_node = member.child_by_field_name("type")
        if not type_node:
            return

        line = member.start_point[0] + 1

        def _collect_types(n: Node) -> list[str]:
            """Recursively collect type_identifier names from a type node."""
            names = []
            if n.type == "type_identifier":
                names.append(_text(src, n))
            elif n.type == "generic_type":
                # Children are positional: [base_type, type_arguments?]
                for c in n.children:
                    if c.type == "type_arguments":
                        for arg in c.named_children:
                            names.extend(_collect_types(arg))
                    else:
                        names.extend(_collect_types(c))
            elif n.type == "array_type":
                elem = n.child_by_field_name("element")
                if elem:
                    names.extend(_collect_types(elem))
            elif n.type == "scoped_type_identifier":
                name_node = n.child_by_field_name("name")
                if name_node:
                    names.append(_text(src, name_node))
            return names

        refd_types = _collect_types(type_node)

        # Determine cardinality from container type
        type_text = _text(src, type_node)
        base_name = type_text.split("<")[0].split("[")[0].strip()
        is_many = base_name in self._COLLECTION_TYPES or base_name in self._MAP_TYPES or "[]" in type_text
        card = Cardinality.ONE_TO_MANY if is_many else Cardinality.ONE_TO_ONE

        for ref_name in refd_types:
            if ref_name in self._PRIMITIVES or ref_name in self._JDK_TYPES or ref_name in self._COLLECTION_TYPES | self._MAP_TYPES | self._CONTAINER_TYPES:
                continue
            result.edges.append(TypedEdge(
                source_id=type_id, target_id=f"class:{ref_name}",
                type=EdgeType.REFERENCES, cardinality=card,
                evidence=[Evidence(file=str(file), line=line)],
            ))
