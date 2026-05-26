import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import ConfigManager
from .logger import writeLog
from .orchestrator import Orchestrator

# ── 지원 LLM 목록 (표시 이름, 내부 키) ───────────────────────────────────────
SUPPORTED_LLMS = [
    ("Claude", "claude"),
    ("ChatGPT", "chatgpt"),
    ("Gemini", "gemini"),
]

POLL_INTERVAL_MS = 100  # 이벤트 큐 폴링 주기 (밀리초)


class MultiMindApp:
    def __init__(self, root: tk.Tk):
        # ── 앱 초기화 ──────────────────────────────────────────────────────────
        self.root = root
        self.configManager = ConfigManager()
        self.config = self.configManager.load()
        self.eventQueue: queue.Queue = queue.Queue()
        self._polling = False

        self._initVars()
        self._buildUi()
        self._applySavedConfig()
        self._onHeadChanged()

        # ── 이전 창 크기/위치 복원 ─────────────────────────────────────────────
        geometry = self.config.get("window_geometry", "900x700+100+100")
        self.root.geometry(geometry)
        self.root.protocol("WM_DELETE_WINDOW", self._onClose)

    # ── 변수 초기화 ────────────────────────────────────────────────────────────

    def _initVars(self):
        """tkinter 상태 변수 초기화"""
        self.headVar = tk.StringVar(value="claude")
        self.workerVars = {key: tk.BooleanVar(value=False)
                           for _, key in SUPPORTED_LLMS}

    # ── UI 구성 ────────────────────────────────────────────────────────────────

    def _buildUi(self):
        """전체 UI 레이아웃 구성"""
        self.root.title("MultiMind — 멀티 LLM 오케스트레이터")
        self.root.configure(bg="#f5f5f5")

        # ── 메인 프레임 ────────────────────────────────────────────────────────
        mainFrame = ttk.Frame(self.root, padding="12")
        mainFrame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        mainFrame.columnconfigure(0, weight=1)

        self._buildHeadSection(mainFrame)
        self._buildWorkerSection(mainFrame)
        self._buildPromptSection(mainFrame)
        self._buildRunSection(mainFrame)
        self._buildOutputSection(mainFrame)
        self._buildLogSection(mainFrame)

    def _buildHeadSection(self, parent):
        """Head LLM 선택 라디오버튼 섹션"""
        frame = ttk.LabelFrame(parent, text="Head LLM (프롬프트 정제 + 결과 종합)",
                               padding="8")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            rb = ttk.Radiobutton(
                frame, text=label, variable=self.headVar, value=key,
                command=self._onHeadChanged
            )
            rb.grid(row=0, column=i, padx=12, sticky="w")

    def _buildWorkerSection(self, parent):
        """Worker LLM 선택 체크박스 섹션"""
        frame = ttk.LabelFrame(parent, text="Worker LLM (Head 선택 시 자동 비활성화)",
                               padding="8")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        self.workerCheckboxes = {}
        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            cb = ttk.Checkbutton(frame, text=label, variable=self.workerVars[key])
            cb.grid(row=0, column=i, padx=12, sticky="w")
            self.workerCheckboxes[key] = cb

    def _buildPromptSection(self, parent):
        """프롬프트 입력 텍스트 영역"""
        frame = ttk.LabelFrame(parent, text="프롬프트 입력", padding="8")
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)

        self.promptText = tk.Text(frame, height=6, wrap="word",
                                  font=("맑은 고딕", 10))
        self.promptText.grid(row=0, column=0, sticky="ew")

        scrollbar = ttk.Scrollbar(frame, command=self.promptText.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.promptText["yscrollcommand"] = scrollbar.set

    def _buildRunSection(self, parent):
        """상태 레이블 및 실행 버튼"""
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky="e", pady=(0, 6))

        self.statusLabel = ttk.Label(frame, text="", foreground="#555555")
        self.statusLabel.grid(row=0, column=0, padx=(0, 12))

        self.runButton = ttk.Button(frame, text="▶  실행",
                                    command=self._onRunClicked)
        self.runButton.grid(row=0, column=1)

    def _buildOutputSection(self, parent):
        """최종 합성 결과 출력 텍스트 영역"""
        frame = ttk.LabelFrame(parent, text="최종 합성 결과", padding="8")
        frame.grid(row=4, column=0, sticky="nsew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=3)

        self.outputText = tk.Text(frame, height=10, wrap="word",
                                  state="disabled", font=("맑은 고딕", 10),
                                  bg="#ffffff")
        self.outputText.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, command=self.outputText.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.outputText["yscrollcommand"] = scrollbar.set

    def _buildLogSection(self, parent):
        """실시간 진행 로그 텍스트 영역"""
        frame = ttk.LabelFrame(parent, text="진행 로그", padding="8")
        frame.grid(row=5, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(5, weight=1)

        self.logText = tk.Text(frame, height=6, wrap="word",
                               state="disabled", font=("Consolas", 9),
                               bg="#1e1e1e", fg="#d4d4d4")
        self.logText.grid(row=0, column=0, sticky="nsew")
        self.logText.tag_config("error", foreground="#f48771")
        self.logText.tag_config("success", foreground="#4ec9b0")
        self.logText.tag_config("phase", foreground="#dcdcaa")

        scrollbar = ttk.Scrollbar(frame, command=self.logText.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.logText["yscrollcommand"] = scrollbar.set

    # ── 설정 적용 ──────────────────────────────────────────────────────────────

    def _applySavedConfig(self):
        """저장된 config에서 Head/Worker 선택 복원"""
        head = self.config.get("head", "claude")
        workers = self.config.get("workers", ["chatgpt", "gemini"])
        self.headVar.set(head)
        for key, var in self.workerVars.items():
            var.set(key in workers)

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _onHeadChanged(self, *args):
        """Head LLM 선택 변경 시 동일 Worker 체크박스 자동 비활성화"""
        selectedHead = self.headVar.get()
        for key, cb in self.workerCheckboxes.items():
            if key == selectedHead:
                self.workerVars[key].set(False)
                cb.configure(state="disabled")
            else:
                cb.configure(state="normal")

    def _onRunClicked(self):
        """실행 버튼 클릭 — 유효성 검사 후 오케스트레이션 스레드 시작"""
        # ── 입력 유효성 검사 ───────────────────────────────────────────────────
        prompt = self.promptText.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("입력 오류", "프롬프트를 입력해주세요.")
            return

        head = self.headVar.get()
        workers = [key for key, var in self.workerVars.items()
                   if var.get() and key != head]

        if not workers:
            messagebox.showwarning("설정 오류", "Worker LLM을 최소 1개 이상 선택해주세요.")
            return

        # ── 설정 저장 및 UI 초기화 ─────────────────────────────────────────────
        self.configManager.save(head, workers, geometry=self.root.geometry())
        writeLog(f"실행 시작 | Head={head} | Workers={workers}")

        self.runButton.configure(state="disabled")
        self._clearOutput()
        self._clearLog()

        # ── 오케스트레이터 백그라운드 스레드 시작 ─────────────────────────────
        self.eventQueue = queue.Queue()
        orchestrator = Orchestrator(
            head, workers, prompt, self.eventQueue,
            settings=self.config.get("settings", {})
        )
        threading.Thread(target=orchestrator.run, daemon=True).start()

        # ── 이벤트 큐 폴링 시작 ────────────────────────────────────────────────
        self._polling = True
        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _onClose(self):
        """창 닫기 시 현재 설정 저장"""
        self.configManager.save(
            self.headVar.get(),
            [k for k, v in self.workerVars.items() if v.get()],
            geometry=self.root.geometry()
        )
        self.root.destroy()

    # ── 이벤트 큐 처리 ────────────────────────────────────────────────────────

    def _pollEventQueue(self):
        """100ms 주기로 이벤트 큐를 소비하여 GUI 업데이트 (메인 스레드 전용)"""
        if not self._polling:
            return

        # ── 큐에 남은 모든 이벤트를 한 번에 소비 ─────────────────────────────
        try:
            while True:
                event = self.eventQueue.get_nowait()
                self._handleEvent(event)
        except queue.Empty:
            pass

        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _handleEvent(self, event: dict):
        """이벤트 타입에 따라 GUI 업데이트"""
        etype = event.get("type")

        if etype == "log":
            self._appendLog(event["message"])

        elif etype == "phase":
            phaseText = f"[Phase {event['phase']}] {event['description']}"
            self._appendLog(phaseText, tag="phase")
            self.statusLabel.configure(text=event["description"])

        elif etype == "worker_done":
            msg = f"[{event['llm'].upper()}] 응답 수신 완료 ✓"
            self._appendLog(msg, tag="success")

        elif etype == "worker_error":
            msg = f"[{event['llm'].upper()}] 오류: {event['error']}"
            self._appendLog(msg, tag="error")

        elif etype == "final_result":
            self._setOutput(event["text"])
            self._appendLog("오케스트레이션 완료 ✓", tag="success")
            self.statusLabel.configure(text="완료")
            self._finish()

        elif etype == "fatal_error":
            self._appendLog(f"오류: {event['error']}", tag="error")
            messagebox.showerror("실행 오류", event["error"])
            self.statusLabel.configure(text="오류 발생")
            self._finish()

    def _finish(self):
        """실행 완료 후 UI 복원 (실행 버튼 재활성화, 폴링 중단)"""
        self._polling = False
        self.runButton.configure(state="normal")

    # ── 텍스트 위젯 헬퍼 ──────────────────────────────────────────────────────

    def _appendLog(self, message: str, tag: str = None):
        """로그 텍스트 영역에 메시지 추가 (자동 스크롤)"""
        self.logText.configure(state="normal")
        if tag:
            self.logText.insert("end", message + "\n", tag)
        else:
            self.logText.insert("end", message + "\n")
        self.logText.see("end")
        self.logText.configure(state="disabled")

    def _setOutput(self, text: str):
        """결과 텍스트 영역 내용 교체"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.insert("1.0", text)
        self.outputText.configure(state="disabled")

    def _clearOutput(self):
        """결과 텍스트 영역 초기화"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.configure(state="disabled")

    def _clearLog(self):
        """로그 텍스트 영역 초기화"""
        self.logText.configure(state="normal")
        self.logText.delete("1.0", "end")
        self.logText.configure(state="disabled")
