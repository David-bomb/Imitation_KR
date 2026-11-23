from collections import Counter
from dataclasses import replace
from itertools import combinations, product
import random
import unittest

from config import GeneratorConfig
from models import Node
from simulation import Simulation, allocate


def cluster(*capacities):
    """Каждая пара — (фактическая ёмкость, число свободных GPU)."""
    return [
        Node(i, [None] * free + [-1] * (capacity - free))
        for i, (capacity, free) in enumerate(capacities)
    ]


class AllocationTests(unittest.TestCase):
    def test_agreed_examples(self):
        examples = [
            ([(8, 8), (8, 5), (8, 4)], 9, {0: 8, 1: 1}),
            ([(8, 5), (8, 4)], 9, {0: 5, 1: 4}),
            ([(8, 8), (8, 8), (8, 4), (8, 3)], 15, {0: 8, 1: 7}),
            ([(8, 8), (8, 6)], 14, {0: 8, 1: 6}),
            ([(8, 8), (8, 8), (8, 1)], 17, {0: 8, 1: 8, 2: 1}),
            ([(8, 4), (8, 4), (8, 8)], 8, {2: 8}),
            ([(8, 4), (8, 3), (8, 8)], 7, {2: 7}),
            ([(8, 8), (8, 5), (8, 4)], 17, {0: 8, 1: 5, 2: 4}),
            ([(8, 5), (8, 5), (6, 6)], 10, {0: 5, 1: 5}),
            ([(8, 7), (8, 7), (2, 2)], 16, {0: 7, 1: 7, 2: 2}),
        ]
        for capacities, request, expected in examples:
            with self.subTest(capacities=capacities, request=request):
                nodes = cluster(*capacities)
                before = [node.gpus[:] for node in nodes]
                placement = allocate(nodes, request)
                self.assertEqual(Counter(node for node, _ in placement), expected)
                self.assertEqual(len(placement), request)
                self.assertEqual(len(set(placement)), request)
                self.assertEqual([node.gpus for node in nodes], before)

    def test_not_enough_gpus_and_stable_slot_order(self):
        nodes = [Node(0, [10, None, 10, None]), Node(1, [None] * 8)]
        self.assertIsNone(allocate(nodes, 11))
        self.assertEqual(allocate(nodes, 9), [(1, slot) for slot in range(8)] + [(0, 1)])

    def test_matches_exhaustive_search_after_full_groups(self):
        # Эталон перебирает все подмножества; он не повторяет рабочий алгоритм.
        for specs in product(((8, 8), (8, 5), (8, 3), (2, 2)), repeat=3):
            nodes = cluster(*specs)
            total = sum(free for _, free in specs)
            for request in range(1, total + 1):
                full_ids = [n.id for n in nodes if len(n.gpus) == len(n.free) == 8][:request // 8]
                remaining = request - 8 * len(full_ids)
                candidates = [n for n in nodes if n.id not in full_ids]
                costs = []
                for count in range(len(candidates) + 1):
                    for subset in combinations(candidates, count):
                        if sum(len(n.free) for n in subset) >= remaining:
                            costs.append((count, sum(len(n.free) == len(n.gpus) for n in subset)))
                placement = allocate(nodes, request)
                counts = Counter(node for node, _ in placement)
                self.assertTrue(all(counts[node] == 8 for node in full_ids))
                tail_ids = set(counts) - set(full_ids)
                actual = (len(tail_ids), sum(len(nodes[i].free) == len(nodes[i].gpus) for i in tail_ids))
                self.assertEqual(actual, min(costs), (specs, request, placement))


class SimulationTests(unittest.TestCase):
    def test_cluster_sizes(self):
        for count, sizes in ((256, [8] * 32), (250, [8] * 31 + [2]), (1, [1])):
            sim = Simulation(count)
            self.assertEqual([len(n.gpus) for n in sim.nodes], sizes)

    def test_lifecycle_and_next_tick_reuse(self):
        sim = Simulation(8)
        first = sim.add_task("one", 1, 8)
        second = sim.add_task("two", 2, 8)
        sim.step()
        self.assertEqual((first.started_at, first.remaining, second.started_at), (1, 1, None))
        sim.step()
        self.assertEqual((first.finished_at, second.started_at, second.remaining), (2, None, 2))
        self.assertTrue(all(owner is None for owner in sim.nodes[0].gpus))
        sim.step()
        self.assertEqual((second.started_at, second.remaining), (3, 2))
        sim.step()
        sim.step()
        self.assertEqual((second.finished_at, second.remaining), (5, 0))

    def test_fifo_blocking_and_multiple_starts(self):
        sim = Simulation(16)
        first = sim.add_task("busy", 2, 12)
        large = sim.add_task("head", 1, 8)
        small = sim.add_task("tail", 1, 1)
        sim.step()
        self.assertEqual(list(sim.running), [first.id])
        self.assertEqual(list(sim.queue), [large, small])
        sim.step()
        sim.step()
        self.assertIsNone(small.started_at)
        sim.step()
        self.assertIsNone(small.started_at)
        sim.step()
        self.assertEqual((large.started_at, small.started_at), (5, 5))

    def test_penalty_duration_and_next_tick_reuse(self):
        for gpus, expected in ((8, 20), (9, 30), (17, 40), (25, 50)):
            with self.subTest(gpus=gpus):
                sim = Simulation(gpus)
                task = sim.add_task("penalty", 20, gpus)
                waiting = sim.add_task("next", 1, gpus)
                self.assertIsNone(task.effective_ticks)
                sim.step()
                self.assertEqual((task.time_ticks, task.effective_ticks, task.remaining), (20, expected, expected))
                for _ in range(expected):
                    sim.step()
                self.assertEqual((task.finished_at, task.remaining), (1 + expected, 0))
                self.assertIsNone(waiting.started_at)
                self.assertEqual(waiting.remaining, 1)
                sim.step()
                self.assertEqual(waiting.started_at, expected + 2)

    def test_penalty_uses_actual_fragmented_placement(self):
        sim = Simulation(24)
        for node in sim.nodes:
            node.gpus[3:] = [-1] * 5
        task = sim.add_task("fragmented", 20, 9)
        sim.step()
        self.assertEqual(Counter(n for n, _ in task.allocations), {0: 3, 1: 3, 2: 3})
        self.assertEqual(task.effective_ticks, 40)

    def test_penalty_rounding_and_disabled_mode(self):
        for duration, penalty, expected in ((1, .5, 2), (3, .5, 5), (100, .1, 110), (3, 0, 3)):
            with self.subTest(duration=duration, penalty=penalty):
                sim = Simulation(10, node_penalty=penalty)
                task = sim.add_task("rounding", duration, 10)
                sim.step()
                self.assertEqual(task.effective_ticks, expected)
                self.assertEqual(task.time_ticks, duration)

    def test_invalid_penalty(self):
        for value in (-.1, True, "0.5", float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Simulation(8, node_penalty=value)

    def test_input_errors_are_atomic(self):
        sim = Simulation(8)
        for name, duration, gpus in (("", 1, 1), ("x", 0, 1), ("x", 1, 9), ("x", 1, 0), ("x", True, 1)):
            with self.assertRaises(ValueError):
                sim.add_task(name, duration, gpus)
        self.assertFalse(sim.tasks)
        self.assertEqual(sim.add_task(" x ", 1, 1).name, "x")
        self.assertEqual(sim.add_task("x", 1, 1).id, 2)

    def test_generator_probability_limits_and_seed(self):
        settings = GeneratorConfig(enabled=True, probability=0, gpu_max=8, seed=42)
        sim = Simulation(8, settings)
        for _ in range(10):
            sim.step()
        self.assertEqual(len(sim.tasks), 0)
        settings = replace(settings, probability=1, time_min=2, time_max=4, gpu_min=2)
        left, right = Simulation(8, settings), Simulation(8, settings)
        for _ in range(25):
            left.step()
            right.step()
        self.assertEqual(left.tasks, right.tasks)
        self.assertEqual(len(left.tasks), 25)
        self.assertTrue(all(2 <= t.time_ticks <= 4 and 2 <= t.gpu_count <= 8 for t in left.tasks.values()))
        before = left.random.getstate()
        left.set_generator(replace(settings, enabled=False))
        self.assertEqual(left.random.getstate(), before)
        left.step()
        self.assertEqual(len(left.tasks), 25)

    def test_invalid_generator_does_not_replace_settings(self):
        sim = Simulation(8)
        before = sim.generator
        for settings in (
            replace(before, probability=float("nan")), replace(before, probability=2),
            replace(before, time_min=21), replace(before, gpu_max=9), replace(before, seed=1.5)
        ):
            with self.assertRaises(ValueError):
                sim.set_generator(settings)
            self.assertIs(sim.generator, before)

    def test_long_run_resource_invariants(self):
        sim = Simulation(26, GeneratorConfig(enabled=True, probability=0.7, gpu_max=26, seed=19))
        rng = random.Random(12)
        for _ in range(350):
            if rng.random() < 0.3:
                sim.add_task("manual", rng.randint(1, 8), rng.randint(1, 26))
            sim.step()
            allocations = {}
            for task in sim.running.values():
                self.assertGreater(task.remaining, 0)
                self.assertEqual(len(task.allocations), task.gpu_count)
                self.assertEqual(sim.tick - task.started_at, task.effective_ticks - task.remaining)
                for gpu in task.allocations:
                    self.assertNotIn(gpu, allocations)
                    allocations[gpu] = task.id
            actual = {(node.id, slot): owner for node in sim.nodes
                      for slot, owner in enumerate(node.gpus) if owner is not None}
            self.assertEqual(actual, allocations)
            self.assertTrue(all(t.remaining == t.time_ticks and not t.allocations for t in sim.queue))
            self.assertTrue(all(t.remaining == 0 and t.finished_at - t.started_at == t.effective_ticks
                                for t in sim.completed))


if __name__ == "__main__":
    unittest.main()
