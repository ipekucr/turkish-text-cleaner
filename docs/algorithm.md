# Algorithm Notes

This document summarizes the main approaches used in the cleaning stage.

## Design Principles

- Prefer page structure and text statistics over brittle fixed regexes.
- Avoid overfitting to one book whenever possible.
- Do not automate high-risk corrections without stronger context.
- Keep the manual gate explicit until front/back matter detection is reliable.
- Separate language-independent structure from Turkish-specific heuristics.

## 1. Page Association

The algorithm collects the top and bottom lines of each page. Lines that repeat across pages, exactly or fuzzily, become running header/footer candidates.

Signals:

- Cross-page frequency
- Normalized text
- Generalized digits
- Letters-only running header comparison

Targets:

- Book titles
- Author names
- Page-top/page-bottom repeated lines
- OCR variants of running headers

## 2. Page Number Detection

Short isolated numeric lines are collected as candidates. The cleaner then looks for the longest sequence that behaves like printed page numbers.

Signals:

- Top/bottom page position
- Offset between PDF page index and printed page number
- Monotonic sequence
- Minimum run length

This helps distinguish real page numbers from isolated chapter numbers.

## 3. Chapter Heading Detection

Heading candidates are detected with multiple structural signals:

- First non-empty lines of a page
- Isolated short lines
- Uppercase ratio
- Heading keywords
- Centered/title-case lines
- Chapter number line followed by a heading-like line

Protected cases:

- Date lines
- Dialogue lines
- Normal prose sentences

## 4. Footnotes and Citation Blocks

Bottom-of-page footnotes are detected with positional and citation signals.

Signals:

- Lower page position
- Numbered footnote markers
- Citation features: year, publication place, editor markers, page references
- False-positive filters for tables of contents and numbered lists

## 5. Line-Break Hyphenation

If a line ends with a hyphen or soft hyphen and the next line starts with a lowercase letter, the fragments are joined.

Example:

```text
gö-
mülmüştü
```

```text
gömülmüştü
```

## 6. OCR Noise Normalization

Common character-level artifacts are normalized or removed:

- Replacement characters
- Zero-width characters
- Middle-dot artifacts
- Slash-based OCR splits
- A small set of safe glyph substitutions

## 7. Intraword Space Repair

PDF extraction and OCR sometimes split a word internally:

```text
toplumla rının
diye ceğim
```

This stage uses:

- Turkish suffix fragments
- Book-internal vocabulary
- Short-word protection lists
- Context guards
- Known compound-fragment signals

## 8. Glued-Word Splitting

Some words lose a space during extraction:

```text
Bukitap
ayönce
evsatın
```

This stage uses:

- Book-internal vocabulary
- Number-word prefixes
- Apostrophe suffix handling
- Safe phrase splits

## Language Adaptation

The following parts are mostly language-independent:

- PDF extraction
- Page association
- Page-number sequence detection
- Repeated header/footer removal
- Basic heading isolation
- Manual gate workflow

The following parts are language-specific:

- Suffix fragments
- Casing rules
- OCR confusion lists
- Word repair rules
- Morphological validity checks

Future language profiles can move these language-specific components into separate modules.

## Why Not Fix Everything Automatically?

Some errors are context-dependent:

```text
on lar
bir likte
on dan
```

A mechanical rule can easily damage valid text. These cases belong to future morphological or contextual modeling rather than unconditional replacement.
