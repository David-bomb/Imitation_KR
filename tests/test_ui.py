"""Интеграционные проверки Tk: требуют доступного графического сеанса."""

import tkinter as tk
import unittest

from main import App, BORDER, RED


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = App()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.app.withdraw()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()

    def test_start_pause_step_resume_reset(self):
        app = self.app
        app.gpu_var.set("250")
        app.start()
        app.update_idletasks()
        sim = app.simulation
        self.assertEqual(len(sim.nodes), 32)
        self.assertEqual(len(sim.nodes[-1].gpus), 2)
        first_timer = app.timer_id
        self.assertIn(first_timer, app.tk.call("after", "info"))
        app.toggle_pause()
        self.assertIsNone(app.timer_id)
        self.assertNotIn(first_timer, app.tk.call("after", "info"))
        app.name_var.set("test")
        app.duration_var.set("1")
        app.request_var.set("9")
        app.add_task()
        self.assertEqual(len(app.tables["queue"].get_children()), 1)
        app.single_step()
        self.assertEqual(sim.tick, 1)
        self.assertEqual(len(app.tables["running"].get_children()), 1)
        app.draw_nodes()
        if app.gpu_items:
            circle, _ = app.gpu_items[0, 0]
            self.assertEqual(app.canvas.itemcget(circle, "fill"), RED)
            self.assertEqual(app.canvas.itemcget(circle, "outline"), BORDER)
        self.assertEqual(app.tables["running"].set("1", "ticks"), "2/2")
        app.single_step()
        self.assertEqual(app.tables["running"].set("1", "ticks"), "1/2")
        app.single_step()
        self.assertEqual(len(app.tables["done"].get_children()), 1)
        app.toggle_pause()
        self.assertIsNotNone(app.timer_id)
        app.single_step()
        self.assertEqual(sim.tick, 3)
        app.reset()
        self.assertIsNone(app.simulation)
        self.assertIsNone(app.timer_id)
        app.start()
        self.assertEqual(app.simulation.tick, 0)

    def test_invalid_forms_do_not_change_state(self):
        app = self.app
        app.tick_var.set("bad")
        app.start()
        self.assertIsNone(app.simulation)
        app.tick_var.set("1000")
        app.start()
        app.toggle_pause()
        app.name_var.set("test")
        app.duration_var.set("0")
        app.add_task()
        self.assertFalse(app.simulation.queue)
        before = app.simulation.generator
        app.generator_vars["probability"].set("2")
        app.enabled_var.set(True)
        app.apply_generator()
        self.assertEqual(app.simulation.generator, before)
        self.assertFalse(app.enabled_var.get())
        app.generator_vars["probability"].set("1")
        app.generator_vars["seed"].set("42")
        app.enabled_var.set(True)
        app.apply_generator()
        app.single_step()
        self.assertEqual(len(app.simulation.tasks), 1)

    def test_resize_and_scroll_partial_node(self):
        app = self.app
        app.gpu_var.set("250")
        app.start()
        app.toggle_pause()
        app.deiconify()
        app.update()
        app.draw_nodes()
        self.assertEqual(len(app.gpu_items), 256)
        self.assertEqual(len(app.node_labels), 32)
        for node in (0, 1, 2, 3):
            self.assertEqual(app.canvas.coords(app.node_labels[node])[1], 17)
        self.assertEqual(app.canvas.coords(app.node_labels[4])[1], 137)
        app.canvas.yview_moveto(1)
        self.assertGreater(app.canvas.yview()[0], 0)
        _, missing = app.gpu_items[31, 2]
        self.assertEqual(app.canvas.itemcget(missing, "text"), "×")
        app.geometry("1020x760")
        app.update()
        for widget in (app.generator_message, app.status_label):
            bottom = widget.winfo_rooty() - app.winfo_rooty() + widget.winfo_height()
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(bottom, app.winfo_height())


    def test_table_sort_cycle_numeric_values_and_exclusive_columns(self):
        app = self.app
        app.start()
        app.toggle_pause()
        sim = app.simulation
        for gpu, duration in [(10, 2), (2, 10), (2, 1)] + [(20, 20)] * 9:
            sim.add_task("test", duration, gpu)
        app.refresh()
        table = app.tables["queue"]
        natural = tuple(str(i) for i in range(1, 13))
        self.assertEqual(table.get_children(), natural)
        self.assertEqual(table.heading("id", "text"), "ID ↑")
        table.selection_set("2")

        app.tk.call(table.heading("id", "command"))
        self.assertEqual(table.get_children(), natural[::-1])
        app.tk.call(table.heading("id", "command"))
        self.assertEqual(table.get_children(), natural)
        self.assertEqual(app.table_sort["queue"], (None, 0))
        app.tk.call(table.heading("id", "command"))
        self.assertEqual(table.heading("id", "text"), "ID ↑")

        app.tk.call(table.heading("gpu", "command"))
        self.assertEqual(table.get_children(), ("2", "3", "1") + natural[3:])
        self.assertEqual(table.heading("id", "text"), "ID")
        app.tk.call(table.heading("gpu", "command"))
        self.assertEqual(table.get_children(), natural[3:] + ("1", "2", "3"))
        app.tk.call(table.heading("ticks", "command"))
        self.assertEqual(table.get_children(), ("3", "1", "2") + natural[3:])
        self.assertEqual(table.heading("gpu", "text"), "GPU")
        self.assertTrue(table.heading("ticks", "text").endswith(" ↑"))
        app.tk.call(table.heading("ticks", "command"))
        self.assertEqual(table.get_children(), natural[3:] + ("2", "1", "3"))
        app.tk.call(table.heading("ticks", "command"))
        self.assertEqual(table.get_children(), natural)
        for column in ("start", "finish"):
            for _ in range(3):
                app.tk.call(table.heading(column, "command"))
                self.assertEqual(table.get_children(), natural)
        self.assertEqual(table.selection(), ("2",))
        self.assertEqual(tuple(str(t.id) for t in sim.queue), natural)
        self.assertEqual(app.table_sort["running"], ("id", 1))
        self.assertEqual(app.table_sort["done"], ("id", 1))
        self.assertFalse(table.heading("name", "command"))
        self.assertFalse(table.heading("nodes", "command"))

    def test_sorting_updates_each_tick_without_changing_fifo(self):
        app = self.app
        app.start()
        app.toggle_pause()
        sim = app.simulation
        sim.add_task("long", 10, 1)
        sim.add_task("short", 2, 1)
        app.single_step()
        table = app.tables["running"]
        app.tk.call(table.heading("ticks", "command"))
        table.selection_set("1")
        self.assertEqual(table.get_children(), ("2", "1"))
        sim.add_task("new", 1, 1)
        app.single_step()
        self.assertEqual(table.get_children(), ("2", "3", "1"))
        self.assertEqual(table.set("2", "ticks"), "1/2")
        self.assertEqual(table.selection(), ("1",))
        self.assertEqual(app.table_sort["running"], ("ticks", 1))

        head = sim.add_task("blocked", 1, 256)
        tail = sim.add_task("small", 1, 1)
        app.refresh()
        queue_table = app.tables["queue"]
        app.tk.call(queue_table.heading("gpu", "command"))
        self.assertEqual(queue_table.get_children(), (str(tail.id), str(head.id)))
        app.single_step()
        self.assertEqual(list(sim.queue), [head, tail])
        self.assertIsNone(tail.started_at)
        self.assertEqual(table.get_children(), ("1",))
        self.assertEqual(app.table_sort["queue"], ("gpu", 1))
        self.assertEqual(app.table_sort["done"], ("id", 1))

    def test_completed_date_sorting_natural_order_and_reset(self):
        app = self.app
        app.start()
        app.toggle_pause()
        sim = app.simulation
        sim.add_task("old but slow", 12, 1)
        sim.add_task("quick", 2, 1)
        app.single_step()
        app.single_step()
        sim.add_task("later", 1, 1)
        for _ in range(11):
            app.single_step()
        self.assertEqual([task.id for task in sim.completed], [2, 3, 1])
        table = app.tables["done"]
        self.assertEqual(table.get_children(), ("1", "2", "3"))
        app.tk.call(table.heading("finish", "command"))
        self.assertEqual(table.get_children(), ("2", "3", "1"))
        app.tk.call(table.heading("finish", "command"))
        self.assertEqual(table.get_children(), ("1", "3", "2"))
        app.tk.call(table.heading("finish", "command"))
        self.assertEqual(table.get_children(), ("2", "3", "1"))
        app.tk.call(table.heading("start", "command"))
        self.assertEqual(table.get_children(), ("2", "1", "3"))
        app.tk.call(table.heading("start", "command"))
        self.assertEqual(table.get_children(), ("3", "2", "1"))
        self.assertEqual([task.id for task in sim.completed], [2, 3, 1])
        app.reset()
        app.start()
        for key, table in app.tables.items():
            self.assertEqual(app.table_sort[key], ("id", 1))
            self.assertEqual(table.heading("id", "text"), "ID ↑")
