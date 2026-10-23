"""房地产估价智能体 · 本地一键启动面板（Tkinter）。

双击 ``start_panel.bat`` 或运行 ``python launcher.py`` 即可打开。面板提供：

- 启动 / 停止本地 Web 服务，并实时显示运行状态；
- 一键打开工作台、重建向量索引、环境自检；
- 服务日志实时滚动、索引与知识文档状态总览。

所有内容都在本机运行，不依赖任何公网部署、隧道或云服务。
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import traceback
import webbrowser

from app import __version__
from app.config import PROJECT_ROOT
from app.local_runtime import collect_status, probe_service, service_url

ROOT = PROJECT_ROOT
ERROR_LOG = ROOT / "data" / "launcher-error.log"

BG = "#0b1c20"
PANEL = "#122b31"
PANEL_ALT = "#17383f"
PANEL_HOVER = "#1e454c"
LINE = "#274a52"
TEXT = "#eaf5f2"
MUTED = "#8fb0ab"
ACCENT = "#2f8f85"
ACCENT_HOVER = "#38a79b"
GOLD = "#d8b36b"
DANGER = "#b5653f"
SUCCESS = "#7fd1a8"
WARN = "#e0b878"
ERROR = "#e08a72"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_BODY = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_TINY = (FONT_FAMILY, 8)
FONT_BOLD = (FONT_FAMILY, 10, "bold")
FONT_CARD = (FONT_FAMILY, 15, "bold")
FONT_TITLE = (FONT_FAMILY, 17, "bold")
FONT_MONO = ("Consolas", 9)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - older Windows fallback
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


class LauncherPanel:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.url = service_url()
        self.status = None
        self.server_process: subprocess.Popen[str] | None = None
        self.server_starting = False
        self.busy_command: str | None = None
        self.events: queue.Queue[tuple] = queue.Queue()
        self._refresh_inflight = False
        self._closing = False
        self._announced = False

        self.root.title("房地产估价智能体 · 本地启动面板")
        self.root.configure(bg=BG)
        self.root.minsize(940, 680)
        self._center_window(980, 720)
        self._build_ui()
        self.append_log("面板已就绪，所有数据仅保存在本机。", "muted")
        self.refresh_status()
        self._poll_events()
        self._schedule_refresh()

    # ------------------------------------------------------------------ UI
    def _center_window(self, width: int, height: int) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max((screen_width - width) // 2, 0)
        y = max((screen_height - height) // 2 - 20, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=26, pady=22)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        self._build_header(outer)
        self._build_cards(outer)
        self._build_actions(outer)
        self._build_log(outer)
        self._build_footer(outer)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(1, weight=1)

        brand = tk.Frame(header, bg=BG)
        brand.grid(row=0, column=0, sticky="w")
        mark = tk.Label(
            brand,
            text="估",
            bg=GOLD,
            fg="#122b31",
            font=(FONT_FAMILY, 16, "bold"),
            width=2,
            height=1,
        )
        mark.pack(side="left", padx=(0, 12), ipady=4)
        titles = tk.Frame(brand, bg=BG)
        titles.pack(side="left")
        tk.Label(
            titles,
            text="房地产估价智能体",
            bg=BG,
            fg=TEXT,
            font=FONT_TITLE,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="REALESTATE EVAL AGENT · LOCAL CONTROL PANEL",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 8),
            anchor="w",
        ).pack(anchor="w")

        self.status_pill = tk.Frame(
            header,
            bg=PANEL,
            highlightbackground=LINE,
            highlightthickness=1,
            padx=14,
            pady=8,
        )
        self.status_pill.grid(row=0, column=2, sticky="e")
        self.status_dot = tk.Label(self.status_pill, text="●", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 11))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_text = tk.Label(self.status_pill, text="服务未启动", bg=PANEL, fg=MUTED, font=FONT_BOLD)
        self.status_text.pack(side="left")

    def _build_cards(self, parent: tk.Frame) -> None:
        cards = tk.Frame(parent, bg=BG)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for column in range(4):
            cards.columnconfigure(column, weight=1, uniform="card")
        self.card_service, self.card_service_detail = self._make_card(cards, 0, "本地服务")
        self.card_address, self.card_address_detail = self._make_card(cards, 1, "访问地址")
        self.card_vectors, self.card_vectors_detail = self._make_card(cards, 2, "向量索引")
        self.card_docs, self.card_docs_detail = self._make_card(cards, 3, "知识文档")

    def _make_card(self, parent: tk.Frame, column: int, title: str) -> tuple[tk.Label, tk.Label]:
        card = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0, 10) if column < 3 else 0,
        )
        tk.Label(card, text=title, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w").pack(
            fill="x", padx=14, pady=(12, 2)
        )
        value = tk.Label(card, text="--", bg=PANEL, fg=TEXT, font=FONT_CARD, anchor="w")
        value.pack(fill="x", padx=14)
        detail = tk.Label(card, text="", bg=PANEL, fg=MUTED, font=FONT_TINY, anchor="w")
        detail.pack(fill="x", padx=14, pady=(3, 12))
        return value, detail

    def _build_actions(self, parent: tk.Frame) -> None:
        actions = tk.Frame(parent, bg=BG)
        actions.grid(row=2, column=0, sticky="new")
        for column in range(4):
            actions.columnconfigure(column, weight=1, uniform="action")
        self.buttons: dict[str, tk.Button] = {}
        definitions = [
            ("start", "▶  启动服务", self.start_server, "primary", 0, 0),
            ("stop", "■  停止服务", self.stop_server, "normal", 0, 1),
            ("open", "↗  打开工作台", self.open_workspace, "normal", 0, 2),
            ("index", "⟳  重建索引", self.rebuild_index, "normal", 0, 3),
            ("check", "✓  环境自检", self.run_check, "normal", 1, 0),
            ("readme", "▤  项目说明", self.open_readme, "ghost", 1, 1),
            ("folder", "▣  项目目录", self.open_folder, "ghost", 1, 2),
            ("exit", "×  退出面板", self.on_close, "ghost", 1, 3),
        ]
        for key, label, command, style, row, column in definitions:
            button = self._make_button(actions, label, command, style)
            button.grid(row=row, column=column, sticky="ew", padx=(0, 10) if column < 3 else 0, pady=(0, 10))
            self.buttons[key] = button

    def _make_button(self, parent: tk.Frame, label: str, command, style: str) -> tk.Button:
        if style == "primary":
            background, foreground, active = ACCENT, "#ffffff", ACCENT_HOVER
        elif style == "ghost":
            background, foreground, active = BG, MUTED, PANEL_ALT
        else:
            background, foreground, active = PANEL_ALT, TEXT, PANEL_HOVER
        button = tk.Button(
            parent,
            text=label,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active,
            activeforeground="#ffffff",
            disabledforeground="#5d7773",
            font=FONT_BOLD,
            relief="flat",
            bd=0,
            padx=12,
            pady=11,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=LINE if style != "ghost" else BG,
            highlightcolor=LINE,
        )
        return button

    def _build_log(self, parent: tk.Frame) -> None:
        log_card = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(6, 14))
        parent.rowconfigure(3, weight=1)
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)

        header = tk.Frame(log_card, bg=PANEL)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 6))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="运行日志", bg=PANEL, fg=TEXT, font=FONT_BOLD, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.log_hint = tk.Label(header, text="实时输出", bg=PANEL, fg=MUTED, font=FONT_TINY, anchor="e")
        self.log_hint.grid(row=0, column=1, sticky="e")

        self.log_text = tk.Text(
            log_card,
            height=11,
            bg="#09171a",
            fg="#cfe6e1",
            insertbackground=TEXT,
            font=FONT_MONO,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            wrap="word",
            state="disabled",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=(12, 0), pady=(0, 12))
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.Vertical.TScrollbar",
            gripcount=0,
            background=LINE,
            troughcolor="#09171a",
            bordercolor="#09171a",
            arrowcolor=MUTED,
            darkcolor=LINE,
            lightcolor=LINE,
            relief="flat",
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[("active", PANEL_HOVER), ("disabled", PANEL), ("!disabled", LINE)],
            arrowcolor=[("disabled", PANEL), ("!disabled", MUTED)],
            troughcolor=[("!disabled", "#09171a")],
        )
        scrollbar = ttk.Scrollbar(
            log_card,
            command=self.log_text.yview,
            style="Dark.Vertical.TScrollbar",
        )
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 12))
        self.log_text.configure(yscrollcommand=scrollbar.set)
        for tag, color in {
            "info": "#cfe6e1",
            "muted": MUTED,
            "command": GOLD,
            "success": SUCCESS,
            "warn": WARN,
            "error": ERROR,
            "server": "#9fc3bd",
        }.items():
            self.log_text.tag_configure(tag, foreground=color)

    def _build_footer(self, parent: tk.Frame) -> None:
        footer = tk.Frame(parent, bg=BG)
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            text="本地运行 · 服务与数据均保存在本机 · 不需要域名、隧道或公网部署",
            bg=BG,
            fg=MUTED,
            font=FONT_TINY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            footer,
            text=f"v{__version__} · Python {sys.version.split()[0]}",
            bg=BG,
            fg=MUTED,
            font=FONT_TINY,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

    # --------------------------------------------------------------- logging
    def append_log(self, message: str, tag: str = "info") -> None:
        self.events.put(("log", message, tag))

    def _display_log(self, message: str, tag: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{time.strftime('%H:%M:%S')}  {message}\n", tag)
        self.log_text.see("end")
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 600:
            self.log_text.delete("1.0", f"{line_count - 500}.0")
        self.log_text.configure(state="disabled")

    # ---------------------------------------------------------- status refresh
    def _schedule_refresh(self) -> None:
        self.root.after(2000, self._scheduled_refresh)

    def _scheduled_refresh(self) -> None:
        if self._closing:
            return
        self.refresh_status()
        self._schedule_refresh()

    def refresh_status(self) -> None:
        if self._refresh_inflight:
            return
        self._refresh_inflight = True
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            self.events.put(("status", collect_status()))
        except Exception as exc:  # noqa: BLE001 - never break the UI loop
            self.events.put(("log", f"状态刷新失败：{exc}", "warn"))
        finally:
            self._refresh_inflight = False

    def _apply_status(self, status) -> None:
        self.status = status
        if status.service_running:
            self.server_starting = False
            self.status_dot.configure(fg=SUCCESS)
            self.status_text.configure(text="服务运行中", fg=SUCCESS)
            self.card_service.configure(text="运行中", fg=SUCCESS)
            self.card_service_detail.configure(text=f"端口 {status.port} · 健康检查通过")
        else:
            self.status_dot.configure(fg=WARN if self.server_starting else MUTED)
            self.status_text.configure(text="正在启动…" if self.server_starting else "服务未启动", fg=WARN if self.server_starting else MUTED)
            self.card_service.configure(text="启动中…" if self.server_starting else "未启动", fg=WARN if self.server_starting else MUTED)
            self.card_service_detail.configure(text=f"端口 {status.port} · 等待健康检查")
        self.card_address.configure(text=status.url.replace("http://", ""))
        self.card_address_detail.configure(text="仅本机可访问")
        if status.vector_count:
            self.card_vectors.configure(text=f"{status.vector_count} 条向量", fg=TEXT)
            self.card_vectors_detail.configure(text="Chroma 索引就绪")
        else:
            self.card_vectors.configure(text="未构建", fg=WARN)
            self.card_vectors_detail.configure(text="点击「重建索引」生成")
        self.card_docs.configure(text=f"{status.docs_count} 份文档")
        self.card_docs_detail.configure(text="data/docs 知识源")
        if not self._announced:
            self._announced = True
            self.append_log(
                f"模型：{status.llm_model} · Embedding：{status.embedding_model}",
                "info",
            )
            self.append_log(
                f"知识库：{status.docs_count} 份文档 · 向量索引 {status.vector_count or 0} 条",
                "success" if status.vector_index_ready else "warn",
            )
            self.append_log(
                "API Key 已配置" if status.api_key_configured else "API Key 未配置，估价与问答不可用",
                "success" if status.api_key_configured else "error",
            )
        start_disabled = status.service_running or self.server_starting
        self.buttons["start"].configure(
            state="disabled" if start_disabled else "normal",
            bg="#1a4a48" if start_disabled else ACCENT,
            fg="#8fb0ab" if start_disabled else "#ffffff",
            disabledforeground="#8fb0ab",
        )
        self.buttons["stop"].configure(
            state="normal" if (self.server_process and self.server_process.poll() is None) else "disabled"
        )
        busy = self.busy_command is not None
        for key in ("index", "check"):
            self.buttons[key].configure(state="disabled" if busy else "normal")
        self.buttons["open"].configure(state="normal")

    # -------------------------------------------------------------- commands
    def _run_streaming_command(self, label: str, arguments: list[str], on_exit=None) -> subprocess.Popen | None:
        if self.busy_command:
            self.append_log(f"已有任务在执行：{self.busy_command}", "warn")
            return None
        self.busy_command = label
        self.append_log(f"$ {' '.join(arguments)}", "command")
        try:
            process = subprocess.Popen(
                arguments,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:  # noqa: BLE001
            self.busy_command = None
            self.append_log(f"启动失败：{exc}", "error")
            return None
        threading.Thread(
            target=self._pump_stream,
            args=(process, label, on_exit),
            daemon=True,
        ).start()
        return process

    def _pump_stream(self, process: subprocess.Popen, label: str, on_exit) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    text = line.rstrip()
                    if text:
                        self.events.put(("log", text, "server" if label == "server" else "info"))
        finally:
            code = process.wait()
            self.events.put(("process_exit", label, code, process, on_exit))

    def start_server(self) -> None:
        if probe_service(timeout=0.8).running:
            self.append_log("本地服务已经在运行，无需重复启动。", "warn")
            self.refresh_status()
            return
        if self.server_process and self.server_process.poll() is None:
            return
        self.append_log(f"正在启动本地服务：{self.url}", "command")
        self.server_starting = True
        try:
            self.server_process = subprocess.Popen(
                [sys.executable, str(ROOT / "run.py"), "web"],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as exc:  # noqa: BLE001
            self.server_starting = False
            self.append_log(f"服务启动失败：{exc}", "error")
            self.server_process = None
            return
        self.append_log(f"服务进程已创建（PID {self.server_process.pid}），等待健康检查…", "info")
        threading.Thread(
            target=self._pump_stream,
            args=(self.server_process, "server", None),
            daemon=True,
        ).start()
        self.buttons["start"].configure(state="disabled")
        self.root.after(1200, self.refresh_status)
        threading.Thread(target=self._wait_until_ready, daemon=True).start()

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            if probe_service(timeout=0.6).running:
                self.events.put(("log", "服务已就绪，可打开工作台。", "success"))
                self.events.put(("refresh", None))
                return
            time.sleep(0.7)
        self.server_starting = False
        self.events.put(("log", "服务启动超时，请查看上方日志。", "error"))
        self.events.put(("refresh", None))

    def stop_server(self) -> None:
        process = self.server_process
        if not process or process.poll() is not None:
            self.append_log("当前没有由面板启动的服务进程。", "warn")
            self.refresh_status()
            return
        self.append_log("正在停止本地服务…", "command")
        self.server_starting = False
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"停止服务时出现异常：{exc}", "warn")
        finally:
            self.server_process = None
            self.append_log("本地服务已停止。", "success")
            self.root.after(500, self.refresh_status)

    def open_workspace(self) -> None:
        if probe_service(timeout=0.8).running:
            webbrowser.open(self.url)
            self.append_log(f"已在浏览器打开 {self.url}", "success")
            return
        self.append_log("服务尚未启动，正在启动并在就绪后自动打开浏览器…", "command")
        self.start_server()

        def wait_and_open() -> None:
            deadline = time.time() + 20
            while time.time() < deadline:
                if probe_service(timeout=0.6).running:
                    webbrowser.open(self.url)
                    self.events.put(("log", f"已在浏览器打开 {self.url}", "success"))
                    return
                time.sleep(0.7)
            self.events.put(("log", "打开工作台超时，请查看日志。", "error"))

        threading.Thread(target=wait_and_open, daemon=True).start()

    def rebuild_index(self) -> None:
        if not messagebox.askyesno(
            "重建向量索引",
            "将读取 data/docs 并重建本地 Chroma 向量库，可能需要几十秒。\n是否继续？",
            parent=self.root,
        ):
            return
        process = self._run_streaming_command("index", [sys.executable, str(ROOT / "run.py"), "index"])
        if process:
            self.append_log("正在重建向量索引…", "command")

    def run_check(self) -> None:
        process = self._run_streaming_command("check", [sys.executable, str(ROOT / "run.py"), "check"])
        if process:
            self.append_log("正在执行环境自检…", "command")

    def open_readme(self) -> None:
        path = ROOT / "README.md"
        if not path.exists():
            self.append_log("未找到 README.md", "error")
            return
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - local file
        else:
            webbrowser.open(path.as_uri())

    def open_folder(self) -> None:
        if os.name == "nt":
            os.startfile(str(ROOT))  # noqa: S606 - local folder
        else:
            webbrowser.open(ROOT.as_uri())

    # ----------------------------------------------------------------- events
    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._display_log(event[1], event[2])
                elif kind == "status":
                    self._apply_status(event[1])
                elif kind == "refresh":
                    self.refresh_status()
                elif kind == "process_exit":
                    self._handle_process_exit(*event[1:])
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(120, self._poll_events)

    def _handle_process_exit(self, label: str, code: int, process: subprocess.Popen, on_exit) -> None:
        if label == "server":
            self.server_starting = False
            if self.server_process is process:
                self.server_process = None
            self.append_log(f"服务进程已退出（退出码 {code}）。", "warn" if code else "info")
        else:
            self.busy_command = None
            tag = "success" if code == 0 else "error"
            self.append_log(f"任务「{label}」结束，退出码 {code}。", tag)
        if on_exit:
            on_exit(code)
        self.refresh_status()

    # ------------------------------------------------------------------ close
    def on_close(self) -> None:
        if self._closing:
            return
        process = self.server_process
        self._closing = True
        if process and process.poll() is None:
            if not messagebox.askyesno(
                "退出面板",
                "本地服务仍在运行，退出面板会同时停止服务。\n是否继续退出？",
                parent=self.root,
            ):
                self._closing = False
                return
            try:
                self.stop_server()
            except Exception:  # noqa: BLE001
                pass
        self.root.destroy()


def run(screenshot_path: str | None = None) -> None:
    _enable_dpi_awareness()
    root = tk.Tk()
    panel = LauncherPanel(root)
    if screenshot_path:
        def capture() -> None:
            try:
                from PIL import ImageGrab

                root.update_idletasks()
                x, y = root.winfo_rootx(), root.winfo_rooty()
                width, height = root.winfo_width(), root.winfo_height()
                image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
                target = Path(screenshot_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
                print(f"launcher screenshot saved: {target}")
            except Exception as exc:  # noqa: BLE001
                print(f"launcher screenshot failed: {exc}")
            finally:
                root.after(200, root.destroy)

        root.after(3200, capture)
    root.mainloop()
    del panel


def main() -> None:
    screenshot_path = None
    if "--screenshot" in sys.argv:
        index = sys.argv.index("--screenshot")
        if index + 1 < len(sys.argv):
            screenshot_path = sys.argv[index + 1]
    try:
        run(screenshot_path)
    except Exception:  # noqa: BLE001 - write a log and show a friendly dialog
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        ERROR_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror(
                "启动面板出错",
                f"面板启动失败，详情已写入：\n{ERROR_LOG}",
            )
        except Exception:  # noqa: BLE001
            print(traceback.format_exc())


if __name__ == "__main__":
    main()
