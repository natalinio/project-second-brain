"""Convert source/ documents (PDF, DOCX, PPTX) into curated Markdown in knowledge/.

Uses Docling, which is structure-aware: it preserves the heading hierarchy and emits
complex tables as Markdown tables instead of flattening them into prose. That property
is the whole reason this step exists.

Parsing is a batch step, cached on disk. It never runs on the agent's critical path.

Requires the optional dependency group:  uv sync --extra docs
(first run downloads Docling's layout and table models from Hugging Face).

Network notes (see PREREQUISITES.md):
  * Behind a TLS-intercepting proxy the model download fails with
    CERTIFICATE_VERIFY_FAILED. Install the `tls` extra and set KB_USE_TRUSTSTORE=1
    (or pass --truststore): Python then uses the operating-system trust store.
  * OCR is off by default: right for digital-native documents, and it needs an extra
    model download. `--ocr` enables it for scanned PDFs.

Usage:
    uv run python tools/ingest/parse_docs.py                 # parse everything not yet parsed
    uv run python tools/ingest/parse_docs.py --force         # re-parse
    uv run python tools/ingest/parse_docs.py --only spec     # filename substring filter
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# source subfolder -> destination folder.
# prior_deliverables are earlier work products (often LLM-assisted), NOT primary evidence:
# they land in artifacts/_imported/ and their claims must be re-verified against primary
# docs before anything from them is treated as ground truth. They never enter knowledge/.
ROUTES = {
    "specs": "knowledge/extracted/specs",
    "meeting_notes": "knowledge/extracted/meeting_notes",
    "prior_deliverables": "artifacts/_imported",
    # Exports produced by a system itself (object definitions, DDL, configuration dumps):
    # the only material that can carry evidence `verified`, because it is the system
    # describing itself rather than someone describing it.
    "system_exports": "knowledge/extracted/system_exports",
}
DEFAULT_ROUTE = "knowledge/extracted/specs"
EXTENSIONS = {".pdf", ".docx", ".pptx", ".html", ".md", ".txt"}
# Plain text goes through verbatim: running a layout model over a meeting transcript
# would only risk altering it. Copy is the most faithful parse there is.
PLAIN_TEXT = {".txt", ".md"}

FRONTMATTER = """---
title: {title}
type: {doc_type}
status: {status}
origin: {origin}
evidence: {evidence}
domain: TODO
source: {source}
extracted: {today}
updated: {today}
tags: []
---

> Auto-extracted by Docling from `{source}`. Citable at its evidence level; while
> `status: extracted`, cite it with "(extraction unchecked)". `/review-note` checks
> the extraction (tables intact, images listed, domain, abstract) and sets `checked`.
> The body is immutable: corrections and syntheses go to `knowledge/curated/`.

