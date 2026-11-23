from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from config import load_config, validate_cluster


class ConfigTests(unittest.TestCase):
    def test_project_defaults(self):
        tick, gpu, generator, penalty = load_config(Path(__file__).resolve().parents[1] / "config.toml")
        self.assertEqual((tick, gpu, generator.enabled, generator.gpu_max), (1000, 256, False, 32))
        self.assertEqual(penalty, 0.5)

    def test_small_cluster_default_and_invalid_files(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            path.write_text("gpu_count = 2\n", encoding="utf-8")
            self.assertEqual(load_config(path)[2].gpu_max, 2)
            for source in ("tick_ms = 0", "gpu_count = true", "not toml", "[generator]\nprobability = 2",
                           "node_penalty = -0.1", "node_penalty = true", "node_penalty = nan",
                           "node_penalty = inf", 'node_penalty = "0.5"'):
                path.write_text(source, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_node_penalty_config(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            for value in (0, 0.1, 0.5, 2):
                path.write_text(f"node_penalty = {value}\n", encoding="utf-8")
                self.assertEqual(load_config(path)[3], value)

    def test_positive_integers(self):
        for tick, gpu in ((0, 256), (1000, 0), (True, 8), (1.5, 8), (2**31, 8)):
            with self.assertRaises(ValueError):
                validate_cluster(tick, gpu)
