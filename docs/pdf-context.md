# PDF Context Extraction

[context-model.md](context-model.md) notes that canonical documents are "summarized when useful" and "load originals when exact evidence is required" — but until now nothing actually extracted a PDF's text. `build_context_manifest.py` and `validate_context.py` both explicitly treat a PDF as an opaque binary (`"type": "binary"`, recorded but never parsed). `scripts/pdf_extract.py` fills that gap: deterministic, local, page-provenance-preserving text extraction to Markdown.

## What it does

```
python scripts/pdf_extract.py <pdf-or-dir> [--force] [--ocr auto|never|only]
```

For each PDF (a single file, or every `*.pdf` under a directory, recursively):

1. Compute the file's SHA-256 (`scripts/hash_content.py`).
2. Extract embedded text **page by page** via `pypdf`.
3. Write Markdown beside the PDF, same basename (e.g. `resume.pdf` → `resume.md`), with a `## Page N` header per page.
4. Write a `<stem>.extraction.json` sidecar (**not** a single shared `extraction.json`, deliberately — see below) recording the source path, SHA-256, page count, extractor name/version, OCR usage, and a per-page `{page, chars, method}` record.
5. **Skip unchanged files**: if the sidecar's recorded SHA-256 matches the current file, the PDF is not re-extracted (unless `--force`).
6. **OCR only when a page has no usable embedded text**, and only when a rasterizer (`pymupdf`/`fitz`) plus `pytesseract` and `Pillow` are all installed. Missing any of them marks that page `method: "ocr_unavailable"` — text is never invented. `--ocr never` disables the OCR path entirely (`method: "no_text_ocr_disabled"`); `--ocr only` forces OCR for every page (useful for exercising that path deliberately).

No model call, no network call, no API key. Works on Windows — pathlib throughout, so filenames with spaces (e.g. a resume named with a full name) are handled without any shell quoting concerns inside the script itself.

## One deliberate deviation from the target layout

The original design sketch showed a single shared `extraction.json` beside one `resume.pdf`. The real `context/canonical/resume/README.md` explicitly anticipates **multiple** PDFs in that directory ("a single master resume... and/or role-specific variants"). A shared filename would silently collide or overwrite between them, so `pdf_extract.py` uses a per-PDF sidecar (`<stem>.extraction.json`) instead. This is a correctness fix applied before shipping, not an oversight — documented here so it doesn't read as a departure from spec later.

## Privacy

`context/canonical/` (the entire tree, not just `resume/`) is git-ignored — see `.gitignore`. Both the source PDF and every file this script writes (`.md`, `.extraction.json`) land inside that same ignored tree, so nothing this script produces becomes trackable by accident. `scripts/hook_guard.py` (the PreToolUse privacy guard) only inspects writes under `.claude/skills/` and `.claude/agents/` — it has no reason to touch `context/canonical/resume/`, and doesn't need to.

Verified against a real private resume in this session:

```
python scripts/pdf_extract.py "context/canonical/resume/<your-resume>.pdf" --ocr auto
```

produced `sha256`, `pageCount: 1`, `1 page extracted via method: "embedded"` (real text layer, no OCR needed), and `git check-ignore -v` confirmed both the new `.md` and `.extraction.json` fall under the `context/canonical/` ignore rule. The extracted content itself is not reproduced here — that would defeat the point of keeping it private.

## Deterministic test coverage

`t_pdf_extract` in `evals/run_evals.py` builds a tiny, hand-constructed, fully synthetic 2-page PDF (a correct minimal xref table, no third-party PDF-writing library needed for the fixture itself) with one page of real text and one deliberately blank page, then asserts: extraction produces the expected page count and text; the blank page is marked `chars: 0` with an explicit `method` field, never fabricated prose; re-running without `--force` reports `skipped: true`; changing the PDF's content causes re-extraction; the sidecar carries only path/hash/page metadata, nothing else.

## Dependencies

`pypdf` is the one required (but optional-to-the-framework-core) dependency — see `scripts/requirements.txt`. `pymupdf` + `pytesseract` + `Pillow` are optional, needed only to exercise the OCR fallback; their absence degrades gracefully to `"ocr_unavailable"`, it never crashes the rest of the suite.
