#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Turkish Book Text Extraction Pipeline
=======================================
Pipeline for extracting cleaner plain text from book PDFs.

Usage:
    python run_pipeline.py                          # Process all books (extract + clean)
    python run_pipeline.py --book "Book.pdf"        # Process one book
    python run_pipeline.py --clean-only             # Only clean existing RAW files
    python run_pipeline.py --force                  # Overwrite existing outputs
    python run_pipeline.py --audit                  # Quality audit
    python run_pipeline.py --list                   # List books

Pipeline:
    1. PDF → RAW text   (extract_text.py)
    2. Open the RAW file and manually remove front/back matter
       (publisher pages, prefaces, bibliographies, etc.).
    3. RAW → CLEAN text (clean_text.py)
       Page numbers, repeated headers/footers, chapter headings,
       decorative lines, and OCR artifacts are cleaned automatically.
"""

import argparse

from extract_text import BOOK_INPUT_DIR, BOOK_OUTPUT_RAW, process_book as extract_book, process_all as extract_all
from clean_text import BOOK_OUTPUT_CLEAN, process_book as clean_book, process_all as clean_all


def list_books():
    """List books and output status."""
    pdfs = sorted(BOOK_INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {BOOK_INPUT_DIR}/")
        return

    print(f"\n{'PDF':<45} {'RAW':<8} {'CLEAN':<8}")
    print("-" * 62)

    for pdf in pdfs:
        stem = pdf.stem
        raw = "YES" if (BOOK_OUTPUT_RAW / f"{stem}_RAW.txt").exists() else "-"
        clean = "YES" if (BOOK_OUTPUT_CLEAN / f"{stem}_CLEAN.txt").exists() else "-"
        print(f"{pdf.name:<45} {raw:<8} {clean:<8}")

    print(f"\nTotal: {len(pdfs)} books")


def audit_quality():
    """Run a lightweight quality audit on CLEAN files."""
    cleans = sorted(BOOK_OUTPUT_CLEAN.glob("*_CLEAN.txt"))
    if not cleans:
        print("No CLEAN files found")
        return

    print(f"\n{'Book':<45} {'Words':<10} {'Chars':<12} {'Suspicious'}")
    print("-" * 85)

    for clean in cleans:
        with open(clean, 'r', encoding='utf-8') as f:
            text = f.read()

        words = len(text.split())
        chars = len(text)

        issues = []

        # Check for remaining ISBN
        if 'ISBN' in text:
            issues.append("ISBN found")
        # Check for remaining URLs
        if 'www.' in text or 'http' in text:
            issues.append("URL found")
        # Check for remaining email
        if '@' in text and '.' in text:
            # Simple email check: @ plus a dot after the domain part.
            for word in text.split():
                if '@' in word and '.' in word.split('@')[-1]:
                    issues.append("email found")
                    break
        # Check for pipe-separated headers
        pipe_count = 0
        i = 0
        while i < len(text):
            if text[i] == '|':
                # Pipe followed by optional spaces and a short number.
                j = i + 1
                while j < len(text) and text[j] == ' ':
                    j += 1
                digit_start = j
                while j < len(text) and text[j].isdigit():
                    j += 1
                if j > digit_start and (j - digit_start) <= 4:
                    pipe_count += 1
            i += 1
        if pipe_count > 3:
            issues.append(f"{pipe_count} pipe-headers")
        # Very short text
        if words < 5000:
            issues.append("very short")

        status = ", ".join(issues) if issues else "OK"
        print(f"{clean.stem:<45} {words:<10} {chars:<12} {status}")


def run_single_book(pdf_name: str, force: bool = False):
    """Run the pipeline for one PDF."""
    pdf_path = BOOK_INPUT_DIR / pdf_name
    if not pdf_path.exists():
        # Try a fuzzy filename match.
        candidates = list(BOOK_INPUT_DIR.glob(f"*{pdf_name}*"))
        if candidates:
            pdf_path = candidates[0]
            print(f"Matched: {pdf_path.name}")
        else:
            print(f"PDF not found: {pdf_name}")
            return

    # Step 1: Extract
    print(f"\n[1/3] EXTRACT: {pdf_path.name}")
    raw_path = extract_book(pdf_path, force=force)

    # Step 2: User manually edits RAW file
    if raw_path.exists():
        print(f"\n[2/3] MANUAL EDIT REQUIRED:")
        print(f"  Open {raw_path} and remove non-main-text front/back matter")
        print(f"  such as publisher pages, prefaces, bibliographies, and appendices.")
        input("  Press Enter when you are done editing...")

    # Step 3: Clean
    if raw_path.exists():
        print(f"\n[3/3] CLEAN: {raw_path.name}")
        clean_book(raw_path, force=force)
    else:
        print(f"RAW file not found, skipping clean")
        return


def run_all(force: bool = False, clean_only: bool = False):
    """Run the pipeline for all local PDFs/RAW files."""
    if not clean_only:
        print("=" * 60)
        print("[1/3] EXTRACTING ALL BOOKS")
        print("=" * 60)
        extract_all(force=force)

        print("\n" + "=" * 60)
        print("[2/3] MANUAL EDIT REQUIRED")
        print("=" * 60)
        print("  Open the RAW files in book-output-raw/ and remove non-main-text")
        print("  front/back matter such as publisher pages, prefaces, bibliographies,")
        print("  tables of contents, and appendices.")
        input("  Press Enter when you are done editing...")

    print("\n" + "=" * 60)
    print("[3/3] CLEANING ALL BOOKS")
    print("=" * 60)
    clean_all(force=force)


def main():
    parser = argparse.ArgumentParser(description="Turkish Book Text Pipeline")
    parser.add_argument("--book", type=str, help="Process single book (PDF filename)")
    parser.add_argument("--list", action="store_true", help="List books and status")
    parser.add_argument("--audit", action="store_true", help="Quality audit")
    parser.add_argument("--clean-only", action="store_true", help="Only run cleaning (skip extraction)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    args = parser.parse_args()

    if args.list:
        list_books()
    elif args.audit:
        audit_quality()
    elif args.book:
        run_single_book(args.book, force=args.force)
    else:
        run_all(force=args.force, clean_only=args.clean_only)


if __name__ == "__main__":
    main()
