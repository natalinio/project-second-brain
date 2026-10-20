"""Parse email threads (.eml) into curated correspondence notes.

Correspondence is a distinct evidence class. An answer written by the party that owns
the subject is stronger than a workshop recollection and weaker than an exported
definition: it is a dated, attributable, written statement. It gets its own lane so it
is never confused with a functional specification.

A thread is not one document. It is a stack of messages, each with its own author and
date, and the same question can be answered differently three months apart. This splits
the stack so each message can be cited individually.

Email addresses are reduced to `Name (domain)`. Names are kept — attribution is the
whole evidentiary point — but the addresses themselves are personal data that does not
need to live in a Git-versioned note.

Usage:
    uv run python tools/ingest/parse_email.py
    uv run python tools/ingest/parse_email.py --only invoice
"""

from __future__ import annotations

import argparse
import datetime as dt
import email
import email.policy
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "source" / "correspondence"
OUT_DIR = REPO / "knowledge" / "extracted" / "correspondence"
MEDIA_ROOT = REPO / "source" / "_extracted"

# Desktop mail clients write the quoted stack with these headers, localised by the sender's client.
# re.M matters: these are searched across a multi-line window as well as matched
# line by line, and without MULTILINE the ^ anchor only binds to the window's start.
HEADER_FROM = re.compile(r"^\s*(?:From|De|Da|Von)\s*:\s*(.+)$", re.I | re.M)
HEADER_SENT = re.compile(r"^\s*(?:Sent|Enviado|Inviato|Gesendet)\s*:\s*(.+)$", re.I | re.M)
HEADER_SUBJ = re.compile(r"^\s*(?:Subject|Asunto|Oggetto|Betreff)\s*:\s*(.+)$", re.I | re.M)
MAILTO = re.compile(r"<mailto:[^>]*>", re.I)
ADDRESS = re.compile(r"<?([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})>?")
SEPARATOR = re.compile(r"^\s*_{8,}\s*$")


def deidentify(text: str) -> str:
    """Keep the person, drop the address: `Jane Doe <j@corp.com>` -> `Jane Doe (corp.com)`."""
    text = MAILTO.sub("", text)
    return ADDRESS.sub(lambda m: f"({m.group(2)})", text).replace(" <>", "").replace("<>", "")


def decode_body(message) -> str:
    part = message.get_body(preferencelist=("plain",))
    if part is not None:
        try:
            return part.get_content()
        except (LookupError, UnicodeDecodeError):
            payload = part.get_payload(decode=True) or b""
            return payload.decode("utf-8", errors="replace")
    # No plain alternative: fall back to HTML with tags stripped, rather than losing it.
    part = message.get_body(preferencelist=("html",))
    if part is None:
        return ""
    raw = part.get_content()
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    import html as _html

    return _html.unescape(raw)


def split_thread(body: str) -> list[dict]:
    """Split the quoted stack into individual messages, in file order (newest first)."""
    lines = [SEPARATOR.sub("", ln).rstrip() for ln in body.splitlines()]
    starts: list[int] = []
    for i, line in enumerate(lines):
        if HEADER_FROM.match(line):
            # A real message header has Sent:/Subject: within the next few lines;
            # a bare "From:" inside prose does not.
            window = "\n".join(lines[i : i + 5])
            if HEADER_SENT.search(window) or HEADER_SUBJ.search(window):
                starts.append(i)

    messages = []
    bounds = [0] + starts + [len(lines)]
    for idx in range(len(bounds) - 1):
        start, end = bounds[idx], bounds[idx + 1]
        chunk = lines[start:end]
        if not any(ln.strip() for ln in chunk):
            continue
        sender = sent = subject = ""
        first_body = 0
        for j, line in enumerate(chunk[:8]):
            if m := HEADER_FROM.match(line):
                sender = deidentify(m.group(1)).strip()
                first_body = max(first_body, j + 1)
            elif m := HEADER_SENT.match(line):
                sent = m.group(1).strip()
                first_body = max(first_body, j + 1)
            elif m := HEADER_SUBJ.match(line):
                subject = m.group(1).strip()
                first_body = max(first_body, j + 1)
            elif re.match(r"^\s*(To|Cc|Para|CC)\s*:", line, re.I):
                first_body = max(first_body, j + 1)
        text = "\n".join(chunk[first_body:]).strip()
        if not text and not sender:
            continue
        messages.append({"from": sender, "sent": sent, "subject": subject, "text": text})
    return messages


