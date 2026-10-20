"""Discover the physical format of every data sample, without loading them.

Real-world samples arrive in many physical formats (delimited, fixed-width, compressed,
with or without a header row), often gigabytes of them. Loading them blindly would either
blow up memory or, worse, silently mis-split records. So this step only *describes* them: encoding, compression,
delimiter or fixed-width, field count and its stability, row count, and a few raw lines.

Everything is streamed. Nothing is parsed into a table here — that is the next step, and
it needs the record layouts first.

Output: metadata/sample_formats.md (versioned) — the physical-format register.

Usage:
    uv run python tools/ingest/profile_samples.py
    uv run python tools/ingest/profile_samples.py --only orders
"""

from __future__ import annotations

import argparse
import gzip
import io
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAMPLES = REPO / "source" / "data"
REPORT = REPO / "metadata" / "sample_formats.md"

CANDIDATE_DELIMITERS = ["\t", "|", ",", ";", "~", "\x01"]
DELIMITER_NAMES = {"\t": "TAB", "|": "PIPE", ",": "COMMA", ";": "SEMICOLON", "~": "TILDE", "\x01": "SOH"}
SAMPLE_LINES = 200
# Counting hundreds of MB line by line is slow; above this we extrapolate instead
# and say so, rather than quietly reporting a guess as a fact.
EXACT_COUNT_LIMIT = 40 * 1024 * 1024


def open_text(path: Path):
    """Return (stream, compression, encoding). Handles .gz and single-entry .zip."""
    suffix = path.suffix.lower()
    if suffix == ".gz":
        raw, compression = gzip.open(path, "rb"), "gzip"
    elif suffix == ".zip":
        archive = zipfile.ZipFile(path)
        names = [n for n in archive.namelist() if not n.endswith("/")]
        if not names:
            raise ValueError("empty zip")
        raw, compression = archive.open(names[0]), f"zip ({names[0]})"
    else:
        raw, compression = open(path, "rb"), "none"

    head = raw.read(65536)
    encoding = "utf-8"
    if head.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            encoding = "latin-1"

    # Reopen: the underlying stream may not be seekable (zip members are not).
    raw.close()
    if suffix == ".gz":
        raw = gzip.open(path, "rb")
    elif suffix == ".zip":
        raw = zipfile.ZipFile(path).open(names[0])
    else:
        raw = open(path, "rb")
    return io.TextIOWrapper(raw, encoding=encoding, errors="replace", newline=""), compression, encoding


def detect_delimiter(lines: list[str]) -> tuple[str | None, int, float]:
    """Pick the delimiter whose field count is most stable across sampled lines.

    Parsed with the csv module rather than by counting characters: quoted fields
    routinely contain the delimiter, and naive counting misreads a well-formed quoted
    CSV as having an unstable field count — and then mistakes it for a headerless
    fixed-width file.

    Stability matters more than frequency: a pipe-delimited file and a prose file can
    both contain commas, but only the real delimiter yields the same count every line.
    """
    import csv

    usable = [line for line in lines if line.strip()]
    best = (None, 0, 0.0)
    for delim in CANDIDATE_DELIMITERS:
        try:
            rows = list(csv.reader(usable, delimiter=delim, quotechar='"'))
        except csv.Error:
            continue
        counts = [len(r) for r in rows if r]
        if not counts or max(counts) < 2:
            continue
        most_common, hits = Counter(counts).most_common(1)[0]
        stability = hits / len(counts)
        score = stability * min(most_common, 50)
        if score > best[2]:
            best = (delim, most_common, stability)
    return best


def detect_fixed_width(lines: list[str]) -> list[int]:
    """Find column boundaries: positions that are blank in every sampled line.

    Returns the start offsets of each field. Only meaningful for files with no
    delimiter; a wrong answer here is visible because the field count is implausible.
    """
    usable = [line.rstrip("\r\n") for line in lines if line.strip()]
    if not usable:
        return []
    width = max(len(line) for line in usable)
    blank = [all(len(line) <= i or line[i] == " " for line in usable) for i in range(width)]

    boundaries, in_gap = [], True
    for i, is_blank in enumerate(blank):
        if in_gap and not is_blank:
            boundaries.append(i)
            in_gap = False
        elif not in_gap and is_blank:
            # Require at least 2 blank columns to call it a real gap; single spaces
            # occur inside text fields such as "New York".
            if i + 1 < width and blank[i + 1]:
                in_gap = True
    return boundaries


