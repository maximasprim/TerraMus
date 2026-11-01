"""Batch numbers restart in every production cycle ("Batch 1", "Batch 2" ... in cycle 2 as well as cycle 1).

Pure helpers (no database, no framework imports) that decide which existing batch a worksheet sheet refers to,
so the rule is unit-testable on its own.

  * a cycle is selected  -> only batches IN THAT CYCLE can match a sheet's batch number;
  * no cycle selected    -> the original behaviour: match across the whole organisation, preferring batches that
                            belong to no cycle, then the oldest (identical to before whenever numbers are unique).
"""
from __future__ import annotations

from typing import Any, Iterable


def existing_by_number(rows: Iterable[Any], cycle_id) -> dict[int, Any]:
    """rows: batch objects ordered oldest first. -> {batch_number: batch}."""
    out: dict[int, Any] = {}
    if cycle_id is None:
        for b in sorted(rows, key=lambda x: x.production_cycle_id is not None):     # stable: unassigned first, then oldest
            out.setdefault(b.batch_number, b)
    else:
        for b in rows:
            if b.production_cycle_id == cycle_id:
                out[b.batch_number] = b
    return out


def unassigned_by_number(rows: Iterable[Any]) -> dict[int, Any]:
    """Batches that belong to no cycle yet, by number (candidates to be adopted into the selected cycle)."""
    out: dict[int, Any] = {}
    for b in rows:
        if b.production_cycle_id is None:
            out.setdefault(b.batch_number, b)
    return out
