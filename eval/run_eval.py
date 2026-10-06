#!/usr/bin/env python
"""Measure retrieval quality against the golden set.

Bad recall produces bad agent output, which is the failure this store exists to
prevent -- so it gets measured rather than assumed.

This also gates the embeddings decision. Keyword search stays until a specific
query can be shown to fail on it; the per-query table below is that evidence.
Run with --failures to see only what is broken.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge_store.store import Store  # noqa: E402

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DEFAULT_DB = ROOT / "fixtures" / "synthetic.db"
DEFAULT_QUERIES = ROOT / "queries.yaml"

#: A private golden set over a real corpus, if the operator keeps one. Gitignored.
LOCAL_DB = ROOT / "fixtures" / "local.db"
LOCAL_QUERIES = ROOT / "queries.local.yaml"

#: Two floors, because they catch different regressions. Recall catches retrieval
#: collapsing outright; MRR catches ranking drift, which recall@10 is blind to --
#: an entry sliding from rank 1 to rank 9 leaves recall untouched.
#:
#: Both are calibrated to the synthetic corpus in eval/corpus and are only
#: meaningful against it. A different corpus has a different achievable ceiling,
#: so --local reports numbers without enforcing these unless floors are passed
#: explicitly.
RECALL_FLOOR = 0.80
MRR_FLOOR = 0.90


def evaluate(store: Store, queries: list[dict], limit: int = 10) -> list[dict]:
    rows = []
    for spec in queries:
        relevant = set(spec["relevant"])
        resp = store.search(
            query=spec["query"],
            project=spec.get("project"),
            cross_project=spec.get("cross_project", False),
            limit=limit,
        )
        # Passages collapse to their source file, keeping first-seen order.
        ranked: list[str] = []
        for r in resp.results:
            key = f"{r.project}/{r.source}" if r.source else f"{r.project}/<written>"
            if key not in ranked:
                ranked.append(key)

        first = next((i + 1 for i, k in enumerate(ranked) if k in relevant), None)
        found = set(ranked[:limit]) & relevant
        rows.append({
            "query": spec["query"],
            "project": spec.get("project"),
            "cross": spec.get("cross_project", False),
            "rank": first,
            "hit1": bool(ranked[:1]) and ranked[0] in relevant,
            "hit5": any(k in relevant for k in ranked[:5]),
            "recall": len(found) / len(relevant) if relevant else 0.0,
            "rr": 1.0 / first if first else 0.0,
            "top": ranked[:3],
            "relevant": sorted(relevant),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--failures", action="store_true", help="Only show what missed.")
    ap.add_argument("--floor", type=float, default=RECALL_FLOOR)
    ap.add_argument("--mrr-floor", type=float, default=MRR_FLOOR)
    ap.add_argument("--local", action="store_true",
                    help="Use the private golden set and database instead of the "
                         "synthetic corpus (see eval/queries.local.yaml).")
    args = ap.parse_args(argv)

    explicit_floors = {"--floor", "--mrr-floor"} & {a.split("=")[0] for a in (argv or sys.argv[1:])}
    if args.local:
        if args.db == DEFAULT_DB:
            args.db = LOCAL_DB
        if args.queries == DEFAULT_QUERIES:
            args.queries = LOCAL_QUERIES
        if not args.queries.exists():
            print(f"No private golden set at {args.queries}.", file=sys.stderr)
            return 2
        if not explicit_floors:
            # The default floors describe the synthetic corpus, not this one.
            args.floor = args.mrr_floor = 0.0

    if not args.db.exists():
        corpus = "<your corpus>" if args.local else CORPUS
        print(f"No eval database at {args.db}.\nBuild one:\n"
              f"  python -m knowledge_store.ingest {corpus} --db {args.db}",
              file=sys.stderr)
        return 2

    queries = yaml.safe_load(args.queries.read_text())
    store = Store(args.db)
    rows = evaluate(store, queries, args.limit)
    n = len(rows)

    print(f"{store.count()} passages, {len(store.projects())} projects, {n} queries\n")
    header = f"{'':2} {'rank':>4}  {'rec':>4}  query"
    print(header)
    print("-" * 78)
    for r in rows:
        if args.failures and r["hit5"] and r["recall"] >= 0.5:
            continue
        mark = "ok" if r["hit1"] else ("~" if r["hit5"] else "XX")
        rank = str(r["rank"]) if r["rank"] else "-"
        scope = " [x]" if r["cross"] else ""
        print(f"{mark:2} {rank:>4}  {r['recall']:4.2f}  {r['query']}{scope}")
        if not r["hit1"]:
            print(f"{'':12}want: {', '.join(r['relevant'])}")
            print(f"{'':12}got : {', '.join(r['top']) or '(nothing)'}")

    hit1 = sum(r["hit1"] for r in rows) / n
    hit5 = sum(r["hit5"] for r in rows) / n
    recall = sum(r["recall"] for r in rows) / n
    mrr = sum(r["rr"] for r in rows) / n
    misses = [r for r in rows if not r["hit5"]]

    print("-" * 78)
    print(f"hit@1 {hit1:.2f}   hit@5 {hit5:.2f}   "
          f"recall@{args.limit} {recall:.2f}   MRR {mrr:.3f}")
    if misses:
        print(f"\n{len(misses)} queries with no relevant result in the top 5 -- "
              "these are the candidates that would justify hybrid search:")
        for r in misses:
            print(f"  - {r['query']}")

    failures = []
    if recall < args.floor:
        failures.append(f"recall {recall:.2f} < floor {args.floor:.2f}")
    if mrr < args.mrr_floor:
        failures.append(f"MRR {mrr:.3f} < floor {args.mrr_floor:.2f}")
    if failures:
        print("\nFAIL: " + "; ".join(failures))
        return 1
    if args.floor == 0.0 and args.mrr_floor == 0.0:
        print("\nReported without a gate: the default floors describe the synthetic "
              "corpus.\nPass --floor/--mrr-floor to enforce one for this corpus.")
        return 0
    print(f"\nPASS: recall {recall:.2f} >= {args.floor:.2f}, "
          f"MRR {mrr:.3f} >= {args.mrr_floor:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
