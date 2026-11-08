"""Compare two benchmark artifact directories (Phase A baseline vs optimized).

Usage (from `anveksha_backend/`):

    .\\.venv\\Scripts\\python.exe -m bench.compare baseline optimized
    .\\.venv\\Scripts\\python.exe -m bench.compare path/to/a path/to/b

Accepts labels under `bench/artifacts/` or absolute/relative paths.

What "equivalence" means here (the bar for the optimization work):
  * every read snapshot deep-equals after normalization,
  * every write-pass record has the same statuses in the same order,
  * the post-write DB dump deep-equals table by table.

Latency and SQL-count deltas are reported informationally (improvements
are the point of the exercise); a *status* change or a SQL-count increase
is called out. Exit code 1 only on data/state/status mismatches.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from bench.common import ARTIFACTS_DIR


def _resolve(p: str) -> Path:
    cand = Path(p)
    if cand.exists():
        return cand
    return ARTIFACTS_DIR / p


def _load(d: Path, name: str) -> Any:
    f = d / name
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def first_diff(a: Any, b: Any, path: str = "$") -> Optional[str]:
    """Return a compact path description of the first structural difference."""
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: only in B"
            if k not in b:
                return f"{path}.{k}: only in A"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: len {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if a != b:
        sa, sb = repr(a), repr(b)
        if len(sa) > 90:
            sa = sa[:90] + "..."
        if len(sb) > 90:
            sb = sb[:90] + "..."
        return f"{path}: A={sa} B={sb}"
    return None


def pct_delta(a: float, b: float) -> str:
    if a <= 0:
        return "n/a"
    return f"{(b - a) / a * 100:+.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", help="baseline label or path")
    ap.add_argument("b", help="optimized label or path")
    args = ap.parse_args()

    da, db = _resolve(args.a), _resolve(args.b)
    if not da.exists() or not db.exists():
        print(f"missing artifact dir: {da if not da.exists() else db}")
        return 2
    print(f"A = {da}\nB = {db}\n")

    failures: list[str] = []
    warnings: list[str] = []

    # ── Boot / seed phase (H1) ─────────────────────────────────────────
    ra, rb = _load(da, "results.json"), _load(db, "results.json")
    if ra is None or rb is None:
        print("results.json missing in one of the dirs")
        return 2
    ba, bb = ra.get("boot", {}), rb.get("boot", {})
    print("=== BOOT (schema+seed phase of app lifespan) ===")
    print(f"  cold seed ms:  {ba.get('seed_phase_ms')}  ->  {bb.get('seed_phase_ms')}"
          f"  ({pct_delta(ba.get('seed_phase_ms') or 0, bb.get('seed_phase_ms') or 0)})")
    print(f"  cold seed q:   {ba.get('seed_phase_queries')}  ->  {bb.get('seed_phase_queries')}")
    # H1: warm restart on an already-seeded DB — should fast-path to a
    # couple of queries instead of replaying every seeder.
    wms_a, wms_b = ba.get("warm_reboot_ms", "n/a"), bb.get("warm_reboot_ms", "n/a")
    wq_a, wq_b = ba.get("warm_reboot_queries", "n/a"), bb.get("warm_reboot_queries", "n/a")
    print(f"  warm reboot ms:{wms_a}  ->  {wms_b}")
    print(f"  warm reboot q: {wq_a}  ->  {wq_b}\n")

    # ── Reads ─────────────────────────────────────────────────────────
    reads_a, reads_b = ra["reads"], rb["reads"]
    print(f"=== READS ({len(reads_a)} vs {len(reads_b)} endpoints) ===")
    print(f"  {'endpoint':<66} {'p50 A':>8} {'p50 B':>8} {'delta':>8} "
          f"{'p95 A':>8} {'p95 B':>8} {'sqlA':>5} {'sqlB':>5}")
    sql_up = sql_down = 0
    lat_up: list[tuple[float, str]] = []
    for key in sorted(set(reads_a) | set(reads_b)):
        a, b = reads_a.get(key), reads_b.get(key)
        if not a or not b:
            failures.append(f"read endpoint only in one run: {key}")
            continue
        if a["statuses"] != b["statuses"]:
            failures.append(f"status change {key}: {a['statuses']} -> {b['statuses']}")
        sa, sb = a["sql_max"], b["sql_max"]
        if sb > sa:
            sql_up += 1
            warnings.append(f"SQL count increased {key}: {sa} -> {sb}")
        elif sb < sa:
            sql_down += 1
        p50a, p50b = a["latency_ms"]["p50"], b["latency_ms"]["p50"]
        # sub-ms endpoints swing tens of percent between identical runs —
        # only flag when both relative (>20%) and absolute (>1ms) matter
        if p50a > 0 and (p50b - p50a) / p50a > 0.20 and (p50b - p50a) > 1.0:
            lat_up.append(((p50b - p50a) / p50a, key, p50b - p50a))
        print(f"  {key:<66} {p50a:8.2f} {p50b:8.2f} {pct_delta(p50a, p50b):>8} "
              f"{a['latency_ms']['p95']:8.2f} {b['latency_ms']['p95']:8.2f} {sa:5} {sb:5}")
    print(f"  sql: {sql_down} endpoints fewer, {sql_up} endpoints more\n")

    # ── Writes ────────────────────────────────────────────────────────
    wa, wb = _load(da, "writes.json"), _load(db, "writes.json")
    print(f"=== WRITES ({len(wa) if wa else 0} vs {len(wb) if wb else 0} ops) ===")
    if wa is None or wb is None:
        failures.append("writes.json missing")
    elif len(wa) != len(wb):
        failures.append(f"write op count differs: {len(wa)} != {len(wb)}")
    else:
        print(f"  {'op':<66} {'p50 A':>8} {'p50 B':>8} {'delta':>8} {'sqlA':>5} {'sqlB':>5} status")
        for i, (a, b) in enumerate(zip(wa, wb)):
            if a["key"] != b["key"]:
                failures.append(f"write order/key mismatch at #{i}: {a['key']} != {b['key']}")
                continue
            if a["statuses"] != b["statuses"]:
                failures.append(
                    f"write status change {a['key']}: {a['statuses']} -> {b['statuses']}")
            if b["sql_max"] > a["sql_max"]:
                warnings.append(
                    f"write SQL count increased {a['key']}: {a['sql_max']} -> {b['sql_max']}")
            p50a, p50b = a["latency_ms"]["p50"], b["latency_ms"]["p50"]
            st = "ok" if a["statuses"] == b["statuses"] else "CHANGED"
            print(f"  {a['key']:<66} {p50a:8.2f} {p50b:8.2f} {pct_delta(p50a, p50b):>8} "
                  f"{a['sql_max']:5} {b['sql_max']:5} {st}")
    print()

    # ── Snapshots (data equivalence for reads + writes) ───────────────
    print("=== SNAPSHOTS (normalized response bodies) ===")
    snaps_a = {p.relative_to(da) for p in (da / "snapshots").rglob("*.json")}
    snaps_b = {p.relative_to(db) for p in (db / "snapshots").rglob("*.json")}
    for missing in sorted(snaps_a - snaps_b):
        failures.append(f"snapshot only in A: {missing}")
    for missing in sorted(snaps_b - snaps_a):
        failures.append(f"snapshot only in B: {missing}")
    n_same = 0
    for rel in sorted(snaps_a & snaps_b):
        try:
            ja = json.loads((da / rel).read_text(encoding="utf-8"))
            jb = json.loads((db / rel).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"snapshot unparsable {rel}: {e}")
            continue
        d = first_diff(ja, jb, str(rel))
        if d:
            failures.append(f"snapshot diff: {d}")
        else:
            n_same += 1
    print(f"  {n_same}/{len(snaps_a & snaps_b)} identical\n")

    # ── State dump ────────────────────────────────────────────────────
    print("=== DB STATE (post-write-pass dump) ===")
    sa_, sb_ = _load(da, "state.json"), _load(db, "state.json")
    if sa_ is None or sb_ is None:
        failures.append("state.json missing")
    else:
        n_rows_a = sum(len(v) for v in sa_.values())
        n_rows_b = sum(len(v) for v in sb_.values())
        for t in sorted(set(sa_) | set(sb_)):
            if t not in sa_:
                failures.append(f"table only in B: {t}")
            elif t not in sb_:
                failures.append(f"table only in A: {t}")
            else:
                d = first_diff(sa_[t], sb_[t], t)
                if d:
                    failures.append(f"state diff: {d}")
        print(f"  tables: {len(sa_)} vs {len(sb_)}, rows: {n_rows_a} vs {n_rows_b}")
        state_bad = [f for f in failures if f.startswith("state diff") or "table only" in f]
        print(f"  {'identical' if not state_bad else 'DIFFERS — see failures'}\n")

    # ── Summary ───────────────────────────────────────────────────────
    if lat_up:
        print("=== LATENCY REGRESSIONS (>+20% p50 and >+1ms) ===")
        for d, k, abs_d in sorted(lat_up, reverse=True):
            print(f"  {k}: {d * 100:+.1f}% (+{abs_d:.2f} ms)")
        print()
    if warnings:
        print(f"=== WARNINGS ({len(warnings)}) ===")
        for w in warnings:
            print(f"  {w}")
        print()
    if failures:
        print(f"=== FAILURES ({len(failures)}) ===")
        for f in failures:
            print(f"  {f}")
        print("\nRESULT: FAIL (data/state/status equivalence broken)")
        return 1
    print("RESULT: PASS (data equivalence holds; see tables above for perf deltas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
