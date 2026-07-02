"""Python extractor using tree-sitter."""

from __future__ import annotations
from pathlib import Path
from tree_sitter import Language, Parser, Node
from tree_sitter_python import language as py_language
from deepgraph.extract.base import Extractor
from deepgraph.core.types import (
    ExtractionResult, TypedNode, TypedEdge, Evidence,
    NodeType, EdgeType, Cardinality,
)

PY_LANG = Language(py_language())


def _text(src: bytes, node: Node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8")


class PythonExtractor(Extractor):
    @property
    def name(self) -> str:
        return "python"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py"}

    def extract(self, files: list[Path]) -> ExtractionResult:
        parser = Parser(PY_LANG)
        result = ExtractionResult()

        for file in files:
            rel = file.relative_to(self._find_root(files, file))
            module_name = ".".join(rel.with_suffix("").parts)
            module_id = f"module:{module_name}"

            result.nodes.append(TypedNode(
                id=module_id, type=NodeType.MODULE, label=module_name,
                source_location=str(file),
            ))

            source_text = file.read_text(encoding="utf-8", errors="replace")
            src = source_text.encode("utf-8")
            tree = parser.parse(src)

            self._extract_classes(tree, src, file, module_id, result)
            self._extract_functions(tree, src, file, module_id, result)
            self._extract_imports(tree, src, module_id, result)

        return result

    def _find_root(self, files: list[Path], file: Path) -> Path:
        parents = [p.parents for p in files]
        for candidate in file.parents:
            if all(candidate in ps for ps in parents):
                return candidate
        return file.parent

    def _extract_classes(self, tree, src: bytes, file: Path, module_id: str, result: ExtractionResult):
        root = tree.root_node
        for child in root.children:
            if child.type != "class_definition":
                continue
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            class_id = f"{module_id}.{name}"

            result.nodes.append(TypedNode(
                id=class_id, type=NodeType.CLASS, label=name,
                properties={"module": module_id},
                source_location=str(file),
            ))
            result.edges.append(TypedEdge(
                source_id=module_id, target_id=class_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=str(file), line=name_node.start_point[0] + 1)],
            ))

            base_node = child.child_by_field_name("superclass")
            if base_node:
                self._extract_base_classes(base_node, src, class_id, file, result)

            body = child.child_by_field_name("body")
            if body:
                self._extract_methods(body, src, file, class_id, result)

    def _extract_base_classes(self, base_node, src: bytes, class_id: str, file: Path, result: ExtractionResult):
        if base_node.type == "argument_list":
            for arg in base_node.children:
                if arg.type in ("identifier", "attribute"):
                    result.edges.append(TypedEdge(
                        source_id=class_id, target_id=f"class:{_text(src, arg)}",
                        type=EdgeType.EXTENDS,
                        evidence=[Evidence(file=str(file), line=base_node.start_point[0] + 1)],
                    ))
        elif base_node.type in ("identifier", "attribute"):
            result.edges.append(TypedEdge(
                source_id=class_id, target_id=f"class:{_text(src, base_node)}",
                type=EdgeType.EXTENDS,
                evidence=[Evidence(file=str(file), line=base_node.start_point[0] + 1)],
            ))

    def _extract_methods(self, body, src: bytes, file: Path, class_id: str, result: ExtractionResult):
        for stmt in body.children:
            if stmt.type != "function_definition":
                continue
            fn_node = stmt.child_by_field_name("name")
            if not fn_node:
                continue
            fn_name = _text(src, fn_node)
            fn_id = f"{class_id}.{fn_name}"

            result.nodes.append(TypedNode(
                id=fn_id, type=NodeType.METHOD, label=fn_name,
                properties={"class": class_id},
                source_location=str(file),
            ))
            result.edges.append(TypedEdge(
                source_id=class_id, target_id=fn_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=str(file), line=fn_node.start_point[0] + 1)],
            ))

    def _extract_functions(self, tree, src: bytes, file: Path, module_id: str, result: ExtractionResult):
        root = tree.root_node
        for child in root.children:
            if child.type != "function_definition":
                continue
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = _text(src, name_node)
            fn_id = f"{module_id}.{name}"

            result.nodes.append(TypedNode(
                id=fn_id, type=NodeType.FUNCTION, label=name,
                properties={"module": module_id},
                source_location=str(file),
            ))
            result.edges.append(TypedEdge(
                source_id=module_id, target_id=fn_id,
                type=EdgeType.CONTAINS, cardinality=Cardinality.ONE_TO_MANY,
                evidence=[Evidence(file=str(file), line=name_node.start_point[0] + 1)],
            ))

    def _extract_imports(self, tree, src: bytes, module_id: str, result: ExtractionResult):
        root = tree.root_node
        for child in root.children:
            if child.type == "import_statement":
                for node in child.children:
                    if node.type in ("dotted_name", "identifier"):
                        target = _text(src, node)
                        result.edges.append(TypedEdge(
                            source_id=module_id, target_id=f"module:{target}",
                            type=EdgeType.DEPENDS_ON,
                            evidence=[Evidence(file="", line=node.start_point[0] + 1)],
                        ))
            elif child.type == "import_from_statement":
                for node in child.children:
                    if node.type in ("dotted_name", "relative_import"):
                        target = _text(src, node)
                        result.edges.append(TypedEdge(
                            source_id=module_id, target_id=f"module:{target}",
                            type=EdgeType.DEPENDS_ON,
                            evidence=[Evidence(file="", line=node.start_point[0] + 1)],
                        ))
