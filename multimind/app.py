# Tkinter GUI 모듈 — MultiMind 메인 인터페이스
# 라이트 테마, 밑줄 탭 LLM 선택, macOS 네이티브 스타일

import platform
import queue
import threading
import tkinter as tk
from tkinter import messagebox

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

# ── 라이트 테마 컬러 팔레트 (쿨 그레이) ──────────────────────────────────────

C = {
    "bg":           "#F5F6FA",
    "surface":      "#FFFFFF",
    "inputBg":      "#FFFFFF",
    "border":       "#E2E4EA",
    "borderFocus":  "#007AFF",
    "text":         "#1D1D1F",
    "text2":        "#6E7179",
    "text3":        "#A0A3AB",
    "accent":       "#007AFF",
    "success":      "#34C759",
    "error":        "#FF3B30",
    "warning":      "#FF9500",
    "info":         "#007AFF",
    "btnPrimary":   "#007AFF",
    "btnPrimaryH":  "#0062CC",
    "btnSecondary": "#E8E9ED",
    "btnSecondaryH":"#D5D6DA",
    "btnDanger":    "#FF3B30",
    "btnDangerH":   "#D63028",
    "statusBar":    "#ECEDF1",
    "logBg":        "#F8F9FC",
    "logBorder":    "#E2E4EA",
    "progressTrack":"#E2E4EA",
    "disabledBg":   "#F0F1F4",
    "disabledText": "#C5C7CD",
}

# LLM별 브랜드 색상 (밑줄 탭 컬러)
LLM_COLORS = {
    "claude":     "#D97706",
    "chatgpt":    "#10A37F",
    "gemini":     "#4285F4",
    "grok":       "#6B7280",
    "perplexity": "#20808D",
}

# 프롬프트 플레이스홀더
_PLACEHOLDER = "여기에 프롬프트를 입력하세요..."


def _fontFamily() -> str:
    """OS별 시스템 폰트"""
    s = platform.system()
    if s == "Windows":
        return "맑은 고딕"
    if s == "Darwin":
        return "Apple SD Gothic Neo"
    return "Noto Sans CJK KR"


def _monoFamily() -> str:
    """OS별 고정폭 폰트"""
    s = platform.system()
    if s == "Windows":
        return "Consolas"
    if s == "Darwin":
        return "Menlo"
    return "Monospace"


