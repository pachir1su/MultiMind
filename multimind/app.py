# Tkinter GUI 모듈 — MultiMind 메인 인터페이스
# 다크 테마 기반 모던 UI, 이벤트 큐 비동기 업데이트, LLM 브랜드 컬러 pill 선택

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

# ── 다크 테마 컬러 팔레트 ────────────────────────────────────────────────────

COLORS = {
    "bg":          "#0f1117",
    "surface":     "#1a1b2e",
    "surface2":    "#252640",
    "inputBg":     "#141525",
    "border":      "#2d2e4a",
    "borderFocus": "#6c5ce7",
    "text":        "#e8e8f0",
    "text2":       "#9090a8",
    "text3":       "#5a5a70",
    "accent":      "#6c5ce7",
    "accentHover": "#8b7cf7",
    "success":     "#00b894",
    "error":       "#ff6b6b",
    "warning":     "#feca57",
    "info":        "#54a0ff",
    "runBg":       "#6c5ce7",
    "runHover":    "#8b7cf7",
    "stopBg":      "#ff6b6b",
    "stopHover":   "#ff8787",
    "statusBar":   "#0a0b12",
    "logBg":       "#0d0e18",
    "pillBg":      "#1e1f35",
}

# LLM별 브랜드 색상
LLM_COLORS = {
    "claude":     "#d97706",
    "chatgpt":    "#10a37f",
    "gemini":     "#4285f4",
    "grok":       "#8b8b9a",
    "perplexity": "#20808d",
}

# 프롬프트 플레이스홀더
_PLACEHOLDER = "여기에 프롬프트를 입력하세요..."


def _detectFontFamily() -> str:
    """OS별 최적 한글 폰트 반환"""
    osName = platform.system()
    if osName == "Windows":
        return "맑은 고딕"
    elif osName == "Darwin":
        return "Apple SD Gothic Neo"
    return "Noto Sans CJK KR"


def _detectMonoFamily() -> str:
    """OS별 고정폭 폰트 반환"""
    osName = platform.system()
    if osName == "Windows":
        return "Consolas"
    elif osName == "Darwin":
        return "Menlo"
    return "Monospace"


