import json
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent)
MACRO_DIR = ROOT / "macros"
SETTINGS_FILE = ROOT / "macro_settings.json"
WINDOW_FILE = ROOT / "window_config.json"


def read_json(path):
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    value = read_json(SETTINGS_FILE)
    if not isinstance(value, dict):
        raise ValueError(f"{SETTINGS_FILE.name} phải chứa một object JSON.")
    return value


def load_macros():
    macros = {}
    candidates = list(ROOT.glob("*.json"))
    if MACRO_DIR.exists():
        candidates.extend(MACRO_DIR.glob("*.json"))

    ignored = {"macro_settings.json", "window_config.json"}
    for path in candidates:
        if path.name.lower() in ignored:
            continue
        document = read_json(path)
        if isinstance(document, list):
            macros[path.stem] = {"steps": document, "path": path}
        elif isinstance(document, dict):
            for name, steps in document.items():
                if name.startswith("__") or not isinstance(steps, list):
                    continue
                macros.setdefault(name, {"steps": steps, "path": path})

    return macros


def format_condition(config):
    return str(config.get("cond_mode", "Tắt quét ảnh (Chạy luôn)"))


def image_paths_for(config):
    paths = config.get("cond_images") or []
    if not paths and config.get("cond_image"):
        paths = [config["cond_image"]]

    resolved = []
    for raw_path in paths:
        path = Path(str(raw_path))
        if path.is_file():
            resolved.append(path)
            continue
        candidate = MACRO_DIR / "images" / path.name
        resolved.append(candidate)
    return resolved


