#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2: Raw Text → Clean Text

Clean noise from RAW text after the user manually removes front/back matter:

1. Page association: detect repeated running headers/footers across pages
2. Page-number detection: isolated numbers at page tops/bottoms
3. Chapter-heading detection: isolated short non-prose lines
4. Decorative lines: separators such as ***, ---, •••
5. Hyphen repair: line-break hyphenation
6. OCR noise normalization and intraword space repair

Core principle: use cross-page statistical analysis and Turkish-first text
repair heuristics instead of brittle fixed regexes. Safe rules may be derived
from local book reviews, but book data and copyrighted content are not included
in the repository.

Output: book-output-clean/{book_name}_CLEAN.txt
"""

import sys
import textwrap
from pathlib import Path
from collections import Counter, defaultdict
from difflib import SequenceMatcher


BOOK_OUTPUT_RAW = Path(__file__).parent / "book-output-raw"
BOOK_OUTPUT_CLEAN = Path(__file__).parent / "book-output-clean"



# PAGE-ASSOCIATION: Cross-page repeated line detection


def _normalize_for_comparison(text: str) -> str:
    """Normalize for comparison: remove numbers, lowercase letters, simplify spaces."""
    s = text.strip().lower()
    # Replace the numbers with '#' (consecutive numbers become a single '#')
    result = []
    in_digit = False
    for c in s:
        if c.isdigit():
            if not in_digit:
                result.append('#')
                in_digit = True
        else:
            in_digit = False
            result.append(c)
    s = ''.join(result)
    # Simplify the spaces
    s = ' '.join(s.split())
    return s


def _fuzzy_match(a: str, b: str, threshold: float = 0.7) -> bool:
    """Do the two strings match fuzzy? (Tolerant to OCR errors)"""
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


_TURKISH_LETTERS = set(
    'abcçdefgğhıijklmnoöprsştuüvyzâîû'
    'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZÂÎÛ'
)


def _normalize_for_running_header(text: str) -> str:
    """For running header comparison: remove numbers, punctuation, and spaces, leaving only letters. 
    '6 • OsMANCIK' and '348 • ÜSMANCIK' become similar as 'osmancık' / 'üsmancık'."""
    s = text.strip().lower()
    # Keep only letters and spaces.
    filtered = []
    for c in s:
        if c in _TURKISH_LETTERS or c.isalpha() or c == ' ':
            filtered.append(c)
    s = ''.join(filtered)
    # Simplify spaces.
    s = ' '.join(s.split())
    return s


def detect_repeated_lines_by_page(pages: list, n_top: int = 3, n_bottom: int = 3,
                                   min_frequency: float = 0.15) -> dict:
    """
    Page-Association algorithm: Identifies repeating header/footer/page numbers by comparing
    the first/last N lines of each page with other pages.

    Two stages:
    1) Exact-normalized: Numbers are converted to '#' and compared (standard Page-Association)
    2) Running-header: Numbers and symbols are completely removed and only letters are
    compared (captures formats like "osmancık: "6 • OsMANCIK" vs "ÜSMANCIK • 9")

    Args:
        pages: List of page texts (separated by \\f)
        n_top: How many lines from the beginning of each page should be looked at?
        n_bottom: How many lines from the end of each page should be looked at?
        min_frequency: Minimum repetition rate (0.15 = per 15% of pages)

    Returns:
        dict: {page_idx: set of line indices to remove}
    """
    total_pages = len(pages)
    if total_pages < 5:
        return {}

    min_count = max(3, int(total_pages * min_frequency))

    # Add up the top and bottom lines of each page.
    page_lines = []
    for page in pages:
        lines = page.split('\n')
        non_empty_top = []
        non_empty_bottom = []

        # First n_top non-empty lines from the top.
        for li, line in enumerate(lines):
            if line.strip():
                non_empty_top.append((li, line.strip()))
                if len(non_empty_top) >= n_top:
                    break

        # Last n_bottom non-empty lines from the bottom.
        for li in range(len(lines) - 1, -1, -1):
            if lines[li].strip():
                non_empty_bottom.append((li, lines[li].strip()))
                if len(non_empty_bottom) >= n_bottom:
                    break
        non_empty_bottom.reverse()

        page_lines.append({
            'lines': lines,
            'top': non_empty_top,
            'bottom': non_empty_bottom,
        })

    #  Step 1: Standard normalized matching
    normalized_counts = Counter()
    line_map = []

    for pi, pl in enumerate(page_lines):
        for li, text in pl['top'] + pl['bottom']:
            norm = _normalize_for_comparison(text)
            if norm and len(norm) > 0:
                normalized_counts[norm] += 1
                line_map.append((pi, li, text, norm))

    frequent_patterns = {pat for pat, count in normalized_counts.items() if count >= min_count}

    # Fuzzy matching also captures similar but not exact patterns.
    all_norms = list(normalized_counts.keys())
    merged_patterns = set(frequent_patterns)

    for pat in frequent_patterns:
        for other in all_norms:
            if other not in merged_patterns and _fuzzy_match(pat, other, 0.75):
                if normalized_counts[pat] + normalized_counts[other] >= min_count:
                    merged_patterns.add(other)

    removals = {}
    for pi, li, text, norm in line_map:
        if norm in merged_patterns:
            if pi not in removals:
                removals[pi] = set()
            removals[pi].add(li)

    # Step 2: Running header detection (letters-only matching) 
    # "6 • OsMANCIK" → "osmancık", "Hayatmn En Mutlu An" → "hayatmn en mutlu an"
    # For short lines (<60 characters). Skip long lines (which may be actual text).
    rh_counts = Counter()
    rh_map = []

    for pi, pl in enumerate(page_lines):
        for li, text in pl['top'] + pl['bottom']:
            if len(text) > 60:
                continue
            rh = _normalize_for_running_header(text)
            if rh and len(rh) >= 3:
                rh_counts[rh] += 1
                rh_map.append((pi, li, text, rh))

    # Running header threshold: at least 20% of the pages
    rh_min = max(5, int(total_pages * 0.20))
    frequent_rh = set()
    for pat, count in rh_counts.items():
        if count >= rh_min:
            frequent_rh.add(pat)

    # Fuzzy match for OCR variants (osmancık vs üsmancık)
    all_rh = list(rh_counts.keys())
    merged_rh = set(frequent_rh)
    for pat in frequent_rh:
        for other in all_rh:
            if other not in merged_rh and _fuzzy_match(pat, other, 0.70):
                if rh_counts[pat] + rh_counts[other] >= rh_min:
                    merged_rh.add(other)

    for pi, li, text, rh in rh_map:
        if rh in merged_rh:
            if pi not in removals:
                removals[pi] = set()
            removals[pi].add(li)

    return removals



# PAGE NUMBER DETECTION


def _looks_like_page_number(text: str, max_page: int = 2000) -> bool:
    """Does the text look like a page number?"""
    return _parse_page_number_value(text, max_page=max_page) is not None


def _looks_like_bracketed_page_number_artifact(text: str) -> bool:
    """Is it an isolated page number remnant that can be outside
     the sequence, like `9)`?"""
    s = text.strip()
    if not s:
        return False
    if not (s[0] in '([' or s[-1] in ')]'):
        return False
    return _parse_page_number_value(s) is not None


def _parse_page_number_value(text: str, max_page: int = 2000) -> int | None:
    """Convert the isolated page number candidate to an integer.

    Without using Regex, it only accepts standalone numerical lines:
    "7", "123", "(7)", "[123]" and some OCR variants ("lO", "ı ı").
    """
    s = text.strip()
    if not s:
        return None

    if len(s) >= 3 and s[0] in '([' and s[-1] in ')]':
        s = s[1:-1].strip()
    elif len(s) >= 2 and s[0] in '([':
        s = s[1:].strip()
    elif len(s) >= 2 and s[-1] in ')]':
        s = s[:-1].strip()

    digit_chars = []
    saw_digit = False
    for c in s:
        if c.isdigit():
            digit_chars.append(c)
            saw_digit = True
        elif c in "lIı":
            digit_chars.append('1')
        elif c in "Oo":
            digit_chars.append('0')
        elif c in "Ss" and saw_digit:
            digit_chars.append('5')
        elif c in "Ss" and any(ch.isdigit() for ch in s):
            digit_chars.append('5')
        elif c in " ''`":
            continue
        else:
            return None

    if not digit_chars:
        return None

    value = int(''.join(digit_chars))
    if 1 <= value <= max_page:
        return value
    return None


def _collect_page_number_candidates(pages: list, scan_depth: int = 3) -> list:
    """Extract isolated page number candidates from the top/bottom margins of the page."""
    candidates = []

    for pi, page in enumerate(pages):
        lines = page.split('\n')

        top_seen = 0
        for li, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            top_seen += 1
            value = _parse_page_number_value(s)
            if value is not None and len(s) < 12:
                candidates.append({
                    'page_idx': pi,
                    'line_idx': li,
                    'position': 'top',
                    'rank': top_seen,
                    'value': value,
                    'text': s,
                })
            if top_seen >= scan_depth:
                break

        bottom_seen = 0
        for li in range(len(lines) - 1, -1, -1):
            s = lines[li].strip()
            if not s:
                continue
            bottom_seen += 1
            value = _parse_page_number_value(s)
            if value is not None and len(s) < 12:
                candidates.append({
                    'page_idx': pi,
                    'line_idx': li,
                    'position': 'bottom',
                    'rank': bottom_seen,
                    'value': value,
                    'text': s,
                })
            if bottom_seen >= scan_depth:
                break

    return candidates


def _longest_consistent_page_number_run(candidates: list) -> list:
    """Find the longest sequence among the candidates,
    increasing in order like printed page number.

   In a consistent sequence, 
   the PDF page index and the printed numbering follow the same pattern:
   When page_idx is +1, value also becomes +1.
   If there are unnumbered pages, such as the beginning of a section,
   page_idx and value can increase with larger differences.
    """
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda c: (c['page_idx'], c['value'], c['line_idx']))
    best_len = [1] * len(ordered)
    prev = [-1] * len(ordered)

    for i, cur in enumerate(ordered):
        for j in range(i):
            old = ordered[j]
            page_gap = cur['page_idx'] - old['page_idx']
            value_gap = cur['value'] - old['value']
            if page_gap <= 0 or value_gap <= 0:
                continue
            if page_gap != value_gap:
                continue
            if best_len[j] + 1 > best_len[i]:
                best_len[i] = best_len[j] + 1
                prev[i] = j

    end = max(range(len(ordered)), key=lambda idx: best_len[idx])
    run = []
    while end != -1:
        run.append(ordered[end])
        end = prev[end]
    run.reverse()
    return run


def _select_page_number_sequences(candidates: list, total_pages: int) -> set:
    """Select reliable page number candidates.

    First, it finds the fixed offset groups: printed_page_number - pdf_page_index.
    Then, it performs a monotonic sequence check within each group. 
    This eliminates page numbers that flow throughout the book, rather than individual chapter numbers like "1".
    """
    if not candidates or total_pages < 3:
        return set()

    min_run = max(3, int(total_pages * 0.12))
    accepted = set()

    grouped = defaultdict(list)
    for cand in candidates:
        key = (cand['position'], cand['value'] - cand['page_idx'])
        grouped[key].append(cand)

    for group in grouped.values():
        unique_pages = {cand['page_idx'] for cand in group}
        if len(unique_pages) < min_run:
            continue
        run = _longest_consistent_page_number_run(group)
        if len({cand['page_idx'] for cand in run}) >= min_run:
            for cand in run:
                accepted.add((cand['page_idx'], cand['line_idx']))

    if accepted:
        return accepted

    #In some OCR outputs, individual errors can break the offset. We search for the longest consistent sequence at the same position in fallback, 
    # but we keep the threshold a little tighter.
    by_position = defaultdict(list)
    for cand in candidates:
        by_position[cand['position']].append(cand)

    fallback_min_run = max(4, int(total_pages * 0.18))
    for group in by_position.values():
        run = _longest_consistent_page_number_run(group)
        if len({cand['page_idx'] for cand in run}) >= fallback_min_run:
            for cand in run:
                accepted.add((cand['page_idx'], cand['line_idx']))

    return accepted


def detect_page_numbers(pages: list) -> dict:
    """
   Identify isolated page numbers at the beginning/end of pages.

    Strategy: Eliminate short numerical candidates at the top/bottom margin of each page, 
    then find reliable sequences that increase sequentially, like printed page numbers.
    This eliminates page numbers that run in the same position throughout the book, rather than individual chapter numbers or years within the text.
    Returns:
        dict: {page_idx: set of line indices to remove}
    """
    removals = {}
    total = len(pages)
    candidates = _collect_page_number_candidates(pages)
    accepted = _select_page_number_sequences(candidates, total)

    for pi, li in accepted:
        if pi not in removals:
            removals[pi] = set()
        removals[pi].add(li)

    return removals



# FOOTNOTE DETECTION 


# It should be at least this far down the page (0.6 = bottom 40%).
_FOOTNOTE_MIN_REL_POS = 0.6


def _leading_number_marker(line: str) -> tuple[int | None, str, int]:
    """Parse the short numbered marker at the beginning of the line without using regex.

    Returns: (number, separator, spaces_after_separator)
    e.g.: "12.   Kaynak" → (12, ".", 3)
    """
    i = 0
    while i < len(line) and line[i].isspace():
        i += 1

    digits = []
    while i < len(line) and line[i].isdigit() and len(digits) < 3:
        digits.append(line[i])
        i += 1

    if not digits or i >= len(line):
        return None, '', 0

    sep = line[i]
    if sep not in '.-':
        return None, '', 0
    i += 1

    spaces = 0
    while i < len(line) and line[i].isspace():
        spaces += 1
        i += 1

    return int(''.join(digits)), sep, spaces


def _looks_like_footnote_marker(line: str) -> bool:
    """Like the beginning of a footnote? Without regex: N. + min 2 spaces."""
    number, sep, spaces = _leading_number_marker(line)
    return number is not None and 1 <= number <= 99 and sep == '.' and spaces >= 2


def _looks_like_numbered_list_marker(line: str) -> bool:
    """Like a table of contents/numbered list row? Without regex."""
    number, sep, spaces = _leading_number_marker(line)
    return number is not None and 1 <= number <= 99 and sep in '.-' and spaces >= 1


def _count_dots_runs(line: str) -> int:
    """Count the number of times a three-dot/leader point is used in the row."""
    count = 0
    run = 0
    for c in line:
        if c == '.':
            run += 1
        else:
            if run >= 3:
                count += 1
            run = 0
    if run >= 3:
        count += 1
    if '…' in line:
        count += line.count('…')
    return count


def _indent_width(line: str) -> int:
    """Return the number of spaces at the beginning of each line."""
    count = 0
    for c in line:
        if c == ' ':
            count += 1
        elif c == '\t':
            count += 4
        else:
            break
    return count


def _is_isolated_line(lines: list, line_idx: int) -> bool:
    """Are there blank lines on either side of the current line?"""
    prev_empty = line_idx == 0 or not lines[line_idx - 1].strip()
    next_empty = line_idx + 1 >= len(lines) or not lines[line_idx + 1].strip()
    return prev_empty and next_empty


def _has_four_digit_year(line: str) -> bool:
    """Are there any four-digit years between 1500 and 2099 in the row? Searching without regex."""
    digits = []
    for c in line:
        if c.isdigit():
            digits.append(c)
        else:
            if len(digits) == 4:
                value = int(''.join(digits))
                if 1500 <= value <= 2099:
                    return True
            digits = []
    if len(digits) == 4:
        value = int(''.join(digits))
        return 1500 <= value <= 2099
    return False


def _citation_signal_score(lines: list) -> int:
    """Score the bibliographic block signals at the bottom of the page."""
    text = ' '.join(line.strip() for line in lines)
    lower = _lower_tr(text)
    score = 0

    if _has_four_digit_year(text):
        score += 1
    if '(' in text and ')' in text:
        score += 1
    if ':' in text and ('(' in text or ')' in text):
        score += 1

    for token in (
        'ed.', 'bkz.', 's.', 'cilt', 'press', 'university', 'yayınları',
        'verlag', 'journal', 'dergisi', 'essays', 'identity'
    ):
        if token in lower:
            score += 1

    return score


def _find_bottom_citation_block(lines: list, min_rel_pos: float) -> int:
    """Find the beginning of the unnumbered page six source blocks."""
    total_lines = len(lines)
    li = total_lines - 1

    while li >= 0 and not lines[li].strip():
        li -= 1
    if li < 0:
        return None

    end = li
    while li >= 0 and lines[li].strip():
        li -= 1
    start = li + 1

    if start >= total_lines:
        return None
    if start / total_lines < min_rel_pos:
        return None

    block = lines[start:end + 1]
    if not (1 <= len(block) <= 6):
        return None

    indented = sum(1 for line in block if _indent_width(line) >= 4)
    avg_len = sum(len(line.strip()) for line in block) / len(block)
    if indented < max(1, len(block) - 1):
        return None
    if avg_len < 25:
        return None
    if _citation_signal_score(block) < 3:
        return None

    return start


def detect_footnotes(pages: list) -> dict:
    """
   Detect footnotes at the bottom of the page.

   Academic and research books contain numbered footnotes at the bottom of the page. These footnotes get mixed up in the text flow after OCR. This function:

        1. Finds lines starting with "N." in the bottom 40% of each page.
        2. Marks all lines from the first footnote line to the end of the page as footnotes (including subsequent lines).
        3. Verifies that the footnote block is separated from the main text.

    Those that escape this algorithm:
        - Unnumbered footnotes (asterisks, etc.)
        - In-text parenthetical references "(Smith, 2020)"
        - Chapter endnotes

    Returns:
        dict: {page_idx: set of line indices to remove}
    """
    removals = {}

    for pi, page in enumerate(pages):
        lines = page.split('\n')
        total_lines = len(lines)
        if total_lines < 5:
            continue

        # Find the first footnote marker starting from the bottom half.
        footnote_start = None
        for li in range(total_lines - 1, -1, -1):
            rel_pos = li / total_lines
            if rel_pos < _FOOTNOTE_MIN_REL_POS:
                break

            stripped = lines[li].strip()
            if not stripped:
                continue

            if _looks_like_footnote_marker(lines[li]):
                footnote_start = li

        if footnote_start is None:
            footnote_start = _find_bottom_citation_block(lines, _FOOTNOTE_MIN_REL_POS)
            if footnote_start is None:
                continue

        # False positive check: Table of contents / numbered list pages
        # Two signals:
        # 1) If there is "N." or "N-" in the upper half of the page as well → numbered list
        # 2) If the page contains too many "..." (sequences of periods, table of contents style)

        top_half_markers = 0
        dots_lines = 0
        for li in range(total_lines):
            line_s = lines[li].strip()
            if li < footnote_start and _looks_like_numbered_list_marker(lines[li]):
                top_half_markers += 1
            if _count_dots_runs(line_s) > 0:
                dots_lines += 1

        if top_half_markers >= 2 or dots_lines >= 3:
            # Numbered list or table of contents → not a footnote
            continue

        # Mark the footnote block: from footnote_start to the end of the page.
        if pi not in removals:
            removals[pi] = set()
        for li in range(footnote_start, total_lines):
            removals[pi].add(li)

    return removals



# CHAPTER HEADING / ISOLATED SHORT LINE DETECTION


_TURKISH_UPPER = set('ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ')
_TURKISH_LOWER = set('abcçdefgğhıijklmnoöprsştuüvyz')
_ROMAN_NUMERAL_CHARS = set('IVXLC')


def _is_roman_numeral(text: str) -> bool:
    """Is the text a Roman numeral? Like 'IV', 'XII', 'III'."""
    s = text.rstrip('.')
    if not s:
        return False
    return all(c in _ROMAN_NUMERAL_CHARS for c in s)



# Heading Detection Constants

# Empirical thresholds — there is no basis for these specific values ​​in the academic literature
# (Nguyen et al. 2021 Survey of Post-OCR Processing).
# They have been established as practical heuristics for heading detection on pure text without font metadata.

_HEADING_UPPER_RATIO = 0.6     # Letter size ratio threshold (60%+)
_HEADING_MAX_WORDS = 6         # Maximum number of words for capitalization rule
_HEADING_MAX_LINE_LEN = 60     # Heading candidate maximum character length
_HEADING_MAX_TOTAL_WORDS = 8   # Maximum number of words for any heading rule
_PROSE_MIN_WORDS = 4           # Minimum word count for Prose filter
_PROSE_MIN_LOWERCASE = 2       # Minimum lowercase letters for process filter


_ORDINAL_WORDS_TR = {
    'BİR', 'İKİ', 'ÜÇ', 'DÖRT', 'BEŞ', 'ALTI', 'YEDİ', 'SEKİZ', 'DOKUZ', 'ON',
    'BİRİNCİ', 'İKİNCİ', 'ÜÇÜNCÜ', 'DÖRDÜNCÜ', 'BEŞİNCİ', 'ALTINCI',
    'YEDİNCİ', 'SEKİZİNCİ', 'DOKUZUNCU', 'ONUNCU',
    'YİRMİ', 'OTUZ', 'KIRK', 'ELLİ', 'ALTMIŞ', 'YETMİŞ', 'SEKSEN', 'DOKSAN', 'YÜZ',
}
# Chapter title keywords (correct spelling).
# OCR variants (BALI, BÖLUM, etc.) are captured using fuzzy matching, not hardcoding.
_HEADING_KEYWORDS = {
    'BÖLÜM', 'BÖLÜMÜ', 'KISIM',
    'GİRİŞ', 'SONUÇ', 'ÖNSÖZ', 'SONSÖZ', 'SUNUŞ', 'İÇİNDEKİLER',
    'EK',
}

_TITLE_CONNECTOR_WORDS = {
    've', 'ile', 'veya', 'yahut', 'de', 'da', 'ki', 'için',
}


# During OCR, it is common for Turkish special characters to be converted to their ASCII equivalents
# (İ→I, Ö→O, Ü→U, Ş→S, Ğ→G, Ç→C). These equivalencies are used for fuzzy matching.
_TR_CHAR_NORMALIZE = str.maketrans(
    'ÖÜİŞĞÇöüişğç',
    'OUISGCouisgc',
)


def _fuzzy_keyword_match(word: str, min_similarity: float = 0.70) -> bool:
    """Does the word resemble one of the known title keywords?

       Uses Turkish character normalization + character-level similarity to catch OCR distortions. 
       'BOLUM' → 'BOLUM' vs 'BOLUM' (100%), 'BALI' → (40%, rejected).

       Reference: Inspired by the Page-Association (Lin, 2003) fuzzy match approach.
    """
    w_upper = word.upper()
    if w_upper in _HEADING_KEYWORDS:
        return True

    #Fuzzy matching is risky for short words (EK → ER? No)
    if len(w_upper) < 4:
        return False

    # Normalize Turkish characters to their ASCII equivalents.
    w_norm = w_upper.translate(_TR_CHAR_NORMALIZE)

    for kw in _HEADING_KEYWORDS:
        if len(kw) < 4:
            continue
        # Skip if the length difference is too great
        if abs(len(w_norm) - len(kw)) > 2:
            continue
        kw_norm = kw.translate(_TR_CHAR_NORMALIZE)
        # Common character ratio (normalized)
        common = 0
        kw_chars = list(kw_norm)
        for c in w_norm:
            if c in kw_chars:
                kw_chars.remove(c)
                common += 1
        max_len = max(len(w_norm), len(kw_norm))
        if max_len > 0 and common / max_len >= min_similarity:
            return True

    return False


def _looks_like_heading_text(text: str) -> bool:
    """
   Does the text resemble a chapter heading? Very strict rules.

   It only returns True in the following cases:
   A) The vast majority are in CAPITAL LETTERS (>60%) AND a maximum of 6 words AND not prose-like
   B) Known heading keyword + a maximum of 6 words (CHAPTER, SECTION, INTRODUCTION...)
   C) Only Roman numerals (I, II, III, IV, V, VI...)
   D) Only Turkish ordinal words (ONE, TWO, THREE, FIRST... - all in capital letters)
    """
    s = text.strip()
    if not s or len(s) > _HEADING_MAX_LINE_LEN:
        return False

    words = s.split()
    if not words or len(words) > _HEADING_MAX_TOTAL_WORDS:
        return False

    # — Negative signals (rapid output) —

    # If it starts with a dialog box → prose
    if s[0] in '-–—‐"\'«“„':
        return False

    # If the sentence ends with punctuation → prose
    if s[-1] in '.?!;…:':
        return False
    if s.endswith('...') or s.endswith('..'):
        return False

    # If it ends with a hyphen → spelling (broken line, definite prose)
    if s.endswith('-') or s.endswith('­'):
        return False

    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False

    upper_letters = [c for c in letters if c.isupper() or c in _TURKISH_UPPER]
    upper_ratio = len(upper_letters) / len(letters) if letters else 0
    noisy_heading_keyword = any(_fuzzy_keyword_match(w.rstrip('.,;:!?')) for w in words)

    # If it starts with a lowercase letter → broken sentence.
    # Exception: OCR corrupted "İKİNCİ" to "iKÎNCl" but it has "BÖLÜM" next to it.

    first_alpha = ''
    for c in s:
        if c.isalpha():
            first_alpha = c
            break
    if first_alpha and first_alpha in _TURKISH_LOWER and not (
        noisy_heading_keyword and upper_ratio > 0.45
    ):
        return False

    # Prose filter: number of lowercase words in multi-word lines
    # (empirical threshold — for distinguishing heading/procedures without font metadata)

    if len(words) >= _PROSE_MIN_WORDS:
        lowercase_words = sum(1 for w in words if w[0:1].islower())
        if lowercase_words >= _PROSE_MIN_LOWERCASE:
            return False

    # If it contains a comma → prose (commas are rare in headings)
    if ',' in s:
        return False

    #── Positive signals ──

    # A) The vast majority of letters are in CAPITAL LETTERS and there is a maximum word limit.

    if upper_ratio > _HEADING_UPPER_RATIO and len(letters) >= 2 and len(words) <= _HEADING_MAX_WORDS:
        return True

    # B) Known title keywords (capture OCR variants with fuzzy match)
    for w in words:
        cleaned = w.rstrip('.,;:!?')
        if _fuzzy_keyword_match(cleaned):
            return True

    # C) Roman numerals only (single word or with ".")
    if len(words) <= 2:
        for w in words:
            if _is_roman_numeral(w) and len(w.rstrip('.')) <= 6:
                return True

    # D) Only ordinal words (ONE, TWO...) - all in capital letters.
    if all(w.upper().rstrip('.,;:!?') in _ORDINAL_WORDS_TR for w in words):
        # are all of them capital letters? (In prose it would be "Four people...", in heading it would be "FOUR")
        if upper_ratio > _HEADING_UPPER_RATIO:
            return True

    return False


def _clean_heading_word(word: str) -> str:
    """For title formatting control, retrieve the letters in the word and the OCR 1/l variant."""
    chars = []
    for c in word:
        if c.isalpha():
            chars.append(c)
        elif c == '1':
            chars.append('l')
    return ''.join(chars)


def _looks_like_centered_title_heading(line: str) -> bool:
    """Title Case: Capture centered/indented and isolated subheadings.

    Since there is no font information in the pure text,
    this rule only works with structural signals: short lines, unpuncted, indented, and title-shaped words.
    In examples where OCR splits the title word, such as `Boğaziçi Meden iyeti`, the smaller second part is considered a continuation of the preceding capitalized word.
    """
    s = line.strip()
    if not s or len(s) > _HEADING_MAX_LINE_LEN:
        return False

    indent = _indent_width(line)
    if indent < 6:
        return False

    if s[0] in '-–—‐"\'«“„':
        return False
    if s[-1] in '.?!;…:':
        return False
    if ',' in s:
        return False

    words = s.split()
    if not words or len(words) > _HEADING_MAX_TOTAL_WORDS:
        return False

    content_words = []
    previous_was_titleish = False
    for raw_word in words:
        cleaned = _clean_heading_word(raw_word)
        if not cleaned:
            continue

        lowered = _lower_tr(cleaned)
        if lowered in _TITLE_CONNECTOR_WORDS:
            continue

        first_alpha = ''
        for c in cleaned:
            if c.isalpha():
                first_alpha = c
                break
        if not first_alpha:
            continue

        is_titleish = first_alpha.isupper() or first_alpha in _TURKISH_UPPER
        is_ocr_continuation = (
            previous_was_titleish
            and first_alpha in _TURKISH_LOWER
            and len(cleaned) <= 8
        )

        content_words.append(is_titleish or is_ocr_continuation)
        previous_was_titleish = is_titleish or is_ocr_continuation

    if not content_words:
        return False

    titleish_ratio = sum(1 for ok in content_words if ok) / len(content_words)
    return titleish_ratio >= 0.75


def _looks_like_numbered_heading_line(text: str) -> bool:
    """Identify the header line that follows the separate number line.

    The standard heading filter counts lines ending in `?`. However, if "section number + isolated short uppercase line" appears together, headings with question marks, 
    such as `YIKILIŞ?`, are also considered safe heading blocks.
    """
    s = text.strip().strip('"\'“”‘’')
    if not s or len(s) > _HEADING_MAX_LINE_LEN:
        return False

    if _looks_like_heading_text(s):
        return True

    s = s.rstrip('.?!;…: ').strip()
    if not s:
        return False

    words = s.split()
    if not words or len(words) > _HEADING_MAX_TOTAL_WORDS:
        return False

    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False

    upper_letters = [c for c in letters if c.isupper() or c in _TURKISH_UPPER]
    upper_ratio = len(upper_letters) / len(letters)
    return upper_ratio > _HEADING_UPPER_RATIO


def detect_chapter_headings(pages: list) -> dict:
    """
   Identify the section headings.

   Very strict rules:
   1. Must be within the first 3 filled lines at the top of the page.
   2. Must pass the _looks_like_heading_text() test (CAPS, heading words, etc.).
   3. Must be followed by a blank line OR the next line must also be heading-like (isolated).
   4. Must not contain a page number (handled separately).
  
    Returns:
        dict: {page_idx: set of line indices to remove}
    """
    removals = {}

    for pi, page in enumerate(pages):
        lines = page.split('\n')

        # Look at the first few full lines at the top of the page.
        found_content = 0
        for li, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue

            found_content += 1
            if found_content > 3:
                break

            if _looks_like_page_number(s):
                # At the beginning of chapters, the number can appear on a separate line, directly below the title:
                # "2" + "Müslüman ve Tüccar". The sequential page numbering algorithm preserves this unique number;
                # here we clean it up together as a structural title block.
                for ni in range(li + 1, min(li + 5, len(lines))):
                    ns = lines[ni].strip()
                    if not ns:
                        continue
                    if _is_decorative_line(lines[ni]):
                        continue
                    if _looks_like_numbered_heading_line(ns) and not _looks_like_page_number(ns):
                        if pi not in removals:
                            removals[pi] = set()
                        removals[pi].add(li)
                        removals[pi].add(ni)
                    break
                continue

            # Controling Heading text 
            if _looks_like_heading_text(s):
                # If it is not page number 
                if not _looks_like_page_number(s):
                    # Is there a blank line after that? (Is it isolated?)
                    next_line_empty = True
                    if li + 1 < len(lines) and lines[li + 1].strip():
                        next_line_empty = False
                    # Is the next filled line also heading-like? (multi-line heading)
                    next_also_heading = False
                    for ni in range(li + 1, min(li + 3, len(lines))):
                        if lines[ni].strip():
                            next_also_heading = _looks_like_heading_text(lines[ni].strip())
                            break

                    
                    # If it's the first full line of the page:
                    # the page margin is already a separator,
                    # " _looks_like_heading_text" is already very tight, no additional isolation is needed.

                    is_first_on_page = (found_content == 1)

                    if next_line_empty or next_also_heading or is_first_on_page:
                        if pi not in removals:
                            removals[pi] = set()
                        removals[pi].add(li)

        # Second transition: headings in the middle of the page, bordered on both sides by blank lines.
        # (Headings that escape the first 3 full lines check, but are isolated)

        for li, line in enumerate(lines):
            # Skip if it's already checked
            if pi in removals and li in removals[pi]:
                continue
            s = line.strip()
            if not s:
                continue
            if _looks_like_page_number(s):
                prev_empty = (li == 0 or not lines[li - 1].strip())
                if prev_empty:
                    for ni in range(li + 1, min(li + 5, len(lines))):
                        ns = lines[ni].strip()
                        if not ns:
                            continue
                        if _is_decorative_line(lines[ni]):
                            continue
                        if _looks_like_numbered_heading_line(ns) and not _looks_like_page_number(ns):
                            if pi not in removals:
                                removals[pi] = set()
                            removals[pi].add(li)
                            removals[pi].add(ni)
                        break
                continue
            # Are there blank lines on both sides?
            prev_empty = (li == 0 or not lines[li - 1].strip())
            next_empty = (li + 1 >= len(lines) or not lines[li + 1].strip())
            if prev_empty and next_empty:
                if (
                    (
                        _looks_like_heading_text(s)
                        or _looks_like_centered_title_heading(line)
                    )
                    and not _looks_like_page_number(s)
                ):
                    if pi not in removals:
                        removals[pi] = set()
                    removals[pi].add(li)

    return removals



# DECORATIVE / NOISE LINES


_DECORATIVE_CHARS = set('*-_=~•·.§+#() []')
_PUNCTUATION_ONLY_CHARS = set(' .,;:!?-—–')


def _is_decorative_line(line: str) -> bool:
    """A line of decorative dividers? (***, ---, •••, === e.g)"""
    s = line.strip()
    if not s:
        return False
    # Lines made only of decorative symbols.
    if all(c in _DECORATIVE_CHARS for c in s):
        return True
    # Lines made only of punctuation.
    if all(c in _PUNCTUATION_ONLY_CHARS for c in s):
        return True
    return False


def _is_lone_ocr_artifact(line: str) -> bool:
    """ is single-character OCR noise?

    Single letters/symbols that OCR misreads from the PDF page:
    Lines like 'S', 'A', '·'. Numbers are skipped here as they are also captured as page numbers; 
    Roman numerals are already processed by "detect_chapter_headings".

    Example: 'S' → noise, '7' → page number (skip).
    """
    s = line.strip()
    if len(s) != 1:
        return False
    if s.isdigit():
        return False   # Page numbers are handled separately.
    return True        # Single letter or symbol → OCR noise


def _is_isolated_roman_ocr_artifact(lines: list, line_idx: int) -> bool:
    """Capture isolated OCR remnants, such as the section number `II` being read as `IL`."""
    s = lines[line_idx].strip()
    return _lower_tr(s) in {'il', 'ıl'} and _is_isolated_line(lines, line_idx)



# INLINE CLEANING


def _clean_inline(line: str) -> str:
    """Remove inline non-printable characters and encoding artifacts.

    Preserved: tab (0x09), LF (0x0A), CR (0x0D), and U+00AD soft hyphen.
    Removed:
    - Zero-width characters (U+200B/200C/200D/FEFF)
    - C0 controls (0x00-0x08, 0x0B, 0x0E-0x1F, 0x7F)
    - C1 controls (0x80-0x9F) -- Windows-1252 artifacts
    - Private Use Area (0xE000-0xF8FF) -- Symbol/Wingdings artifacts
    - Form feed (0x0C)
    - U+25A0 (■, FILLED SQUARE) -- OCR dialogue-marker artifact
    - Standalone combining marks (U+0307 dot, U+0327 cedilla)
    Converted:
    - U+2010 (‐, HYPHEN) -> U+002D (-) -- typographic hyphen normalization
    """
    result = []
    for c in line:
        cp = ord(c)
        if cp == 0x00AD:           # soft hyphen: preserve for fix_hyphens
            result.append(c)
            continue
        if cp == 0x2010:           # typographic hyphen → ASCII hyphen
            result.append('-')
            continue
        if cp in (0x200B, 0x200C, 0x200D, 0xFEFF):  # zero-width
            continue
        if cp == 0x0C:             # form feed
            continue
        if cp < 0x09:              # C0: before HT
            continue
        if cp == 0x0B:             # vertical tab
            continue
        if 0x0E <= cp <= 0x1F:     # C0: SO..US
            continue
        if cp == 0x7F:             # DEL
            continue
        if 0x80 <= cp <= 0x9F:     # C1 control / Windows-1252 artifact
            continue
        if cp == 0x0307:           # standalone dot (combining dot above) artifact
            continue
        if cp == 0x0327:           # standalone cedilla (combining cedilla) artifact
            continue
        if cp == 0x25A0:           # ■ FILLED SQUARE -- OCR dialogue artifact
            continue
        if 0xE000 <= cp <= 0xF8FF: # Private Use Area
            continue
        result.append(c)
    return ''.join(result)


def normalize_ocr_glyph_words(text: str) -> tuple[str, int]:
    """Repair common OCR glyph substitutions inside words."""
    replacements = {
        'cne': 'öne',
        'cnc': 'önc',
        'cni': 'öni',
        'saün': 'satın',
        'rlüşündü': 'düşündü',
        'ycrleşmişti': 'yerleşmişti',
        'yangm': 'yangın',
        'ikıyüz': 'iki yüz',
        'yarısmdayken': 'yarısındayken',
        'dakikalannda': 'dakikalarında',
        'arahalann': 'arabaların',
        'bümahallede': 'bu mahallede',
    }
    fixes = 0
    result = []
    current = []

    def flush_word():
        nonlocal fixes
        if not current:
            return
        word = ''.join(current)
        lower = _lower_tr(word)
        replacement = replacements.get(lower)
        if replacement:
            result.append(_match_original_case(word, replacement))
            fixes += 1
        else:
            result.append(word)
        current.clear()

    for c in text:
        if c.isalpha():
            current.append(c)
        else:
            flush_word()
            result.append(c)
    flush_word()

    return ''.join(result), fixes


_TURKISH_LOWER_SET = set('abcçdefgğhıijklmnoöprsştuüvyzâîû')


def fix_hyphens(text: str) -> str:
    """Join line-break hyphenation.

    Algorithm: scan lines. If a line ends with a soft hyphen or hyphen
    and the next line starts with a lowercase letter, join the two lines.
    """
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Is there a next line?
        if i + 1 < len(lines):
            next_line = lines[i + 1].lstrip()
            # First letter of the next line.
            next_first = ''
            for c in next_line:
                if c.isalpha():
                    next_first = c
                    break

            # Does it end with a soft hyphen (\u00ad)?
            if stripped.endswith('\u00ad'):
                # Remove the soft hyphen and join with the next line.
                result.append(stripped.rstrip('\u00ad').rstrip() + next_line)
                i += 2
                continue

            # Does it end with a normal hyphen and is the next line lowercase?
            if stripped and stripped[-1] in '-\u002d':
                # Is the character before the hyphen alphanumeric?
                pre_hyphen = stripped[:-1].rstrip()
                if pre_hyphen and pre_hyphen[-1].isalnum():
                    if next_first and next_first in _TURKISH_LOWER_SET:
                        result.append(pre_hyphen + next_line)
                        i += 2
                        continue

        result.append(line)
        i += 1

    return '\n'.join(result)


# NOTE: remove_footnote_numbers was removed.
# In OCR, 'l' -> '1' and 'ı' -> '1' substitutions are common, so detecting
# footnotes with a letter+digit pattern produced false positives:
#   'attığ1 her adımda' -> 'attığ her adımda' (wrong: 1=ı, should be 'attığı')
#   'maku1 düşünceyi' -> 'maku düşünceyi' (wrong: 1=l, should be 'makul')
# Reliable footnote detection in plain text is not possible without font-size
# or position information (McGill .txtLab, 2014).


_SHORT_WORDS_TO_KEEP = {
    'o', 've', 'de', 'da', 'ki', 'mi', 'mı', 'mu', 'mü', 'ne', 'bu', 'şu',
    'ya', 'ile', 'ama', 'hem', 'pek', 'bir', 'çok', 'az', 'en', 'ben',
    'sen', 'biz', 'siz', 'yi', 'yı', 'yu', 'yü',
    'ak', 'üç', 'uc', 'iki', 'dört', 'dort', 'beş', 'bes', 'altı', 'alti',
    'yedi', 'sekiz', 'dokuz', 'on',
}

_ORDINAL_LEFT_WORDS = {
    'bir', 'iki', 'üç', 'uc', 'dört', 'dort', 'beş', 'bes',
    'altı', 'alti', 'yedi', 'sekiz', 'dokuz', 'on',
}

_KNOWN_SINGLE_LETTER_JOIN_WORDS = {
    'ankara', 'izmir', 'ışık', 'ışığı', 'ön', 'önce', 'önünde', 'önündeki',
    'önüne', 'önlerinden', 'üst', 'üstü', 'üstüme', 'üstüne', 'üstünde',
    'üstünden', 'üstleri', 'üstüste', 'kimi', 'kimler', 'bir', 'biri',
    'birkaç', 'birlik', 'birlikte', 'birer', 'birkesiklik', 'elleri', 'yirmi',
    'rakam', 'rakamlarıyla',
}

# Turkish suffixes that are almost never used as standalone words.
# Only fragments that behave like suffixes are included; forms such as
# 'den', 'siz', and 'ken', which are also common standalone tokens, are
# intentionally EXCLUDED because adding them would cause false joins.
# For broader morphological validation, Zemberek/Zeyrek is recommended.
#
# NOTE: Tuple order matters because str.startswith(tuple) returns on the first match.
# Longer suffixes should come BEFORE shorter ones (for example, 'ların' can also
# match 'lar', but keeping 'ların' explicit makes the intent clearer).
_SUFFIX_LIKE_FRAGMENTS = (
    # Aorist / present progressive
    'yor', 'yordu', 'yormuş', 'mıyor', 'miyor',
    # Question suffix after verbs
    'rmı', 'rmi', 'rmu', 'rmü',
    # Past tense
    'mış', 'miş', 'muş', 'müş',
    'lmış', 'lmiş', 'lmuş', 'lmüş',
    # Future tense
    'acak', 'ecek', 'cek', 'acağı', 'eceği',
    'acağım', 'eceğim', 'acağımız', 'eceğimiz',
    'acağın', 'eceğin', 'acağınız', 'eceğiniz',
    'acağımın', 'eceğimin',
    'ceğim', 'cağım', 'ceğiz', 'cağız',
    'yacak', 'yecek', 'yacağı', 'yeceği',
    # -DIktAn adverbial participle
    'dıktan', 'dikten', 'duktan', 'dükten',
    'tıktan', 'tikten', 'tuktan', 'tükten',
    # Locative-derived -DAkI
    'daki', 'deki', 'taki', 'teki',
    # Plural and plural+case suffixes
    'ların', 'lerin', 'larına', 'lerine', 'larından', 'lerinden',
    'larını', 'lerini', 'larıyla', 'leriyle',
    'lara', 'lere', 'lar', 'ler',
    # -lI possession/quality suffix
    'lığı', 'liği', 'lığın', 'liğin', 'lığını', 'liğini',
    'lık', 'lik', 'luk', 'lük',
    'lı', 'li', 'lu', 'lü',
    # -lI + locative/copular fragments: "canlılı ktad ır" -> "canlılıktadır"
    'ktad', 'kted',
    # Ordinal-number fragments: "Iki nci", "üç üncü"
    'ncı', 'nci', 'ncu', 'ncü',
    # Profession/adjective derivational suffix: "ara cı" -> "aracı"
    'cı', 'ci', 'cu', 'cü',
    # Safe root fragments: "siga raya", "tep side", "ra kam"
    'raya', 'reye', 'side', 'kam', 'sim',
    'tında', 'tinde', 'tından', 'tinden',
    'tlarla', 'tlerle',
    # High-confidence joined fragments such as "teşek kür"
    'kür',
    # -mAsI / -mEsI verbal noun fragments; never standalone words
    'ması', 'mesi', 'masını', 'mesini', 'masına', 'mesine',
    'maya', 'meye', 'mayı', 'meyi', 'madan', 'meden',
    'madım', 'medim', 'madın', 'medin', 'mamış', 'memiş',
    'mesen', 'irmek',
    'yarak', 'yerek',
    'suzluğu', 'süzlüğü', 'suzluğunu', 'süzlüğünü',
    'suzluk', 'süzlük',
    # -mA + possessive/case/instrumental fragments
    'sıyla', 'siyle', 'suyla', 'süyle',
    'uyla', 'üyle',
    # -lAnArAk reflexive/passive verb fragment: "kul lanarak"
    'lanarak', 'lenerek',
    'lanması', 'lenmesi', 'lanmasını', 'lenmesini', 'lanmasına', 'lenmesine',
    'lanır', 'lenir', 'lanıyor', 'leniyor',
    'lanımı', 'lenimi', 'lanımını', 'lenimini', 'lanımına', 'lenimine',
    # -ArAk / -ErEk adverbial participle; never a standalone word
    'arak', 'erek',
    # Ablative -ndAn; excludes standalone 'dan/den', but 'ndan/nden' are not standalone
    'ndan', 'nden',
    # Locative -ndA; not standalone
    'nda', 'nde',
    # Possessive + case suffixes; not standalone
    'sında', 'sinde', 'sından', 'sinden',
    'sına', 'sine', 'sını', 'sini',
    'sının', 'sinin',
    'mızın', 'mizin', 'muzun', 'müzün',
    # Genitive (-nIn). Short forms like 'nin' can appear independently,
    # but after a 4+ letter left fragment they are almost always suffixes.
    'ının', 'inin', 'unun', 'ünün',
    'nın', 'nin', 'nun', 'nün',
    'nlar', 'nler',
    # -DA case suffix; excludes standalone 'da/de', but 'ında/inde' are not standalone
    'ında', 'inde', 'unda', 'ünde',
    # Participial / adverbial suffixes
    'dığı', 'diği', 'duğu', 'düğü',
    'dığını', 'diğini', 'duğunu', 'düğünü',
    'tığı', 'tiği', 'tuğu', 'tüğü',
    # OCR sometimes leaves soft-g on the right fragment: "olmadı ğını"
    'ğını', 'ğini', 'ğunu', 'ğünü',
    # Mid-suffix fragments: OCR can attach the plural suffix to the root and split the rest.
    # "toplumla rının" = "toplumlARININ" split as "toplumla" + "rının"
    # These fragments are never used as standalone words.
    'rının', 'rinin', 'runun', 'rünün',     # plural+possessive+genitive
    'rında', 'rinde', 'runda', 'ründe',     # plural+possessive+locative
    'rından', 'rinden',                     # plural+possessive+ablative
    'rına', 'rine', 'runa', 'rüne',         # plural+possessive+dative
    'rını', 'rini', 'runu', 'rünü',         # plural+possessive+accusative
    'rıyla', 'riyle',                       # plural+possessive+instrumental
)

_SHORT_PAST_FRAGMENTS = {'dı', 'di', 'du', 'dü', 'tı', 'ti', 'tu', 'tü'}
_POSSESSIVE_CASE_FRAGMENTS = {
    'ını', 'ini', 'unu', 'ünü',
    'nı', 'ni', 'nu', 'nü',
}

_NUMBER_WORD_PREFIXES = {
    'bir', 'iki', 'üç', 'uc', 'dört', 'dort', 'beş', 'bes', 'altı', 'alti',
    'yedi', 'sekiz', 'dokuz', 'on', 'onbir', 'oniki', 'onüç', 'onuc',
}


_KNOWN_JOINED_WORDS = {
    'hiçbir', 'birkaç', 'birçok', 'biraz', 'birazdan', 'birden', 'birdenbire', 'birtakım',
    'biricik', 'anlamadım', 'ucuyla', 'eniştemiz',
    'nişantaşı',
    'altında', 'altındaki', 'altından', 'altına', 'altındadır',
    'biri', 'biriyle', 'birine', 'birini', 'birinin', 'birinde', 'birinden',
    'birbiri', 'birbiriyle', 'birbirine', 'birbirini', 'birbirinin',
    'birinci', 'birincisi', 'ikinci', 'ikincisi', 'üçüncü', 'üçüncüsü',
    'dördüncü', 'dördüncüsü', 'beşinci', 'beşincisi', 'altıncı', 'altıncısı',
    'yedinci', 'yedincisi', 'sekizinci', 'sekizincisi', 'dokuzuncu',
    'dokuzuncusu', 'onuncu', 'onuncusu',
}

_NO_JOIN_AFTER_SHORT_PHRASES = {
    ('iş', 'güç'),
    ('bir', 'an'),
    ('her', 'şey'),
    ('her', 'şeyi'),
    ('göz', 'ucu'),
    ('vız', 'gelir'),
}

_NO_JOIN_RIGHT_AFTER_PREVIOUS = {
    ('bir', 'an'): {
        'durdu', 'bakıştılar', 'sessizlikten', 'sessizlik', 'önce'
    },
}

_NO_JOIN_RIGHT_BEFORE_NEXT = {
    ('araba', 'da'): {'satın'},
}

# Compound-word fragments that OCR tends to split consistently.
# Left fragment (prefix) + beginning of right fragment (suffix_start) -> join.
# These are not book-specific; they are standard Turkish compound/derived words.
# They are not valid as independent left+right phrases in this usage.
_COMPOUND_WORD_PREFIXES = {
    # Hristiyan and derivatives: 'Hris' is not a standalone word
    'hris': ('tiyan',),
    # İlişki and derivatives: 'iliş' is not a standalone word
    'iliş': ('ki',),
    # Medeniyet: 'mede' is rare as a standalone word and belongs to another context
    'mede': ('niyet',),
    'medeni': ('yet',),
    # Anayurt-related OCR splits; these left fragments are not standalone in this sense
    'teşek': ('kür',),
    'siga': ('ra',),
    'tep': ('si',),
    're': ('sim',),
    'fır': ('ladı',),
    'gel': ('mesen',),
    'anlam': ('adım',),
    'kur': ('tarır',),
    'malum': ('at',),
    'eniş': ('temiz',),
    'kere': ('vet',),
    'çerçe': ('ve',),
    'tabi': ('at',),
    'kav': ('rul',),
    'zikza': ('k',),
    # Coğrafya: 'coğraf' is not a standalone word
    'coğraf': ('ya',),
    # Yahudi and derivatives: 'Yahu' can be an interjection, but "Yahu diler" is an OCR split
    'yahu': ('di',),
    # Rasyonel/radikal OCR splitleri
    'ra': ('syon', 'dikal', 'kam'),
    'rakam': ('lar',),
    # Abdül- names: 'Abdül' is not used alone
    'abdül': ('hamid', 'aziz', 'mecid', 'kadir', 'rahman', 'kerim', 'hamit'),
    # -istan place names: 'istan' is not a standalone word
    'yunan': ('istan',),
    'hind': ('istan',),
    'macar': ('istan',),
    'gürc': ('istan',),
    'gürcü': ('stan',),
    'bulgar': ('istan',),
    'ermenistan': (),  # already joined
}


def _lower_tr(text: str) -> str:
    """More stable lowercase conversion for Turkish İ/ı."""
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def _iter_alpha_words(text: str):
    """Yield alphabetic words from the text in order."""
    current = []
    for c in text:
        if c.isalpha():
            current.append(c)
        else:
            if current:
                yield ''.join(current)
                current = []
    if current:
        yield ''.join(current)


def _word_before(text: str, space_idx: int) -> str:
    """Return the contiguous alphabetic fragment before space_idx."""
    i = space_idx - 1
    chars = []
    while i >= 0 and text[i].isalpha():
        chars.append(text[i])
        i -= 1
    chars.reverse()
    return ''.join(chars)


def _word_after(text: str, space_idx: int) -> str:
    """Return the contiguous alphabetic fragment after space_idx."""
    i = space_idx + 1
    chars = []
    while i < len(text) and text[i].isalpha():
        chars.append(text[i])
        i += 1
    return ''.join(chars)


def _previous_word_before(text: str, word_start_idx: int) -> str:
    """Return the previous alphabetic word before word_start_idx."""
    i = word_start_idx - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    chars = []
    while i >= 0 and text[i].isalpha():
        chars.append(text[i])
        i -= 1
    chars.reverse()
    return ''.join(chars)


def _next_word_after(text: str, word_end_idx: int) -> str:
    """Return the next alphabetic word after word_end_idx."""
    i = word_end_idx
    while i < len(text) and text[i].isspace():
        i += 1
    chars = []
    while i < len(text) and text[i].isalpha():
        chars.append(text[i])
        i += 1
    return ''.join(chars)


def _is_apostrophe_suffix_left(text: str, word_start_idx: int) -> bool:
    """Avoid joining the next word when the left part is a post-apostrophe suffix."""
    if word_start_idx <= 0:
        return False
    return text[word_start_idx - 1] in {"'", "’", "‘"}


def _should_keep_space(left: str, right: str, prev_word: str, next_word: str = '') -> bool:
    """Keep the space in known valid short phrases."""
    left_l = _lower_tr(left)
    right_l = _lower_tr(right)
    prev_l = _lower_tr(prev_word)
    next_l = _lower_tr(next_word)

    if (left_l, right_l) in _NO_JOIN_AFTER_SHORT_PHRASES:
        return True

    blocked = _NO_JOIN_RIGHT_AFTER_PREVIOUS.get((prev_l, left_l))
    if blocked and right_l in blocked:
        return True

    blocked_next = _NO_JOIN_RIGHT_BEFORE_NEXT.get((left_l, right_l))
    if blocked_next and next_l in blocked_next:
        return True

    if right_l.startswith('dakika'):
        return True

    return False


def _looks_like_intraword_split(left: str, right: str, vocabulary: set) -> bool:
    """Does the pair of word fragments look like it actually belongs to one word?"""
    if not left or not right:
        return False
    if not right[0].islower():
        return False

    left_l = _lower_tr(left)
    right_l = _lower_tr(right)
    combined_l = _lower_tr(left + right)

    if len(left_l) == 1 and left[0].isupper() and combined_l in _KNOWN_SINGLE_LETTER_JOIN_WORDS:
        return True

    if len(left_l) == 1 and left[0].isupper() and left_l not in {'i', 'ı'}:
        return False

    if left_l == 'bir' and right_l == 'kesiklik':
        return True

    if left_l == 'bir' and right_l == 'azdan':
        return True

    if left_l in _ORDINAL_LEFT_WORDS and right_l in {'inci', 'incisi'}:
        return True

    if (
        len(left_l) >= 4
        and left_l.endswith(('la', 'le'))
        and (
            right_l in {'ra', 're'}
            or (len(right_l) > 4 and right_l[:2] in {'ra', 're'})
        )
    ):
        return True

    if right_l == 'ne' and left_l.endswith(('ları', 'leri')):
        return True

    if combined_l in vocabulary and left_l not in _SHORT_WORDS_TO_KEEP:
        return True

    # Known compound-word fragments (Hris+tiyan, Yunan+istan, Abdül+hamid...)
    if left_l in _COMPOUND_WORD_PREFIXES:
        suffixes = _COMPOUND_WORD_PREFIXES[left_l]
        if any(right_l.startswith(s) for s in suffixes):
            return True

    if left_l.endswith('iy') and right_l.startswith('le') and len(right_l) > 2:
        return True

    if left_l == 'ses' and right_l.startswith('siz'):
        return True

    if len(left_l) == 1:
        return left_l not in {'o'}

    if right_l in _POSSESSIVE_CASE_FRAGMENTS:
        return len(left_l) >= 4

    if right_l.startswith(_SUFFIX_LIKE_FRAGMENTS):
        # Turkish root words can be long (Müslüman=8, Hristiyan=9,
        # medeniyetsizleştirmek=21). Use only a lower bound instead of
        # imposing an upper bound; one-letter left fragments are handled above.
        return len(left_l) >= 2

    if right_l in {'ır', 'ir'} and left_l.endswith(('tad', 'ted')):
        return True

    if right_l == 'cek' and left_l.endswith('e') and len(left_l) >= 4:
        return True

    if right_l.startswith(('aki', 'eki')) and left_l.endswith(('d', 't')):
        return True

    if left_l == 'ucu' and right_l.startswith('nuo'):
        return True

    if right_l.startswith(('ğıismi', 'ğiismi', 'ğuisim', 'ğüisim')):
        return True

    if right_l in _SHORT_PAST_FRAGMENTS:
        return 2 <= len(left_l) <= 4

    if left_l in {'cı', 'ci', 'cu', 'cü'}:
        return False

    if len(left_l) == 2 and left_l not in _SHORT_WORDS_TO_KEEP and len(right_l) >= 3:
        return True

    return False


def repair_intraword_spaces(text: str) -> tuple[str, int]:
    """Repair intraword spaces caused by PDF extraction.

    Examples:
    "d iyormuş" -> "diyormuş"
    "k adın" -> "kadın"
    "d izine" -> "dizine"

    Uses alphabetic fragments and within-book word frequency instead of regex.
    """
    word_counts = Counter(_lower_tr(w) for w in _iter_alpha_words(text) if len(w) >= 4)
    vocabulary = {word for word, count in word_counts.items() if count >= 1}

    result = []
    repairs = 0
    i = 0
    while i < len(text):
        if text[i] == ' ':
            previous_is_alpha = i > 0 and text[i - 1].isalpha()
            next_is_alpha = i + 1 < len(text) and text[i + 1].isalpha()
            single_space = (
                previous_is_alpha
                and next_is_alpha
                and (i + 1 >= len(text) or text[i + 1] != ' ')
                and (i - 1 < 0 or text[i - 1] != ' ')
            )
            if single_space:
                left = _word_before(text, i)
                right = _word_after(text, i)
                left_start = i - len(left)
                right_end = i + 1 + len(right)
                prev_word = _previous_word_before(text, left_start)
                next_word = _next_word_after(text, right_end)
                if _is_apostrophe_suffix_left(text, left_start):
                    result.append(text[i])
                    i += 1
                    continue
                if _should_keep_space(left, right, prev_word, next_word):
                    result.append(text[i])
                    i += 1
                    continue
                if (
                    len(prev_word) == 1
                    and prev_word.isupper()
                    and len(left) == 1
                    and left.islower()
                ):
                    result.append(text[i])
                    i += 1
                    continue
                if _looks_like_intraword_split(left, right, vocabulary):
                    repairs += 1
                    i += 1
                    continue

        result.append(text[i])
        i += 1

    return ''.join(result), repairs


def normalize_ocr_noise(text: str) -> tuple[str, int]:
    """Algorithmically normalize common OCR character noise.

    No regex is used. There are no book-specific fixed rules.

    Handled cases:

    1. Replacement character (U+FFFD '�') -> removed
    2. Middle dot (·) between letters -> removed and letters are joined
       'An·kara' -> 'Ankara'
    3. Middle dot (·) between a letter and a space -> removed
       'An· kara' -> 'An kara'   (repair_intraword_spaces closes this gap)
    4. Angle brackets < > between letters -> removed
       'Di<b' -> 'Dib'  (OCR page-edge artifact)
    5. Slash (/):
       a. letter + '/' + uppercase letter -> word boundary (space)
          'Gecikme/Ankara'  -> 'Gecikme Ankara'
       b. letter + '/' + lowercase + uppercase -> slash + bridge letter removed, space added
          'Gecikme/iAnkara' -> 'Gecikme Ankara'
       c. letter + '/' + lowercase letter -> OCR reading for 'l' (or 'ı')
          'e/ektrik'        -> 'elektrik'
 
    Not safely repairable without a book-specific dictionary:
    - 'Enıekli' -> 'Emekli'   (character-level OCR substitution; needs a dictionary)
    - 'Di<! çöküp'            (multi-layer noise; needs context)
    """
    fixes = 0

    # ── Stage 1: Simple character replacements ──
    if '\\ufffd' in text or '�' in text:
        count = text.count('�')
        text = text.replace('�', '')
        fixes += count

    # ── Stage 2: Character-level scan (while loop allows skipping characters) ──
    out = []
    j = 0
    n = len(text)

    while j < n:
        c = text[j]

        if c in {'I', 'l'}:
            next_chunk = text[j:j + 3]
            if next_chunk in {'Işı', 'lşı'}:
                out.append('I' if c == 'I' else 'ı')
                fixes += 1
                j += 1
                continue

        # ── Middle dot (· U+00B7) ──
        if c == '·':
            prev_alpha = j > 0 and text[j - 1].isalpha()
            next_alpha = j + 1 < n and text[j + 1].isalpha()
            # Whitespace: ASCII space, newline, or tab (can also follow line-break hyphenation)
            next_space = j + 1 < n and text[j + 1] in (' ', '\n', '\t')
            next_end   = (j + 1 >= n)

            if prev_alpha and next_alpha:
                # Letter·letter -> join the two letters and remove the dot.
                fixes += 1
                j += 1
                continue
            elif prev_alpha and (next_space or next_end):
                # Letter·space/newline/end -> remove the dot.
                # ('An· kara' -> 'An kara'; 'ka·\npıyı' -> 'ka\npıyı')
                fixes += 1
                j += 1
                continue
            elif prev_alpha:
                # Letter·punctuation -> OCR noise; remove the dot.
                # 'sö·:erek' -> 'sö:erek'; 'almıştım·.' -> 'almıştım.'
                fixes += 1
                j += 1
                continue
            elif not prev_alpha and next_alpha:
                # Word-start middle-dot noise: after space/hyphen and before a letter.
                # '- ·nlamadın' -> '- nlamadın'  (first letter is lost; unrecoverable)
                # '·çengel bir' -> 'çengel bir'  (separator artifact; remove)
                fixes += 1
                j += 1
                continue
            else:
                # Fully isolated noise (space·space, ·-, etc.) -> remove.
                fixes += 1
                j += 1
                continue

        # ── Angle brackets < and > ──
        elif c in '<>':
            prev_alpha = j > 0 and text[j - 1].isalpha()
            next_alpha = j + 1 < n and text[j + 1].isalpha()
            # Noise char after a letter and before another noise char (for example, < followed by !).
            next_is_noise = (j + 1 < n and
                             not text[j + 1].isalnum() and
                             text[j + 1] not in ' \n\t\r')
            if prev_alpha and (next_alpha or next_is_noise):
                # 'Di<b' or 'Di<!' -> remove '<'.
                fixes += 1
                j += 1
                continue

        # ── Slash (/) ──
        elif c == '/':
            prev_alpha = j > 0 and text[j - 1].isalpha()
            next_alpha = j + 1 < n and text[j + 1].isalpha()

            if prev_alpha and next_alpha:
                next_c = text[j + 1]

                # Case a: letter + '/' + uppercase → space + uppercase
                if next_c.isupper():
                    out.append(' ')
                    j += 1          # skip '/', uppercase letter will be added normally
                    fixes += 1
                    continue

                # Case b: letter + '/' + lowercase + uppercase → space (bridge skipped)
                elif (next_c.islower() and
                      j + 2 < n and text[j + 2].isupper()):
                    out.append(' ')
                    j += 2          # skip '/' and the bridge letter
                    fixes += 1
                    continue

                # Case c: letter + '/' + lowercase → OCR 'l' substitution
                else:
                    out.append('l')
                    j += 1
                    fixes += 1
                    continue

        out.append(c)
        j += 1

    return ''.join(out), fixes


def _normalize_paragraph_text(paragraph: str) -> str:
    """Collapse extra spaces inside a paragraph to a single space."""
    return ' '.join(paragraph.split())


def _repair_initial_dropcap(paragraph: str) -> tuple[str, int]:
    """Repair paragraph-initial drop-cap splits: 'B u kitap' -> 'Bu kitap'."""
    if not paragraph:
        return paragraph, 0

    words = paragraph.split()
    if len(words) < 3:
        return paragraph, 0

    quote_chars = '"\'“”‘’'
    first = words[0].strip(quote_chars)
    second = words[1].strip(quote_chars)
    third = words[2].strip(quote_chars)

    if (
        len(first) == 1
        and first.isalpha()
        and first.isupper()
        and len(second) == 1
        and second.isalpha()
        and second.islower()
        and len(third) >= 3
        and third[0].islower()
    ):
        words[0] = words[0].replace(first, first + second, 1)
        del words[1]
        return ' '.join(words), 1

    return paragraph, 0


def _repair_known_single_letter_splits(text: str) -> tuple[str, int]:
    """Repair remaining safe single-letter splits inside text."""
    words = text.split()
    if len(words) < 2:
        return text, 0

    repaired = []
    fixes = 0
    i = 0
    while i < len(words):
        if i + 1 < len(words):
            left = words[i].strip('"\'“”‘’')
            right = words[i + 1].strip('"\'“”‘’.,;:!?')
            combined_l = _lower_tr(left + right)
            if (
                len(left) == 1
                and left.isalpha()
                and left.isupper()
                and right
                and right[0].islower()
                and combined_l in _KNOWN_SINGLE_LETTER_JOIN_WORDS
            ):
                repaired.append(words[i] + words[i + 1])
                fixes += 1
                i += 2
                continue

        repaired.append(words[i])
        i += 1

    return ' '.join(repaired), fixes


def repair_apostrophe_spacing(text: str) -> tuple[str, int]:
    """Remove spaces that slipped between an apostrophe and its suffix.

    Example:
    `Boğaz' ınseyrine` -> `Boğaz'ınseyrine`
    The later split stage turns this into `Boğaz'ın seyrine`.
    """
    out = []
    fixes = 0
    i = 0
    n = len(text)
    apostrophes = {"'", "’", "‘"}
    suffix_starts = {
        'a', 'e', 'ı', 'i', 'u', 'ü',
        'l', 'n', 'y', 'd', 't',
    }

    while i < n:
        c = text[i]
        out.append(c)
        if c in apostrophes and i > 0 and text[i - 1].isalpha():
            j = i + 1
            spaces = 0
            while j < n and text[j] == ' ':
                spaces += 1
                j += 1
            if spaces and j < n and _lower_tr(text[j]) in suffix_starts:
                fixes += spaces
                i = j
                continue
        i += 1

    return ''.join(out), fixes


def _match_original_case(original: str, replacement: str) -> str:
    """Preserve simple capitalization for a repaired word fragment."""
    if not original:
        return replacement
    if original[0].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _split_glued_alpha_word(
    word: str,
    vocabulary: set = None,
    previous_char: str = '',
) -> tuple:
    """Split alphabetic words glued together because of missing spaces.

    There are no book-specific fixed rules. The approach has three layers:

    A) Vocabulary-based split (primary, generalizable):
       At each possible split point, if both the left and right pieces are
       present in the book's own vocabulary (frequency >= 2), split.
       'emeklisubay' -> ('emekli' in vocab) + ('subay' in vocab) -> 'emekli subay'

    B) Post-apostrophe suffixes:
       Structural Turkish suffix patterns after apostrophes.

    C) Number-word prefixes (_NUMBER_WORD_PREFIXES):
       'üçgün' -> 'üç gün', while valid words such as 'ikinci' are preserved.
    """
    lower = _lower_tr(word)
    exact_splits = {
        'bümahallede': 'bu mahallede',
    }
    if lower in exact_splits:
        return _match_original_case(word, exact_splits[lower]), 1

    glued_prefix_splits = (
        ('herşeyi', 'her', 'şeyi'),
        ('herşeye', 'her', 'şeye'),
        ('herşeyden', 'her', 'şeyden'),
        ('herşeyde', 'her', 'şeyde'),
        ('herşeyin', 'her', 'şeyin'),
        ('herşeyim', 'her', 'şeyim'),
        ('herşey', 'her', 'şey'),
        ('işdeğiş', 'iş', 'değiş'),
        ('işyokmuş', 'iş', 'yokmuş'),
        ('işyok', 'iş', 'yok'),
        ('işde', 'iş', 'de'),
        ('vızgelir', 'vız', 'gelir'),
        ('önodalarında', 'ön', 'odalarında'),
        ('gidipgelirken', 'gidip', 'gelirken'),
        ('kocamanküreklerinin', 'kocaman', 'küreklerinin'),
        ('sudeğirmeni', 'su', 'değirmeni'),
        ('teolduğu', 'te', 'olduğu'),
        ('ınseyrine', 'ın', 'seyrine'),
        ('zikzakvapurlar', 'zikzak', 'vapurlar'),
        ('eşbulunduğu', 'eş', 'bulunduğu'),
        ('istanbulmedeniyetinden', 'istanbul', 'medeniyetinden'),
        ('yapmakkülfetinden', 'yapmak', 'külfetinden'),
        ('daharekabet', 'daha', 'rekabet'),
        ('tanrutubetten', 'tan', 'rutubetten'),
        ('arkasındandolaşmak', 'arkasından', 'dolaşmak'),
        ('ipatar', 'ip', 'atar'),
        ('ucunomuzuna', 'ucunu', 'omuzuna'),
        ('ucunuomuzuna', 'ucunu', 'omuzuna'),
        ('kaplıkürkü', 'kaplı', 'kürkü'),
        ('delüzum', 'de', 'lüzum'),
        ('onunda', 'onun', 'da'),
        ('ankör', 'an', 'kör'),
        ('sözlerinlüzum', 'sözlerin', 'lüzum'),
        ('söylememeklüzumunu', 'söylememek', 'lüzumunu'),
        ('bucümlenin', 'bu', 'cümlenin'),
        ('vecümleler', 've', 'cümleler'),
        ('yanalüzumsuz', 'yana', 'lüzumsuz'),
        ('aniçinde', 'an', 'içinde'),
        ('bütünsınıf', 'bütün', 'sınıf'),
        ('dizboyu', 'diz', 'boyu'),
        ('pantolonlaceketi', 'pantolonla', 'ceketi'),
        ('evişlerini', 'ev', 'işlerini'),
        ('evişleri', 'ev', 'işleri'),
        ('ankeyfi', 'an', 'keyfi'),
        ('ahseni', 'ah', 'seni'),
        ('vedüğün', 've', 'düğün'),
        ('ayönce', 'ay', 'önce'),
        ('evsatın', 'ev', 'satın'),
        ('ayertelerim', 'ay', 'ertelerim'),
        ('albakayım', 'al', 'bakayım'),
        ('vesinirli', 've', 'sinirli'),
        ('yalıncümlelerle', 'yalın', 'cümlelerle'),
        ('bucızırtı', 'bu', 'cızırtı'),
        ('meydanıcıvılcıvıldı', 'meydanı', 'cıvılcıvıldı'),
        ('kadarsinirlisin', 'kadar', 'sinirlisin'),
    )
    for prefix, left, right in glued_prefix_splits:
        if lower.startswith(prefix):
            left_part = word[:len(left)]
            rest = word[len(prefix):]
            return left_part + ' ' + right + rest, 1

    if len(lower) < 5 and previous_char not in {''', ''', "'"}:
        return word, 0
    if lower in _KNOWN_JOINED_WORDS:
        return word, 0

    if lower.startswith('bukitap') and len(lower) > 5:
        return _match_original_case(word[:2], 'bu') + ' ' + word[2:], 1

    if len(lower) >= 10:
        for split_pos in range(6, len(lower) - 3):
            left_l = lower[:split_pos]
            right_l = lower[split_pos:]
            if left_l.endswith(('nın', 'nin', 'nun', 'nün')) and right_l.startswith('sınır'):
                return word[:split_pos] + ' ' + word[split_pos:], 1
            if (
                vocabulary
                and
                left_l.endswith(('lara', 'lere'))
                and (right_l in vocabulary or right_l.endswith(('mak', 'mek')))
            ):
                return word[:split_pos] + ' ' + word[split_pos:], 1

    for suffix in ('kadar', 'gibi'):
        if lower.endswith(suffix) and len(lower) > len(suffix) + 5:
            before = lower[:-len(suffix)]
            if before.endswith(('acak', 'ecek', 'yacak', 'yecek', 'dığı', 'diği')):
                split_pos = len(word) - len(suffix)
                return word[:split_pos] + ' ' + word[split_pos:], 1

    if lower.endswith('ismi') and lower[:-4].endswith(('dığı', 'diği', 'duğu', 'düğü')):
        return word[:-4] + ' ' + word[-4:], 1

    # ── A) Vocabulary-based split ──
    # At every position: are both left and right pieces in the vocabulary?
    # Choose the shortest valid left piece (greedy-left).
    #
    # IMPORTANT: Do not split if the right piece looks like a Turkish suffix.
    # OCR creates splits such as "Müslüman ların"; "ların" can enter the
    # vocabulary, repair joins it, and split can separate it again. Checking
    # whether the right piece is suffix-like breaks this loop.
    if vocabulary and len(lower) >= 6:
        for split_pos in range(3, len(lower) - 2):
            left_l  = lower[:split_pos]
            right_l = lower[split_pos:]
            if (left_l in vocabulary and
                    right_l in vocabulary and
                    right_l[0].islower() and          # right piece starts lowercase
                    left_l not in _SHORT_WORDS_TO_KEEP):  # left piece is a meaningful word
                # If the right piece starts with a Turkish suffix pattern, do not split.
                if right_l.startswith(_SUFFIX_LIKE_FRAGMENTS):
                    continue
                # If the right piece is a possessive/case fragment, do not split.
                if right_l in _POSSESSIVE_CASE_FRAGMENTS:
                    continue
                # If this is a known compound-word fragment, do not split.
                if left_l in _COMPOUND_WORD_PREFIXES:
                    cpx = _COMPOUND_WORD_PREFIXES[left_l]
                    if any(right_l.startswith(s) for s in cpx):
                        continue
                return word[:split_pos] + ' ' + word[split_pos:], 1

    # OCR can produce splits such as "zamanla rayoğunlaşmak": left part
    # "zamanla", right part "rayoğunlaşmak". Split the "ra/re" bridge on
    # its own to produce "zamanlara yoğunlaşmak".
    if lower.startswith(('ra', 're')) and len(lower) > 5 and previous_char == ' ':
        rest = word[2:]
        rest_l = lower[2:]
        if rest and rest[0].islower() and (rest_l in vocabulary or rest_l.endswith(('mak', 'mek'))):
            return word[:2] + ' ' + rest, 1

    # ── B) Post-apostrophe suffixes ──
    if previous_char in {''', ''', "'"}:
        for suffix in ('daki', 'deki', 'taki', 'teki',
                       'nin', 'nın', 'nun', 'nün',
                       'in', 'ın', 'un', 'ün',
                       'le', 'la', 'ye', 'ya', 'e', 'a',
                       'ı', 'i', 'u', 'ü'):
            if lower.startswith(suffix) and len(lower) > len(suffix) + 1:
                rest = word[len(suffix):]
                if rest and rest[0].islower():
                    return word[:len(suffix)] + ' ' + rest, 1

    # ── C) Number-word prefixes ──
    for prefix in sorted(_NUMBER_WORD_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix) and len(lower) > len(prefix) + 2:
            rest = word[len(prefix):]
            if rest and rest[0].islower():
                left = _match_original_case(word[:len(prefix)], prefix)
                return left + ' ' + rest, 1

    return word, 0


def split_glued_words(text: str, vocabulary: set = None) -> tuple:
    """Split glued words with a vocabulary-based algorithmic approach."""
    result = []
    current = []
    splits = 0

    for c in text:
        if c.isalpha():
            current.append(c)
        else:
            if current:
                previous_char = result[-1] if result else ''
                if previous_char in {"'", "’", "‘"}:
                    before_previous = result[-2] if len(result) >= 2 else ''
                    if not before_previous.isalpha():
                        previous_char = ''
                fixed, count = _split_glued_alpha_word(
                    ''.join(current), vocabulary, previous_char
                )
                result.append(fixed)
                splits += count
                current = []
            result.append(c)

    if current:
        previous_char = result[-1] if result else ''
        if previous_char in {"'", "’", "‘"}:
            before_previous = result[-2] if len(result) >= 2 else ''
            if not before_previous.isalpha():
                previous_char = ''
        fixed, count = _split_glued_alpha_word(
            ''.join(current), vocabulary, previous_char
        )
        result.append(fixed)
        splits += count

    return ''.join(result), splits


def _wrap_paragraphs(paragraphs: list, width: int = 100) -> str:
    """Wrap the CLEAN text into readable lines; the content remains one text string."""
    wrapped = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        wrapped.append(textwrap.fill(
            paragraph,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        ))
    return '\n\n'.join(wrapped).strip()


# MAIN CLEANING FUNCTION


def clean_raw_text(raw_text: str) -> tuple:
    """
    Clean raw text.

    Expectation: front/back matter has already been manually removed.

    Pipeline:
    1. Split into pages by \\f
    2. Page-Association -> repeated header/footer detection
    3. Page-number detection
    4. Chapter-heading detection
    5. Decorative-line removal + page merge
    6. Hyphen repair
    7. OCR character-noise normalization
    8. Intraword-space repair
    9. Paragraph construction + glued-word splitting

    Returns: (clean_text, stats_dict)
    """
    stats = {
        'total_pages': 0,
        'repeated_lines_removed': 0,
        'page_numbers_removed': 0,
        'chapter_headings_removed': 0,
        'decorative_lines_removed': 0,
        'footnote_lines_removed': 0,
        'intraword_spaces_repaired': 0,
        'ocr_noise_normalized': 0,
    }

    # ── Step 1: Split into pages ──
    pages = raw_text.split('\f')
    stats['total_pages'] = len(pages)

    # ── Step 2: Page-Association ──
    repeated_removals = detect_repeated_lines_by_page(pages)

    # ── Step 3: Page numbers ──
    page_num_removals = detect_page_numbers(pages)

    # ── Step 4: Chapter headings ──
    heading_removals = detect_chapter_headings(pages)

    # ── Step 4b: Footnote detection ──
    footnote_removals = detect_footnotes(pages)

    # ── Step 5: Line removal + inline cleaning ──
    cleaned_lines = []

    for pi, page in enumerate(pages):
        lines = page.split('\n')

        remove_set = set()
        if pi in repeated_removals:
            remove_set |= repeated_removals[pi]
            stats['repeated_lines_removed'] += len(repeated_removals[pi])
        if pi in page_num_removals:
            remove_set |= page_num_removals[pi]
            stats['page_numbers_removed'] += len(page_num_removals[pi])
        if pi in heading_removals:
            # Count only headings that do not overlap with repeated/page-number removals.
            new_headings = heading_removals[pi] - remove_set
            remove_set |= heading_removals[pi]
            stats['chapter_headings_removed'] += len(new_headings)
        if pi in footnote_removals:
            new_footnotes = footnote_removals[pi] - remove_set
            remove_set |= footnote_removals[pi]
            stats['footnote_lines_removed'] += len(new_footnotes)

        for li, line in enumerate(lines):
            if li in remove_set:
                continue

            if (
                _looks_like_bracketed_page_number_artifact(line)
                and _is_isolated_line(lines, li)
            ):
                stats['page_numbers_removed'] += 1
                continue

            if _is_isolated_roman_ocr_artifact(lines, li):
                stats['chapter_headings_removed'] += 1
                continue

            if _is_decorative_line(line) or _is_lone_ocr_artifact(line):
                stats['decorative_lines_removed'] += 1
                continue

            line = _clean_inline(line)
            cleaned_lines.append(line)

    # ── Step 6: Merge pages ──
    text = '\n'.join(cleaned_lines)

    # ── Step 7: Hyphen repair ──
    text = fix_hyphens(text)

    # ── Step 8: OCR character noise ──
    text, ocr_fixes = normalize_ocr_noise(text)
    text, glyph_fixes = normalize_ocr_glyph_words(text)
    stats['ocr_noise_normalized'] = ocr_fixes + glyph_fixes

    # ── Step 9: Intraword spaces caused by PDF extraction ──
    text, intraword_repairs = repair_intraword_spaces(text)
    text = text.replace('\u00ad', '')
    stats['intraword_spaces_repaired'] = intraword_repairs

    # ── Step 10: Normalize ──
    # Reduce excessive blank lines (4+ consecutive newlines -> 3 newlines).
    lines_raw = text.split('\n')
    collapsed = []
    empty_count = 0
    for line in lines_raw:
        if line.strip():
            collapsed.append(line)
            empty_count = 0
        else:
            empty_count += 1
            if empty_count <= 2:
                collapsed.append(line)
    text = '\n'.join(collapsed)

    # Join lines into paragraphs.
    lines_final = text.split('\n')
    paragraphs = []
    current_para = []

    for line in lines_final:
        s = line.strip()
        if s:
            current_para.append(s)
        else:
            if current_para:
                paragraphs.append(' '.join(current_para))
                current_para = []
    if current_para:
        paragraphs.append(' '.join(current_para))

    # Build the vocabulary once from the whole text.
    # split_glued_words uses this vocabulary as a book-local reference and can
    # automatically split glued words such as 'emeklisubay'.
    word_counts = Counter(
        _lower_tr(w) for w in _iter_alpha_words(text) if len(w) >= 4
    )
    shared_vocabulary = {w for w, cnt in word_counts.items() if cnt >= 2}

    readable_paragraphs = []
    for paragraph in paragraphs:
        normalized = _normalize_paragraph_text(paragraph)
        normalized, apostrophe_repairs = repair_apostrophe_spacing(normalized)
        stats['intraword_spaces_repaired'] += apostrophe_repairs
        normalized, dropcap_repairs = _repair_initial_dropcap(normalized)
        stats['intraword_spaces_repaired'] += dropcap_repairs
        normalized, single_letter_repairs = _repair_known_single_letter_splits(normalized)
        stats['intraword_spaces_repaired'] += single_letter_repairs
        repaired, paragraph_repairs = repair_intraword_spaces(normalized)
        stats['intraword_spaces_repaired'] += paragraph_repairs
        split_repaired, split_repairs = split_glued_words(repaired, shared_vocabulary)
        stats['intraword_spaces_repaired'] += split_repairs
        readable_paragraphs.append(split_repaired)

    clean_text = _wrap_paragraphs(readable_paragraphs)

    stats['final_char_count'] = len(clean_text)
    stats['final_word_count'] = len(clean_text.split())

    return clean_text, stats



# FILE PROCESSING


def process_book(raw_path: Path, force: bool = False) -> Path:
    """Clean one RAW text file."""
    stem = raw_path.stem.replace('_RAW', '')
    out_path = BOOK_OUTPUT_CLEAN / f"{stem}_CLEAN.txt"

    if out_path.exists() and not force:
        print(f"  SKIP (exists): {out_path.name}")
        return out_path

    print(f"  Cleaning: {raw_path.name}")

    with open(raw_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    clean_text, stats = clean_raw_text(raw_text)

    BOOK_OUTPUT_CLEAN.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(clean_text)

    print(f"  Pages: {stats['total_pages']}")
    print(f"  Repeated headers/footers removed: {stats['repeated_lines_removed']}")
    print(f"  Page numbers removed: {stats['page_numbers_removed']}")
    print(f"  Chapter headings removed: {stats['chapter_headings_removed']}")
    print(f"  Decorative lines removed: {stats['decorative_lines_removed']}")
    print(f"  Footnote lines removed: {stats['footnote_lines_removed']}")
    print(f"  OCR noise normalized: {stats['ocr_noise_normalized']}")
    print(f"  Intraword spaces repaired: {stats['intraword_spaces_repaired']}")
    print(f"  Final: {stats['final_word_count']} words, {stats['final_char_count']} chars")
    print(f"  OK: {out_path.name}")

    return out_path


def process_all(force: bool = False):
    """Clean all RAW text files."""
    raws = sorted(BOOK_OUTPUT_RAW.glob("*_RAW.txt"))
    if not raws:
        print(f"No RAW files found in {BOOK_OUTPUT_RAW}")
        return

    print(f"Found {len(raws)} RAW files")
    for raw in raws:
        process_book(raw, force=force)
        print()


def _clean_output_path(raw_path: Path) -> Path:
    """Return the CLEAN output path for a RAW file."""
    stem = raw_path.stem.replace('_RAW', '')
    return BOOK_OUTPUT_CLEAN / f"{stem}_CLEAN.txt"


def _format_clean_status(raw_path: Path) -> str:
    """Return CLEAN output status for a RAW file."""
    return "CLEAN exists" if _clean_output_path(raw_path).exists() else "no CLEAN"


def _print_raw_menu(raws: list):
    """Print a numbered RAW selection menu."""
    print(f"\nRAW files found: {len(raws)}")
    print("-" * 82)
    for i, raw in enumerate(raws, start=1):
        print(f"{i:>2}. {raw.name:<60} {_format_clean_status(raw)}")
    print("-" * 82)


def _parse_menu_selection(selection: str, item_count: int) -> list[int]:
    """Parse user selection text into 0-based indices."""
    s = selection.strip().lower()
    if not s:
        return []
    if s in {"q", "quit", "çık", "cik", "exit"}:
        return []
    if s in {"all", "hepsi", "tümü", "tum", "*"}:
        return list(range(item_count))

    selected = []
    for part in s.replace(",", " ").split():
        if not part.isdigit():
            continue
        idx = int(part) - 1
        if 0 <= idx < item_count and idx not in selected:
            selected.append(idx)
    return selected


def process_interactive():
    """Show a numbered RAW menu and clean selected files."""
    raws = sorted(BOOK_OUTPUT_RAW.glob("*_RAW.txt"))
    if not raws:
        print(f"No RAW files found in {BOOK_OUTPUT_RAW}")
        return

    _print_raw_menu(raws)
    print("Enter the number of the RAW file you want to clean.")
    print("For multiple files: 1 3 5")
    print("For all files: all")
    selection = input("Selection: ")
    selected_indices = _parse_menu_selection(selection, len(raws))

    if not selected_indices:
        print("No selection made; cancelled.")
        return

    has_existing_clean = any(_clean_output_path(raws[idx]).exists() for idx in selected_indices)
    force = False
    if has_existing_clean:
        overwrite = input("Overwrite existing CLEAN files? [y/N]: ").strip().lower()
        force = overwrite in {"y", "yes", "e", "evet"}

    for idx in selected_indices:
        clean_path = process_book(raws[idx], force=force)
        if clean_path.exists():
            print(f"  Ready: {clean_path}")
        print()


def print_demo_menu():
    """Print a screenshot-safe demo menu without touching local files."""
    demo_rows = [
        ("sample-book_RAW.txt", "no CLEAN"),
        ("public-domain-demo_RAW.txt", "CLEAN exists"),
        ("synthetic-ocr-example_RAW.txt", "no CLEAN"),
    ]

    print(f"\nRAW files found: {len(demo_rows)}")
    print("-" * 82)
    for i, (name, status) in enumerate(demo_rows, start=1):
        print(f"{i:>2}. {name:<60} {status}")
    print("-" * 82)
    print("Enter the number of the RAW file you want to clean.")
    print("For multiple files: 1 3 5")
    print("For all files: all")
    print("Selection:")


if __name__ == "__main__":
    force = "--force" in sys.argv
    if "--demo-menu" in sys.argv:
        print_demo_menu()
    elif "--all" in sys.argv:
        process_all(force=force)
    elif len(sys.argv) > 1 and sys.argv[1] not in {"--force", "--interactive", "--demo-menu"}:
        raw = Path(sys.argv[1])
        if raw.exists():
            process_book(raw, force=force)
        else:
            print(f"File not found: {raw}")
    else:
        process_interactive()
