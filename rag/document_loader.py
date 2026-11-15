"""Document loading for the RAG pipeline.

Supports plain text, Markdown, JSON and PDF (via PyPDF2). Categories are
inferred from filenames so retrieved chunks can be filtered later.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".pdf"}

CATEGORY_BY_FILENAME = {
    "refund": "billing",
    "payment": "billing",
    "billing": "billing",
    "login": "account",
    "account": "account",
    "password": "account",
    "technical": "technical",
    "faq": "technical",
    "crash": "technical",
    "app": "technical",
}


def clean_text(text: str) -> str:
    """Normalise whitespace while preserving paragraph structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def infer_category(filename: str) -> str:
    """Infer a knowledge category from a filename."""
    name = Path(filename).stem.lower()
    for keyword, category in CATEGORY_BY_FILENAME.items():
        if keyword in name:
            return category
    return "general"


def _read_pdf(path: Path) -> str:
    from PyPDF2 import PdfReader  # lazy import (only needed for PDFs)

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def load_file(path: str | Path, category: Optional[str] = None) -> dict:
    """Load one file into ``{title, content, category, source}``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Supported: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if path.suffix.lower() == ".pdf":
        content = _read_pdf(path)
    elif path.suffix.lower() == ".json":
        raw = path.read_text(encoding="utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            content = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            content = raw
    else:
        content = path.read_text(encoding="utf-8", errors="ignore")

    content = clean_text(content)
    if not content:
        raise ValueError(f"File is empty: {path.name}")

    return {
        "title": path.stem,
        "content": content,
        "category": category or infer_category(path.name),
        "source": str(path),
    }


def load_directory(directory: str | Path) -> list[dict]:
    """Load every supported document in a directory (non-recursive)."""
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {directory}")
    documents = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                documents.append(load_file(path))
            except Exception as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
    return documents


def load_many(paths: Iterable[str | Path]) -> list[dict]:
    return [load_file(p) for p in paths]