class MacroRunner:
    def __init__(self, status_callback):
        self.stop_event = threading.Event()
        self.status_callback = status_callback

    def stop(self):
        self.stop_event.set()

    def _wait(self, seconds):
        end_time = time.monotonic() + max(0, seconds)
        while time.monotonic() < end_time:
            if self.stop_event.wait(min(0.05, end_time - time.monotonic())):
                return False
        return not self.stop_event.is_set()

    def _window(self, title):
        import pygetwindow

        windows = [window for window in pygetwindow.getWindowsWithTitle(title)
                   if window.width > 0 and window.height > 0]
        if not windows:
            raise RuntimeError(f"Không tìm thấy cửa sổ có tiêu đề “{title}”.")
        window = windows[0]
        window.activate()
        if not self._wait(0.3):
            return None
        return window

    @staticmethod
    def _image_matches(window, config):
        import cv2
        import numpy as np
        import pyautogui

        paths = image_paths_for(config)
        if not paths:
            raise RuntimeError("Điều kiện ảnh được bật nhưng chưa có ảnh mẫu.")

        region = (window.left, window.top, window.width, window.height)
        screen = cv2.cvtColor(np.array(pyautogui.screenshot(region=region)),
                              cv2.COLOR_RGB2GRAY)
        confidence = float(config.get("confidence", 0.8))
        results = []
        for path in paths:
            if not path.is_file():
                raise RuntimeError(f"Không tìm thấy ảnh điều kiện: {path.name}")
            template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                raise RuntimeError(f"Không đọc được ảnh điều kiện: {path.name}")
            height, width = template.shape[:2]
            if height > screen.shape[0] or width > screen.shape[1]:
                results.append(False)
                continue
            match = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            results.append(float(cv2.minMaxLoc(match)[1]) >= confidence)

        mode = format_condition(config).lower()
        logic = str(config.get("logic_mode", "AND")).upper()
        if "đủ ảnh" in mode or "all" in mode:
            return all(results)
        if "k.có ảnh" in mode or "không có ảnh" in mode:
            return not all(results) if logic == "OR" else not any(results)
        if "có ảnh" in mode or "chờ đến khi" in mode or "wait" in mode:
            return any(results)
        if logic == "OR":
            return any(results)
        return all(results)

    def _condition(self, window, config):
        mode = format_condition(config).lower()
        if "tắt quét ảnh" in mode:
            return True

        timeout = float(config.get("timeout", 60))
        if timeout <= 0:
            timeout = 60
        deadline = time.monotonic() + timeout
        wait_for_image = "chờ đến khi" in mode or "wait" in mode
        while not self.stop_event.is_set():
            matched = self._image_matches(window, config)
            if wait_for_image:
                if matched:
                    return True
            else:
                return matched
            if time.monotonic() >= deadline:
                return False
            self.status_callback("Đang chờ điều kiện ảnh…")
            if not self._wait(0.25):
                return False
        return False

    def _fallback(self, window, config):
        action = str(config.get("fallback_action", "SKIP")).upper()
        if action == "RETRY":
            retries = max(0, int(config.get("fallback_retry_count", 3)))
            wait = max(0, float(config.get("fallback_retry_wait", 5)))
            for _ in range(retries):
                if not self._wait(wait):
                    return False
                if self._condition(window, config):
                    return True
        return False

    def _play_steps(self, window, steps, config):
        import pyautogui

        speed = float(str(config.get("speed", "1.0x")).lower().replace("x", ""))
        if speed <= 0:
            raise ValueError("Tốc độ phải lớn hơn 0.")
        loops = max(1, int(config.get("loops", 1)))
        for loop_index in range(loops):
            for index, step in enumerate(steps, 1):
                if self.stop_event.is_set():
                    return
                kind = step.get("type")
                if kind == "click":
                    x = window.left + int(step["x"])
                    y = window.top + int(step["y"])
                    if not (window.left <= x < window.left + window.width and
                            window.top <= y < window.top + window.height):
                        raise RuntimeError(
                            f"Toạ độ click ở bước {index} nằm ngoài cửa sổ mục tiêu.")
                    button = str(step.get("button", "left"))
                    if button not in {"left", "right", "middle"}:
                        raise ValueError(f"Nút chuột không hỗ trợ ở bước {index}: {button}")
                    pyautogui.click(x=x, y=y, button=button)
                elif kind == "key":
                    key = str(step["key"]).lower()
                    pyautogui.press(key)
                else:
                    raise ValueError(f"Loại thao tác không hỗ trợ ở bước {index}: {kind}")
                delay = max(0, float(step.get("delay", 0))) / speed
                self.status_callback(
                    f"Vòng {loop_index + 1}/{loops} · Bước {index}/{len(steps)}"
                )
                if not self._wait(delay):
                    return

    def run(self, macro_names, macros, settings, window_title):
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            window = self._window(window_title)
            if window is None:
                self.status_callback("Đã dừng.")
                return

            index = 0
            while index < len(macro_names) and not self.stop_event.is_set():
                name = macro_names[index]
                macro = macros[name]
                config = settings.get(name, {})
                self.status_callback(f"Kiểm tra điều kiện: {name}")
                if not self._condition(window, config):
                    if self.stop_event.is_set():
                        break
                    if self._fallback(window, config):
                        pass
                    else:
                        action = str(config.get("fallback_action", "SKIP")).upper()
                        if action == "GOTO":
                            target = int(config.get("fallback_goto_step", 0))
                            if target < 0 or target >= len(macro_names):
                                raise ValueError(f"Điểm đến GOTO không hợp lệ ở macro “{name}”.")
                            index = target
                            continue
                        self.status_callback(f"Bỏ qua: {name} (không đạt điều kiện)")
                        index += 1
                        continue

                delay = max(0, float(config.get("delay", 0)))
                if not self._wait(delay):
                    break
                self.status_callback(f"Đang chạy: {name}")
                self._play_steps(window, macro["steps"], config)
                index += 1
            if self.stop_event.is_set():
                self.status_callback("Đã dừng.")
            else:
                self.status_callback("Hoàn tất.")
        except Exception as error:
            self.status_callback(f"Lỗi: {error}")


class MacroApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoClick Macro · Giao diện mới")
        self.geometry("1060x680")
        self.minsize(850, 560)
        self.configure(bg="#f4f6fa")
        self.settings = load_settings()
        self.macros = load_macros()
        self.runner = None
        self.active_macro = None
        self._style()
        self._build()
        self._populate()

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Segoe UI", 10),
                        background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("TCombobox", padding=5)

    def _build(self):
        header = tk.Frame(self, bg="#17243a", padx=20, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="AUTOCLICK", font=("Segoe UI", 17, "bold"),
                 fg="white", bg="#17243a").pack(side="left")
        tk.Label(header, text="Quản lý kịch bản · xem bước · chạy có kiểm soát",
                 font=("Segoe UI", 10), fg="#cbd5e1", bg="#17243a").pack(
                     side="left", padx=18, pady=(4, 0))

        body = tk.Frame(self, bg="#f4f6fa", padx=16, pady=14)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg="white", width=250, padx=12, pady=12)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="KỊCH BẢN", font=("Segoe UI", 10, "bold"),
                 fg="#64748b", bg="white").pack(anchor="w", pady=(0, 8))
        self.macro_list = tk.Listbox(sidebar, bd=0, highlightthickness=0,
                                     activestyle="none", font=("Segoe UI", 10),
                                     selectbackground="#dbeafe",
                                     selectforeground="#1d4ed8")
        self.macro_list.pack(fill="both", expand=True)
        self.macro_list.bind("<<ListboxSelect>>", self._select_macro)
        self.run_all_button = tk.Button(
            sidebar, text="▶  Chạy thứ tự đã lưu", command=self._run_all,
            bg="#2563eb", fg="white", activebackground="#1d4ed8",
            relief="flat", padx=10, pady=9, font=("Segoe UI", 10, "bold"))
        self.run_all_button.pack(fill="x", pady=(10, 0))

        main = tk.Frame(body, bg="#f4f6fa")
        main.pack(side="left", fill="both", expand=True, padx=(14, 0))
        top = tk.Frame(main, bg="white", padx=14, pady=12)
        top.pack(fill="x")
        self.name_label = tk.Label(top, text="Chọn một kịch bản",
                                   font=("Segoe UI", 15, "bold"),
                                   fg="#17243a", bg="white")
        self.name_label.pack(anchor="w")
        self.info_label = tk.Label(top, text="", font=("Segoe UI", 9),
                                   fg="#64748b", bg="white")
        self.info_label.pack(anchor="w", pady=(3, 0))

        config = tk.LabelFrame(main, text="Thiết lập chạy", bg="white",
                               padx=12, pady=10, font=("Segoe UI", 10, "bold"))
        config.pack(fill="x", pady=(10, 0))
        self.condition_var = tk.StringVar()
        self.speed_var = tk.StringVar()
        self.loops_var = tk.StringVar()
        self.delay_var = tk.StringVar()
        self.confidence_var = tk.StringVar()
        self.timeout_var = tk.StringVar()
        self.logic_var = tk.StringVar()
        self.fallback_var = tk.StringVar()
        self.goto_var = tk.StringVar()
        self.retry_count_var = tk.StringVar()
        self.retry_wait_var = tk.StringVar()
        self.window_var = tk.StringVar(value=self._window_title())
        fields = [
            ("Điều kiện", self.condition_var, 0, 0, 2, "condition"),
            ("Tốc độ", self.speed_var, 0, 2, 1, "entry"),
            ("Số vòng", self.loops_var, 0, 3, 1, "entry"),
            ("Trễ trước (giây)", self.delay_var, 1, 0, 1, "entry"),
            ("Độ tin cậy ảnh", self.confidence_var, 1, 1, 1, "entry"),
            ("Chờ ảnh tối đa (giây)", self.timeout_var, 1, 2, 1, "entry"),
            ("Cửa sổ mục tiêu", self.window_var, 1, 3, 1, "entry"),
            ("Logic ảnh", self.logic_var, 2, 0, 1, "logic"),
            ("Xử lý dự phòng", self.fallback_var, 2, 1, 1, "fallback"),
            ("Vị trí GOTO", self.goto_var, 2, 2, 1, "entry"),
            ("Số lần thử lại", self.retry_count_var, 2, 3, 1, "entry"),
            ("Chờ giữa lần thử (giây)", self.retry_wait_var, 3, 0, 1, "entry"),
        ]
        for label, variable, row, column, span, kind in fields:
            tk.Label(config, text=label, bg="white", fg="#475569",
                     font=("Segoe UI", 9)).grid(row=row * 2, column=column,
                                                columnspan=span, sticky="w",
                                                padx=(0, 10), pady=(2, 0))
            if kind == "condition":
                widget = ttk.Combobox(
                    config, textvariable=variable, state="readonly",
                    values=[
                        "Tắt quét ảnh (Chạy luôn)",
                        "Có ảnh ➔ Chạy (K.Có ➔ Bỏ qua)",
                        "Chờ đến khi Có ảnh ➔ Chạy",
                        "K.Có ảnh ➔ Chạy (Phức hợp)",
                        "Có đủ ảnh ➔ Chạy (Phức hợp)",
                    ])
            elif kind == "logic":
                widget = ttk.Combobox(config, textvariable=variable,
                                      state="readonly", values=["AND", "OR"])
            elif kind == "fallback":
                widget = ttk.Combobox(config, textvariable=variable,
                                      state="readonly",
                                      values=["SKIP", "GOTO", "RETRY"])
            else:
                widget = ttk.Entry(config, textvariable=variable)
            widget.grid(row=row * 2 + 1, column=column, columnspan=span,
                        sticky="ew", padx=(0, 10), pady=(2, 8))
        for column in range(4):
            config.columnconfigure(column, weight=1)
        tk.Button(config, text="Lưu thiết lập", command=self._save_settings,
                  bg="#e2e8f0", fg="#17243a", relief="flat",
                  padx=10, pady=6).grid(row=8, column=3, sticky="e")

        steps_frame = tk.LabelFrame(main, text="Các bước thao tác",
                                    bg="white", padx=8, pady=8,
                                    font=("Segoe UI", 10, "bold"))
        steps_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.steps_table = ttk.Treeview(
            steps_frame, columns=("action", "detail", "delay"),
            show="headings", selectmode="browse")
        self.steps_table.heading("action", text="Thao tác")
        self.steps_table.heading("detail", text="Chi tiết")
        self.steps_table.heading("delay", text="Trễ (giây)")
        self.steps_table.column("action", width=110, anchor="w")
        self.steps_table.column("detail", width=380, anchor="w")
        self.steps_table.column("delay", width=100, anchor="center")
        self.steps_table.pack(fill="both", expand=True)

        footer = tk.Frame(main, bg="#f4f6fa", pady=10)
        footer.pack(fill="x")
        self.run_button = tk.Button(
            footer, text="▶  Chạy kịch bản đang chọn", command=self._run_selected,
            bg="#16a34a", fg="white", activebackground="#15803d",
            relief="flat", padx=12, pady=9, font=("Segoe UI", 10, "bold"))
        self.run_button.pack(side="left")
        self.stop_button = tk.Button(
            footer, text="■  Dừng ngay", command=self._stop,
            bg="#fee2e2", fg="#b91c1c", relief="flat",
            padx=12, pady=9, font=("Segoe UI", 10, "bold"), state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.status_var = tk.StringVar(value="Sẵn sàng · Chưa có thao tác nào được chạy")
        tk.Label(footer, textvariable=self.status_var, bg="#f4f6fa",
                 fg="#475569", font=("Segoe UI", 9)).pack(side="left", padx=8)

    def _window_title(self):
        try:
            value = read_json(WINDOW_FILE)
            return str(value.get("target_window_title", "MicroEmulator"))
        except (OSError, ValueError, AttributeError):
            return "MicroEmulator"

    def _populate(self):
        self.names = list(self.macros)
        order = self.settings.get("__macro_order__", [])
        self.names.sort(key=lambda name: (order.index(name) if name in order else len(order), name.lower()))
        for name in self.names:
            self.macro_list.insert("end", name)
        if self.names:
            self.macro_list.selection_set(0)
            self._show_macro(self.names[0])

    def _select_macro(self, _event=None):
        selection = self.macro_list.curselection()
        if selection:
            self._show_macro(self.names[selection[0]])

    def _show_macro(self, name):
        self.active_macro = name
        macro = self.macros[name]
        config = self.settings.get(name, {})
        self.name_label.config(text=name)
        self.info_label.config(
            text=f"{macro['path'].name}  ·  {len(macro['steps'])} bước  ·  "
                 f"{format_condition(config)}")
        self.condition_var.set(format_condition(config))
        self.speed_var.set(str(config.get("speed", "1.0x")))
        self.loops_var.set(str(config.get("loops", "1")))
        self.delay_var.set(str(config.get("delay", "0")))
        self.confidence_var.set(str(config.get("confidence", "0.8")))
        self.timeout_var.set(str(config.get("timeout", "60")))
        self.logic_var.set(str(config.get("logic_mode", "AND")).upper())
        self.fallback_var.set(str(config.get("fallback_action", "SKIP")).upper())
        self.goto_var.set(str(config.get("fallback_goto_step", "0")))
        self.retry_count_var.set(str(config.get("fallback_retry_count", "3")))
        self.retry_wait_var.set(str(config.get("fallback_retry_wait", "5")))
        self.steps_table.delete(*self.steps_table.get_children())
        for index, step in enumerate(macro["steps"], 1):
            if step.get("type") == "click":
                detail = f"({step.get('x')}, {step.get('y')}) · {step.get('button', 'left')}"
                action = "Click"
            elif step.get("type") == "key":
                detail = str(step.get("key", ""))
                action = "Phím"
            else:
                detail = json.dumps(step, ensure_ascii=False)
                action = str(step.get("type", "Không rõ"))
            self.steps_table.insert(
                "", "end", values=(f"{index:02}", detail, step.get("delay", 0)))

    def _save_settings(self):
        if not self.active_macro:
            return False
        try:
            speed = float(self.speed_var.get().lower().replace("x", ""))
            loops = int(self.loops_var.get())
            delay = float(self.delay_var.get())
            confidence = float(self.confidence_var.get())
            timeout = float(self.timeout_var.get())
            goto = int(self.goto_var.get())
            retry_count = int(self.retry_count_var.get())
            retry_wait = float(self.retry_wait_var.get())
            if (speed <= 0 or loops < 1 or delay < 0 or
                    not 0 <= confidence <= 1 or timeout <= 0 or
                    goto < 0 or retry_count < 0 or retry_wait < 0):
                raise ValueError("Tốc độ/vòng lặp/thời gian/độ tin cậy nằm ngoài phạm vi.")
            if self.logic_var.get().upper() not in {"AND", "OR"}:
                raise ValueError("Logic ảnh chỉ hỗ trợ AND hoặc OR.")
            if self.fallback_var.get().upper() not in {"SKIP", "GOTO", "RETRY"}:
                raise ValueError("Xử lý dự phòng không hợp lệ.")
            config = self.settings.setdefault(self.active_macro, {})
            config.update({
                "cond_mode": self.condition_var.get(),
                "speed": self.speed_var.get(),
                "loops": str(loops),
                "delay": str(delay),
                "confidence": str(confidence),
                "timeout": str(timeout),
                "logic_mode": self.logic_var.get().upper(),
                "fallback_action": self.fallback_var.get().upper(),
                "fallback_goto_step": str(goto),
                "fallback_retry_count": str(retry_count),
                "fallback_retry_wait": str(retry_wait),
            })
            SETTINGS_FILE.write_text(
                json.dumps(self.settings, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            self.status_var.set("Đã lưu thiết lập.")
            self._show_macro(self.active_macro)
            return True
        except (ValueError, OSError) as error:
            messagebox.showerror("Không thể lưu", str(error))
            return False

    def _run_selected(self):
        if self.active_macro:
            self._begin_run([self.active_macro])

    def _run_all(self):
        order = [name for name in self.settings.get("__macro_order__", [])
                 if name in self.macros]
        self._begin_run(order or self.names)

    def _begin_run(self, names):
        if not names:
            messagebox.showwarning("Chưa có macro", "Không tìm thấy kịch bản để chạy.")
            return
        if self.active_macro and not self._save_settings():
            return
        title = self.window_var.get().strip()
        if not title:
            messagebox.showerror("Thiếu cửa sổ", "Hãy nhập tiêu đề cửa sổ mục tiêu.")
            return
        scripts = ", ".join(names)
        if not messagebox.askyesno(
                "Xác nhận chạy",
                f"Sẽ gửi click/phím tới cửa sổ “{title}”.\n\n"
                f"Kịch bản: {scripts}\n\n"
                "Hãy bảo đảm đúng cửa sổ và nội dung thao tác. Tiếp tục?"):
            return
        self.runner = MacroRunner(lambda text: self.after(0, self.status_var.set, text))
        self.run_button.config(state="disabled")
        self.run_all_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.status_var.set("Đang chuẩn bị…")
        thread = threading.Thread(
            target=self.runner.run,
            args=(names, self.macros, self.settings, title),
            daemon=True)
        thread.start()
        self.after(150, self._watch_runner)

    def _watch_runner(self):
        if self.runner and self.status_var.get() not in ("Hoàn tất.", "Đã dừng.") and not self.status_var.get().startswith("Lỗi:"):
            self.after(150, self._watch_runner)
            return
        self.run_button.config(state="normal")
        self.run_all_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def _stop(self):
        if self.runner:
            self.runner.stop()
            self.status_var.set("Đang dừng…")


if __name__ == "__main__":
    try:
        app = MacroApp()
        app.mainloop()
    except Exception as error:
        messagebox.showerror("Không thể mở ứng dụng", str(error))
