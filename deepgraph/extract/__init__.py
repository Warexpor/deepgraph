"""Extractor plugins for multiple languages."""
from deepgraph.extract.base import Extractor
from deepgraph.extract.registry import register, for_files, detect_files
from deepgraph.extract.python import PythonExtractor
from deepgraph.extract.java import JavaExtractor
from deepgraph.extract.javascript import JavaScriptExtractor, TypeScriptExtractor
from deepgraph.extract.cpp import CppExtractor
from deepgraph.extract.csharp import CSharpExtractor
from deepgraph.extract.go import GoExtractor
from deepgraph.extract.rust import RustExtractor

__all__ = [
    "Extractor", "register", "for_files", "detect_files",
    "PythonExtractor", "JavaExtractor",
    "JavaScriptExtractor", "TypeScriptExtractor",
    "CppExtractor", "CSharpExtractor", "GoExtractor", "RustExtractor",
]