def profile(path: Path) -> dict:
    info: dict = {"path": path, "size": path.stat().st_size}
    try:
        stream, compression, encoding = open_text(path)
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
        return info
    info["compression"] = compression
    info["encoding"] = encoding

    with stream:
        lines, rows, chars = [], 0, 0
        for line in stream:
            rows += 1
            chars += len(line)
            if len(lines) < SAMPLE_LINES:
                lines.append(line)
            elif info["size"] > EXACT_COUNT_LIMIT:
                break
        exact = info["size"] <= EXACT_COUNT_LIMIT or rows < SAMPLE_LINES

    info["line_ending"] = "CRLF" if lines and lines[0].endswith("\r\n") else "LF"
    if exact:
        info["rows"] = rows
        info["rows_exact"] = True
    else:
        avg = chars / max(rows, 1)
        info["rows"] = int(info["size"] / max(avg, 1))
        info["rows_exact"] = False

    delim, fields, stability = detect_delimiter(lines)
    if delim and stability >= 0.9 and fields >= 3:
        info["format"] = f"delimited ({DELIMITER_NAMES.get(delim, repr(delim))})"
        info["fields"] = fields
        info["stability"] = stability
    else:
        starts = detect_fixed_width(lines)
        if starts and len(starts) >= 2:
            info["format"] = "fixed-width"
            info["fields"] = len(starts)
            info["field_starts"] = starts
        else:
            info["format"] = "unknown / single column"
            info["fields"] = 1
    info["sample"] = [ln.rstrip("\r\n")[:160] for ln in lines[:2]]
    info["has_header"] = detect_header(lines, delim if info["fields"] > 1 and delim else None)
    return info


def detect_header(lines: list[str], delim: str | None) -> bool:
    """True when the first row names the columns rather than carrying data.

    Whether a file names its own columns decides whether an external record layout is
    needed at all — the single most consequential fact about an unlabelled extract, and
    one worth measuring rather than assuming.
    """
    import csv
    import re

    if delim is None:
        return False
    usable = [ln for ln in lines if ln.strip()][:8]
    if len(usable) < 2:
        return False
    rows = list(csv.reader(usable, delimiter=delim, quotechar='"'))
    if len(rows) < 2 or not rows[0]:
        return False
    first, rest = rows[0], rows[1:]
    named = sum(1 for c in first if re.fullmatch(r"[A-Za-z][A-Za-z0-9_#./ -]*", c.strip()))
    numeric_below = sum(1 for r in rest for c in r if re.fullmatch(r"-?\d+([.,]\d+)?", c.strip()))
    return named >= max(2, int(0.8 * len(first))) and numeric_below > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="only paths containing this substring")
    args = parser.parse_args()

    paths = [
        p
        for p in sorted(SAMPLES.rglob("*"))
        if p.is_file()
        and p.name != ".gitkeep"
        and p.suffix.lower() not in {".xlsx", ".xls"}
        and (not args.only or args.only.lower() in str(p).lower())
    ]
    if not paths:
        print("No sample files found.")
        return 0

    results = []
    for path in paths:
        print(f"  {path.relative_to(SAMPLES).as_posix()} ...", flush=True)
        results.append(profile(path))

    lines = [
        "---",
        "title: Sample physical format register",
        "type: report",
        "status: generated",
        "---",
        "",
        "# Sample physical format register",
        "",
        "Generated by `tools/ingest/profile_samples.py`. Do not edit by hand.",
        "",
        "Physical format only — encoding, framing, field count. It says nothing about",
        "what the fields *mean*: for files without a header row, column names must",
        "come from the record layouts in the specifications.",
        "",
        "| File | Size | Compression | Encoding | EOL | Format | Header | Fields | Rows |",
        "|---|---:|---|---|---|---|---|---:|---:|",
    ]
    for r in results:
        if "error" in r:
            lines.append(
                f"| `{r['path'].relative_to(SAMPLES).as_posix()}` | "
                f"{r['size'] / 1024 / 1024:.1f} MB | — | — | — | **ERROR: {r['error']}** | — | — | — |"
            )
            continue
        rows = f"{r['rows']:,}" + ("" if r["rows_exact"] else " *(est.)*")
        lines.append(
            f"| `{r['path'].relative_to(SAMPLES).as_posix()}` | {r['size'] / 1024 / 1024:.1f} MB | "
            f"{r['compression']} | {r['encoding']} | {r['line_ending']} | {r['format']} | "
            f"{'**yes**' if r.get('has_header') else 'no'} | {r.get('fields', '?')} | {rows} |"
        )

    lines += ["", "## Raw first lines", ""]
    for r in results:
        if "error" in r:
            continue
        lines += [f"### `{r['path'].relative_to(SAMPLES).as_posix()}`", "", "```"]
        lines += r["sample"]
        lines += ["```", ""]
        if r.get("field_starts"):
            lines += [
                f"Detected fixed-width field starts ({len(r['field_starts'])}): "
                f"`{r['field_starts']}`",
                "",
                "> Positions are inferred from blank columns in the sample, **not** from a "
                "record layout. They are a starting point for locating the real copybook, "
                "not a substitute for it.",
                "",
            ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nregister -> {REPORT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
