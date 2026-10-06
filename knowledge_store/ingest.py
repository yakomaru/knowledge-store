"""Load a directory of markdown into a store. Operator tool, not an MCP tool.

This exists to make retrieval *measurable*. The real store starts empty and fills
from write() as sessions happen; point this at a corpus to build the throwaway
database the eval harness runs against.

Passage splitting is deliberately dumb -- split on H2, carry the headings for
context, done. Chunking strategy is not worth engineering before there is a
corpus big enough to demand it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .store import Store

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", "target", ".mypy_cache", "site-packages",
}

#: Opening or closing of a fenced block: ``` or ~~~, optionally indented.
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_H1 = re.compile(r"^#\s+(.*)")
_H2 = re.compile(r"^##\s+(.*)")

#: A passage shorter than this carries no retrievable signal (stub headings,
#: single-line sections).
MIN_PASSAGE_CHARS = 80

#: Split a heading-less run of prose once it gets past this.
MAX_PASSAGE_CHARS = 4000


def split_markdown(text: str) -> list[str]:
    """Split into passages on H2 boundaries, prefixed with their headings.

    Headings inside fenced code blocks are not headings. This corpus is full of
    fenced directory trees whose lines start with ``#``, and treating those as
    section breaks shreds the documents that matter most.
    """
    lines = text.splitlines()
    h1 = ""
    fence: str | None = None
    sections: list[tuple[str, list[str]]] = [("", [])]

    for line in lines:
        m = _FENCE.match(line)
        if m:
            marker = m.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            sections[-1][1].append(line)
            continue

        if fence is None:
            if not h1 and (m1 := _H1.match(line)):
                h1 = m1.group(1).strip()
            if m2 := _H2.match(line):
                sections.append((m2.group(1).strip(), []))
                continue

        sections[-1][1].append(line)

    passages: list[str] = []
    for heading, body in sections:
        content = "\n".join(body).strip()
        if not content:
            continue
        prefix = " > ".join(p for p in (h1, heading) if p)
        for chunk in _split_long(content):
            passages.append(f"{prefix}\n\n{chunk}".strip() if prefix else chunk)
    return [p for p in passages if len(p) >= MIN_PASSAGE_CHARS]


def _split_long(content: str) -> list[str]:
    """Break an over-long section on blank lines, without splitting code fences."""
    if len(content) <= MAX_PASSAGE_CHARS:
        return [content]
    out, buf, fence = [], [], None
    for para in content.split("\n\n"):
        fences = _FENCE.findall(para)
        for f in fences:
            marker = f[0]
            fence = marker if fence is None else (None if marker == fence else fence)
        buf.append(para)
        if fence is None and sum(len(p) for p in buf) >= MAX_PASSAGE_CHARS:
            out.append("\n\n".join(buf))
            buf = []
    if buf:
        out.append("\n\n".join(buf))
    return out


def project_of(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else root.name


def source_of(path: Path, root: Path) -> str:
    """Path relative to the project, not the corpus root.

    The ``project`` column already carries the first segment; repeating it here
    would make every source read ``alpha/docs/x.md`` inside project ``alpha``.
    Project-relative is also what someone would type to open the file.
    """
    rel = path.relative_to(root)
    return str(Path(*rel.parts[1:])) if len(rel.parts) > 1 else str(rel)


def iter_markdown(root: Path):
    for path in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def ingest(root: Path, db: Path, strict: bool = False, verbose: bool = False,
           reset: bool = False) -> dict:
    root = root.expanduser().resolve()
    store = Store(db)

    existing = store.count()
    if existing:
        if not reset:
            store.close()
            raise SystemExit(
                f"{db} already holds {existing} entries. Re-ingesting would append a "
                f"second copy of every passage and quietly skew any measurement taken "
                f"from it.\nPass --reset to rebuild it from scratch, or choose another "
                f"--db path."
            )
        store.conn.executescript(
            "DELETE FROM entries; INSERT INTO entries_fts(entries_fts) VALUES('rebuild');"
        )
    stats = {"files": 0, "passages": 0, "skipped": 0, "refused": 0, "projects": set()}

    for path in iter_markdown(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stats["skipped"] += 1
            continue
        passages = split_markdown(text)
        if not passages:
            stats["skipped"] += 1
            continue
        project = project_of(path, root)
        source = source_of(path, root)
        stats["files"] += 1
        stats["projects"].add(project)
        for passage in passages:
            try:
                store.write(
                    content=passage, project=project, provenance="sourced",
                    source=source, enforce=strict,
                )
                stats["passages"] += 1
            except Exception as exc:
                stats["refused"] += 1
                if verbose:
                    print(f"  refused {source}: {exc}", file=sys.stderr)
        if verbose:
            print(f"{project:22} {source:52} {len(passages):3} passages")

    store.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("directory", type=Path)
    ap.add_argument("--db", type=Path, required=True,
                    help="Target database. Use a throwaway path, not your real store.")
    ap.add_argument("--strict", action="store_true",
                    help="Apply the write gate to bulk content (off by default).")
    ap.add_argument("--reset", action="store_true",
                    help="Clear the database first. Required when it already has "
                         "entries, since ingest otherwise appends.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if not args.directory.is_dir():
        print(f"not a directory: {args.directory}", file=sys.stderr)
        return 1

    stats = ingest(args.directory, args.db, args.strict, args.verbose, args.reset)
    print(f"\n{stats['passages']} passages from {stats['files']} files "
          f"across {len(stats['projects'])} projects -> {args.db}")
    if stats["skipped"]:
        print(f"{stats['skipped']} files skipped (empty or unreadable)")
    if stats["refused"]:
        print(f"{stats['refused']} passages refused by the write gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
