"""Base extractor plugin interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from deepgraph.core.types import ExtractionResult


class Extractor(ABC):
    """Base class for all language/content extractors."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        ...

    def detect(self, files: list[Path]) -> list[Path]:
        return [f for f in files if f.suffix in self.supported_extensions]

    @abstractmethod
    def extract(self, files: list[Path]) -> ExtractionResult:
        ...


class CompoundExtractor(Extractor):
    """Merges results from multiple sub-extractors."""

    def __init__(self, extractors: list[Extractor]):
        self._extractors = extractors

    @property
    def name(self) -> str:
        return "+".join(e.name for e in self._extractors)

    @property
    def supported_extensions(self) -> set[str]:
        exts: set[str] = set()
        for e in self._extractors:
            exts |= e.supported_extensions
        return exts

    def extract(self, files: list[Path]) -> ExtractionResult:
        result = ExtractionResult()
        for ext in self._extractors:
            matched = ext.detect(files)
            if matched:
                result = result.merge(ext.extract(matched))
        return result
