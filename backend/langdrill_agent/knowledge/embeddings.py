from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str = ""
    model: str = ""
    dimensions: int = 0
    enabled: bool = False


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(item_id, len(first_seen))
    return sorted(
        scores.items(),
        key=lambda item: (-item[1], first_seen[item[0]]),
    )