class MultiMindApp:
    """MultiMind 메인 GUI (라이트 테마, macOS 네이티브 스타일)"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.configManager = ConfigManager()
        self.config = self.configManager.load()
        self.eventQueue: queue.Queue = queue.Queue()
        self._polling = False
        self._stopEvent = threading.Event()
        self._ff = _fontFamily()
        self._mf = _monoFamily()
        self._hasPlaceholder = True

        self._initVars()
        self._buildUi()
        self._applySavedConfig()
        self._onHeadChanged()
        self._bindShortcuts()

        geometry = self.config.get("window_geometry", "1000x750+100+100")
        self.root.geometry(geometry)
        self.root.protocol("WM_DELETE_WINDOW", self._onClose)

    # ── 초기화 ─────────────────────────────────────────────────────────────────

    def _initVars(self):
        self.headVar = tk.StringVar(value="claude")
        self.workerVars = {
            key: tk.BooleanVar(value=False) for _, key in SUPPORTED_LLMS
        }

    def _bindShortcuts(self):
        self.root.bind("<Control-Return>", lambda e: self._onRunClicked())
        self.root.bind("<Control-q>", lambda e: self._onClose())

    # ── UI 구성 ────────────────────────────────────────────────────────────────

    def _buildUi(self):
        self.root.title("MultiMind")
        self.root.configure(bg=C["bg"])

        main = tk.Frame(self.root, bg=C["bg"], padx=20, pady=16)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        self._buildHeader(main)
        self._buildHeadSection(main)
        self._buildWorkerSection(main)
        self._buildPromptSection(main)
        self._buildButtonSection(main)
        self._buildProgressSection(main)
        self._buildOutputSection(main)
        self._buildLogSection(main)
        self._buildStatusBar()

    # ── 헤더 ───────────────────────────────────────────────────────────────────

    def _buildHeader(self, parent):
        frame = tk.Frame(parent, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))

        tk.Label(
            frame, text="MultiMind",
            font=(self._ff, 20, "bold"),
            fg=C["text"], bg=C["bg"],
        ).pack(side="left")

        # 구분선
        tk.Frame(parent, bg=C["border"], height=1).grid(
            row=0, column=0, sticky="sew"
        )

    # ── Head LLM ───────────────────────────────────────────────────────────────

    def _buildHeadSection(self, parent):
        card = self._card(parent, row=1)

        titleRow = tk.Frame(card, bg=C["surface"])
        titleRow.pack(fill="x", pady=(0, 12))
        tk.Label(
            titleRow, text="Head LLM",
            font=(self._ff, 11, "bold"), fg=C["text"], bg=C["surface"],
        ).pack(side="left")

        tabRow = tk.Frame(card, bg=C["surface"])
        tabRow.pack(fill="x")
        self._headTabs = {}
        for _, (label, key) in enumerate(SUPPORTED_LLMS):
            tab = self._tab(
                tabRow, label, key,
                onClick=lambda k=key: self._selectHead(k),
            )
            tab.pack(side="left", padx=(0, 24))
            self._headTabs[key] = tab

    # ── Worker LLM ─────────────────────────────────────────────────────────────

    def _buildWorkerSection(self, parent):
        card = self._card(parent, row=2)

        titleRow = tk.Frame(card, bg=C["surface"])
        titleRow.pack(fill="x", pady=(0, 12))
        tk.Label(
            titleRow, text="Worker LLM",
            font=(self._ff, 11, "bold"), fg=C["text"], bg=C["surface"],
        ).pack(side="left")

        self._workerCountLabel = tk.Label(
            titleRow, text="0개 선택",
            font=(self._ff, 9, "bold"), fg=C["accent"], bg=C["surface"],
        )
        self._workerCountLabel.pack(side="right")

        tabRow = tk.Frame(card, bg=C["surface"])
        tabRow.pack(fill="x")
        self._workerTabs = {}
        for _, (label, key) in enumerate(SUPPORTED_LLMS):
            tab = self._tab(
                tabRow, label, key,
                onClick=lambda k=key: self._toggleWorker(k),
            )
            tab.pack(side="left", padx=(0, 24))
            self._workerTabs[key] = tab

    # ── 프롬프트 ───────────────────────────────────────────────────────────────

    def _buildPromptSection(self, parent):
        card = self._card(parent, row=3)

        titleRow = tk.Frame(card, bg=C["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        titleRow.columnconfigure(0, weight=1)
        tk.Label(
            titleRow, text="프롬프트",
            font=(self._ff, 11, "bold"), fg=C["text"], bg=C["surface"],
        ).grid(row=0, column=0, sticky="w")

        self._charCountLabel = tk.Label(
            titleRow, text="0자",
            font=(self._ff, 9), fg=C["text3"], bg=C["surface"],
        )
        self._charCountLabel.grid(row=0, column=1, sticky="e")

        tk.Label(
            titleRow, text="Ctrl+Enter 실행",
            font=(self._ff, 8), fg=C["text3"], bg=C["surface"],
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        # 입력 필드 (1px 테두리 래퍼)
        self._promptWrapper = tk.Frame(card, bg=C["border"], padx=1, pady=1)
        self._promptWrapper.pack(fill="x")

        self.promptText = tk.Text(
            self._promptWrapper, height=5, wrap="word",
            font=(self._ff, 11),
            bg=C["inputBg"], fg=C["text3"],
            insertbackground=C["text"],
            selectbackground=C["accent"], selectforeground="#FFFFFF",
            relief="flat", bd=0, padx=12, pady=10,
        )
        self.promptText.pack(fill="x")

        self.promptText.insert("1.0", _PLACEHOLDER)
        self._hasPlaceholder = True
        self.promptText.bind("<FocusIn>", self._onPromptFocusIn)
        self.promptText.bind("<FocusOut>", self._onPromptFocusOut)
        self.promptText.bind("<KeyRelease>", self._updateCharCount)

    # ── 버튼 ───────────────────────────────────────────────────────────────────

    def _buildButtonSection(self, parent):
        frame = tk.Frame(parent, bg=C["bg"])
        frame.grid(row=4, column=0, sticky="ew", pady=(10, 4))

        # 실행
        self.runButton = self._btn(
            frame, "▶  실행",
            bg=C["btnPrimary"], hoverBg=C["btnPrimaryH"],
            fg="#FFFFFF", bold=True, padx=20,
            command=self._onRunClicked,
        )
        self.runButton.pack(side="left", padx=(0, 8))

        # 중단
        self.stopButton = self._btn(
            frame, "■  중단",
            bg=C["btnDanger"], hoverBg=C["btnDangerH"],
            fg="#FFFFFF", padx=14,
            command=self._onStopClicked,
        )
        self.stopButton.pack(side="left", padx=(0, 8))
        self._disableBtn(self.stopButton)

        # 지우기
        self._btn(
            frame, "지우기",
            bg=C["btnSecondary"], hoverBg=C["btnSecondaryH"],
            fg=C["text2"], command=self._clearPrompt,
        ).pack(side="left", padx=(0, 6))

        # 결과 복사
        self._btn(
            frame, "결과 복사",
            bg=C["btnSecondary"], hoverBg=C["btnSecondaryH"],
            fg=C["text2"], command=self._copyOutput,
        ).pack(side="left", padx=(0, 6))

        # 종료
        self.exitButton = self._btn(
            frame, "종료",
            bg=C["bg"], hoverBg=C["btnSecondary"],
            fg=C["text3"], command=self._onClose,
        )
        self.exitButton.pack(side="right")

    # ── 프로그레스 ─────────────────────────────────────────────────────────────

    def _buildProgressSection(self, parent):
        self.progressFrame = tk.Frame(parent, bg=C["bg"])
        self.progressFrame.grid(row=5, column=0, sticky="ew", pady=(4, 8))
        self.progressFrame.columnconfigure(0, weight=1)

        labelRow = tk.Frame(self.progressFrame, bg=C["bg"])
        labelRow.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        labelRow.columnconfigure(0, weight=1)

        self.progressLabel = tk.Label(
            labelRow, text="",
            font=(self._ff, 9), fg=C["text2"], bg=C["bg"], anchor="w",
        )
        self.progressLabel.grid(row=0, column=0, sticky="w")

        self._progressPercent = tk.Label(
            labelRow, text="",
            font=(self._ff, 9, "bold"), fg=C["accent"], bg=C["bg"],
        )
        self._progressPercent.grid(row=0, column=1, sticky="e")

        self._progressCanvas = tk.Canvas(
            self.progressFrame, height=4,
            bg=C["progressTrack"], highlightthickness=0, bd=0,
        )
        self._progressCanvas.grid(row=1, column=0, sticky="ew")
        self._progressValue = 0
        self._progressCanvas.bind("<Configure>", self._drawProgress)
        self.progressFrame.grid_remove()

    # ── 최종 결과 ──────────────────────────────────────────────────────────────

    def _buildOutputSection(self, parent):
        card = self._card(parent, row=6, expand=True, weight=3)

        titleRow = tk.Frame(card, bg=C["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        tk.Label(
            titleRow, text="최종 합성 결과",
            font=(self._ff, 11, "bold"), fg=C["text"], bg=C["surface"],
        ).pack(side="left")
        self._outputLenLabel = tk.Label(
            titleRow, text="",
            font=(self._ff, 9), fg=C["text3"], bg=C["surface"],
        )
        self._outputLenLabel.pack(side="right")

        textFrame = tk.Frame(card, bg=C["border"], padx=1, pady=1)
        textFrame.pack(fill="both", expand=True)
        self.outputText = tk.Text(
            textFrame, wrap="word", state="disabled",
            font=(self._ff, 11),
            bg=C["inputBg"], fg=C["text"],
            insertbackground=C["text"],
            selectbackground=C["accent"], selectforeground="#FFFFFF",
            relief="flat", bd=0, padx=12, pady=10,
        )
        sb = tk.Scrollbar(textFrame, command=self.outputText.yview)
        sb.pack(side="right", fill="y")
        self.outputText.pack(side="left", fill="both", expand=True)
        self.outputText["yscrollcommand"] = sb.set

    # ── 진행 로그 ──────────────────────────────────────────────────────────────

    def _buildLogSection(self, parent):
        card = self._card(parent, row=7, expand=True, weight=1)

        titleRow = tk.Frame(card, bg=C["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        tk.Label(
            titleRow, text="진행 로그",
            font=(self._ff, 11, "bold"), fg=C["text"], bg=C["surface"],
        ).pack(side="left")

        textFrame = tk.Frame(card, bg=C["logBorder"], padx=1, pady=1)
        textFrame.pack(fill="both", expand=True)
        self.logText = tk.Text(
            textFrame, wrap="word", state="disabled",
            font=(self._mf, 9),
            bg=C["logBg"], fg=C["text2"],
            insertbackground=C["text"],
            selectbackground=C["accent"], selectforeground="#FFFFFF",
            relief="flat", bd=0, padx=12, pady=8,
        )
        sb = tk.Scrollbar(textFrame, command=self.logText.yview)
        sb.pack(side="right", fill="y")
        self.logText.pack(side="left", fill="both", expand=True)
        self.logText["yscrollcommand"] = sb.set

        self.logText.tag_config("error", foreground=C["error"])
        self.logText.tag_config("success", foreground="#2D9E46")
        self.logText.tag_config("phase", foreground=C["warning"])
        self.logText.tag_config("info", foreground=C["accent"])

    # ── 상태 바 ────────────────────────────────────────────────────────────────

    def _buildStatusBar(self):
        bar = tk.Frame(self.root, bg=C["statusBar"], height=26)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)

        self._statusDot = tk.Canvas(
            bar, width=8, height=8, bg=C["statusBar"], highlightthickness=0,
        )
        self._statusDot.pack(side="left", padx=(12, 6), pady=9)
        self._statusDot.create_oval(0, 0, 8, 8, fill=C["success"], outline="")

        self.statusLabel = tk.Label(
            bar, text="대기 중",
            font=(self._ff, 9), fg=C["text2"], bg=C["statusBar"], anchor="w",
        )
        self.statusLabel.pack(side="left", fill="x")

    # ── 위젯 헬퍼: 카드 ──────────────────────────────────────────────────────

    def _card(self, parent, row, expand=False, weight=0):
        outer = tk.Frame(parent, bg=C["border"], padx=1, pady=1)
        outer.grid(
            row=row, column=0,
            sticky="nsew" if expand else "ew",
            pady=(0, 10),
        )
        if expand:
            parent.rowconfigure(row, weight=weight)
        inner = tk.Frame(outer, bg=C["surface"], padx=16, pady=14)
        inner.pack(fill="both", expand=True)
        return inner

    # ── 위젯 헬퍼: 밑줄 탭 ───────────────────────────────────────────────────

    def _tab(self, parent, label, key, onClick=None):
        """밑줄 스타일 탭 — 선택 시 브랜드 컬러 밑줄 표시"""
        brandColor = LLM_COLORS.get(key, C["accent"])

        frame = tk.Frame(parent, bg=C["surface"], cursor="hand2")

        textLabel = tk.Label(
            frame, text=label,
            font=(self._ff, 11), fg=C["text2"], bg=C["surface"],
            cursor="hand2", pady=4,
        )
        textLabel.pack()

        # 밑줄 바 (미선택 시 투명 = surface 배경과 동일)
        underline = tk.Frame(frame, height=2, bg=C["surface"])
        underline.pack(fill="x", pady=(2, 0))

        # 내부 상태
        frame._key = key
        frame._isSelected = False
        frame._isDisabled = False
        frame._brandColor = brandColor
        frame._textLabel = textLabel
        frame._underline = underline

        for w in (frame, textLabel):
            w.bind("<Button-1>", lambda e, cb=onClick: cb() if cb else None)
        return frame

    # ── 위젯 헬퍼: 버튼 ──────────────────────────────────────────────────────

    def _btn(self, parent, text, bg, hoverBg,
             command=None, fg="#FFFFFF", bold=False, padx=14):
        b = tk.Button(
            parent, text=text, command=command,
            font=(self._ff, 10, "bold" if bold else "normal"),
            fg=fg, bg=bg,
            activeforeground=fg, activebackground=hoverBg,
            disabledforeground=C["disabledText"],
            relief="flat", bd=0, cursor="hand2",
            padx=padx, pady=6,
        )
        b._normalBg = bg
        b._hoverBg = hoverBg
        b._normalFg = fg
        b.bind("<Enter>", lambda e, btn=b: self._btnEnter(btn))
        b.bind("<Leave>", lambda e, btn=b: self._btnLeave(btn))
        return b

    def _btnEnter(self, b):
        if str(b["state"]) != "disabled":
            b.configure(bg=b._hoverBg)

    def _btnLeave(self, b):
        if str(b["state"]) != "disabled":
            b.configure(bg=b._normalBg)

    def _disableBtn(self, b):
        b.configure(state="disabled", bg=C["disabledBg"], cursor="")

    def _enableBtn(self, b):
        b.configure(state="normal", bg=b._normalBg, cursor="hand2")

    # ── 탭 상태 갱신 ──────────────────────────────────────────────────────────

    def _selectHead(self, key):
        self.headVar.set(key)
        self._refreshHeadTabs()
        self._onHeadChanged()

    def _toggleWorker(self, key):
        # Head와 동일한 LLM 선택 시도 → 경고
        if key == self.headVar.get():
            self._setStatus(
                "Head LLM은 Worker로 선택할 수 없습니다", "warning"
            )
            return
        tab = self._workerTabs.get(key)
        if tab and tab._isDisabled:
            self._setStatus(
                "Head LLM은 Worker로 선택할 수 없습니다", "warning"
            )
            return
        self.workerVars[key].set(not self.workerVars[key].get())
        self._refreshWorkerTabs()

    def _refreshHeadTabs(self):
        sel = self.headVar.get()
        for key, tab in self._headTabs.items():
            selected = key == sel
            tab._isSelected = selected
            if selected:
                tab._textLabel.configure(
                    fg=C["text"], font=(self._ff, 11, "bold"),
                )
                tab._underline.configure(bg=tab._brandColor)
            else:
                tab._textLabel.configure(
                    fg=C["text2"], font=(self._ff, 11),
                )
                tab._underline.configure(bg=C["surface"])

    def _refreshWorkerTabs(self):
        head = self.headVar.get()
        count = 0
        for key, tab in self._workerTabs.items():
            disabled = key == head
            selected = self.workerVars[key].get() and not disabled
            tab._isDisabled = disabled
            tab._isSelected = selected

            if disabled:
                tab._textLabel.configure(
                    fg=C["disabledText"], font=(self._ff, 11),
                    cursor="arrow",
                )
                tab._underline.configure(bg=C["surface"])
                tab.configure(cursor="arrow")
            elif selected:
                count += 1
                tab._textLabel.configure(
                    fg=C["text"], font=(self._ff, 11, "bold"),
                    cursor="hand2",
                )
                tab._underline.configure(bg=tab._brandColor)
                tab.configure(cursor="hand2")
            else:
                tab._textLabel.configure(
                    fg=C["text2"], font=(self._ff, 11),
                    cursor="hand2",
                )
                tab._underline.configure(bg=C["surface"])
                tab.configure(cursor="hand2")

        self._workerCountLabel.configure(text=f"{count}개 선택")

    # ── 프로그레스 렌더링 ──────────────────────────────────────────────────────

    def _drawProgress(self, event=None):
        cv = self._progressCanvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        cv.create_rectangle(0, 0, w, h, fill=C["progressTrack"], outline="")
        if self._progressValue > 0:
            cv.create_rectangle(
                0, 0, int(w * self._progressValue / 100), h,
                fill=C["accent"], outline="",
            )

    # ── 설정 적용 ──────────────────────────────────────────────────────────────

    def _applySavedConfig(self):
        headVal = self.config.get("head", "claude")
        workerList = self.config.get("workers", ["chatgpt", "gemini"])
        self.headVar.set(headVal)
        for key, var in self.workerVars.items():
            var.set(key in workerList)
        self._refreshHeadTabs()
        self._refreshWorkerTabs()

    # ── 플레이스홀더 ──────────────────────────────────────────────────────────

    def _onPromptFocusIn(self, event):
        self._promptWrapper.configure(bg=C["borderFocus"])
        if self._hasPlaceholder:
            self.promptText.delete("1.0", "end")
            self.promptText.configure(fg=C["text"])
            self._hasPlaceholder = False

    def _onPromptFocusOut(self, event):
        self._promptWrapper.configure(bg=C["border"])
        if not self.promptText.get("1.0", "end").strip():
            self.promptText.insert("1.0", _PLACEHOLDER)
            self.promptText.configure(fg=C["text3"])
            self._hasPlaceholder = True

    def _getPromptText(self) -> str:
        if self._hasPlaceholder:
            return ""
        return self.promptText.get("1.0", "end").strip()

    def _updateCharCount(self, event=None):
        self._charCountLabel.configure(text=f"{len(self._getPromptText())}자")

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _onHeadChanged(self, *args):
        sel = self.headVar.get()
        if self.workerVars[sel].get():
            self.workerVars[sel].set(False)
        self._refreshHeadTabs()
        self._refreshWorkerTabs()

    def _onRunClicked(self):
        prompt = self._getPromptText()
        if not prompt:
            messagebox.showwarning("입력 오류", "프롬프트를 입력해주세요.")
            return

        head = self.headVar.get()
        workers = [
            k for k, v in self.workerVars.items()
            if v.get() and k != head
        ]
        if not workers:
            messagebox.showwarning(
                "설정 오류", "Worker LLM을 최소 1개 이상 선택해주세요."
            )
            return

        self.configManager.save(head, workers, geometry=self.root.geometry())
        writeLog(f"실행 시작 | Head={head} | Workers={workers}")

        self._setRunningState(True)
        self._clearOutput()
        self._clearLog()

        self._stopEvent.clear()
        self.eventQueue = queue.Queue()
        orch = Orchestrator(
            head, workers, prompt, self.eventQueue,
            settings=self.config.get("settings", {}),
            stopEvent=self._stopEvent,
        )
        threading.Thread(target=orch.run, daemon=True).start()
        self._polling = True
        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _onStopClicked(self):
        if messagebox.askyesno("실행 중단", "진행 중인 작업을 중단하시겠습니까?"):
            self._stopEvent.set()
            self._appendLog("사용자에 의해 실행이 중단되었습니다.", tag="error")
            self._setStatus("중단됨", "error")
            self._finish()

    def _onClose(self):
        if self._polling:
            if not messagebox.askyesno(
                "종료 확인", "작업이 진행 중입니다. 종료하시겠습니까?"
            ):
                return
            self._stopEvent.set()
        self.configManager.save(
            self.headVar.get(),
            [k for k, v in self.workerVars.items() if v.get()],
            geometry=self.root.geometry(),
        )
        self.root.destroy()

    def _copyOutput(self):
        val = self.outputText.get("1.0", "end").strip()
        if val:
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            self._setStatus("결과가 클립보드에 복사되었습니다", "success")
        else:
            self._setStatus("복사할 결과가 없습니다", "warning")

    def _clearPrompt(self):
        self.promptText.delete("1.0", "end")
        self.promptText.insert("1.0", _PLACEHOLDER)
        self.promptText.configure(fg=C["text3"])
        self._hasPlaceholder = True
        self._updateCharCount()

    # ── 이벤트 큐 ──────────────────────────────────────────────────────────────

    def _pollEventQueue(self):
        if not self._polling:
            return
        try:
            while True:
                ev = self.eventQueue.get_nowait()
                self._handleEvent(ev)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _handleEvent(self, ev: dict):
        t = ev.get("type")
        if t == "log":
            self._appendLog(ev["message"])
        elif t == "phase":
            self._appendLog(
                f"[Phase {ev['phase']}] {ev['description']}", tag="phase"
            )
            self._setStatus(ev["description"], "info")
            self._updateProgress(ev["phase"], ev["description"])
        elif t == "worker_done":
            self._appendLog(
                f"[{ev['llm'].upper()}] 응답 수신 완료", tag="success"
            )
        elif t == "worker_error":
            self._appendLog(
                f"[{ev['llm'].upper()}] 오류: {ev['error']}", tag="error"
            )
        elif t == "final_result":
            self._setOutput(ev["text"])
            self._appendLog("오케스트레이션 완료", tag="success")
            self._setStatus("완료", "success")
            self._updateProgress(4, "완료")
            self._finish()
        elif t == "fatal_error":
            self._appendLog(f"오류: {ev['error']}", tag="error")
            messagebox.showerror("실행 오류", ev["error"])
            self._setStatus("오류 발생", "error")
            self._finish()
        elif t == "stopped":
            self._appendLog("실행이 중단되었습니다.", tag="error")
            self._setStatus("중단됨", "error")
            self._finish()

    # ── 상태 전환 ──────────────────────────────────────────────────────────────

    def _finish(self):
        self._polling = False
        self._setRunningState(False)

    def _setRunningState(self, running: bool):
        if running:
            self._disableBtn(self.runButton)
            self._enableBtn(self.stopButton)
            self.stopButton.configure(bg=C["btnDanger"])
            self.exitButton.configure(state="disabled", cursor="")
            self._progressValue = 0
            self.progressLabel.configure(text="")
            self._progressPercent.configure(text="")
            self.progressFrame.grid()
            self._drawProgress()
            self._setStatus("실행 중...", "info")
        else:
            self._enableBtn(self.runButton)
            self.runButton.configure(bg=C["btnPrimary"])
            self._disableBtn(self.stopButton)
            self._enableBtn(self.exitButton)
            self.exitButton.configure(bg=self.exitButton._normalBg)

    def _updateProgress(self, phase: int, desc: str):
        mapping = {0: 10, 1: 30, 2: 60, 3: 85, 4: 100}
        val = mapping.get(phase, 0)
        self._progressValue = val
        self._drawProgress()
        names = {
            0: "브라우저 시작", 1: "프롬프트 정제",
            2: "Worker 응답 생성", 3: "결과 종합", 4: "완료",
        }
        self.progressLabel.configure(
            text=f"Phase {phase}/4 · {names.get(phase, desc)}"
        )
        self._progressPercent.configure(text=f"{val}%")

    def _setStatus(self, text: str, level: str = "info"):
        colors = {
            "info": C["info"], "success": C["success"],
            "error": C["error"], "warning": C["warning"],
        }
        self._statusDot.delete("all")
        self._statusDot.create_oval(
            0, 0, 8, 8, fill=colors.get(level, C["text2"]), outline=""
        )
        self.statusLabel.configure(text=text)

    # ── 텍스트 헬퍼 ──────────────────────────────────────────────────────────

    def _appendLog(self, msg: str, tag: str = None):
        self.logText.configure(state="normal")
        line = f"› {msg}\n"
        if tag:
            self.logText.insert("end", line, tag)
        else:
            self.logText.insert("end", line)
        self.logText.see("end")
        self.logText.configure(state="disabled")

    def _setOutput(self, text: str):
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.insert("1.0", text)
        self.outputText.configure(state="disabled")
        self._outputLenLabel.configure(text=f"{len(text)}자")

    def _clearOutput(self):
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.configure(state="disabled")
        self._outputLenLabel.configure(text="")

    def _clearLog(self):
        self.logText.configure(state="normal")
        self.logText.delete("1.0", "end")
        self.logText.configure(state="disabled")
