"""Детерминированный движок; один step() равен одному логическому тику."""

from collections import deque
from fractions import Fraction
from math import ceil
import random

from config import GeneratorConfig, validate_node_penalty
from models import Node, Task


def allocate(nodes: list[Node], requested: int) -> list[tuple[int, int]] | None:
    """Сначала полные восьмёрки, затем минимум нод и новых пустых нод."""
    available = [(node, node.free) for node in nodes if None in node.gpus]
    if sum(len(slots) for _, slots in available) < requested:
        return None

    full = sorted(
        (item for item in available if len(item[1]) == 8),
        key=lambda item: item[0].id,
    )[:requested // 8]
    allocations = [(node.id, slot) for node, slots in full for slot in slots]
    remaining = requested - len(allocations)
    if not remaining:
        return allocations

    selected_ids = {node.id for node, _ in full}
    available = sorted(
        (item for item in available if item[0].id not in selected_ids),
        key=lambda item: (-len(item[1]), item[0].id),
    )
    occupied = [item for item in available if len(item[1]) < len(item[0].gpus)]
    empty = [item for item in available if len(item[1]) == len(item[0].gpus)]

    capacity = 0
    for count, (_, slots) in enumerate(available, 1):
        capacity += len(slots)
        if capacity >= remaining:
            break

    for empty_count in range(count + 1):
        chosen = occupied[:count - empty_count] + empty[:empty_count]
        if len(chosen) == count and sum(len(slots) for _, slots in chosen) >= remaining:
            break

    for node, slots in sorted(chosen, key=lambda item: (-len(item[1]), item[0].id)):
        take = min(remaining, len(slots))
        allocations.extend((node.id, slot) for slot in slots[:take])
        remaining -= take
    return allocations


class Simulation:
    def __init__(self, gpu_count: int, generator: GeneratorConfig | None = None, node_penalty: float = 0.5):
        if type(gpu_count) is not int or gpu_count < 1:
            raise ValueError("Количество GPU должно быть положительным целым числом.")
        validate_node_penalty(node_penalty)
        # Точная десятичная дробь исключает лишний тик из-за округления float.
        self.node_penalty = Fraction(str(node_penalty))
        self.gpu_count = gpu_count
        self.nodes = [
            Node(index // 8, [None] * min(8, gpu_count - index))
            for index in range(0, gpu_count, 8)
        ]
        self.tick = 0
        self.tasks: dict[int, Task] = {}
        self.queue: deque[Task] = deque()
        self.running: dict[int, Task] = {}
        self.completed: list[Task] = []
        self.generator = generator or GeneratorConfig(gpu_max=min(32, gpu_count))
        self.generator.validate(gpu_count)
        self.random = random.Random(self.generator.seed)
        self.generated_count = 0

    def add_task(self, name: str, time_ticks: int, gpu_count: int) -> Task:
        name = name.strip()
        if not name:
            raise ValueError("Введите название задачи.")
        if type(time_ticks) is not int or time_ticks < 1:
            raise ValueError("Длительность должна быть положительным целым числом.")
        if type(gpu_count) is not int or not 1 <= gpu_count <= self.gpu_count:
            raise ValueError(f"Задача должна запрашивать от 1 до {self.gpu_count} GPU.")
        task = Task(len(self.tasks) + 1, name, time_ticks, gpu_count, time_ticks)
        self.tasks[task.id] = task
        self.queue.append(task)
        return task

    def set_generator(self, settings: GeneratorConfig) -> None:
        settings.validate(self.gpu_count)
        if settings.seed != self.generator.seed:
            self.random.seed(settings.seed)
        self.generator = settings

    def step(self) -> None:
        self.tick += 1
        previous = list(self.running.values())
        settings = self.generator
        if settings.enabled and self.random.random() < settings.probability:
            self.generated_count += 1
            self.add_task(
                f"Автозадача {self.generated_count:03}",
                self.random.randint(settings.time_min, settings.time_max),
                self.random.randint(settings.gpu_min, settings.gpu_max),
            )

        while self.queue:
            task = self.queue[0]
            placement = allocate(self.nodes, task.gpu_count)
            if placement is None:
                break
            self.queue.popleft()
            task.allocations = placement
            node_count = len({node_id for node_id, _ in placement})
            task.effective_ticks = ceil(task.time_ticks * (1 + self.node_penalty * (node_count - 1)))
            task.remaining = task.effective_ticks
            task.started_at = self.tick
            for node_id, slot in placement:
                self.nodes[node_id].gpus[slot] = task.id
            self.running[task.id] = task

        for task in previous:
            task.remaining -= 1
            if task.remaining == 0:
                task.finished_at = self.tick
                for node_id, slot in task.allocations:
                    self.nodes[node_id].gpus[slot] = None
                del self.running[task.id]
                self.completed.append(task)
