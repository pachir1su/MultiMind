# Tkinter GUI 모듈 — MultiMind 앱 메인 인터페이스
# 이벤트 큐 기반 비동기 UI 업데이트, 오케스트레이터 제어

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .config import ConfigManager
from .logger import writeLog
from .orchestrator import Orchestrator

# 지원 LLM 목록 (표시 이름, 내부 키)
SUPPORTED_LLMS = [
    ("Claude", "claude"),
    ("ChatGPT", "chatgpt"),
    ("Gemini", "gemini"),
    ("Grok", "grok"),
    ("Perplexity", "perplexity"),
]

# 이벤트 큐 폴링 주기 (밀리초)
POLL_INTERVAL_MS = 100


class MultiMindApp:
    """MultiMind 메인 GUI 애플리케이션"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.configManager = ConfigManager()
        self.config = self.configManager.load()
        self.eventQueue: queue.Queue = queue.Queue()
        self._polling = False
        # 오케스트레이터 중단 이벤트 (중단 버튼에서 사용)
        self._stopEvent = threading.Event()

        self._initVars()
        self._configureStyles()
        self._buildUi()
        self._applySavedConfig()
        self._onHeadChanged()

        # 저장된 창 크기/위치 복원
        geometry = self.config.get("window_geometry", "900x700+100+100")
        self.root.geometry(geometry)
        self.root.protocol("WM_DELETE_WINDOW", self._onClose)

    # ── 변수 초기화 ────────────────────────────────────────────────────────────

    def _initVars(self):
        """Head/Worker LLM 선택 변수 초기화"""
        self.headVar = tk.StringVar(value="claude")
        self.workerVars = {key: tk.BooleanVar(value=False)
                          for _, key in SUPPORTED_LLMS}

    # ── 스타일 설정 ────────────────────────────────────────────────────────────

    def _configureStyles(self):
        """ttk 위젯 테마 및 커스텀 스타일 설정"""
        style = ttk.Style()
        style.theme_use("clam")

        # 전역 배경 및 기본 폰트
        style.configure(".", font=("맑은 고딕", 10), background="#f0f2f5")

        # 프레임 스타일
        style.configure("TFrame", background="#f0f2f5")
        style.configure("TLabelframe", background="#f0f2f5",
                        font=("맑은 고딕", 10, "bold"))
        style.configure("TLabelframe.Label", background="#f0f2f5",
                        foreground="#333333", font=("맑은 고딕", 10, "bold"))

        # 라디오 버튼 / 체크박스 스타일
        style.configure("TRadiobutton", background="#f0f2f5",
                        font=("맑은 고딕", 10))
        style.configure("TCheckbutton", background="#f0f2f5",
                        font=("맑은 고딕", 10))

        # 실행 버튼 (강조 스타일)
        style.configure("Run.TButton", font=("맑은 고딕", 10, "bold"),
                        padding=(16, 6))

        # 중단 버튼
        style.configure("Stop.TButton", font=("맑은 고딕", 10),
                        padding=(12, 6))

        # 일반 액션 버튼
        style.configure("Action.TButton", font=("맑은 고딕", 9),
                        padding=(10, 4))

        # 종료 버튼
        style.configure("Exit.TButton", font=("맑은 고딕", 9),
                        padding=(10, 4))

        # 하단 상태바 라벨
        style.configure("Status.TLabel", background="#e0e3e8",
                        foreground="#555555", font=("맑은 고딕", 9),
                        padding=(8, 4))

    # ── UI 구성 ────────────────────────────────────────────────────────────────

    def _buildUi(self):
        """전체 UI 레이아웃 구축"""
        self.root.title("MultiMind v0.4.0 — 멀티 LLM 오케스트레이터")
        self.root.configure(bg="#f0f2f5")

        # 메인 컨테이너 프레임
        mainFrame = ttk.Frame(self.root, padding="12")
        mainFrame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        mainFrame.columnconfigure(0, weight=1)

        # 각 UI 섹션 빌드
        self._buildHeader(mainFrame)
        self._buildHeadSection(mainFrame)
        self._buildWorkerSection(mainFrame)
        self._buildPromptSection(mainFrame)
        self._buildButtonSection(mainFrame)
        self._buildProgressSection(mainFrame)
        self._buildOutputSection(mainFrame)
        self._buildLogSection(mainFrame)

        # 하단 상태바
        self._buildStatusBar()

    def _buildHeader(self, parent):
        """앱 상단 타이틀 헤더"""
        headerFrame = ttk.Frame(parent)
        headerFrame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        headerFrame.columnconfigure(0, weight=1)

        titleLabel = ttk.Label(
            headerFrame, text="MultiMind",
            font=("맑은 고딕", 18, "bold"),
            foreground="#1a1a2e", background="#f0f2f5"
        )
        titleLabel.grid(row=0, column=0, sticky="w")

        subtitleLabel = ttk.Label(
            headerFrame, text="멀티 LLM 오케스트레이터",
            font=("맑은 고딕", 9),
            foreground="#7f8c8d", background="#f0f2f5"
        )
        subtitleLabel.grid(row=1, column=0, sticky="w")

        versionLabel = ttk.Label(
            headerFrame, text="v0.4.0",
            font=("맑은 고딕", 9),
            foreground="#95a5a6", background="#f0f2f5"
        )
        versionLabel.grid(row=0, column=1, sticky="e", padx=(0, 4))

    def _buildHeadSection(self, parent):
        """Head LLM 선택 라디오 버튼 섹션"""
        frame = ttk.LabelFrame(parent, text="  Head LLM (프롬프트 정제 + 결과 종합)  ",
                               padding="10")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        # 5개 LLM을 2행으로 배치
        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            row = i // 3
            col = i % 3
            rb = ttk.Radiobutton(
                frame, text=f"  {label}", variable=self.headVar, value=key,
                command=self._onHeadChanged
            )
            rb.grid(row=row, column=col, padx=16, pady=2, sticky="w")

    def _buildWorkerSection(self, parent):
        """Worker LLM 선택 체크박스 섹션"""
        frame = ttk.LabelFrame(parent, text="  Worker LLM (Head 선택 시 자동 비활성화)  ",
                               padding="10")
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        self.workerCheckboxes = {}
        # 5개 LLM을 2행으로 배치
        for i, (label, key) in enumerate(SUPPORTED_LLMS):
            row = i // 3
            col = i % 3
            cb = ttk.Checkbutton(
                frame, text=f"  {label}", variable=self.workerVars[key]
            )
            cb.grid(row=row, column=col, padx=16, pady=2, sticky="w")
            self.workerCheckboxes[key] = cb

    def _buildPromptSection(self, parent):
        """프롬프트 입력 텍스트 영역 섹션"""
        frame = ttk.LabelFrame(parent, text="  프롬프트 입력  ", padding="10")
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)

        self.promptText = tk.Text(
            frame, height=5, wrap="word",
            font=("맑은 고딕", 10),
            relief="flat", bd=0,
            highlightthickness=1, highlightcolor="#3498db",
            highlightbackground="#bdc3c7",
            padx=8, pady=6
        )
        self.promptText.grid(row=0, column=0, sticky="ew")

        # 프롬프트 스크롤바
        promptScrollbar = ttk.Scrollbar(frame, command=self.promptText.yview)
        promptScrollbar.grid(row=0, column=1, sticky="ns")
        self.promptText["yscrollcommand"] = promptScrollbar.set

    def _buildButtonSection(self, parent):
        """실행/중단/지우기/복사/종료 버튼 섹션"""
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, sticky="ew", pady=(4, 8))

        # 실행 버튼
        self.runButton = ttk.Button(
            frame, text="▶  실행", style="Run.TButton",
            command=self._onRunClicked
        )
        self.runButton.pack(side="left", padx=(0, 6))

        # 중단 버튼 (실행 중에만 활성화)
        self.stopButton = ttk.Button(
            frame, text="■  중단", style="Stop.TButton",
            command=self._onStopClicked, state="disabled"
        )
        self.stopButton.pack(side="left", padx=(0, 6))

        # 프롬프트 지우기 버튼
        clearPromptButton = ttk.Button(
            frame, text="지우기", style="Action.TButton",
            command=self._clearPrompt
        )
        clearPromptButton.pack(side="left", padx=(0, 6))

        # 결과 복사 버튼
        copyButton = ttk.Button(
            frame, text="결과 복사", style="Action.TButton",
            command=self._copyOutput
        )
        copyButton.pack(side="left", padx=(0, 6))

        # 종료 버튼 (#27: 프로그램 종료 버튼 추가)
        self.exitButton = ttk.Button(
            frame, text="종료", style="Exit.TButton",
            command=self._onClose
        )
        self.exitButton.pack(side="right")

    def _buildProgressSection(self, parent):
        """프로그레스 바 섹션 (오케스트레이션 진행 상태 표시)"""
        self.progressFrame = ttk.Frame(parent)
        self.progressFrame.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self.progressFrame.columnconfigure(0, weight=1)

        self.progressBar = ttk.Progressbar(
            self.progressFrame, mode="determinate",
            maximum=100, value=0
        )
        self.progressBar.grid(row=0, column=0, sticky="ew")

        self.progressLabel = ttk.Label(
            self.progressFrame, text="",
            font=("맑은 고딕", 8), foreground="#7f8c8d",
            background="#f0f2f5"
        )
        self.progressLabel.grid(row=1, column=0, sticky="w")

        # 초기 상태에서는 숨김
        self.progressFrame.grid_remove()

    def _buildOutputSection(self, parent):
        """최종 합성 결과 출력 섹션"""
        frame = ttk.LabelFrame(parent, text="  최종 합성 결과  ", padding="10")
        frame.grid(row=6, column=0, sticky="nsew", pady=(0, 6))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(6, weight=3)

        self.outputText = tk.Text(
            frame, height=10, wrap="word",
            state="disabled", font=("맑은 고딕", 10),
            bg="#ffffff", relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#bdc3c7",
            padx=8, pady=6
        )
        self.outputText.grid(row=0, column=0, sticky="nsew")

        # 결과 스크롤바
        outputScrollbar = ttk.Scrollbar(frame, command=self.outputText.yview)
        outputScrollbar.grid(row=0, column=1, sticky="ns")
        self.outputText["yscrollcommand"] = outputScrollbar.set

    def _buildLogSection(self, parent):
        """진행 로그 출력 섹션 (다크 테마)"""
        frame = ttk.LabelFrame(parent, text="  진행 로그  ", padding="10")
        frame.grid(row=7, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(7, weight=1)

        self.logText = tk.Text(
            frame, height=6, wrap="word",
            state="disabled", font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4",
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#555555",
            padx=8, pady=6,
            insertbackground="#ffffff"
        )
        self.logText.grid(row=0, column=0, sticky="nsew")

        # 로그 색상 태그 정의
        self.logText.tag_config("error", foreground="#f48771")
        self.logText.tag_config("success", foreground="#4ec9b0")
        self.logText.tag_config("phase", foreground="#dcdcaa")
        self.logText.tag_config("info", foreground="#569cd6")

        # 로그 스크롤바
        logScrollbar = ttk.Scrollbar(frame, command=self.logText.yview)
        logScrollbar.grid(row=0, column=1, sticky="ns")
        self.logText["yscrollcommand"] = logScrollbar.set

    def _buildStatusBar(self):
        """하단 상태 표시줄"""
        self.statusLabel = ttk.Label(
            self.root, text="  대기 중",
            style="Status.TLabel", anchor="w"
        )
        self.statusLabel.grid(row=1, column=0, sticky="ew")

    # ── 저장된 설정 적용 ──────────────────────────────────────────────────────

    def _applySavedConfig(self):
        """config.json에서 로드한 Head/Worker 설정을 UI에 반영"""
        headValue = self.config.get("head", "claude")
        workerList = self.config.get("workers", ["chatgpt", "gemini"])
        self.headVar.set(headValue)
        for key, var in self.workerVars.items():
            var.set(key in workerList)

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _onHeadChanged(self, *args):
        """Head LLM 변경 시 동일 Worker 체크박스 비활성화"""
        selectedHead = self.headVar.get()
        for key, cb in self.workerCheckboxes.items():
            if key == selectedHead:
                self.workerVars[key].set(False)
                cb.configure(state="disabled")
            else:
                cb.configure(state="normal")

    def _onRunClicked(self):
        """실행 버튼 클릭 — 입력 검증 후 오케스트레이터 백그라운드 실행"""
        # 프롬프트 입력 검증
        promptValue = self.promptText.get("1.0", "end").strip()
        if not promptValue:
            messagebox.showwarning("입력 오류", "프롬프트를 입력해주세요.")
            return

        # Worker 선택 검증
        headValue = self.headVar.get()
        workerList = [key for key, var in self.workerVars.items()
                      if var.get() and key != headValue]

        if not workerList:
            messagebox.showwarning("설정 오류",
                                   "Worker LLM을 최소 1개 이상 선택해주세요.")
            return

        # 현재 설정 저장
        self.configManager.save(headValue, workerList,
                                geometry=self.root.geometry())
        writeLog(f"실행 시작 | Head={headValue} | Workers={workerList}")

        # UI 상태 전환 (실행 중)
        self._setRunningState(True)
        self._clearOutput()
        self._clearLog()

        # 중단 이벤트 초기화 및 오케스트레이터 생성
        self._stopEvent.clear()
        self.eventQueue = queue.Queue()
        orchestrator = Orchestrator(
            headValue, workerList, promptValue, self.eventQueue,
            settings=self.config.get("settings", {}),
            stopEvent=self._stopEvent
        )

        # 백그라운드 스레드에서 오케스트레이션 실행
        threading.Thread(target=orchestrator.run, daemon=True).start()

        # 이벤트 큐 폴링 시작
        self._polling = True
        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _onStopClicked(self):
        """중단 버튼 클릭 — 실행 중인 오케스트레이션 중단"""
        if messagebox.askyesno("실행 중단", "진행 중인 작업을 중단하시겠습니까?"):
            self._stopEvent.set()
            self._appendLog("사용자에 의해 실행이 중단되었습니다.", tag="error")
            self.statusLabel.configure(text="  중단됨")
            self._finish()

    def _onClose(self):
        """프로그램 종료 — 종료 버튼 및 창 닫기(X) 공용 핸들러"""
        # 실행 중이면 종료 확인
        if self._polling:
            if not messagebox.askyesno("종료 확인",
                                       "작업이 진행 중입니다. 종료하시겠습니까?"):
                return
            self._stopEvent.set()

        # 현재 설정 저장 후 종료
        self.configManager.save(
            self.headVar.get(),
            [k for k, v in self.workerVars.items() if v.get()],
            geometry=self.root.geometry()
        )
        self.root.destroy()

    def _copyOutput(self):
        """결과 텍스트를 클립보드에 복사"""
        outputValue = self.outputText.get("1.0", "end").strip()
        if outputValue:
            self.root.clipboard_clear()
            self.root.clipboard_append(outputValue)
            self.statusLabel.configure(text="  결과가 클립보드에 복사되었습니다")
        else:
            self.statusLabel.configure(text="  복사할 결과가 없습니다")

    def _clearPrompt(self):
        """프롬프트 입력 텍스트 지우기"""
        self.promptText.delete("1.0", "end")

    # ── 이벤트 큐 처리 ────────────────────────────────────────────────────────

    def _pollEventQueue(self):
        """이벤트 큐를 주기적으로 폴링하여 UI 업데이트 처리"""
        if not self._polling:
            return

        try:
            while True:
                event = self.eventQueue.get_nowait()
                self._handleEvent(event)
        except queue.Empty:
            pass

        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _handleEvent(self, event: dict):
        """이벤트 타입별 UI 업데이트 분기 처리"""
        eventType = event.get("type")

        if eventType == "log":
            self._appendLog(event["message"])

        elif eventType == "phase":
            # Phase 변경 로그 (강조 표시) 및 프로그레스 바 업데이트
            phaseText = f"[Phase {event['phase']}] {event['description']}"
            self._appendLog(phaseText, tag="phase")
            self.statusLabel.configure(text=f"  {event['description']}")
            self._updateProgress(event["phase"], event["description"])

        elif eventType == "worker_done":
            msg = f"[{event['llm'].upper()}] 응답 수신 완료"
            self._appendLog(msg, tag="success")

        elif eventType == "worker_error":
            msg = f"[{event['llm'].upper()}] 오류: {event['error']}"
            self._appendLog(msg, tag="error")

        elif eventType == "final_result":
            # 오케스트레이션 성공 완료
            self._setOutput(event["text"])
            self._appendLog("오케스트레이션 완료", tag="success")
            self.statusLabel.configure(text="  완료")
            self._updateProgress(4, "완료")
            self._finish()

        elif eventType == "fatal_error":
            # 치명적 오류 — 다이얼로그 표시
            self._appendLog(f"오류: {event['error']}", tag="error")
            messagebox.showerror("실행 오류", event["error"])
            self.statusLabel.configure(text="  오류 발생")
            self._finish()

        elif eventType == "stopped":
            # 사용자 중단
            self._appendLog("실행이 중단되었습니다.", tag="error")
            self.statusLabel.configure(text="  중단됨")
            self._finish()

    def _finish(self):
        """실행 완료/오류/중단 후 UI 상태 복원"""
        self._polling = False
        self._setRunningState(False)

    def _setRunningState(self, isRunning: bool):
        """실행 상태에 따라 버튼 활성/비활성 및 프로그레스 바 전환"""
        if isRunning:
            self.runButton.configure(state="disabled")
            self.stopButton.configure(state="normal")
            self.exitButton.configure(state="disabled")
            self.progressBar["value"] = 0
            self.progressLabel.configure(text="")
            self.progressFrame.grid()
        else:
            self.runButton.configure(state="normal")
            self.stopButton.configure(state="disabled")
            self.exitButton.configure(state="normal")

    def _updateProgress(self, phase: int, description: str):
        """Phase에 따라 프로그레스 바 업데이트 (0~3: 각 25%, 4: 완료)"""
        phaseProgress = {0: 10, 1: 30, 2: 60, 3: 85, 4: 100}
        value = phaseProgress.get(phase, 0)
        self.progressBar["value"] = value
        self.progressLabel.configure(text=f"  Phase {phase}: {description}")

    # ── 텍스트 위젯 헬퍼 ──────────────────────────────────────────────────────

    def _appendLog(self, message: str, tag: str = None):
        """로그 텍스트 위젯에 메시지 추가 (선택적 색상 태그)"""
        self.logText.configure(state="normal")
        if tag:
            self.logText.insert("end", message + "\n", tag)
        else:
            self.logText.insert("end", message + "\n")
        self.logText.see("end")
        self.logText.configure(state="disabled")

    def _setOutput(self, text: str):
        """결과 텍스트 위젯 내용 설정"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.insert("1.0", text)
        self.outputText.configure(state="disabled")

    def _clearOutput(self):
        """결과 텍스트 위젯 초기화"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.configure(state="disabled")

    def _clearLog(self):
        """로그 텍스트 위젯 초기화"""
        self.logText.configure(state="normal")
        self.logText.delete("1.0", "end")
        self.logText.configure(state="disabled")
