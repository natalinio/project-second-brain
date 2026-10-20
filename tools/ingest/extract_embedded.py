"""Extract images and embedded objects from Office files before they are parsed.

Docling handles text, headings and tables very well — including the cached data behind
Excel charts. Two things it does NOT recover, verified on test fixtures:

  1. **Images.** They become a bare `<!-- image -->` placeholder. Position survives,
     content is lost.
  2. **Embedded objects.** A workbook embedded inside another workbook (or a document)
     is stored verbatim under `xl/embeddings/` or `word/embeddings/` in the file's zip.
     Docling ignores it completely, so its data silently disappears.

Both are recoverable directly from the OOXML package, because .docx/.xlsx/.pptx are
just zip archives. This script pulls them out into `source/_extracted/` so that:

  * images can be described by a vision-capable agent and transcribed into
    `knowledge/curated/diagrams/` as Mermaid + prose;
  * embedded workbooks are picked up by `build_inventory.py` like any other workbook.

It also writes an extraction report, so anything found is *tracked* rather than
silently dropped.

Usage:
    uv run python tools/ingest/extract_embedded.py
    uv run python tools/ingest/extract_embedded.py --only spec
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "source"
EXTRACTED = SOURCE / "_extracted"
REPORT = REPO / "metadata" / "extraction_report.md"

OOXML = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}
MEDIA_PREFIXES = ("word/media/", "xl/media/", "ppt/media/")
EMBED_PREFIXES = ("word/embeddings/", "xl/embeddings/", "ppt/embeddings/")
CHART_PREFIX = "xl/charts/chart"

# OLE stream name -> extension of the legacy file it wraps.
OLE_SIGNATURES = {"Workbook": ".xls", "Book": ".xls", "WordDocument": ".doc", "PowerPoint Document": ".ppt"}

# Payload signature -> extension, for naming a blob whose label carries no suffix.
MAGIC = {b"%PDF": ".pdf", b"PK\x03\x04": ".zip", b"\xd0\xcf\x11\xe0": ".bin"}


def read_ole10native(data: bytes) -> tuple[str, bytes]:
    """Parse an OLE1 Package stream: the wrapping Word uses for a dragged-in file.

    Layout is a DWORD total size, a WORD flag, the original filename and source
    path as null-terminated strings, two more WORDs, then a length-prefixed temp
    path and finally the length-prefixed payload. The label is the only place the
    attachment's real filename survives, so it is returned alongside the bytes.
    """
    pos = 6

    def cstr(start: int) -> tuple[str, int]:
        end = data.index(b"\x00", start)
        return data[start:end].decode("latin-1"), end + 1

    label, pos = cstr(pos)
    _source_path, pos = cstr(pos)
    pos += 4
    (temp_len,) = struct.unpack("<I", data[pos : pos + 4])
    pos += 4 + temp_len
    (size,) = struct.unpack("<I", data[pos : pos + 4])
    pos += 4
    return label, data[pos : pos + size]


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "-", text).strip("-").lower()


def unwrap_ole(blob: Path) -> list[Path]:
    """Turn an oleObject*.bin into real files where possible.

    Three wrappings occur in this corpus and each hides the payload differently:
    `Package` (modern Office, raw child bytes), `Ole10Native` (OLE1, a header
    carrying the original filename) and `CONTENTS` (PDF, the raw PDF).
    Handling only the first silently loses e.g. file-definition PDFs attached to a
    specification, so all three are read.
    """
    try:
        import olefile
    except ImportError:
        return []
    if not olefile.isOleFile(str(blob)):
        return []

    produced: list[Path] = []
    with olefile.OleFileIO(str(blob)) as ole:
        streams = {"/".join(s) for s in ole.listdir()}
        if "Package" in streams:
            out = blob.with_name(blob.stem + "_package.bin")
            out.write_bytes(ole.openstream("Package").read())
            # The Package payload is usually itself an OOXML zip; name it accordingly.
            if zipfile.is_zipfile(out):
                renamed = out.with_suffix("")
                renamed = renamed.with_name(renamed.name.replace("_package", "") + ".xlsx")
                out.replace(renamed)
                out = renamed
            produced.append(out)
        if "\x01Ole10Native" in streams:
            try:
                label, payload = read_ole10native(ole.openstream("\x01Ole10Native").read())
            except (ValueError, struct.error) as exc:
                print(f"  Ole10Native unreadable in {blob.name}: {exc}")
            else:
                # Windows caps paths at 260 characters; the label only needs to identify.
                stem = slug(Path(label).stem)[:40] or blob.stem
                ext = Path(label).suffix.lower() or MAGIC.get(payload[:4], ".bin")
                out = blob.with_name(f"{blob.stem}_{stem}{ext}")
                out.write_bytes(payload)
                produced.append(out)
        if "CONTENTS" in streams:
            # PDF keeps the PDF verbatim; anything else here we leave alone.
            data = ole.openstream("CONTENTS").read()
            if data.startswith(b"%PDF"):
                out = blob.with_name(blob.stem + ".pdf")
                out.write_bytes(data)
                produced.append(out)
        for stream, ext in OLE_SIGNATURES.items():
            if stream in streams:
                out = blob.with_name(blob.stem + "_legacy" + ext)
                out.write_bytes(ole.openstream(stream).read())
                produced.append(out)
                break
    return produced


def extract(path: Path, depth: int = 0) -> dict:
    """Pull media, embedded objects and chart parts out of one OOXML file."""
    stats = {"file": path, "images": [], "embedded": [], "charts": 0, "nested": []}
    if not zipfile.is_zipfile(path):
        stats["error"] = "not a zip / not an OOXML package"
        return stats

    target = EXTRACTED / slug(path.stem)
    indent = "    " * depth

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        stats["charts"] = sum(1 for n in names if n.startswith(CHART_PREFIX))

        for name in names:
            if name.endswith("/"):
                continue
            if name.startswith(MEDIA_PREFIXES):
                out = target / "media" / Path(name).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(name))
                stats["images"].append(out)
                print(f"{indent}  image    {name} -> {out.relative_to(SOURCE).as_posix()}")
            elif name.startswith(EMBED_PREFIXES):
                out = target / "embedded" / Path(name).name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(name))
                stats["embedded"].append(out)
                print(f"{indent}  embedded {name} -> {out.relative_to(SOURCE).as_posix()}")

    # Unwrap OLE blobs, then recurse into any embedded OOXML file we recovered.
    for blob in list(stats["embedded"]):
        if blob.suffix.lower() == ".bin":
            for unwrapped in unwrap_ole(blob):
                stats["embedded"].append(unwrapped)
                print(f"{indent}  unwrap   {blob.name} -> {unwrapped.name}")
    for child in list(stats["embedded"]):
        if child.suffix.lower() in OOXML and depth < 3:
            print(f"{indent}  recurse into {child.name}")
            stats["nested"].append(extract(child, depth + 1))

    return stats


def flatten(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        out.append(r)
        out.extend(flatten(r.get("nested", [])))
    return out


def write_report(results: list[dict]) -> None:
    rows = flatten(results)
    total_img = sum(len(r["images"]) for r in rows)
    total_emb = sum(1 for r in rows for e in r["embedded"] if e.suffix.lower() != ".bin")

    lines = [
        "---",
        "title: Embedded content extraction report",
        "type: report",
        "status: generated",
        "---",
        "",
        "# Embedded content extraction report",
        "",
        "Generated by `tools/ingest/extract_embedded.py`. Do not edit by hand.",
        "",
        "Everything listed here is content that **Docling alone would not recover**.",
        "Images still need a description before they are usable: read each one and",
        "transcribe it into `knowledge/curated/diagrams/` as Mermaid plus prose.",
        "",
        f"- Documents scanned: **{len(rows)}**",
        f"- Images extracted: **{total_img}** (awaiting description)",
        f"- Embedded objects recovered: **{total_emb}**",
        "",
        "| Document | Images | Embedded objects | Chart parts |",
        "|---|---|---|---|",
    ]
    for r in rows:
        name = r["file"].relative_to(SOURCE).as_posix() if SOURCE in r["file"].parents else r["file"].name
        embeds = [e.name for e in r["embedded"] if e.suffix.lower() != ".bin"] or ["—"]
        lines.append(
            f"| `{name}` | {len(r['images'])} | {', '.join(embeds)} | {r['charts']} |"
        )

    if total_img:
        lines += ["", "## Images awaiting description", "", "| Image | From |", "|---|---|"]
        for r in rows:
            for img in r["images"]:
                lines.append(f"| `{img.relative_to(SOURCE).as_posix()}` | `{r['file'].name}` |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport -> {REPORT.relative_to(REPO)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="only files whose name contains this substring")
    parser.add_argument("--clean", action="store_true", help="wipe source/_extracted/ first")
    args = parser.parse_args()

    if args.clean and EXTRACTED.exists():
        # Cloud-sync clients and antivirus may hold directory handles, so
        # a hard rmtree can fail on Windows. Extraction overwrites by filename anyway; a
        # partial clean is harmless.
        shutil.rmtree(EXTRACTED, onerror=lambda f, p, e: print(f"  locked, kept: {p}"))

    paths = [
        p
        for p in sorted(SOURCE.rglob("*"))
        if p.suffix.lower() in OOXML
        and not p.name.startswith("~$")
        and EXTRACTED not in p.parents  # never re-scan our own output
        and (not args.only or args.only.lower() in p.name.lower())
    ]
    if not paths:
        print("No Office files found under source/. Nothing to extract.")
        return 0

    results = []
    for path in paths:
        print(f"\n{path.relative_to(SOURCE).as_posix()}")
        results.append(extract(path))

    write_report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
