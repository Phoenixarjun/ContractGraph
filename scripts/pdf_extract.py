#!/usr/bin/env python3
"""pdf_extract - deterministic, local PDF -> Markdown extractor with page provenance.

Extracts embedded text page-by-page via `pypdf`. Writes Markdown beside the PDF
(same basename, .md extension) plus a `<stem>.extraction.json` sidecar recording
the source sha256, page count, extractor name/version, and per-page
{page, chars, method}. A per-PDF sidecar name (rather than one shared
`extraction.json`) avoids collisions when a directory holds multiple resume
variants, which context/canonical/resume/README.md explicitly anticipates.

Re-extraction is skipped when the PDF's sha256 matches the sidecar (unless
--force). OCR is used ONLY for a page with no usable embedded text, and only
when a rasterizer (`pymupdf`/`fitz`) plus `pytesseract` and `Pillow` are all
installed; missing any of them marks that page method="ocr_unavailable" --
text is never invented.

No model call, no network call, no API key. Works on Windows (pathlib
throughout, UTF-8 I/O, no shell dependency for filenames with spaces).
Requires the OPTIONAL `pypdf` package (pip install pypdf); OCR needs the
OPTIONAL `pymupdf` + `pytesseract` + `Pillow` packages (see requirements.txt).

Usage:
  python scripts/pdf_extract.py <pdf-or-dir> [--force] [--ocr auto|never|only]
    --ocr auto  (default) OCR a page only if it has no embedded text and OCR
                deps are installed.
    --ocr never never attempt OCR; textless pages are marked
                method="no_text_ocr_disabled".
    --ocr only  skip embedded-text extraction entirely and OCR every page
                (useful to exercise/validate the OCR path).
Output: JSON {ok, processed, results:[...]}. Exit 0 ok, 2 IO/usage,
3 pypdf not installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hash_content import sha256_file  # noqa: E402

NO_TEXT_MARK = "_(no extractable text"


def _pypdf():
    try:
        import pypdf  # type: ignore
        return pypdf
    except ImportError as exc:
        raise ImportError("pypdf not installed. Install it with: pip install pypdf") from exc


def _ocr_backend():
    """Return (fitz, pytesseract, Image) or None if any OCR dependency is missing."""
    try:
        import fitz  # type: ignore  # PyMuPDF: rasterizes a PDF page to an image
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return fitz, pytesseract, Image
    except ImportError:
        return None


def _ocr_page(fitz_mod, pytesseract_mod, image_mod, pdf_path: Path, page_index: int) -> str:
    doc = fitz_mod.open(str(pdf_path))
    try:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=200)
        img = image_mod.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return pytesseract_mod.image_to_string(img)
    finally:
        doc.close()


def _sidecar_path(pdf_path: Path) -> Path:
    return pdf_path.parent / f"{pdf_path.stem}.extraction.json"


def extract_one(pdf_path: Path, ocr_mode: str = "auto") -> dict:
    pypdf = _pypdf()
    sha = sha256_file(pdf_path)
    md_path = pdf_path.with_suffix(".md")
    meta_path = _sidecar_path(pdf_path)

    reader = pypdf.PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    ocr_backend = _ocr_backend() if ocr_mode != "never" else None
    ocr_used = False
    notes = []
    pages_meta = []
    md_parts = [
        f"# {pdf_path.stem}\n",
        f"*Extracted from `{pdf_path.name}` (sha256 {sha}) by pdf_extract.py "
        f"using pypdf {getattr(pypdf, '__version__', 'unknown')}. {page_count} page(s).*\n",
    ]

    for i, page in enumerate(reader.pages):
        page_no = i + 1
        text = ""
        if ocr_mode != "only":
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:  # noqa: BLE001 - one malformed page must not abort the run
                notes.append(f"page {page_no}: embedded-text extraction raised {exc!r}")
                text = ""

        if text:
            method = "embedded"
        elif ocr_mode == "never":
            method = "no_text_ocr_disabled"
        elif ocr_backend is None:
            method = "ocr_unavailable"
        else:
            try:
                ocr_text = (_ocr_page(*ocr_backend, pdf_path, i) or "").strip()
                if ocr_text:
                    text, method, ocr_used = ocr_text, "ocr", True
                else:
                    method = "no_text"
            except Exception as exc:  # noqa: BLE001
                method = "ocr_unavailable"
                notes.append(f"page {page_no}: OCR raised {exc!r}")

        pages_meta.append({"page": page_no, "chars": len(text), "method": method})
        md_parts.append(f"\n## Page {page_no}\n")
        md_parts.append(text if text else f"{NO_TEXT_MARK} -- method: {method})_")

    md_path.write_text("\n".join(md_parts) + "\n", encoding="utf-8")

    extraction = {
        "documentType": "ContractGraphPdfExtraction",
        "sourcePdf": pdf_path.as_posix(),
        "sha256": sha,
        "pageCount": page_count,
        "extractor": "pypdf",
        "extractorVersion": getattr(pypdf, "__version__", "unknown"),
        "ocrUsed": ocr_used,
        "pages": pages_meta,
        "notes": notes,
        "markdownPath": md_path.as_posix(),
    }
    meta_path.write_text(json.dumps(extraction, indent=2) + "\n", encoding="utf-8")
    return {"pdf": pdf_path.as_posix(), "skipped": False, **extraction}


def _unchanged(pdf_path: Path, meta_path: Path) -> bool:
    if not meta_path.is_file():
        return False
    try:
        prior = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return prior.get("sha256") == sha256_file(pdf_path)


def run(target: Path, force: bool, ocr_mode: str) -> list:
    pdfs = [target] if target.is_file() else sorted(target.rglob("*.pdf"))
    results = []
    for pdf_path in pdfs:
        meta_path = _sidecar_path(pdf_path)
        if not force and _unchanged(pdf_path, meta_path):
            prior = json.loads(meta_path.read_text(encoding="utf-8"))
            results.append({"pdf": pdf_path.as_posix(), "skipped": True, **prior})
            continue
        results.append(extract_one(pdf_path, ocr_mode))
    return results


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: pdf_extract.py <pdf-or-dir> [--force] [--ocr auto|never|only]", file=sys.stderr)
        return 2
    target = Path(argv[0])
    force = "--force" in argv
    ocr_mode = "auto"
    if "--ocr" in argv:
        ocr_mode = argv[argv.index("--ocr") + 1]
    if not target.exists():
        print(json.dumps({"ok": False, "error": f"not found: {target}"}), file=sys.stderr)
        return 2
    try:
        results = run(target, force, ocr_mode)
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 3
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "processed": len(results), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
