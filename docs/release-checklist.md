# Release Checklist

Use this checklist before publishing the repository.

## Copyright and Data

- [ ] `book-input/` contains no PDFs to be committed, or it is ignored by git.
- [ ] `book-output-raw/` is not tracked.
- [ ] `book-output-clean/` is not tracked.
- [ ] Screenshots do not contain long copyrighted text excerpts.
- [ ] README clearly says users must provide their own legally usable input files.

## Code

- [ ] The demo command works:

```bash
python clean_text.py examples/demo_raw.txt --force
```

- [ ] Python files compile:

```bash
python -m py_compile extract_text.py clean_text.py run_pipeline.py
```

- [ ] Cache files are not committed.
- [ ] `.venv/` is not committed.

## Documentation

- [ ] README explains the pipeline.
- [ ] `docs/algorithm.md` explains the algorithms.
- [ ] `docs/future-work.md` lists contribution areas.
- [ ] `CONTRIBUTING.md` explains contribution and copyright rules.

## GitHub

- [ ] License selected.
- [ ] Repository description added.
- [ ] Issue templates enabled.
- [ ] Initial issues created:
  - Front/back matter classifier
  - Turkish morphological analyzer integration
  - Public-domain mini test corpus
  - Post-OCR correction scoring
  - Language profile interface

## Suggested License

MIT is a practical choice for this type of tooling project. The license should cover code only, not any book text processed locally by users.
