#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: PDF → Raw Text Extraction
==================================
Extracts raw text from PDF files.
Tries three methods: pdftotext (Poppler), PyMuPDF, and Tesseract OCR.

Output: book-output-raw/{book_name}_RAW.txt
"""

import os
import subprocess
import sys
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────────────
BOOK_INPUT_DIR = Path(__file__).parent / "book-input"
BOOK_OUTPUT_RAW = Path(__file__).parent / "book-output-raw"

# Tool paths (macOS homebrew defaults)
PDFTOTEXT_BIN = os.environ.get("PDFTOTEXT_BIN", "/opt/homebrew/bin/pdftotext")
TESSERACT_BIN = os.environ.get("TESSERACT_BIN", "/opt/homebrew/bin/tesseract")


def _run_pdftotext(pdf_path: Path, mode: str = "default") -> str:
    """Extract text with pdftotext (Poppler)."""
    args = [PDFTOTEXT_BIN]
    if mode == "layout":
        args.append("-layout")
    args += [str(pdf_path), "-"]

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def _score_extraction(text: str) -> float:
    """Score extraction quality; higher is better."""
    if not text or len(text.strip()) < 200:
        return 0.0
    lines = text.splitlines()
    n = min(len(lines), 4000)
    if n == 0:
        return 0.0
    sample = lines[:n]
    long_lines = sum(1 for ln in sample if len(ln.strip()) > 45)
    tiny_lines = sum(1 for ln in sample if 0 < len(ln.strip()) <= 2)
    alnum = sum(c.isalnum() for c in text[:50000])
    total = min(len(text), 50000)
    alnum_ratio = alnum / total if total else 0
    return 0.55 * (long_lines / n) - 0.12 * (tiny_lines / n) + 0.35 * min(alnum_ratio / 0.5, 1.0)


def _try_pdftotext_best(pdf_path: Path) -> str:
    """Automatically choose the best pdftotext mode."""
    candidates = []
    for mode in ("default", "layout"):
        text = _run_pdftotext(pdf_path, mode)
        if text.strip():
            candidates.append((mode, text, _score_extraction(text)))

    if not candidates:
        return ""

    best = max(candidates, key=lambda x: x[2])
    print(f"  pdftotext mode: {best[0]} (score: {best[2]:.3f})")
    return best[1]


def _try_pymupdf(pdf_path: Path) -> tuple:
    """Extract text with PyMuPDF. Returns (text, page_count)."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        text = "\n".join(parts)
        if len(text.strip()) > 100:
            return text, page_count
    except ImportError:
        print("  PyMuPDF not available")
    except Exception as e:
        print(f"  PyMuPDF error: {e}")
    return "", 0


def _try_tesseract(pdf_path: Path) -> tuple:
    """Extract text with Tesseract OCR as a fallback. Returns (text, page_count)."""
    try:
        from pdf2image import convert_from_path
        import pytesseract

        print("  OCR starting (this may take a while)...")
        images = convert_from_path(str(pdf_path), dpi=300, fmt="png")
        page_count = len(images)
        parts = []
        for i, img in enumerate(images):
            if (i + 1) % 10 == 0:
                print(f"  OCR page {i+1}/{page_count}...")
            text = pytesseract.image_to_string(img, lang="tur")
            parts.append(text)
        return "\n".join(parts), page_count
    except Exception as e:
        print(f"  Tesseract error: {e}")
    return "", 0


