"""Данные симуляции. Номера нод и GPU внутри модели начинаются с нуля."""

from dataclasses import dataclass, field


@dataclass
class Node:
    id: int
    gpus: list[int | None]

    @property
    def free(self) -> list[int]:
        return [slot for slot, owner in enumerate(self.gpus) if owner is None]


@dataclass
class Task:
    id: int
    name: str
    time_ticks: int
    gpu_count: int
    remaining: int
    effective_ticks: int | None = None
    allocations: list[tuple[int, int]] = field(default_factory=list)
    started_at: int | None = None
    finished_at: int | None = None
