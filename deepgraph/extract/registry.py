"""Extractor plugin registry."""

from __future__ import annotations
from pathlib import Path
from deepgraph.extract.base import Extractor, CompoundExtractor


_registry: dict[str, Extractor] = {}


def register(extractor: Extractor):
    _registry[extractor.name] = extractor


def get(name: str) -> Extractor | None:
    return _registry.get(name)


def all() -> list[Extractor]:
    return list(_registry.values())


def for_files(files: list[Path]) -> CompoundExtractor:
    """Build a CompoundExtractor from all registered extractors that match the given files."""
    matched = [e for e in _registry.values() if e.detect(files)]
    return CompoundExtractor(matched)


def detect_files(root: Path) -> list[Path]:
    """Walk root and return all files with supported extensions."""
    exts: set[str] = set()
    for e in _registry.values():
        exts |= e.supported_extensions
    files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and "node_modules" not in p.parts and ".git" not in p.parts:
            files.append(p)
    return files
