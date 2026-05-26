import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import ConfigManager
from .logger import write_log
from .orchestrator import Orchestrator

# 지원 LLM 목록 (표시 이름, 내부 키)
SUPPORTED_LLMS = [
    ("Claude", "claude"),
    ("ChatGPT", "chatgpt"),
    ("Gemini", "gemini"),
]

POLL_INTERVAL_MS = 100  # 이벤트 큐 폴링 주기 (밀리초)


class MultiMindApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        self.event_queue: queue.Queue = queue.Queue()
        self._polling = False

        self._init_vars()
        self._build_ui()
        self._apply_saved_config()
        self._on_head_changed()

        # 창 크기/위치 복원
        geometry = self.config.get("window_geometry", "900x700+100+100")
        self.root.geometry(geometry)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 변수 초기화 ────────────────────────────────────────────────────────────

    def _init_vars(self):
        self.head_var = tk.StringVar(value="claude")
        self.worker_vars = {key: tk.BooleanVar(value=False)
                            for _, key in SUPPORTED_LLMS}

    # ── UI 구성 ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.title("MultiMind — 멀티 LLM 오케스트레이터")
        self.root.configure(bg="#f5f5f5")

        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        self._build_head_section(main_frame)
        self._build_worker_section(main_frame)
        self._build_prompt_section(main_frame)
        self._build_run_section(main_frame)
        self._build_output_section(main_frame)
        self._build_log_section(main_frame)

    def _build_head_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Head LLM (프롬프트 정제 + 결과 종합)",
                               padding="8")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            rb = ttk.Radiobutton(
                frame, text=label, variable=self.head_var, value=key,
                command=self._on_head_changed
            )
            rb.grid(row=0, column=i, padx=12, sticky="w")

    def _build_worker_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Worker LLM (Head 선택 시 자동 비활성화)",
                               padding="8")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        self.worker_checkboxes = {}
        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            cb = ttk.Checkbutton(
                frame, text=label, variable=self.worker_vars[key]
            )
            cb.grid(row=0, column=i, padx=12, sticky="w")
            self.worker_checkboxes[key] = cb

    def _build_prompt_section(self, parent):
        frame = ttk.LabelFrame(parent, text="프롬프트 입력", padding="8")
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)

        self.prompt_text = tk.Text(frame, height=6, wrap="word",
                                   font=("맑은 고딕", 10))
        self.prompt_text.grid(row=0, column=0, sticky="ew")

        scrollbar = ttk.Scrollbar(frame, command=self.prompt_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.prompt_text["yscrollcommand"] = scrollbar.set

    def _build_run_section(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky="e", pady=(0, 6))

        self.status_label = ttk.Label(frame, text="", foreground="#555555")
        self.status_label.grid(row=0, column=0, padx=(0, 12))

        self.run_button = ttk.Button(frame, text="▶  실행",
                                     command=self._on_run_clicked)
        self.run_button.grid(row=0, column=1)

    def _build_output_section(self, parent):
        frame = ttk.LabelFrame(parent, text="최종 합성 결과", padding="8")
        frame.grid(row=4, column=0, sticky="nsew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=3)

        self.output_text = tk.Text(frame, height=10, wrap="word",
                                   state="disabled", font=("맑은 고딕", 10),
                                   bg="#ffffff")
        self.output_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text["yscrollcommand"] = scrollbar.set

    def _build_log_section(self, parent):
        frame = ttk.LabelFrame(parent, text="진행 로그", padding="8")
        frame.grid(row=5, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(5, weight=1)

        self.log_text = tk.Text(frame, height=6, wrap="word",
                                state="disabled", font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_config("error", foreground="#f48771")
        self.log_text.tag_config("success", foreground="#4ec9b0")
        self.log_text.tag_config("phase", foreground="#dcdcaa")

        scrollbar = ttk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text["yscrollcommand"] = scrollbar.set

    # ── 설정 적용 ──────────────────────────────────────────────────────────────

    def _apply_saved_config(self):
        head = self.config.get("head", "claude")
        workers = self.config.get("workers", ["chatgpt", "gemini"])
        self.head_var.set(head)
        for key, var in self.worker_vars.items():
            var.set(key in workers)

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _on_head_changed(self, *args):
        """Head LLM과 동일한 Worker 체크박스를 비활성화"""
        selected_head = self.head_var.get()
        for key, cb in self.worker_checkboxes.items():
            if key == selected_head:
                self.worker_vars[key].set(False)
                cb.configure(state="disabled")
            else:
                cb.configure(state="normal")

    def _on_run_clicked(self):
        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 오류", "프롬프트를 입력해주세요.")
            return

        head = self.head_var.get()
        workers = [key for key, var in self.worker_vars.items()
                   if var.get() and key != head]

        if not workers:
            messagebox.showwarning("설정 오류",
                                   "Worker LLM을 최소 1개 이상 선택해주세요.")
            return

        # 설정 저장
        self.config_manager.save(head, workers,
                                 geometry=self.root.geometry())
        write_log(f"실행 시작 | Head={head} | Workers={workers}")

        # UI 초기화 및 비활성화
        self.run_button.configure(state="disabled")
        self._clear_output()
        self._clear_log()

        # 백그라운드 스레드에서 오케스트레이터 실행
        self.event_queue = queue.Queue()
        orchestrator = Orchestrator(
            head, workers, prompt, self.event_queue,
            settings=self.config.get("settings", {})
        )
        threading.Thread(target=orchestrator.run, daemon=True).start()

        # 이벤트 큐 폴링 시작
        self._polling = True
        self.root.after(POLL_INTERVAL_MS, self._poll_event_queue)

    def _on_close(self):
        self.config_manager.save(
            self.head_var.get(),
            [k for k, v in self.worker_vars.items() if v.get()],
            geometry=self.root.geometry()
        )
        self.root.destroy()

    # ── 이벤트 큐 처리 ────────────────────────────────────────────────────────

    def _poll_event_queue(self):
        if not self._polling:
            return

        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

        self.root.after(POLL_INTERVAL_MS, self._poll_event_queue)

    def _handle_event(self, event: dict):
        etype = event.get("type")

        if etype == "log":
            self._append_log(event["message"])

        elif etype == "phase":
            phase_text = f"[Phase {event['phase']}] {event['description']}"
            self._append_log(phase_text, tag="phase")
            self.status_label.configure(text=event["description"])

        elif etype == "worker_done":
            msg = f"[{event['llm'].upper()}] 응답 수신 완료 ✓"
            self._append_log(msg, tag="success")

        elif etype == "worker_error":
            msg = f"[{event['llm'].upper()}] 오류: {event['error']}"
            self._append_log(msg, tag="error")

        elif etype == "final_result":
            self._set_output(event["text"])
            self._append_log("오케스트레이션 완료 ✓", tag="success")
            self.status_label.configure(text="완료")
            self._finish()

        elif etype == "fatal_error":
            self._append_log(f"오류: {event['error']}", tag="error")
            messagebox.showerror("실행 오류", event["error"])
            self.status_label.configure(text="오류 발생")
            self._finish()

    def _finish(self):
        """실행 완료 후 UI 복원"""
        self._polling = False
        self.run_button.configure(state="normal")

    # ── 텍스트 위젯 헬퍼 ──────────────────────────────────────────────────────

    def _append_log(self, message: str, tag: str = None):
        self.log_text.configure(state="normal")
        if tag:
            self.log_text.insert("end", message + "\n", tag)
        else:
            self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_output(self, text: str):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", text)
        self.output_text.configure(state="disabled")

    def _clear_output(self):
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