def _get_page_count(pdf_path: Path) -> int:
    """Return PDF page count."""
    try:
        result = subprocess.run(
            [PDFTOTEXT_BIN.replace("pdftotext", "pdfinfo"), str(pdf_path)],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    # fallback: PyMuPDF
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except Exception:
        pass
    return 0


def extract_pdf(pdf_path: Path) -> tuple:
    """
    Extract text from a PDF. Tries available methods in order.
    Returns: (raw_text, method_used, page_count)
    """
    page_count = _get_page_count(pdf_path)

    # 1. pdftotext
    text = _try_pdftotext_best(pdf_path)
    if text and len(text.strip()) > 200:
        alnum = sum(c.isalnum() for c in text[:10000])
        ratio = alnum / min(len(text), 10000) if text else 0
        if ratio > 0.25:
            return text, "pdftotext", page_count

    # 2. PyMuPDF
    text, pc = _try_pymupdf(pdf_path)
    if pc > 0:
        page_count = pc
    if text and len(text.strip()) > 200:
        return text, "pymupdf", page_count

    # 3. Tesseract OCR
    text, pc = _try_tesseract(pdf_path)
    if pc > 0:
        page_count = pc
    return text, "tesseract", page_count


def process_book(pdf_path: Path, force: bool = False) -> Path:
    """Process one PDF and save its RAW text output."""
    stem = pdf_path.stem
    out_path = BOOK_OUTPUT_RAW / f"{stem}_RAW.txt"

    if out_path.exists() and not force:
        print(f"  SKIP (exists): {out_path.name}")
        return out_path

    print(f"  Extracting: {pdf_path.name}")
    text, method, page_count = extract_pdf(pdf_path)

    if not text or len(text.strip()) < 100:
        print(f"  WARNING: Very little text extracted from {pdf_path.name}")
        return out_path

    BOOK_OUTPUT_RAW.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"  OK: {out_path.name} ({method}, {page_count} pages, {len(text)} chars)")
    return out_path


def process_all(force: bool = False):
    """Process all PDFs."""
    pdfs = sorted(BOOK_INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {BOOK_INPUT_DIR}")
        return

    print(f"Found {len(pdfs)} PDF files")
    for pdf in pdfs:
        process_book(pdf, force=force)


def _format_status(pdf_path: Path) -> str:
    """Return RAW output status for a PDF."""
    raw_path = BOOK_OUTPUT_RAW / f"{pdf_path.stem}_RAW.txt"
    return "RAW exists" if raw_path.exists() else "no RAW"


def _print_pdf_menu(pdfs: list):
    """Print a numbered PDF selection menu."""
    print(f"\nPDF files found: {len(pdfs)}")
    print("-" * 78)
    for i, pdf in enumerate(pdfs, start=1):
        print(f"{i:>2}. {pdf.name:<55} {_format_status(pdf)}")
    print("-" * 78)


def _parse_menu_selection(selection: str, pdf_count: int) -> list[int]:
    """Parse user selection text into 0-based PDF indices."""
    s = selection.strip().lower()
    if not s:
        return []
    if s in {"q", "quit", "çık", "cik", "exit"}:
        return []
    if s in {"all", "hepsi", "tümü", "tum", "*"}:
        return list(range(pdf_count))

    selected = []
    for part in s.replace(",", " ").split():
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < pdf_count and idx not in selected:
            selected.append(idx)
    return selected


def process_interactive():
    """Show a numbered PDF menu and extract selected files."""
    pdfs = sorted(BOOK_INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {BOOK_INPUT_DIR}")
        return

    _print_pdf_menu(pdfs)
    print("Enter the number of the PDF you want to extract.")
    print("For multiple files: 1 3 5")
    print("For all files: all")
    selection = input("Selection: ")
    selected_indices = _parse_menu_selection(selection, len(pdfs))

    if not selected_indices:
        print("No selection made; cancelled.")
        return

    overwrite = input("Overwrite existing RAW files? [y/N]: ").strip().lower()
    force = overwrite in {"y", "yes", "e", "evet"}

    for idx in selected_indices:
        raw_path = process_book(pdfs[idx], force=force)
        if raw_path.exists():
            print(f"  Ready: {raw_path}")
        print()


if __name__ == "__main__":
    force = "--force" in sys.argv
    if "--all" in sys.argv:
        process_all(force=force)
    elif len(sys.argv) > 1 and sys.argv[1] not in {"--force", "--interactive"}:
        pdf = Path(sys.argv[1])
        if pdf.exists():
            process_book(pdf, force=force)
        else:
            print(f"File not found: {pdf}")
    else:
        process_interactive()
