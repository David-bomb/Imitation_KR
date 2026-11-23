"""Оконный интерфейс. Запуск: python main.py."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from config import GeneratorConfig, load_config, validate_cluster
from simulation import Simulation

BG = "#f3f6fb"
WHITE = "#ffffff"
INK = "#17243b"
MUTED = "#68768d"
BLUE = "#315ee8"
RED = "#ed5c64"
BORDER = "#ccd5e2"
FREE = "#eaf0f7"
TABLE_COLUMNS = {
    "id": ("ID", 50, "id"),
    "name": ("Задача", 155, None),
    "gpu": ("GPU", 50, "gpu_count"),
    "ticks": ("Ост./всего", 95, "remaining"),
    "nodes": ("Нода: GPU", 110, None),
    "start": ("Старт", 65, "started_at"),
    "finish": ("Финиш", 70, "finished_at"),
}


class App(tk.Tk):
    def __init__(self, tick_ms=1000, gpu_count=256, generator=None, node_penalty=0.5):
        super().__init__()
        self.title("GPU Lab — симулятор датацентра")
        self.geometry(f"{min(1160, self.winfo_screenwidth() - 60)}x{min(820, self.winfo_screenheight() - 90)}")
        self.minsize(1020, 760)
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", foreground=INK, background=WHITE, font=("Segoe UI", 10))
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=WHITE)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Field.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Number.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("TButton", padding=(12, 6), background="#edf2fb", borderwidth=0)
        style.map("TButton", background=[("active", "#e0e8f8")])
        style.configure("Accent.TButton", background=BLUE, foreground=WHITE)
        style.map("Accent.TButton", background=[("active", "#254dcc"), ("disabled", "#a8b8ec")])
        style.configure("TEntry", padding=3, fieldbackground=WHITE)
        style.configure("Treeview", rowheight=28, fieldbackground=WHITE, borderwidth=0)
        style.configure("Treeview.Heading", background="#eef3fa", padding=(4, 7))
        style.map("Treeview", background=[("selected", "#dae5ff")], foreground=[("selected", INK)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 7), background="#e6edf7")
        style.map("TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", BLUE)])
        style.configure("TScrollbar", background="#d5deec", troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
        self.tick_var = tk.StringVar(value=str(tick_ms))
        self.gpu_var = tk.StringVar(value=str(gpu_count))
        self.node_penalty = node_penalty
        self.generator_config = generator or GeneratorConfig(gpu_max=min(32, gpu_count))
        self.simulation = None
        self.timer_id = None
        self.paused = False
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_setup()

    def field(self, parent, label, variable, row, column=0, width=12):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky="ew", padx=(0, 10), pady=2)
        ttk.Label(frame, text=label, style="Field.TLabel").pack(anchor="w", pady=(0, 2))
        entry = ttk.Entry(frame, textvariable=variable, width=width)
        entry.pack(fill="x")
        return entry

    def show_setup(self):
        self.page = ttk.Frame(self, style="App.TFrame")
        self.page.pack(fill="both", expand=True, padx=28, pady=28)
        card = ttk.Frame(self.page, padding=36, style="Card.TFrame")
        card.place(relx=0.5, rely=0.5, anchor="center", width=570)
        ttk.Label(card, text="GPU / LAB", foreground=BLUE, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(card, text="Ваш датацентр", style="Title.TLabel").pack(anchor="w", pady=(14, 6))
        ttk.Label(card, text="Настройте кластер и наблюдайте, как задачи занимают GPU.",
                  style="Muted.TLabel", wraplength=475).pack(anchor="w", pady=(0, 22))
        fields = ttk.Frame(card)
        fields.pack(fill="x")
        fields.columnconfigure((0, 1), weight=1)
        self.field(fields, "Длительность тика, мс", self.tick_var, 0)
        gpu_entry = self.field(fields, "Количество GPU", self.gpu_var, 0, 1)
        self.node_hint = ttk.Label(card, style="Muted.TLabel")
        self.node_hint.pack(anchor="w", pady=(8, 20))
        gpu_entry.bind("<KeyRelease>", self.update_node_hint)
        self.update_node_hint()
        self.setup_error = ttk.Label(card, foreground="#ba3544", wraplength=470)
        self.setup_error.pack(anchor="w", pady=(0, 8))
        ttk.Button(card, text="Старт  →", style="Accent.TButton", command=self.start).pack(fill="x")
        ttk.Label(card, text=f"8 GPU в ноде  ·  FIFO  ·  Добавка за ноду: {self.node_penalty:.0%}",
                  style="Muted.TLabel").pack(anchor="w", pady=(20, 0))

    def update_node_hint(self, event=None):
        try:
            count = int(self.gpu_var.get())
            text = f"Нод: {(count + 7) // 8}  ·  Последняя нода: {(count - 1) % 8 + 1} GPU" if count > 0 else ""
        except ValueError:
            text = ""
        self.node_hint.configure(text=text)

    def start(self):
        try:
            tick_ms, gpu_count = int(self.tick_var.get()), int(self.gpu_var.get())
            validate_cluster(tick_ms, gpu_count)
            settings = replace(self.generator_config,
                               gpu_min=min(self.generator_config.gpu_min, gpu_count),
                               gpu_max=min(self.generator_config.gpu_max, gpu_count))
            simulation = Simulation(gpu_count, settings, self.node_penalty)
        except ValueError as error:
            self.setup_error.configure(text=str(error) if not str(error).startswith("invalid literal")
                                       else "Введите целые числа для тика и количества GPU.")
            return
        self.tick_ms = tick_ms
        self.simulation = simulation
        self.paused = False
        self.page.destroy()
        self.build_dashboard()
        self.refresh()
        self.timer_id = self.after(self.tick_ms, self.on_timer)

    def build_dashboard(self):
        self.page = ttk.Frame(self, style="App.TFrame")
        self.page.pack(fill="both", expand=True, padx=24, pady=16)
        self.page.columnconfigure(0, weight=1)
        self.page.rowconfigure(2, weight=1)
        header = ttk.Frame(self.page, padding=(18, 8))
        header.grid(row=0, column=0, sticky="ew")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="GPU / LAB", foreground=BLUE, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.clock_label = ttk.Label(title, style="Heading.TLabel")
        self.clock_label.pack(anchor="w", pady=(2, 0))
        controls = ttk.Frame(header)
        controls.pack(side="right")
        self.pause_button = ttk.Button(controls, text="Пауза", command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=4)
        self.step_button = ttk.Button(controls, text="Один тик", command=self.single_step, state="disabled")
        self.step_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Новая симуляция", command=self.reset).pack(side="left", padx=(4, 0))

        stats = ttk.Frame(self.page, style="App.TFrame")
        stats.grid(row=1, column=0, sticky="ew", pady=12)
        self.stats = {}
        for index, (key, title) in enumerate((
            ("gpu", "Занято GPU"), ("queue", "В очереди"), ("running", "Выполняются"), ("done", "Завершены")
        )):
            stats.columnconfigure(index, weight=1, uniform="stats")
            card = ttk.Frame(stats, padding=(16, 6))
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            ttk.Label(card, text=title, style="Muted.TLabel").pack(anchor="w")
            value = ttk.Label(card, style="Number.TLabel")
            value.pack(anchor="w")
            self.stats[key] = value

        body = ttk.Frame(self.page, style="App.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        self.cluster_label = ttk.Label(left, background=BG, style="Muted.TLabel")
        self.cluster_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        cluster = ttk.Frame(left, style="App.TFrame")
        cluster.grid(row=1, column=0, sticky="nsew")
        cluster.rowconfigure(0, weight=1)
        cluster.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(cluster, bg=BG, highlightthickness=0, height=220)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(cluster, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", self.draw_nodes)
        self.canvas.bind("<MouseWheel>", self.scroll_nodes)
        self.canvas.bind("<Motion>", self.hover_gpu)
        self.canvas.bind("<Leave>", lambda event: self.tooltip.place_forget())
        self.tooltip = tk.Label(self.canvas, bg=INK, fg=WHITE, padx=10, pady=7, justify="left",
                                font=("Segoe UI", 9), wraplength=260)
        self.gpu_items = {}
        self.node_labels = {}
        ttk.Label(left, text="●  Занята    ○  Свободна    ×  Недоступна", background=BG,
                  style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 10))

        notebook = ttk.Notebook(left)
        notebook.grid(row=3, column=0, sticky="ew")
        self.tables = {}
        self.table_sort = {}
        for key, title in (("queue", "Очередь"), ("running", "Выполняются"), ("done", "Завершены")):
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=title)
            table = ttk.Treeview(frame, columns=tuple(TABLE_COLUMNS), show="headings", height=5, selectmode="browse")
            self.table_sort[key] = ("id", 1)
            for column, (label, width, attribute) in TABLE_COLUMNS.items():
                table.heading(column, text=label)
                if attribute:
                    table.heading(column, command=lambda key=key, column=column: self.toggle_sort(key, column))
                table.column(column, width=width, minwidth=35, anchor="w" if column in ("name", "nodes") else "center")
            vertical = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
            horizontal = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
            table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            table.grid(row=0, column=0, sticky="nsew")
            vertical.grid(row=0, column=1, sticky="ns")
            horizontal.grid(row=1, column=0, sticky="ew")
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            self.tables[key] = table

        side = ttk.Frame(body, padding=14)
        side.grid(row=0, column=1, sticky="ns")
        side.columnconfigure((0, 1), weight=1)
        ttk.Label(side, text="Добавить задачу", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.name_var = tk.StringVar()
        self.duration_var = tk.StringVar(value="5")
        self.request_var = tk.StringVar(value="9" if self.simulation.gpu_count >= 9 else "1")
        name_frame = ttk.Frame(side)
        name_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        name_frame.columnconfigure(0, weight=1)
        self.field(name_frame, "Название", self.name_var, 0, width=25)
        self.field(side, "Базовое время, тики", self.duration_var, 2, width=13)
        self.field(side, "Количество GPU", self.request_var, 2, 1, width=13)
        ttk.Button(side, text="+  В очередь", style="Accent.TButton", command=self.add_task).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 8))
        self.task_message = ttk.Label(side, wraplength=275, style="Muted.TLabel")
        self.task_message.grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Separator(side).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(side, text="Автогенератор", style="Heading.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")

        settings = self.simulation.generator
        self.enabled_var = tk.BooleanVar(value=settings.enabled)
        ttk.Checkbutton(side, text="Включён", variable=self.enabled_var, command=self.apply_generator).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 3))
        self.generator_vars = {
            key: tk.StringVar(value="" if value is None else str(value))
            for key, value in vars(settings).items() if key != "enabled"
        }
        self.field(side, "Вероятность, 0–1", self.generator_vars["probability"], 8, width=13)
        self.field(side, "Seed (необязательно)", self.generator_vars["seed"], 8, 1, width=13)
        self.field(side, "Базовые тики: мин.", self.generator_vars["time_min"], 9, width=13)
        self.field(side, "Базовые тики: макс.", self.generator_vars["time_max"], 9, 1, width=13)
        self.field(side, "GPU: минимум", self.generator_vars["gpu_min"], 10, width=13)
        self.field(side, "GPU: максимум", self.generator_vars["gpu_max"], 10, 1, width=13)
        ttk.Button(side, text="Применить настройки", command=self.apply_generator).grid(
            row=11, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        self.generator_message = ttk.Label(side, text="Не более одной новой задачи за тик.",
                                           style="Muted.TLabel", wraplength=275)
        self.generator_message.grid(row=12, column=0, columnspan=2, sticky="w")
        side.rowconfigure(13, weight=1)
        self.status_label = ttk.Label(self.page, background=BG, style="Muted.TLabel")
        self.status_label.grid(row=3, column=0, sticky="w", pady=(8, 0))

    def add_task(self):
        try:
            task = self.simulation.add_task(self.name_var.get(), int(self.duration_var.get()), int(self.request_var.get()))
        except ValueError as error:
            self.task_message.configure(text=str(error) if not str(error).startswith("invalid literal")
                                        else "Длительность и GPU должны быть целыми числами.", foreground="#ba3544")
            return
        self.name_var.set("")
        self.task_message.configure(text=f"Задача #{task.id} добавлена в очередь.", foreground=MUTED)
        self.refresh()

    def apply_generator(self):
        try:
            values = {key: variable.get().strip() for key, variable in self.generator_vars.items()}
            settings = GeneratorConfig(
                enabled=self.enabled_var.get(), probability=float(values["probability"].replace(",", ".")),
                time_min=int(values["time_min"]), time_max=int(values["time_max"]),
                gpu_min=int(values["gpu_min"]), gpu_max=int(values["gpu_max"]),
                seed=int(values["seed"]) if values["seed"] else None,
            )
            self.simulation.set_generator(settings)
        except ValueError as error:
            self.enabled_var.set(self.simulation.generator.enabled)
            self.generator_message.configure(text=str(error) if not str(error).startswith(("invalid literal", "could not convert"))
                                             else "Проверьте числовые значения настроек.", foreground="#ba3544")
            return
        self.generator_message.configure(text="Настройки применены." if settings.enabled else "Генератор выключен.",
                                         foreground=MUTED)

    def draw_nodes(self, event=None):
        width = self.canvas.winfo_width()
        if width < 20:
            return
        self.canvas.delete("all")
        self.tooltip.place_forget()
        self.gpu_items.clear()
        self.node_labels.clear()
        cell_width = width / 4
        for node in self.simulation.nodes:
            x, y = (node.id % 4) * cell_width, (node.id // 4) * 120
            right = x + cell_width - 10
            self.canvas.create_rectangle(x + 1, y + 1, right, y + 110, fill=WHITE, outline="#e3e9f2")
            self.canvas.create_text(x + 12, y + 17, text=f"node №{node.id + 1}", fill=INK,
                                    anchor="w", font=("Segoe UI", 10, "bold"))
            self.node_labels[node.id] = self.canvas.create_text(
                right - 10, y + 17, anchor="e", fill=MUTED, font=("Segoe UI", 8))
            gap = min(32, (cell_width - 28) / 4)
            for slot in range(8):
                cx = (x + right) / 2 + (slot % 4 - 1.5) * gap
                cy = y + 49 + (slot // 4) * 34
                tags = (f"gpu:{node.id}:{slot}",)
                circle = self.canvas.create_oval(cx - 11, cy - 11, cx + 11, cy + 11,
                                                 outline=BORDER, width=1, tags=tags)
                label = self.canvas.create_text(cx, cy, text=str(slot + 1) if slot < len(node.gpus) else "×",
                                                font=("Segoe UI", 8), tags=tags)
                self.gpu_items[node.id, slot] = (circle, label)
        rows = (len(self.simulation.nodes) + 3) // 4
        self.canvas.configure(scrollregion=(0, 0, width, max(self.canvas.winfo_height(), rows * 120)))
        self.paint_nodes()

    def paint_nodes(self):
        for node in self.simulation.nodes:
            if node.id in self.node_labels:
                used = len(node.gpus) - len(node.free)
                self.canvas.itemconfigure(self.node_labels[node.id], text=f"{used}/{len(node.gpus)}")
            for slot in range(8):
                if (node.id, slot) not in self.gpu_items:
                    continue
                circle, label = self.gpu_items[node.id, slot]
                present = slot < len(node.gpus)
                busy = present and node.gpus[slot] is not None
                self.canvas.itemconfigure(circle, fill=RED if busy else FREE if present else BG)
                self.canvas.itemconfigure(label, fill=WHITE if busy else MUTED if present else "#aab5c5")

    def hover_gpu(self, event):
        current = self.canvas.find_withtag("current")
        tags = self.canvas.gettags(current[0]) if current else ()
        tag = next((tag for tag in tags if tag.startswith("gpu:")), None)
        if not tag:
            self.tooltip.place_forget()
            return
        _, node_id, slot = tag.split(":")
        node, slot = self.simulation.nodes[int(node_id)], int(slot)
        if slot >= len(node.gpus):
            text = "Место недоступно: GPU отсутствует."
        elif node.gpus[slot] is None:
            text = f"node №{node.id + 1} · GPU {slot + 1}\nСвободна"
        else:
            task = self.simulation.tasks[node.gpus[slot]]
            text = (f"#{task.id} · {task.name}\nОсталось: {task.remaining} из {task.effective_ticks} тиков"
                    f"\nБазовое время: {task.time_ticks}; добавка: {task.effective_ticks - task.time_ticks}"
                    f"\nНод задачи: {len({node_id for node_id, _ in task.allocations})}")
        self.tooltip.configure(text=text)
        x = max(0, min(event.x + 14, self.canvas.winfo_width() - self.tooltip.winfo_reqwidth() - 8))
        y = max(0, min(event.y + 16, self.canvas.winfo_height() - self.tooltip.winfo_reqheight() - 8))
        self.tooltip.place(x=x, y=y)
        self.tooltip.lift()

    def scroll_nodes(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), "units")
        self.tooltip.place_forget()
        return "break"

    def toggle_sort(self, key, column):
        active, order = self.table_sort[key]
        order = (order + 1) % 3 if active == column else 1
        self.table_sort[key] = (column if order else None, order)
        self.refresh()

    def refresh(self):
        sim = self.simulation
        used = sum(len(task.allocations) for task in sim.running.values())
        for key, value in (("gpu", f"{used} / {sim.gpu_count}"), ("queue", len(sim.queue)),
                           ("running", len(sim.running)), ("done", len(sim.completed))):
            self.stats[key].configure(text=value)
        self.clock_label.configure(text=f"Тик {sim.tick}  ·  {self.tick_ms} мс")
        self.cluster_label.configure(text=f"Кластер  /  {len(sim.nodes)} нод  ·  Свободно {sim.gpu_count - used} GPU")
        self.paint_nodes()
        self.tooltip.place_forget()
        for key, tasks in (("queue", sim.queue), ("running", sim.running.values()), ("done", sim.completed)):
            table = self.tables[key]
            tasks = list(tasks)
            column, order = self.table_sort[key]
            for name, (label, _, _) in TABLE_COLUMNS.items():
                marker = (" ↑" if order == 1 else " ↓") if name == column else ""
                table.heading(name, text=label + marker)
            if column:
                attribute = TABLE_COLUMNS[column][2]
                # Пустые даты остаются внизу при обоих направлениях.
                missing = [task for task in tasks if getattr(task, attribute) is None]
                tasks = sorted(
                    (task for task in tasks if getattr(task, attribute) is not None),
                    key=lambda task: getattr(task, attribute), reverse=order == 2,
                ) + missing
            existing = set(table.get_children())
            ids = {str(task.id) for task in tasks}
            for item in existing - ids:
                table.delete(item)
            for position, task in enumerate(tasks):
                counts = Counter(node_id + 1 for node_id, _ in task.allocations)
                nodes = ", ".join(f"{node}: {count}" for node, count in sorted(counts.items())) or "—"
                values = (task.id, task.name, task.gpu_count, f"{task.remaining}/{task.effective_ticks or task.time_ticks}", nodes,
                          task.started_at if task.started_at is not None else "—",
                          task.finished_at if task.finished_at is not None else "—")
                if str(task.id) in existing:
                    table.item(str(task.id), values=values)
                else:
                    table.insert("", "end", iid=str(task.id), values=values)
                table.move(str(task.id), "", position)
        prefix = "Пауза" if self.paused else "Симуляция работает"
        if sim.queue:
            task = sim.queue[0]
            detail = f"Первая в очереди: #{task.id}, требуется {task.gpu_count} GPU."
        else:
            detail = "Очередь пуста — добавьте задачу или включите генератор."
        self.status_label.configure(text=f"{prefix}  ·  {detail}  ·  Добавка за ноду: {self.node_penalty:.0%}")

    def on_timer(self):
        self.timer_id = None
        self.simulation.step()
        self.refresh()
        self.timer_id = self.after(self.tick_ms, self.on_timer)

    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        else:
            self.timer_id = self.after(self.tick_ms, self.on_timer)
        self.pause_button.configure(text="Продолжить" if self.paused else "Пауза")
        self.step_button.configure(state="normal" if self.paused else "disabled")
        self.refresh()

    def single_step(self):
        if self.paused:
            self.simulation.step()
            self.refresh()

    def reset(self):
        if self.timer_id is not None:
            self.after_cancel(self.timer_id)
            self.timer_id = None
        self.generator_config = self.simulation.generator
        self.simulation = None
        self.page.destroy()
        self.show_setup()

    def close(self):
        if self.timer_id is not None:
            self.after_cancel(self.timer_id)
        self.destroy()


def main():
    try:
        settings = load_config(Path(__file__).with_name("config.toml"))
    except (OSError, ValueError, TypeError) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Ошибка конфигурации", f"Проверьте config.toml:\n{error}", parent=root)
        root.destroy()
        return
    App(*settings).mainloop()


if __name__ == "__main__":
    main()
