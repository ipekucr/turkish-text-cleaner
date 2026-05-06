# Contributing

Thanks for your interest in contributing. This project is a Turkish-first, language-adaptable NLP/document-cleaning pipeline for producing cleaner plain text from noisy book PDF extractions.

## Copyright and Data Rules

Please do not share copyrighted book text in issues, pull requests, tests, or screenshots.

Acceptable examples:

- Short synthetic examples
- Short public-domain excerpts with clear source/license notes
- Minimal examples that demonstrate a specific cleaning issue
- Abstract examples that explain an algorithm

Do not submit:

- Full PDF files
- Full RAW/CLEAN book outputs
- Long copyrighted excerpts

## Contribution Areas

High-value contribution areas:

- Front/back matter detection
- Turkish post-OCR correction
- Morphological analysis for word repair
- Footnote/endnote cleanup
- Heading detection
- Tests and regression samples
- Public-domain sample corpus
- Documentation
- Language profiles for other languages

## Reporting a Cleaning Error

When reporting a cleaning issue, please use this format if possible:

```text
Text type: novel / academic / essay / etc.
Pipeline stage: extraction / manual gate / cleaning
Observed output: synthetic or short safe example
Expected output: corrected form
Why this is safe: repeated pattern / clear context / low false-positive risk
Risk: possible false-positive example, if any
```

## Adding a New Cleaning Rule

When adding a new rule:

- Prefer structural or algorithmic signals first.
- Use regex only when a simpler structural method is not enough.
- Explain the false-positive risk.
- Document the decision in `cleaning-notes.md` or `docs/algorithm.md`.
- Add at least one synthetic test example.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python clean_text.py examples/demo_raw.txt --force
```

To run the cleaner on your own local RAW files:

```bash
python clean_text.py --all --force
```

Note: `book-input/`, `book-output-raw/`, and `book-output-clean/` must not be committed.