def save_images(message, slug: str) -> list[Path]:
    out = MEDIA_ROOT / slug / "media"
    saved = []
    for part in message.walk():
        if not part.get_content_type().startswith("image/"):
            continue
        data = part.get_payload(decode=True)
        if not data:
            continue
        name = part.get_filename() or f"inline_{len(saved):03d}.png"
        out.mkdir(parents=True, exist_ok=True)
        path = out / Path(name).name
        path.write_bytes(data)
        saved.append(path)
    return saved


def render(path: Path, message, messages: list[dict], images: list[Path]) -> str:
    today = dt.date.today().isoformat()
    subject = str(message.get("Subject") or path.stem)
    participants = deidentify(
        ", ".join(filter(None, [str(message.get("From") or ""), str(message.get("To") or "")]))
    )

    out = [
        "---",
        f"title: {subject}",
        "type: correspondence",
        "status: extracted",
        "origin: extracted",
        "evidence: primary-doc",
        "domain: TODO",
        f"source: {path.relative_to(REPO).as_posix()}",
        f"thread_date: {message.get('Date') or ''}",
        f"messages: {len(messages)}",
        f"extracted: {today}",
        f"updated: {today}",
        "tags: [correspondence]",
        "---",
        "",
        f"# {subject}",
        "",
        "> Written correspondence. Each message below is separately attributable and dated —",
        "> cite the individual message, not the thread. An answer given in June may have been",
        "> superseded by one given in September; the thread runs newest first.",
        "",
        f"**Participants:** {participants}",
        "",
        f"**Messages in thread:** {len(messages)} · **Latest:** {message.get('Date') or 'unknown'}",
        "",
    ]
    if images:
        out += [
            f"**Inline images:** {len(images)} extracted to "
            f"`{images[0].parent.relative_to(REPO).as_posix()}/` — NOT YET DESCRIBED",
            "",
        ]
    out.append("---")

    for i, msg in enumerate(messages, start=1):
        heading = msg["from"] or "(no sender header)"
        out += ["", f"## Message {i} — {heading}", ""]
        meta = []
        if msg["sent"]:
            meta.append(f"**Sent:** {msg['sent']}")
        if msg["subject"]:
            meta.append(f"**Subject:** {msg['subject']}")
        if meta:
            out += [" · ".join(meta), ""]
        out.append(deidentify(msg["text"]))

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="only files whose name contains this substring")
    parser.add_argument("--force", action="store_true", help="re-parse existing notes")
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"{SOURCE.relative_to(REPO)} does not exist. Nothing to parse.")
        return 0

    # Correspondence also arrives as plain text pasted out of a mail client.
    paths = [
        p
        for p in sorted(SOURCE.rglob("*"))
        if p.suffix.lower() in {".eml", ".txt"}
        and (not args.only or args.only.lower() in p.name.lower())
    ]
    if not paths:
        print("No .eml files found under source/correspondence/.")
        return 0

    written = 0
    for path in paths:
        slug = re.sub(r"[^0-9a-zA-Z]+", "-", path.stem).strip("-").lower()
        out = OUT_DIR / f"{slug}.md"
        if out.exists() and not args.force:
            print(f"  skip  {path.name} (already parsed)")
            continue
        print(f"  parse {path.name} ...", flush=True)
        if path.suffix.lower() == ".txt":
            message = email.message_from_string("", policy=email.policy.default)
            message["Subject"] = path.stem.replace("_", " ")
            body = path.read_text(encoding="utf-8", errors="replace")
        else:
            message = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
            body = decode_body(message)
        messages = split_thread(body)
        images = save_images(message, slug)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(path, message, messages, images), encoding="utf-8")
        print(f"        {len(messages)} message(s), {len(images)} image(s)")
        print(f"        -> {out.relative_to(REPO).as_posix()}")
        written += 1

    print(f"\n{written} note(s) written.")
    if written:
        print("Run tools/kb/refresh.py; /review-note checks the extraction and sets 'checked'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
