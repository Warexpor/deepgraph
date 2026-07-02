"""Typed node, edge, and evidence data models."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class NodeType(Enum):
    FILE = auto()
    MODULE = auto()
    PACKAGE = auto()
    CLASS = auto()
    INTERFACE = auto()
    ENUM = auto()
    RECORD = auto()
    FUNCTION = auto()
    METHOD = auto()
    CONSTRUCTOR = auto()
    FIELD = auto()
    VARIABLE = auto()
    TABLE = auto()
    ENDPOINT = auto()
    CONCEPT = auto()
    DOC_SECTION = auto()


class EdgeType(Enum):
    CONTAINS = auto()       # structural: class contains field, package contains module
    CALLS = auto()          # call graph: function A calls function B
    EXTENDS = auto()        # inheritance: class extends class
    IMPLEMENTS = auto()     # interface: class implements interface
    DEPENDS_ON = auto()     # general dependency
    REFERENCES = auto()     # references by name
    SIMILAR_TO = auto()     # semantic similarity (from LLM pass)
    REQUIRES = auto()       # conceptual: A requires B to function
    PRODUCES = auto()       # conceptual: A produces B


class Cardinality(Enum):
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:N"


class Confidence(Enum):
    CONFIRMED = 1.0    # from AST/parser, deterministic
    EXTRACTED = 0.9    # from document parsing
    INFERRED = 0.7     # from heuristics
    AMBIGUOUS = 0.4    # uncertain / needs review


@dataclass
class Evidence:
    """Traceability back to source."""
    file: str
    line: int
    snippet: str | None = None

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "snippet": self.snippet}


@dataclass
class TypedNode:
    id: str
    type: NodeType
    label: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_location: str | None = None
    confidence: Confidence = Confidence.CONFIRMED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.name.lower(),
            "label": self.label,
            "properties": self.properties,
            "source_location": self.source_location,
            "confidence": self.confidence.name.lower(),
        }


@dataclass
class TypedEdge:
    source_id: str
    target_id: str
    type: EdgeType
    label: str = ""
    cardinality: Cardinality | None = None
    weight: float = 1.0
    confidence: Confidence = Confidence.CONFIRMED
    evidence: list[Evidence] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.name.lower(),
            "label": self.label,
            "cardinality": self.cardinality.value if self.cardinality else None,
            "weight": self.weight,
            "confidence": self.confidence.name.lower(),
            "evidence": [e.to_dict() for e in self.evidence],
            "properties": self.properties,
        }


@dataclass
class ExtractionResult:
    """Output from a single extractor plugin."""
    nodes: list[TypedNode] = field(default_factory=list)
    edges: list[TypedEdge] = field(default_factory=list)

    def merge(self, other: ExtractionResult) -> ExtractionResult:
        return ExtractionResult(
            nodes=self.nodes + other.nodes,
            edges=self.edges + other.edges,
        )


@dataclass
class AnalysisResult:
    """Output from the analysis phase."""
    communities: dict[int, list[str]] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    cohesion: dict[int, float] = field(default_factory=dict)
    god_nodes: list[dict] = field(default_factory=list)
    surprises: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
