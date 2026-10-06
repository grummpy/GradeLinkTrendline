"""Ingest path: read mail, parse, and store. Duplicates are skipped by Message-ID."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gradelinktrendline.mailio import load_messages
from gradelinktrendline.parse import parse_message
from gradelinktrendline.store import Store


@dataclass
class IngestStats:
    messages_seen: int = 0
    messages_inserted: int = 0
    duplicates: int = 0
    observations: int = 0
    review: int = 0


def ingest_path(path: Path, store: Store) -> IngestStats:
    stats = IngestStats()
    for raw in load_messages(path):
        stats.messages_seen += 1
        observations = parse_message(raw)
        if not store.insert(raw, observations):
            stats.duplicates += 1
            continue
        stats.messages_inserted += 1
        stats.observations += len(observations)
        stats.review += sum(1 for item in observations if item.needs_review)
    return stats
