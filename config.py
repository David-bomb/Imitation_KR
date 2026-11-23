"""Чтение настроек и проверка данных на входе."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class GeneratorConfig:
    enabled: bool = False
    probability: float = 0.35
    time_min: int = 1
    time_max: int = 20
    gpu_min: int = 1
    gpu_max: int = 32
    seed: int | None = None

    def validate(self, gpu_count: int) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("Флаг генератора должен быть true или false.")
        if type(self.probability) not in (float, int) or not 0 <= self.probability <= 1:
            raise ValueError("Вероятность должна быть от 0 до 1.")
        values = (self.time_min, self.time_max, self.gpu_min, self.gpu_max)
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError("Границы диапазонов должны быть положительными целыми числами.")
        if self.time_min > self.time_max:
            raise ValueError("Минимальная длительность больше максимальной.")
        if not self.gpu_min <= self.gpu_max <= gpu_count:
            raise ValueError("Диапазон GPU должен помещаться в кластере.")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("Seed должен быть целым числом или оставаться пустым.")


def validate_cluster(tick_ms: int, gpu_count: int) -> None:
    if type(tick_ms) is not int or not 1 <= tick_ms <= 2_147_483_647:
        raise ValueError("Тик должен быть целым числом от 1 до 2147483647 мс.")
    if type(gpu_count) is not int or gpu_count < 1:
        raise ValueError("Количество GPU должно быть положительным целым числом.")


def validate_node_penalty(value: float) -> None:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("Штраф за ноду должен быть конечным неотрицательным числом.")


def load_config(path: Path) -> tuple[int, int, GeneratorConfig, float]:
    with path.open("rb") as source:
        data = tomllib.load(source)
    tick_ms = data.get("tick_ms", 1000)
    gpu_count = data.get("gpu_count", 256)
    validate_cluster(tick_ms, gpu_count)
    node_penalty = data.get("node_penalty", 0.5)
    validate_node_penalty(node_penalty)
    settings = {"gpu_max": min(32, gpu_count)} | data.get("generator", {})
    generator = GeneratorConfig(**settings)
    generator.validate(gpu_count)
    return tick_ms, gpu_count, generator, node_penalty