"""


def use_truststore() -> None:
    """Opt-in: route Python TLS through the OS trust store (TLS-intercepting proxies)."""
    try:
        import truststore
    except ImportError:
        print("KB_USE_TRUSTSTORE is set but truststore is missing: uv sync --extra tls", file=sys.stderr)
        return
    truststore.inject_into_ssl()  # must precede any Hugging Face download


def build_converter(use_ocr: bool, trust: bool = False):
    """Docling converter: table structure on, pictures kept, OCR opt-in."""
    if trust or os.environ.get("KB_USE_TRUSTSTORE") == "1":
        use_truststore()

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = use_ocr  # off by default: digital-native documents do not need it
    opts.do_table_structure = True  # the reason we use Docling at all
    opts.generate_picture_images = True  # without this, PDF pictures are unrecoverable
    opts.images_scale = 2.0  # enough resolution to read labels in an architecture diagram
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def save_pictures(doc, stem: str) -> list[Path]:
    """Write every picture in the document to source/_extracted/<stem>/media/.

    Docling's Markdown export reduces an image to a bare `<!-- image -->` placeholder:
    the position survives but the content is lost. Saving the bitmaps keeps them
    available for description, and keeps them out of Git (source/ is gitignored)
    because they come from confidential documents.
    """
    from docling_core.types.doc import PictureItem

    out_dir = REPO / "source" / "_extracted" / stem / "media"
    saved: list[Path] = []
    for item, _level in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        image = item.get_image(doc)
        if image is None:
            saved.append(None)  # keep positional alignment with the placeholders
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"pic_{len(saved):03d}.png"
        image.save(path)
        saved.append(path)
    return saved


def link_pictures(body: str, pictures: list[Path]) -> str:
    """Replace each `<!-- image -->` placeholder with a reference to the saved bitmap.

    `iterate_items()` walks the document in reading order, the same order the exporter
    emits placeholders, so the Nth placeholder is the Nth picture. Undescribed images
    stay greppable via the NOT-YET-DESCRIBED marker.
    """
    parts = body.split("<!-- image -->")
    if len(parts) == 1:
        return body
    out = parts[0]
    for i, tail in enumerate(parts[1:]):
        path = pictures[i] if i < len(pictures) else None
        if path is None:
            out += "<!-- image: NOT EXTRACTED -->"
        else:
            rel = path.relative_to(REPO).as_posix()
            out += f"<!-- image: {rel} — NOT YET DESCRIBED -->"
        out += tail
    return out


def convert(paths: list[Path], force: bool, use_ocr: bool) -> int:
    try:
        converter = build_converter(use_ocr)
    except ImportError:
        print("docling is not installed. Run:  uv sync --extra docs", file=sys.stderr)
        return 1

    today = dt.date.today().isoformat()
    written = 0

    for path in paths:
        origin = path.relative_to(REPO / "source").parts[0]
        bucket = ROUTES.get(origin, DEFAULT_ROUTE)
        out = REPO / bucket / f"{slug(path.stem)}.md"
        if out.exists() and not force:
            print(f"  skip  {path.name} (already parsed)")
            continue

        print(f"  parse {path.name} ...", flush=True)
        if path.suffix.lower() in PLAIN_TEXT:
            body = path.read_text(encoding="utf-8", errors="replace")
            pictures = []
        else:
            try:
                result = converter.convert(str(path))
            except Exception as exc:  # noqa: BLE001 - one bad document must not stop the batch
                print(f"  FAIL  {path.name}: {exc}", file=sys.stderr)
                continue

            pictures = save_pictures(result.document, slug(path.stem))
            body = link_pictures(result.document.export_to_markdown(), pictures)
            if pictures:
                found = sum(1 for p in pictures if p is not None)
                print(f"        {found} image(s) -> source/_extracted/{slug(path.stem)}/media/")
        doc_type = {
            "meeting_notes": "meeting-note",
            "prior_deliverables": "imported-deliverable",
            "system_exports": "object-definition",
        }.get(origin, "spec")
        header = FRONTMATTER.format(
            title=path.stem,
            doc_type=doc_type,
            # meetings are verbal by protocol (tools/kb/schema.yaml: type_evidence)
            evidence={
                "prior_deliverables": "derived-llm",
                "system_exports": "verified",
                "meeting_notes": "verbal",
            }.get(origin, "primary-doc"),
            status="draft" if origin == "prior_deliverables" else "extracted",
            origin="imported" if origin == "prior_deliverables" else "extracted",
            source=path.relative_to(REPO).as_posix(),
            today=today,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(header + body + "\n", encoding="utf-8")
        print(f"        -> {out.relative_to(REPO).as_posix()}")
        written += 1

    print(f"\n{written} note(s) written.")
    if written:
        print("Next: register the source in source/MANIFEST.md, then run")
        print("tools/kb/refresh.py; /review-note checks each extraction.")
    return 0


def slug(stem: str) -> str:
    import re

    return re.sub(r"[^0-9a-zA-Z]+", "-", stem).strip("-").lower()


def run_isolated(paths: list[Path], force: bool, use_ocr: bool) -> int:
    """Parse each document in its own subprocess.

    Docling's native table model leaks: a long batch segfaults partway through — observed
    at 33 documents — and a segfault cannot be caught with try/except, so it takes the
    whole run with it. One process per document reclaims the memory each time and
    contains any crash to the document that caused it.

    Slower per document, and the only way a large batch finishes unattended.
    """
    import subprocess

    ok = failed = 0
    for i, path in enumerate(paths, start=1):
        print(f"[{i}/{len(paths)}] {path.name}", flush=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--only", path.name]
        if force:
            cmd.append("--force")
        if use_ocr:
            cmd.append("--ocr")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
            print(f"  FAILED (exit {result.returncode})", file=sys.stderr)
            tail = (result.stderr or "").strip().splitlines()[-3:]
            for line in tail:
                print(f"    {line}", file=sys.stderr)
    print(f"\n{ok} parsed, {failed} failed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-parse already-parsed documents")
    parser.add_argument("--only", help="only files whose name contains this substring")
    parser.add_argument(
        "--ocr", action="store_true", help="enable OCR for scanned PDFs (downloads an OCR model)"
    )
    parser.add_argument(
        "--truststore", action="store_true",
        help="use the OS trust store for downloads (TLS-intercepting proxies); same as KB_USE_TRUSTSTORE=1",
    )
    parser.add_argument(
        "--isolate",
        action="store_true",
        help="one subprocess per document — required for batches of more than ~25 PDFs",
    )
    args = parser.parse_args()
    if args.truststore:
        os.environ["KB_USE_TRUSTSTORE"] = "1"  # inherited by --isolate subprocesses too

    paths = []
    for folder in ROUTES:
        base = REPO / "source" / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in EXTENSIONS or path.name.startswith("~$"):
                continue
            if args.only and args.only.lower() not in path.name.lower():
                continue
            paths.append(path)

    if not paths:
        print("No documents found under source/. Nothing to parse.")
        return 0
    if args.isolate:
        # Skip already-parsed work before spawning: a subprocess per no-op is pure cost.
        if not args.force:
            paths = [
                p
                for p in paths
                if not (
                    REPO
                    / ROUTES.get(p.relative_to(REPO / "source").parts[0], DEFAULT_ROUTE)
                    / f"{slug(p.stem)}.md"
                ).exists()
            ]
            if not paths:
                print("Everything already parsed.")
                return 0
        return run_isolated(paths, args.force, args.ocr)
    return convert(paths, args.force, args.ocr)


if __name__ == "__main__":
    raise SystemExit(main())
