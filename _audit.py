#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cleaning audit for local books:
1. Remaining OCR-noise characters in CLEAN text
2. Missed chapter headings
3. TOC-like lines (text + page number)
4. Heading-detection coverage notes (page start vs. page middle)
"""
import sys
sys.path.insert(0, '.')
from clean_text import (
    clean_raw_text, BOOK_OUTPUT_RAW,
    _looks_like_heading_text, _looks_like_page_number,
    detect_chapter_headings,
)
from collections import Counter

# Türkçe metinde normal olan karakterler
_NORMAL_CHARS = set(
    'abcçdefgğhıijklmnoöprsştuüvyzâîû'
    'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZÂÎÛ'
    ' .,;:!?-–—()[]{}0123456789\n\r\t'
    '\'"«»“”‘’„'
    '/\\@#%&*+='
)


def audit_book(raw_path):
    stem = raw_path.stem.replace('_RAW', '')
    with open(raw_path, encoding='utf-8') as f:
        raw = f.read()

    clean, stats = clean_raw_text(raw)
    pages_raw = raw.split('\f')

    issues = {}

    # ── 1. Kalan OCR gürültü karakterleri ──
    noise = Counter()
    for c in clean:
        if c not in _NORMAL_CHARS and not c.isalpha() and not c.isdigit():
            noise[c] += 1
    if noise:
        issues['ocr_noise'] = [(repr(c), n) for c, n in noise.most_common(10)]

    # ── 2. TOC tarzı satırlar: "Başlık Metni 47" ──
    toc_lines = []
    for line in clean.split('\n'):
        s = line.strip()
        if not s:
            continue
        words = s.split()
        if (len(words) >= 2 and words[-1].isdigit()
                and 1 <= int(words[-1]) <= 999
                and len(s) <= 60):
            toc_lines.append(s)
    if toc_lines:
        issues['toc_style'] = toc_lines[:5]

    # ── 3. Kaçan bölüm başlıkları ──
    # Sayfa başında olmayan ama heading gibi görünen kısa satırlar
    missed = []
    for pi, page in enumerate(pages_raw):
        lines = page.split('\n')
        content_count = 0
        for li, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            content_count += 1
            if content_count <= 3:
                continue  # Zaten detect_chapter_headings bakıyor
            # Sayfa ORTASINDA kısa, heading-like satır
            if _looks_like_heading_text(s) and not _looks_like_page_number(s):
                # Çevresine bak: etrafında boş satır var mı?
                prev_empty = (li == 0 or not lines[li - 1].strip())
                next_empty = (li + 1 >= len(lines) or not lines[li + 1].strip())
                if prev_empty and next_empty:
                    missed.append((pi + 1, s))  # (sayfa, metin)
    if missed:
        issues['mid_page_headings'] = missed[:8]

    # ── 4. Kısa sahte-heading'ler: yakalanmış ama yanlış silinmiş olabilir mi? ──
    # Bunları CLEAN metninden yalnız kalan 1-2 kelimelik satırlardan çek
    short_isolated = []
    clean_lines = clean.split('\n')
    for i, line in enumerate(clean_lines):
        s = line.strip()
        if not s:
            continue
        words = s.split()
        if 1 <= len(words) <= 3 and len(s) <= 40:
            prev_empty = (i == 0 or not clean_lines[i - 1].strip())
            next_empty = (i + 1 >= len(clean_lines) or not clean_lines[i + 1].strip())
            if prev_empty and next_empty and not _looks_like_page_number(s):
                short_isolated.append(s)
    if short_isolated:
        issues['short_isolated_in_clean'] = short_isolated[:6]

    return stem, stats, issues


def main():
    raws = sorted(BOOK_OUTPUT_RAW.glob('*_RAW.txt'))
    print(f'Denetleniyor: {len(raws)} kitap\n')
    print('=' * 70)

    clean_books = []
    problem_books = []

    for raw_path in raws:
        try:
            stem, stats, issues = audit_book(raw_path)
        except Exception as e:
            import traceback
            print(f'[{raw_path.stem}] HATA: {e}')
            traceback.print_exc()
            continue

        if not issues:
            clean_books.append(stem)
        else:
            problem_books.append((stem, stats, issues))

    # Sorunsuz kitaplar
    print(f'SORUNSUZ ({len(clean_books)} kitap):')
    for b in clean_books:
        print(f'  - {b}')

    print()
    print('=' * 70)
    print(f'SORUN TESPIT EDILDI ({len(problem_books)} kitap):')
    print('=' * 70)

    for stem, stats, issues in problem_books:
        print(f'\n[{stem}]  ({stats["final_word_count"]} kelime)')

        if 'ocr_noise' in issues:
            nc = ', '.join(f'{c} x{n}' for c, n in issues['ocr_noise'])
            print(f'  OCR gürültü kaldi    : {nc}')

        if 'toc_style' in issues:
            print(f'  TOC tarzı satırlar   :')
            for t in issues['toc_style']:
                print(f'    "{t}"')

        if 'mid_page_headings' in issues:
            print(f'  Sayfa ortası başlık? :')
            for pg, text in issues['mid_page_headings']:
                print(f'    Sayfa {pg:3d}: "{text}"')

        if 'short_isolated_in_clean' in issues:
            print(f'  CLEAN metninde yalnız kısa satır:')
            for t in issues['short_isolated_in_clean']:
                print(f'    "{t}"')

    print()
    print('=' * 70)
    print('Denetim tamamlandi.')


if __name__ == '__main__':
    main()
