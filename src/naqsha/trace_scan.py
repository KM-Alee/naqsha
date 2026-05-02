"""Discover run ids in a JSONL trace directory."""

from __future__ import annotations

from pathlib import Path


def list_run_ids_by_recency(trace_dir: Path) -> list[str]:
    """Return run ids (stem of ``*.jsonl``) newest first by file mtime."""

    root = Path(trace_dir)
    if not root.is_dir():
        return []
    pairs: list[tuple[float, str]] = []
    for path in root.glob("*.jsonl"):
        if path.is_file():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            pairs.append((mtime, path.stem))
    pairs.sort(key=lambda x: x[0], reverse=True)
    return [stem for _, stem in pairs]


def latest_run_id(trace_dir: Path) -> str | None:
    ids = list_run_ids_by_recency(trace_dir)
    return ids[0] if ids else None
