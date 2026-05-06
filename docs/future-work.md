# Future Work

This project is currently a v0.1-style pipeline built with structural heuristics. The following areas are good next steps.

## 1. Front/Back Matter Classifier

The user currently removes non-main-text sections manually from the RAW file.

Goal:

- Detect publisher pages, prefaces, tables of contents, bibliographies, appendices, afterwords, and main-text starts.

Possible signals:

- Page position
- Heading density
- Paragraph length distribution
- Publisher/citation signals
- Names, dates, ISBN, publisher markers
- Layout metadata

Possible models:

- Rule-based baseline
- Classical ML classifier
- Transformer-based text classifier
- Layout-aware document model

## 2. Turkish Morphological Analyzer

Tools could make word-join and word-split decisions safer.

Example targets:

- `bir likte` -> `birlikte`
- `on lar` -> `onlar`
- Contextual decision for `beş eri`

## 3. Post-OCR Correction

Character level OCR corruption needs candidate generation and contextual selection.

Possible approach:

- Edit distance
- Turkish lexicon
- Character confusion matrix
- N-gram or language-model score
- Morphological validity

## 4. Evaluation

The current evaluation process is mostly manual, book by book.

Future metrics:

- Removed-line precision
- Page-number/header recall
- Word-repair precision
- Character error rate
- Manual review sample score

## 5. Public Test Corpus

A small copyright-safe test set is needed.

Possible sources:

- Public domain texts
- Synthetic OCR errors
- Artificial page layout examples

## 6. CLI and Packaging

The pipeline can later be packaged as a command-line tool:

```bash
turkish-text-cleaner extract book.pdf
turkish-text-cleaner clean raw.txt
```


## 7. Language Profiles

The architecture can support other languages by separating language-specific components.

Possible structure:

```text
profiles/
  tr.py
  en.py
  fr.py
```

Each profile could define:

- Alphabet/casing behavior
- Suffix or morphology hints
- OCR confusion rules
- Heading keywords
- Short-word guard lists
- Word repair scoring