class MultiMindApp:
    """MultiMind 메인 GUI 애플리케이션 (다크 테마)"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.configManager = ConfigManager()
        self.config = self.configManager.load()
        self.eventQueue: queue.Queue = queue.Queue()
        self._polling = False
        self._stopEvent = threading.Event()

        # OS별 폰트
        self._fontFamily = _detectFontFamily()
        self._monoFamily = _detectMonoFamily()

        # 플레이스홀더 상태
        self._hasPlaceholder = True

        self._initVars()
        self._buildUi()
        self._applySavedConfig()
        self._onHeadChanged()
        self._bindShortcuts()

        # 저장된 창 크기/위치 복원
        geometry = self.config.get("window_geometry", "1000x750+100+100")
        self.root.geometry(geometry)
        self.root.protocol("WM_DELETE_WINDOW", self._onClose)

    # ── 변수 초기화 ────────────────────────────────────────────────────────────

    def _initVars(self):
        """Head/Worker LLM 선택 변수 초기화"""
        self.headVar = tk.StringVar(value="claude")
        self.workerVars = {
            key: tk.BooleanVar(value=False) for _, key in SUPPORTED_LLMS
        }

    # ── 키보드 단축키 ──────────────────────────────────────────────────────────

    def _bindShortcuts(self):
        """키보드 단축키 바인딩"""
        self.root.bind("<Control-Return>", lambda e: self._onRunClicked())
        self.root.bind("<Control-q>", lambda e: self._onClose())

    # ── 전체 UI 구성 ──────────────────────────────────────────────────────────

    def _buildUi(self):
        """전체 레이아웃 구축"""
        self.root.title("MultiMind — 멀티 LLM 오케스트레이터")
        self.root.configure(bg=COLORS["bg"])

        # 메인 컨테이너
        mainFrame = tk.Frame(self.root, bg=COLORS["bg"], padx=16, pady=12)
        mainFrame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        mainFrame.columnconfigure(0, weight=1)

        # 각 섹션 빌드
        self._buildHeader(mainFrame)
        self._buildHeadSection(mainFrame)
        self._buildWorkerSection(mainFrame)
        self._buildPromptSection(mainFrame)
        self._buildButtonSection(mainFrame)
        self._buildProgressSection(mainFrame)
        self._buildOutputSection(mainFrame)
        self._buildLogSection(mainFrame)
        self._buildStatusBar()

    # ── 헤더 ───────────────────────────────────────────────────────────────────

    def _buildHeader(self, parent):
        """앱 타이틀 + 버전 배지 + 서브타이틀"""
        headerFrame = tk.Frame(parent, bg=COLORS["bg"])
        headerFrame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        headerFrame.columnconfigure(1, weight=1)

        # 타이틀
        tk.Label(
            headerFrame, text="MultiMind",
            font=(self._fontFamily, 22, "bold"),
            fg=COLORS["text"], bg=COLORS["bg"],
        ).grid(row=0, column=0, sticky="w")

        # 버전 배지
        versionBadge = tk.Frame(
            headerFrame, bg=COLORS["accent"], padx=8, pady=2
        )
        versionBadge.grid(row=0, column=2, sticky="e", padx=(8, 0))
        tk.Label(
            versionBadge, text="v0.5.0",
            font=(self._fontFamily, 8, "bold"),
            fg="#ffffff", bg=COLORS["accent"],
        ).pack()

        # 서브타이틀
        tk.Label(
            headerFrame,
            text="멀티 LLM 오케스트레이터  ·  여러 AI의 지혜를 하나로",
            font=(self._fontFamily, 10),
            fg=COLORS["text3"], bg=COLORS["bg"],
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # 구분선
        tk.Frame(headerFrame, bg=COLORS["border"], height=1).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0)
        )

    # ── Head LLM 선택 ─────────────────────────────────────────────────────────

    def _buildHeadSection(self, parent):
        """Head LLM 선택 — 브랜드 컬러 pill 버튼"""
        card = self._createCard(parent, row=1)

        # 제목 행
        titleRow = tk.Frame(card, bg=COLORS["surface"])
        titleRow.pack(fill="x", pady=(0, 10))
        tk.Label(
            titleRow, text="Head LLM",
            font=(self._fontFamily, 11, "bold"),
            fg=COLORS["text"], bg=COLORS["surface"],
        ).pack(side="left")
        tk.Label(
            titleRow, text="프롬프트 정제 + 결과 종합",
            font=(self._fontFamily, 9),
            fg=COLORS["text3"], bg=COLORS["surface"],
        ).pack(side="left", padx=(8, 0))

        # pill 버튼 행
        pillFrame = tk.Frame(card, bg=COLORS["surface"])
        pillFrame.pack(fill="x")
        self._headPills = {}
        for _, (label, key) in enumerate(SUPPORTED_LLMS):
            pill = self._createPill(
                pillFrame, label, key,
                onClick=lambda k=key: self._selectHead(k),
            )
            pill.pack(side="left", padx=(0, 8), pady=2)
            self._headPills[key] = pill

    # ── Worker LLM 선택 ───────────────────────────────────────────────────────

    def _buildWorkerSection(self, parent):
        """Worker LLM 선택 — 토글 pill 버튼"""
        card = self._createCard(parent, row=2)

        titleRow = tk.Frame(card, bg=COLORS["surface"])
        titleRow.pack(fill="x", pady=(0, 10))
        tk.Label(
            titleRow, text="Worker LLM",
            font=(self._fontFamily, 11, "bold"),
            fg=COLORS["text"], bg=COLORS["surface"],
        ).pack(side="left")
        tk.Label(
            titleRow, text="Head 선택 시 자동 비활성화",
            font=(self._fontFamily, 9),
            fg=COLORS["text3"], bg=COLORS["surface"],
        ).pack(side="left", padx=(8, 0))

        # 선택 카운터 라벨
        self._workerCountLabel = tk.Label(
            titleRow, text="0개 선택",
            font=(self._fontFamily, 9, "bold"),
            fg=COLORS["accent"], bg=COLORS["surface"],
        )
        self._workerCountLabel.pack(side="right")

        pillFrame = tk.Frame(card, bg=COLORS["surface"])
        pillFrame.pack(fill="x")
        self._workerPills = {}
        for _, (label, key) in enumerate(SUPPORTED_LLMS):
            pill = self._createPill(
                pillFrame, label, key,
                onClick=lambda k=key: self._toggleWorker(k),
            )
            pill.pack(side="left", padx=(0, 8), pady=2)
            self._workerPills[key] = pill

    # ── 프롬프트 입력 ──────────────────────────────────────────────────────────

    def _buildPromptSection(self, parent):
        """프롬프트 입력 텍스트 영역 + 글자 수 + 단축키 힌트"""
        card = self._createCard(parent, row=3)

        # 제목 행
        titleRow = tk.Frame(card, bg=COLORS["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        titleRow.columnconfigure(0, weight=1)
        tk.Label(
            titleRow, text="프롬프트",
            font=(self._fontFamily, 11, "bold"),
            fg=COLORS["text"], bg=COLORS["surface"],
        ).grid(row=0, column=0, sticky="w")

        self._charCountLabel = tk.Label(
            titleRow, text="0자",
            font=(self._fontFamily, 9),
            fg=COLORS["text3"], bg=COLORS["surface"],
        )
        self._charCountLabel.grid(row=0, column=1, sticky="e")

        tk.Label(
            titleRow, text="Ctrl+Enter 실행",
            font=(self._fontFamily, 8),
            fg=COLORS["text3"], bg=COLORS["surface"],
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        # 입력 필드 래퍼 (1px 테두리 효과)
        self._promptWrapper = tk.Frame(
            card, bg=COLORS["border"], padx=1, pady=1
        )
        self._promptWrapper.pack(fill="x")

        self.promptText = tk.Text(
            self._promptWrapper, height=5, wrap="word",
            font=(self._fontFamily, 11),
            bg=COLORS["inputBg"], fg=COLORS["text3"],
            insertbackground=COLORS["accent"],
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            relief="flat", bd=0, padx=12, pady=10,
        )
        self.promptText.pack(fill="x")

        # 플레이스홀더 삽입
        self.promptText.insert("1.0", _PLACEHOLDER)
        self._hasPlaceholder = True

        # 포커스 이벤트 → 테두리 컬러 + 플레이스홀더 제어
        self.promptText.bind("<FocusIn>", self._onPromptFocusIn)
        self.promptText.bind("<FocusOut>", self._onPromptFocusOut)
        self.promptText.bind("<KeyRelease>", self._updateCharCount)

    # ── 액션 버튼 ──────────────────────────────────────────────────────────────

    def _buildButtonSection(self, parent):
        """실행/중단/지우기/복사/종료 버튼"""
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.grid(row=4, column=0, sticky="ew", pady=(8, 4))

        # 실행 (primary)
        self.runButton = self._createButton(
            frame, "▶  실행",
            bg=COLORS["runBg"], hoverBg=COLORS["runHover"],
            command=self._onRunClicked, bold=True, padx=20,
        )
        self.runButton.pack(side="left", padx=(0, 8))

        # 중단
        self.stopButton = self._createButton(
            frame, "■  중단",
            bg=COLORS["stopBg"], hoverBg=COLORS["stopHover"],
            command=self._onStopClicked, padx=14,
        )
        self.stopButton.pack(side="left", padx=(0, 8))
        self._setButtonDisabled(self.stopButton)

        # 보조: 지우기
        self._createButton(
            frame, "지우기",
            bg=COLORS["surface2"], hoverBg=COLORS["border"],
            command=self._clearPrompt, fg=COLORS["text2"],
        ).pack(side="left", padx=(0, 6))

        # 보조: 결과 복사
        self._createButton(
            frame, "결과 복사",
            bg=COLORS["surface2"], hoverBg=COLORS["border"],
            command=self._copyOutput, fg=COLORS["text2"],
        ).pack(side="left", padx=(0, 6))

        # 종료 (우측)
        self.exitButton = self._createButton(
            frame, "종료",
            bg=COLORS["surface2"], hoverBg="#4a2020",
            command=self._onClose, fg=COLORS["text3"],
        )
        self.exitButton.pack(side="right")

    # ── 프로그레스 ─────────────────────────────────────────────────────────────

    def _buildProgressSection(self, parent):
        """Canvas 기반 프로그레스 바 + 단계 라벨"""
        self.progressFrame = tk.Frame(parent, bg=COLORS["bg"])
        self.progressFrame.grid(row=5, column=0, sticky="ew", pady=(4, 8))
        self.progressFrame.columnconfigure(0, weight=1)

        # 라벨 행
        labelRow = tk.Frame(self.progressFrame, bg=COLORS["bg"])
        labelRow.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        labelRow.columnconfigure(0, weight=1)

        self.progressLabel = tk.Label(
            labelRow, text="",
            font=(self._fontFamily, 9),
            fg=COLORS["text2"], bg=COLORS["bg"], anchor="w",
        )
        self.progressLabel.grid(row=0, column=0, sticky="w")

        self._progressPercent = tk.Label(
            labelRow, text="",
            font=(self._fontFamily, 9, "bold"),
            fg=COLORS["accent"], bg=COLORS["bg"],
        )
        self._progressPercent.grid(row=0, column=1, sticky="e")

        # Canvas 프로그레스 바
        self._progressCanvas = tk.Canvas(
            self.progressFrame, height=6,
            bg=COLORS["surface2"], highlightthickness=0, bd=0,
        )
        self._progressCanvas.grid(row=1, column=0, sticky="ew")
        self._progressValue = 0
        self._progressCanvas.bind("<Configure>", self._drawProgress)

        # 초기 숨김
        self.progressFrame.grid_remove()

    # ── 최종 합성 결과 ─────────────────────────────────────────────────────────

    def _buildOutputSection(self, parent):
        """최종 결과 출력 텍스트 영역"""
        card = self._createCard(parent, row=6, expand=True, weight=3)

        titleRow = tk.Frame(card, bg=COLORS["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        tk.Label(
            titleRow, text="최종 합성 결과",
            font=(self._fontFamily, 11, "bold"),
            fg=COLORS["text"], bg=COLORS["surface"],
        ).pack(side="left")

        self._outputLenLabel = tk.Label(
            titleRow, text="",
            font=(self._fontFamily, 9),
            fg=COLORS["text3"], bg=COLORS["surface"],
        )
        self._outputLenLabel.pack(side="right")

        textFrame = tk.Frame(card, bg=COLORS["border"], padx=1, pady=1)
        textFrame.pack(fill="both", expand=True)

        self.outputText = tk.Text(
            textFrame, wrap="word", state="disabled",
            font=(self._fontFamily, 11),
            bg=COLORS["inputBg"], fg=COLORS["text"],
            insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            relief="flat", bd=0, padx=12, pady=10,
        )
        outputScrollbar = tk.Scrollbar(
            textFrame, command=self.outputText.yview,
            bg=COLORS["surface"], troughcolor=COLORS["inputBg"],
            width=8, relief="flat", bd=0,
        )
        outputScrollbar.pack(side="right", fill="y")
        self.outputText.pack(side="left", fill="both", expand=True)
        self.outputText["yscrollcommand"] = outputScrollbar.set

    # ── 진행 로그 ──────────────────────────────────────────────────────────────

    def _buildLogSection(self, parent):
        """터미널 스타일 로그 출력"""
        card = self._createCard(parent, row=7, expand=True, weight=1)

        titleRow = tk.Frame(card, bg=COLORS["surface"])
        titleRow.pack(fill="x", pady=(0, 8))
        tk.Label(
            titleRow, text="진행 로그",
            font=(self._fontFamily, 11, "bold"),
            fg=COLORS["text"], bg=COLORS["surface"],
        ).pack(side="left")

        textFrame = tk.Frame(card, bg="#1a1a2e", padx=1, pady=1)
        textFrame.pack(fill="both", expand=True)

        self.logText = tk.Text(
            textFrame, wrap="word", state="disabled",
            font=(self._monoFamily, 9),
            bg=COLORS["logBg"], fg="#8a8aa0",
            insertbackground="#ffffff",
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            relief="flat", bd=0, padx=12, pady=8,
        )
        logScrollbar = tk.Scrollbar(
            textFrame, command=self.logText.yview,
            bg=COLORS["surface"], troughcolor=COLORS["logBg"],
            width=8, relief="flat", bd=0,
        )
        logScrollbar.pack(side="right", fill="y")
        self.logText.pack(side="left", fill="both", expand=True)
        self.logText["yscrollcommand"] = logScrollbar.set

        # 로그 색상 태그
        self.logText.tag_config("error", foreground=COLORS["error"])
        self.logText.tag_config("success", foreground=COLORS["success"])
        self.logText.tag_config("phase", foreground=COLORS["warning"])
        self.logText.tag_config("info", foreground=COLORS["info"])

    # ── 상태 바 ────────────────────────────────────────────────────────────────

    def _buildStatusBar(self):
        """하단 상태 표시줄 (상태 도트 + 텍스트 + 버전)"""
        statusFrame = tk.Frame(self.root, bg=COLORS["statusBar"], height=28)
        statusFrame.grid(row=1, column=0, sticky="ew")
        statusFrame.grid_propagate(False)

        # 상태 도트
        self._statusDot = tk.Canvas(
            statusFrame, width=8, height=8,
            bg=COLORS["statusBar"], highlightthickness=0,
        )
        self._statusDot.pack(side="left", padx=(12, 6), pady=10)
        self._statusDot.create_oval(
            0, 0, 8, 8, fill=COLORS["success"], outline=""
        )

        self.statusLabel = tk.Label(
            statusFrame, text="대기 중",
            font=(self._fontFamily, 9),
            fg=COLORS["text2"], bg=COLORS["statusBar"], anchor="w",
        )
        self.statusLabel.pack(side="left", fill="x")

        tk.Label(
            statusFrame, text="MultiMind v0.5.0",
            font=(self._fontFamily, 8),
            fg=COLORS["text3"], bg=COLORS["statusBar"],
        ).pack(side="right", padx=(0, 12))

    # ── 커스텀 위젯 헬퍼 ──────────────────────────────────────────────────────

    def _createCard(self, parent, row, expand=False, weight=0):
        """1px 테두리 카드 프레임 생성"""
        outerFrame = tk.Frame(parent, bg=COLORS["border"], padx=1, pady=1)
        outerFrame.grid(
            row=row, column=0,
            sticky="nsew" if expand else "ew",
            pady=(0, 8),
        )
        if expand:
            parent.rowconfigure(row, weight=weight)

        innerFrame = tk.Frame(
            outerFrame, bg=COLORS["surface"], padx=16, pady=12
        )
        innerFrame.pack(fill="both", expand=True)
        return innerFrame

    def _createPill(self, parent, label, key, onClick=None):
        """LLM pill 버튼 — 좌측 브랜드 컬러 인디케이터 + 라벨"""
        brandColor = LLM_COLORS.get(key, COLORS["accent"])

        pill = tk.Frame(
            parent, bg=COLORS["pillBg"], padx=2, pady=2, cursor="hand2"
        )
        # 브랜드 컬러 좌측 바
        indicator = tk.Frame(pill, bg=brandColor, width=3)
        indicator.pack(side="left", fill="y")

        innerFrame = tk.Frame(pill, bg=COLORS["pillBg"], padx=10, pady=6)
        innerFrame.pack(side="left", fill="both", expand=True)

        textLabel = tk.Label(
            innerFrame, text=label,
            font=(self._fontFamily, 10),
            fg=COLORS["text2"], bg=COLORS["pillBg"], cursor="hand2",
        )
        textLabel.pack()

        # pill 내부 상태 저장
        pill._key = key
        pill._isSelected = False
        pill._isDisabled = False
        pill._brandColor = brandColor
        pill._indicator = indicator
        pill._innerFrame = innerFrame
        pill._textLabel = textLabel

        # 모든 자식 위젯에 클릭 바인딩
        for widget in (pill, innerFrame, textLabel, indicator):
            widget.bind(
                "<Button-1>",
                lambda e, cb=onClick: cb() if cb else None,
            )
        return pill

    def _createButton(self, parent, text, bg, hoverBg,
                      command=None, fg="#ffffff", bold=False, padx=14):
        """호버 효과 버튼"""
        btn = tk.Button(
            parent, text=text, command=command,
            font=(self._fontFamily, 10, "bold" if bold else "normal"),
            fg=fg, bg=bg,
            activeforeground=fg, activebackground=hoverBg,
            disabledforeground=COLORS["text3"],
            relief="flat", bd=0, cursor="hand2",
            padx=padx, pady=6,
        )
        btn._normalBg = bg
        btn._hoverBg = hoverBg
        btn._normalFg = fg
        btn.bind("<Enter>", lambda e, b=btn: self._onButtonEnter(b))
        btn.bind("<Leave>", lambda e, b=btn: self._onButtonLeave(b))
        return btn

    def _onButtonEnter(self, btn):
        """버튼 호버 진입"""
        if str(btn["state"]) != "disabled":
            btn.configure(bg=btn._hoverBg)

    def _onButtonLeave(self, btn):
        """버튼 호버 이탈"""
        if str(btn["state"]) != "disabled":
            btn.configure(bg=btn._normalBg)

    def _setButtonDisabled(self, btn):
        """버튼 비활성 외관 설정"""
        btn.configure(state="disabled", bg=COLORS["text3"], cursor="")

    def _setButtonEnabled(self, btn):
        """버튼 활성 외관 복원"""
        btn.configure(
            state="normal", bg=btn._normalBg, cursor="hand2"
        )

    # ── pill 상태 업데이트 ────────────────────────────────────────────────────

    def _selectHead(self, key):
        """Head LLM 선택"""
        self.headVar.set(key)
        self._updateHeadPills()
        self._onHeadChanged()

    def _toggleWorker(self, key):
        """Worker LLM 토글"""
        if key == self.headVar.get():
            return
        pill = self._workerPills.get(key)
        if pill and pill._isDisabled:
            return
        self.workerVars[key].set(not self.workerVars[key].get())
        self._updateWorkerPills()

    def _updateHeadPills(self):
        """Head pill 시각 상태 갱신"""
        selectedKey = self.headVar.get()
        for key, pill in self._headPills.items():
            selected = key == selectedKey
            pill._isSelected = selected
            if selected:
                pill.configure(bg=pill._brandColor)
                pill._innerFrame.configure(bg=pill._brandColor)
                pill._textLabel.configure(
                    fg="#ffffff", bg=pill._brandColor,
                    font=(self._fontFamily, 10, "bold"),
                )
                pill._indicator.configure(bg="#ffffff")
            else:
                pill.configure(bg=COLORS["pillBg"])
                pill._innerFrame.configure(bg=COLORS["pillBg"])
                pill._textLabel.configure(
                    fg=COLORS["text2"], bg=COLORS["pillBg"],
                    font=(self._fontFamily, 10),
                )
                pill._indicator.configure(bg=pill._brandColor)

    def _updateWorkerPills(self):
        """Worker pill 시각 상태 갱신 (선택/비활성/기본)"""
        selectedHead = self.headVar.get()
        count = 0
        for key, pill in self._workerPills.items():
            disabled = key == selectedHead
            selected = self.workerVars[key].get() and not disabled
            pill._isDisabled = disabled
            pill._isSelected = selected

            if disabled:
                # Head와 동일 → 비활성 스타일
                pill.configure(bg=COLORS["bg"], cursor="")
                pill._innerFrame.configure(bg=COLORS["bg"])
                pill._textLabel.configure(
                    fg=COLORS["text3"], bg=COLORS["bg"],
                    font=(self._fontFamily, 10), cursor="",
                )
                pill._indicator.configure(bg=COLORS["text3"])
            elif selected:
                count += 1
                pill.configure(bg=pill._brandColor, cursor="hand2")
                pill._innerFrame.configure(bg=pill._brandColor)
                pill._textLabel.configure(
                    fg="#ffffff", bg=pill._brandColor,
                    font=(self._fontFamily, 10, "bold"), cursor="hand2",
                )
                pill._indicator.configure(bg="#ffffff")
            else:
                pill.configure(bg=COLORS["pillBg"], cursor="hand2")
                pill._innerFrame.configure(bg=COLORS["pillBg"])
                pill._textLabel.configure(
                    fg=COLORS["text2"], bg=COLORS["pillBg"],
                    font=(self._fontFamily, 10), cursor="hand2",
                )
                pill._indicator.configure(bg=pill._brandColor)

        self._workerCountLabel.configure(text=f"{count}개 선택")

    # ── 프로그레스 바 렌더링 ──────────────────────────────────────────────────

    def _drawProgress(self, event=None):
        """Canvas 위에 프로그레스 바 그리기"""
        canvas = self._progressCanvas
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        # 트랙 배경
        canvas.create_rectangle(0, 0, w, h, fill=COLORS["surface2"], outline="")
        # 진행 바
        if self._progressValue > 0:
            fillW = int(w * self._progressValue / 100)
            canvas.create_rectangle(
                0, 0, fillW, h, fill=COLORS["accent"], outline=""
            )

    # ── 저장된 설정 적용 ──────────────────────────────────────────────────────

    def _applySavedConfig(self):
        """config.json → UI 반영"""
        headValue = self.config.get("head", "claude")
        workerList = self.config.get("workers", ["chatgpt", "gemini"])
        self.headVar.set(headValue)
        for key, var in self.workerVars.items():
            var.set(key in workerList)
        self._updateHeadPills()
        self._updateWorkerPills()

    # ── 플레이스홀더 & 포커스 ─────────────────────────────────────────────────

    def _onPromptFocusIn(self, event):
        """프롬프트 포커스 진입 — 플레이스홀더 제거, 테두리 강조"""
        self._promptWrapper.configure(bg=COLORS["borderFocus"])
        if self._hasPlaceholder:
            self.promptText.delete("1.0", "end")
            self.promptText.configure(fg=COLORS["text"])
            self._hasPlaceholder = False

    def _onPromptFocusOut(self, event):
        """프롬프트 포커스 이탈 — 빈 입력이면 플레이스홀더 복원"""
        self._promptWrapper.configure(bg=COLORS["border"])
        if not self.promptText.get("1.0", "end").strip():
            self.promptText.insert("1.0", _PLACEHOLDER)
            self.promptText.configure(fg=COLORS["text3"])
            self._hasPlaceholder = True

    def _getPromptText(self) -> str:
        """플레이스홀더 상태를 고려한 프롬프트 텍스트 반환"""
        if self._hasPlaceholder:
            return ""
        return self.promptText.get("1.0", "end").strip()

    def _updateCharCount(self, event=None):
        """글자 수 라벨 갱신"""
        text = self._getPromptText()
        self._charCountLabel.configure(text=f"{len(text)}자")

    # ── 이벤트 핸들러 ──────────────────────────────────────────────────────────

    def _onHeadChanged(self, *args):
        """Head 변경 → 동일 Worker 선택 해제 + pill 갱신"""
        selectedHead = self.headVar.get()
        if self.workerVars[selectedHead].get():
            self.workerVars[selectedHead].set(False)
        self._updateHeadPills()
        self._updateWorkerPills()

    def _onRunClicked(self):
        """실행 — 입력 검증 → 오케스트레이터 백그라운드 실행"""
        promptValue = self._getPromptText()
        if not promptValue:
            messagebox.showwarning("입력 오류", "프롬프트를 입력해주세요.")
            return

        headValue = self.headVar.get()
        workerList = [
            key for key, var in self.workerVars.items()
            if var.get() and key != headValue
        ]
        if not workerList:
            messagebox.showwarning(
                "설정 오류", "Worker LLM을 최소 1개 이상 선택해주세요."
            )
            return

        # 설정 저장
        self.configManager.save(
            headValue, workerList, geometry=self.root.geometry()
        )
        writeLog(f"실행 시작 | Head={headValue} | Workers={workerList}")

        # UI 전환
        self._setRunningState(True)
        self._clearOutput()
        self._clearLog()

        # 오케스트레이터 실행
        self._stopEvent.clear()
        self.eventQueue = queue.Queue()
        orchestrator = Orchestrator(
            headValue, workerList, promptValue, self.eventQueue,
            settings=self.config.get("settings", {}),
            stopEvent=self._stopEvent,
        )
        threading.Thread(target=orchestrator.run, daemon=True).start()

        self._polling = True
        self.root.after(POLL_INTERVAL_MS, self._pollEventQueue)

    def _onStopClicked(self):
        """중단 버튼 클릭"""
        if messagebox.askyesno("실행 중단", "진행 중인 작업을 중단하시겠습니까?"):
            self._stopEvent.set()
            self._appendLog(
                "사용자에 의해 실행이 중단되었습니다.", tag="error"
            )
            self._setStatus("중단됨", "error")
            self._finish()

    def _onClose(self):
        """프로그램 종료 — 실행 중이면 확인 다이얼로그"""
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
        """결과 클립보드 복사"""
        outputValue = self.outputText.get("1.0", "end").strip()
        if outputValue:
            self.root.clipboard_clear()
            self.root.clipboard_append(outputValue)
            self._setStatus("결과가 클립보드에 복사되었습니다", "success")
        else:
            self._setStatus("복사할 결과가 없습니다", "warning")

    def _clearPrompt(self):
        """프롬프트 지우기 → 플레이스홀더 복원"""
        self.promptText.delete("1.0", "end")
        self.promptText.insert("1.0", _PLACEHOLDER)
        self.promptText.configure(fg=COLORS["text3"])
        self._hasPlaceholder = True
        self._updateCharCount()

    # ── 이벤트 큐 처리 ────────────────────────────────────────────────────────

    def _pollEventQueue(self):
        """이벤트 큐 폴링 → UI 업데이트"""
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
        """이벤트 타입별 UI 분기"""
        eventType = event.get("type")

        if eventType == "log":
            self._appendLog(event["message"])

        elif eventType == "phase":
            phaseText = f"[Phase {event['phase']}] {event['description']}"
            self._appendLog(phaseText, tag="phase")
            self._setStatus(event["description"], "info")
            self._updateProgress(event["phase"], event["description"])

        elif eventType == "worker_done":
            msg = f"[{event['llm'].upper()}] 응답 수신 완료"
            self._appendLog(msg, tag="success")

        elif eventType == "worker_error":
            msg = f"[{event['llm'].upper()}] 오류: {event['error']}"
            self._appendLog(msg, tag="error")

        elif eventType == "final_result":
            self._setOutput(event["text"])
            self._appendLog("오케스트레이션 완료", tag="success")
            self._setStatus("완료", "success")
            self._updateProgress(4, "완료")
            self._finish()

        elif eventType == "fatal_error":
            self._appendLog(f"오류: {event['error']}", tag="error")
            messagebox.showerror("실행 오류", event["error"])
            self._setStatus("오류 발생", "error")
            self._finish()

        elif eventType == "stopped":
            self._appendLog("실행이 중단되었습니다.", tag="error")
            self._setStatus("중단됨", "error")
            self._finish()

    # ── 실행 상태 전환 ────────────────────────────────────────────────────────

    def _finish(self):
        """실행 완료/오류/중단 후 UI 복원"""
        self._polling = False
        self._setRunningState(False)

    def _setRunningState(self, isRunning: bool):
        """실행 상태에 따라 버튼/프로그레스 전환"""
        if isRunning:
            self._setButtonDisabled(self.runButton)
            self._setButtonEnabled(self.stopButton)
            self.stopButton.configure(bg=COLORS["stopBg"])
            self.exitButton.configure(state="disabled", cursor="")
            self._progressValue = 0
            self.progressLabel.configure(text="")
            self._progressPercent.configure(text="")
            self.progressFrame.grid()
            self._drawProgress()
            self._setStatus("실행 중...", "info")
        else:
            self._setButtonEnabled(self.runButton)
            self.runButton.configure(bg=COLORS["runBg"])
            self._setButtonDisabled(self.stopButton)
            self._setButtonEnabled(self.exitButton)
            self.exitButton.configure(bg=self.exitButton._normalBg)

    def _updateProgress(self, phase: int, description: str):
        """Phase별 프로그레스 갱신"""
        phaseProgress = {0: 10, 1: 30, 2: 60, 3: 85, 4: 100}
        value = phaseProgress.get(phase, 0)
        self._progressValue = value
        self._drawProgress()

        phaseNames = {
            0: "브라우저 시작",
            1: "프롬프트 정제",
            2: "Worker 응답 생성",
            3: "결과 종합",
            4: "완료",
        }
        phaseName = phaseNames.get(phase, description)
        self.progressLabel.configure(text=f"Phase {phase}/4 · {phaseName}")
        self._progressPercent.configure(text=f"{value}%")

    def _setStatus(self, text: str, level: str = "info"):
        """상태 바 텍스트 + 도트 색상 갱신"""
        dotColorMap = {
            "info":    COLORS["info"],
            "success": COLORS["success"],
            "error":   COLORS["error"],
            "warning": COLORS["warning"],
        }
        dotColor = dotColorMap.get(level, COLORS["text2"])
        self._statusDot.delete("all")
        self._statusDot.create_oval(0, 0, 8, 8, fill=dotColor, outline="")
        self.statusLabel.configure(text=text)

    # ── 텍스트 위젯 헬퍼 ──────────────────────────────────────────────────────

    def _appendLog(self, message: str, tag: str = None):
        """로그 텍스트에 메시지 추가"""
        self.logText.configure(state="normal")
        prefix = "› "
        if tag:
            self.logText.insert("end", prefix + message + "\n", tag)
        else:
            self.logText.insert("end", prefix + message + "\n")
        self.logText.see("end")
        self.logText.configure(state="disabled")

    def _setOutput(self, text: str):
        """결과 텍스트 설정"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.insert("1.0", text)
        self.outputText.configure(state="disabled")
        self._outputLenLabel.configure(text=f"{len(text)}자")

    def _clearOutput(self):
        """결과 텍스트 초기화"""
        self.outputText.configure(state="normal")
        self.outputText.delete("1.0", "end")
        self.outputText.configure(state="disabled")
        self._outputLenLabel.configure(text="")

    def _clearLog(self):
        """로그 텍스트 초기화"""
        self.logText.configure(state="normal")
        self.logText.delete("1.0", "end")
        self.logText.configure(state="disabled")
