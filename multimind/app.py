# PySide6 GUI 모듈 — MultiMind 메인 인터페이스
# 라이트 테마, 2컬럼 레이아웃 (사이드바 + 메인 콘텐츠)

import html as htmlLib
import os
import queue
import threading
import time

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QCheckBox,
    QFrame, QScrollArea, QMessageBox, QSizePolicy, QApplication,
)

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

# 프롬프트 최대 글자 수
MAX_PROMPT_LENGTH = 8000

# LLM 아이콘 파일 매핑
ICON_FILES = {
    "claude": "claude_icon.jpg",
    "chatgpt": "ChatGPT_logo.svg.png",
    "gemini": "Google_Gemini_icon_2025.svg.png",
    "grok": "grok_icon.png",
    "perplexity": "perplexity_icon.png",
}

# 아이콘 디렉토리 경로
ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "icon",
)

# LLM별 브랜드 색상
LLM_COLORS = {
    "claude": "#D97706",
    "chatgpt": "#10A37F",
    "gemini": "#4285F4",
    "grok": "#6B7280",
    "perplexity": "#20808D",
}

# ── 라이트 테마 컬러 팔레트 (쿨 그레이) ──────────────────────────────────────
C = {
    "bg":           "#F5F6FA",
    "surface":      "#FFFFFF",
    "border":       "#E2E4EA",
    "borderFocus":  "#007AFF",
    "text":         "#1D1D1F",
    "text2":        "#6E7179",
    "text3":        "#A0A3AB",
    "accent":       "#007AFF",
    "success":      "#34C759",
    "error":        "#FF3B30",
    "warning":      "#FF9500",
}


def _loadIcon(key: str, size: int = 20) -> QPixmap:
    """LLM 아이콘 파일 로드 및 크기 조정"""
    path = os.path.join(ICON_DIR, ICON_FILES.get(key, ""))
    if os.path.exists(path):
        return QPixmap(path).scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
    return QPixmap()


# ══════════════════════════════════════════════════════════════════════════════


class MultiMindApp(QMainWindow):
    """MultiMind 메인 GUI (PySide6, 라이트 테마, 2컬럼 레이아웃)"""

    def __init__(self):
        super().__init__()

        # 설정 및 상태 초기화
        self.configManager = ConfigManager()
        self.config = self.configManager.load()
        self.eventQueue: queue.Queue = queue.Queue()
        self._polling = False
        self._stopEvent = threading.Event()
        self._workerCount = 0
        self._completedWorkers = 0
        self._startTime = None
        self._cardViewMode = True
        self._responseCards: dict = {}
        self._workerCheckboxes: dict = {}
        self._metricLabels: dict = {}

        # UI 구성
        self._initWindow()
        self._buildUi()
        self._applyStyles()
        self._applySavedConfig()
        self._updateWorkerStates()
        self._setupTimers()
        self._bindShortcuts()

    # ── 윈도우 초기화 ─────────────────────────────────────────────────────────

    def _initWindow(self):
        """윈도우 타이틀, 최소 크기, 저장된 geometry 복원"""
        self.setWindowTitle("MultiMind")
        self.setMinimumSize(960, 720)
        geo = self.config.get("window_geometry", "1000x750+100+100")
        try:
            parts = geo.replace("+", "x").split("x")
            self.setGeometry(
                int(parts[2]), int(parts[3]), int(parts[0]), int(parts[1]),
            )
        except (ValueError, IndexError):
            self.resize(1000, 750)

    # ── 메인 레이아웃 ─────────────────────────────────────────────────────────

    def _buildUi(self):
        """2컬럼 레이아웃 — 사이드바 + 메인 콘텐츠"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._buildSidebar())
        layout.addWidget(self._buildContent(), stretch=1)

    def _bindShortcuts(self):
        """키보드 단축키 바인딩"""
        runAct = QAction(self)
        runAct.setShortcut(QKeySequence("Ctrl+Return"))
        runAct.triggered.connect(self._onRunClicked)
        self.addAction(runAct)

        closeAct = QAction(self)
        closeAct.setShortcut(QKeySequence("Ctrl+Q"))
        closeAct.triggered.connect(self.close)
        self.addAction(closeAct)

    # ── 사이드바 ──────────────────────────────────────────────────────────────

    def _buildSidebar(self):
        """좌측 사이드바 — AI 설정, Head/Worker 선택, 실행 버튼"""
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(20, 24, 20, 20)
        lay.setSpacing(12)

        # AI 설정 헤더
        header = QLabel("AI 설정")
        header.setObjectName("sidebarHeader")
        lay.addWidget(header)

        # Head LLM 드롭다운
        lay.addWidget(self._sectionLabel("Head LLM"))
        self.headCombo = QComboBox()
        self.headCombo.setObjectName("headCombo")
        self.headCombo.setIconSize(QSize(20, 20))
        for displayName, key in SUPPORTED_LLMS:
            px = _loadIcon(key)
            icon = QIcon(px) if not px.isNull() else QIcon()
            self.headCombo.addItem(icon, displayName, key)
        self.headCombo.currentIndexChanged.connect(self._onHeadChanged)
        lay.addWidget(self.headCombo)

        # 구분선
        lay.addWidget(self._divider())

        # Worker LLM 체크박스
        lay.addWidget(self._sectionLabel("Worker LLM"))
        for displayName, key in SUPPORTED_LLMS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)

            # LLM 아이콘
            iconLbl = QLabel()
            px = _loadIcon(key, 18)
            if not px.isNull():
                iconLbl.setPixmap(px)
            iconLbl.setFixedSize(18, 18)
            rl.addWidget(iconLbl)

            # 체크박스
            cb = QCheckBox(displayName)
            cb.stateChanged.connect(
                lambda _st, k=key: self._onWorkerToggled(k),
            )
            rl.addWidget(cb)
            rl.addStretch()

            # disabled 시 힌트 라벨
            hintLbl = QLabel()
            hintLbl.setObjectName("disabledHint")
            hintLbl.setVisible(False)
            rl.addWidget(hintLbl)

            lay.addWidget(row)
            self._workerCheckboxes[key] = {"checkbox": cb, "hint": hintLbl}

        # 경고 메시지
        warn = QLabel("※ Head LLM은 Worker로 선택할 수 없습니다.")
        warn.setObjectName("warningLabel")
        warn.setWordWrap(True)
        lay.addWidget(warn)

        lay.addStretch()

        # 액션 버튼
        self.runButton = QPushButton("▶  실행")
        self.runButton.setObjectName("runButton")
        self.runButton.setCursor(Qt.PointingHandCursor)
        self.runButton.clicked.connect(self._onRunClicked)
        lay.addWidget(self.runButton)

        self.stopButton = QPushButton("■  중지")
        self.stopButton.setObjectName("stopButton")
        self.stopButton.setEnabled(False)
        self.stopButton.clicked.connect(self._onStopClicked)
        lay.addWidget(self.stopButton)

        clearBtn = QPushButton("🗑  지우기")
        clearBtn.setObjectName("clearAllButton")
        clearBtn.setCursor(Qt.PointingHandCursor)
        clearBtn.clicked.connect(self._clearAll)
        lay.addWidget(clearBtn)

        return sidebar

    # ── 메인 콘텐츠 ───────────────────────────────────────────────────────────

    def _buildContent(self):
        """우측 메인 콘텐츠 — 프롬프트, 상태, 응답 카드, 로그"""
        content = QWidget()
        content.setObjectName("contentArea")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(20)

        self._buildPromptSection(lay)
        self._buildStatusSection(lay)
        self._buildResponseSection(lay)
        self._buildLogSection(lay)

        return content

    # ── 프롬프트 입력 ─────────────────────────────────────────────────────────

    def _buildPromptSection(self, parentLay):
        """프롬프트 입력 영역 — 텍스트 에디터 + 글자 수 카운터"""
        hdr = QHBoxLayout()
        hdr.addWidget(self._contentTitle("프롬프트 입력"))
        hdr.addStretch()
        self._charCountLabel = QLabel("0 / 8000")
        self._charCountLabel.setObjectName("charCount")
        hdr.addWidget(self._charCountLabel)
        parentLay.addLayout(hdr)

        self.promptEdit = QTextEdit()
        self.promptEdit.setObjectName("promptEdit")
        self.promptEdit.setPlaceholderText("여기에 프롬프트를 입력하세요...")
        self.promptEdit.setFixedHeight(120)
        self.promptEdit.textChanged.connect(self._onPromptChanged)
        parentLay.addWidget(self.promptEdit)

    # ── 실행 상태 대시보드 ────────────────────────────────────────────────────

    def _buildStatusSection(self, parentLay):
        """4개 메트릭 카드 — 진행률, 실행 시간, 완료 AI 수, 토큰"""
        parentLay.addWidget(self._contentTitle("실행 상태"))
        row = QHBoxLayout()
        row.setSpacing(12)

        metricsInfo = [
            ("progress",  "전체 진행률",  "0%"),
            ("elapsed",   "실행 시간",    "00:00:00"),
            ("completed", "완료한 AI",    "0 / 0"),
            ("tokens",    "토큰 사용량",  "—"),
        ]
        for metricKey, title, defaultVal in metricsInfo:
            card = QFrame()
            card.setObjectName("metricCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)

            titleLbl = QLabel(title)
            titleLbl.setObjectName("metricTitle")
            cl.addWidget(titleLbl)

            valLbl = QLabel(defaultVal)
            valLbl.setObjectName("metricValue")
            cl.addWidget(valLbl)

            row.addWidget(card)
            self._metricLabels[metricKey] = valLbl

        parentLay.addLayout(row)

    # ── AI 응답 결과 ──────────────────────────────────────────────────────────

    def _buildResponseSection(self, parentLay):
        """응답 카드 영역 — 카드/리스트 뷰 토글 + 종합 결과 + LLM 카드"""
        # 헤더 (타이틀 + 뷰 전환 버튼)
        hdr = QHBoxLayout()
        hdr.addWidget(self._contentTitle("AI 응답 결과"))
        hdr.addStretch()

        self._cardViewBtn = QPushButton("카드 보기")
        self._cardViewBtn.setObjectName("viewToggle")
        self._cardViewBtn.setCheckable(True)
        self._cardViewBtn.setChecked(True)
        self._cardViewBtn.setCursor(Qt.PointingHandCursor)
        self._cardViewBtn.clicked.connect(lambda: self._setViewMode(True))
        hdr.addWidget(self._cardViewBtn)

        self._listViewBtn = QPushButton("리스트 보기")
        self._listViewBtn.setObjectName("viewToggle")
        self._listViewBtn.setCheckable(True)
        self._listViewBtn.setCursor(Qt.PointingHandCursor)
        self._listViewBtn.clicked.connect(lambda: self._setViewMode(False))
        hdr.addWidget(self._listViewBtn)

        parentLay.addLayout(hdr)

        # 종합 결과 카드 (실행 완료 후 표시)
        self._synthesisCard = QFrame()
        self._synthesisCard.setObjectName("synthesisCard")
        self._synthesisCard.setVisible(False)
        sl = QVBoxLayout(self._synthesisCard)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(8)

        synthHdr = QHBoxLayout()
        synthTitleLbl = QLabel("📋 종합 결과")
        synthTitleLbl.setObjectName("synthesisTitle")
        synthHdr.addWidget(synthTitleLbl)
        synthHdr.addStretch()
        copyBtn = QPushButton("복사")
        copyBtn.setObjectName("smallBtn")
        copyBtn.setCursor(Qt.PointingHandCursor)
        copyBtn.clicked.connect(self._copySynthesis)
        synthHdr.addWidget(copyBtn)
        sl.addLayout(synthHdr)

        self._synthesisText = QTextEdit()
        self._synthesisText.setObjectName("synthesisTextEdit")
        self._synthesisText.setReadOnly(True)
        self._synthesisText.setMaximumHeight(200)
        sl.addWidget(self._synthesisText)
        parentLay.addWidget(self._synthesisCard)

        # 응답 카드 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("responseScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._cardsContainer = QWidget()
        self._cardsContainer.setObjectName("cardsContainer")
        self._cardsLayout = QGridLayout(self._cardsContainer)
        self._cardsLayout.setSpacing(12)
        self._cardsLayout.setContentsMargins(0, 0, 4, 0)

        # 5개 LLM 응답 카드 생성
        for i, (displayName, key) in enumerate(SUPPORTED_LLMS):
            card = self._createResponseCard(key, displayName)
            self._responseCards[key] = card
            self._cardsLayout.addWidget(card, i // 2, i % 2)

        scroll.setWidget(self._cardsContainer)
        parentLay.addWidget(scroll, stretch=2)

    def _createResponseCard(self, key: str, displayName: str):
        """개별 LLM 응답 카드 — 아이콘, 이름, 상태 뱃지, 응답 텍스트"""
        brandColor = LLM_COLORS.get(key, C["accent"])
        cardId = f"rcard_{key}"

        card = QFrame()
        card.setObjectName(cardId)
        card.setStyleSheet(f"""
            #{cardId} {{
                background: {C["surface"]};
                border: 1px solid {C["border"]};
                border-left: 3px solid {brandColor};
                border-radius: 8px;
            }}
        """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # 헤더 행 (아이콘 + 이름 + 상태 뱃지)
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        iconLbl = QLabel()
        px = _loadIcon(key, 22)
        if not px.isNull():
            iconLbl.setPixmap(px)
        iconLbl.setFixedSize(22, 22)
        hdr.addWidget(iconLbl)

        nameLbl = QLabel(displayName)
        nameLbl.setStyleSheet(
            f"font-weight: bold; font-size: 13px; color: {C['text']};"
        )
        hdr.addWidget(nameLbl)
        hdr.addStretch()

        statusLbl = QLabel("대기 중")
        statusLbl.setObjectName("cardStatus")
        statusLbl.setProperty("status", "waiting")
        hdr.addWidget(statusLbl)
        lay.addLayout(hdr)

        # 응답 텍스트
        respLbl = QLabel("")
        respLbl.setWordWrap(True)
        respLbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        respLbl.setStyleSheet(f"font-size: 12px; color: {C['text2']};")
        respLbl.setMinimumHeight(30)
        lay.addWidget(respLbl)

        # 카드 내부 참조
        card._statusLabel = statusLbl
        card._responseLabel = respLbl

        return card

    # ── 실행 로그 ─────────────────────────────────────────────────────────────

    def _buildLogSection(self, parentLay):
        """실행 로그 영역 — 타임스탬프 + 색상 코딩된 로그"""
        hdr = QHBoxLayout()
        hdr.addWidget(self._contentTitle("실행 로그"))
        hdr.addStretch()
        clrBtn = QPushButton("지우기")
        clrBtn.setObjectName("smallBtn")
        clrBtn.setCursor(Qt.PointingHandCursor)
        clrBtn.clicked.connect(self._clearLog)
        hdr.addWidget(clrBtn)
        parentLay.addLayout(hdr)

        self.logText = QTextEdit()
        self.logText.setObjectName("logText")
        self.logText.setReadOnly(True)
        self.logText.setFixedHeight(150)
        parentLay.addWidget(self.logText, stretch=1)

    # ── 헬퍼 위젯 팩토리 ─────────────────────────────────────────────────────

    def _divider(self):
        """수평 구분선"""
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("divider")
        return line

    def _sectionLabel(self, text: str):
        """사이드바 섹션 라벨"""
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _contentTitle(self, text: str):
        """콘텐츠 영역 섹션 타이틀"""
        lbl = QLabel(text)
        lbl.setObjectName("contentSectionTitle")
        return lbl

    # ── 타이머 설정 ───────────────────────────────────────────────────────────

    def _setupTimers(self):
        """이벤트 큐 폴링 + 경과 시간 타이머"""
        self._pollTimer = QTimer(self)
        self._pollTimer.timeout.connect(self._pollEventQueue)
        self._elapsedTimer = QTimer(self)
        self._elapsedTimer.timeout.connect(self._updateElapsedTime)

    # ── 저장된 설정 복원 ──────────────────────────────────────────────────────

    def _applySavedConfig(self):
        """config.json에서 Head/Worker 설정 복원"""
        headVal = self.config.get("head", "claude")
        workerList = self.config.get("workers", ["chatgpt", "gemini"])

        for i in range(self.headCombo.count()):
            if self.headCombo.itemData(i) == headVal:
                self.headCombo.setCurrentIndex(i)
                break

        for key, info in self._workerCheckboxes.items():
            info["checkbox"].setChecked(key in workerList)

    # ── Worker 상태 동기화 ────────────────────────────────────────────────────

    def _updateWorkerStates(self):
        """Head LLM과 동일한 Worker 비활성화 + 힌트 표시"""
        headKey = self.headCombo.currentData()
        for key, info in self._workerCheckboxes.items():
            cb, hint = info["checkbox"], info["hint"]
            isHead = key == headKey
            if isHead:
                cb.setChecked(False)
                cb.setEnabled(False)
                hint.setText("(Head LLM과 동일)")
                hint.setVisible(True)
            else:
                cb.setEnabled(True)
                hint.setVisible(False)

    # ── 이벤트 핸들러 ─────────────────────────────────────────────────────────

    def _onHeadChanged(self, _index):
        """Head LLM 드롭다운 변경 시 Worker 상태 갱신"""
        self._updateWorkerStates()

    def _onWorkerToggled(self, key):
        """Head와 동일한 Worker 선택 방지"""
        if key == self.headCombo.currentData():
            self._workerCheckboxes[key]["checkbox"].setChecked(False)

    def _onPromptChanged(self):
        """프롬프트 입력 시 글자 수 업데이트 + 초과 경고"""
        n = len(self.promptEdit.toPlainText())
        self._charCountLabel.setText(f"{n} / {MAX_PROMPT_LENGTH}")
        overLimit = n > MAX_PROMPT_LENGTH
        self._charCountLabel.setStyleSheet(
            f"color: {C['error']};" if overLimit else f"color: {C['text3']};"
        )

    def _onRunClicked(self):
        """실행 버튼 — 입력 검증 후 오케스트레이터 실행"""
        prompt = self.promptEdit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "입력 오류", "프롬프트를 입력해주세요.")
            return
        if len(prompt) > MAX_PROMPT_LENGTH:
            QMessageBox.warning(
                self, "입력 오류",
                f"프롬프트가 {MAX_PROMPT_LENGTH}자를 초과합니다.",
            )
            return

        head = self.headCombo.currentData()
        workers = [
            k for k, info in self._workerCheckboxes.items()
            if info["checkbox"].isChecked() and k != head
        ]
        if not workers:
            QMessageBox.warning(
                self, "설정 오류",
                "Worker LLM을 최소 1개 이상 선택해주세요.",
            )
            return

        # 설정 저장 및 로그
        self._saveConfig()
        writeLog(f"실행 시작 | Head={head} | Workers={workers}")

        # 상태 초기화
        self._workerCount = len(workers)
        self._completedWorkers = 0
        self._setRunningState(True)
        self._resetCards(head, workers)
        self.logText.clear()
        self._synthesisCard.setVisible(False)
        self._updateMetric("progress", "0%")
        self._updateMetric("elapsed", "00:00:00")
        self._updateMetric("tokens", "—")

        # 오케스트레이터 백그라운드 실행
        self._stopEvent.clear()
        self.eventQueue = queue.Queue()
        orch = Orchestrator(
            head, workers, prompt, self.eventQueue,
            settings=self.config.get("settings", {}),
            stopEvent=self._stopEvent,
        )
        threading.Thread(target=orch.run, daemon=True).start()
        self._polling = True
        self._pollTimer.start(POLL_INTERVAL_MS)
        self._startTime = time.time()
        self._elapsedTimer.start(1000)

    def _onStopClicked(self):
        """중지 버튼 — 확인 후 실행 중단"""
        reply = QMessageBox.question(
            self, "실행 중단", "진행 중인 작업을 중단하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._stopEvent.set()
            self._appendLog("사용자에 의해 실행이 중단되었습니다.", "error")
            self._finish()

    # ── 액션 핸들러 ───────────────────────────────────────────────────────────

    def _clearAll(self):
        """전체 초기화 — 프롬프트, 결과, 로그, 메트릭"""
        self.promptEdit.clear()
        self.logText.clear()
        self._resetAllCards()
        self._synthesisCard.setVisible(False)
        self._updateMetric("progress", "0%")
        self._updateMetric("elapsed", "00:00:00")
        self._updateMetric("completed", "0 / 0")
        self._updateMetric("tokens", "—")

    def _clearLog(self):
        """로그 텍스트만 초기화"""
        self.logText.clear()

    def _copySynthesis(self):
        """종합 결과를 클립보드에 복사"""
        text = self._synthesisText.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    # ── 뷰 모드 전환 ─────────────────────────────────────────────────────────

    def _setViewMode(self, cardMode: bool):
        """카드/리스트 뷰 토글"""
        self._cardViewMode = cardMode
        self._cardViewBtn.setChecked(cardMode)
        self._listViewBtn.setChecked(not cardMode)
        self._rearrangeCards()

    def _rearrangeCards(self):
        """현재 뷰 모드에 맞게 카드 그리드 재배치"""
        while self._cardsLayout.count():
            self._cardsLayout.takeAt(0)

        cols = 2 if self._cardViewMode else 1
        for i, card in enumerate(self._responseCards.values()):
            self._cardsLayout.addWidget(card, i // cols, i % cols)

    # ── 카드 상태 관리 ────────────────────────────────────────────────────────

    def _resetCards(self, head: str, workers: list):
        """실행 시작 시 카드 상태 초기화"""
        for key, card in self._responseCards.items():
            if key == head:
                self._setCardStatus(card, "head", "Head LLM")
            elif key in workers:
                self._setCardStatus(card, "waiting", "대기 중")
            else:
                self._setCardStatus(card, "waiting", "미선택")
            card._responseLabel.setText("")

    def _resetAllCards(self):
        """모든 카드를 대기 상태로 리셋"""
        for card in self._responseCards.values():
            self._setCardStatus(card, "waiting", "대기 중")
            card._responseLabel.setText("")

    def _setCardStatus(self, card, status: str, text: str):
        """카드 상태 뱃지 업데이트 — QSS 동적 프로퍼티 반영"""
        lbl = card._statusLabel
        lbl.setText(text)
        lbl.setProperty("status", status)
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)

    # ── 메트릭 업데이트 ───────────────────────────────────────────────────────

    def _updateMetric(self, key: str, val: str):
        """메트릭 카드 값 갱신"""
        lbl = self._metricLabels.get(key)
        if lbl:
            lbl.setText(val)

    def _updateElapsedTime(self):
        """매초 호출 — 경과 시간 표시 업데이트"""
        if self._startTime is None:
            return
        elapsed = int(time.time() - self._startTime)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        self._updateMetric("elapsed", f"{h:02d}:{m:02d}:{s:02d}")

    # ── 이벤트 큐 폴링 ───────────────────────────────────────────────────────

    def _pollEventQueue(self):
        """QTimer 콜백 — 큐에서 이벤트를 꺼내 처리"""
        if not self._polling:
            return
        try:
            while True:
                self._handleEvent(self.eventQueue.get_nowait())
        except queue.Empty:
            pass

    def _handleEvent(self, ev: dict):
        """오케스트레이터 이벤트 타입별 UI 업데이트"""
        t = ev.get("type")

        if t == "log":
            self._appendLog(ev["message"])

        elif t == "phase":
            phase = ev["phase"]
            self._appendLog(f"[Phase {phase}] {ev['description']}", "phase")
            # 진행률 매핑
            pMap = {0: "10%", 1: "30%", 2: "60%", 3: "85%", 4: "100%"}
            self._updateMetric("progress", pMap.get(phase, "0%"))
            # Phase 2 진입 시 Worker 카드 → 진행 중
            if phase == 2:
                headKey = self.headCombo.currentData()
                for key, card in self._responseCards.items():
                    if key != headKey and self._workerCheckboxes[key][
                        "checkbox"
                    ].isChecked():
                        self._setCardStatus(card, "running", "진행 중")

        elif t == "worker_done":
            llm = ev["llm"]
            card = self._responseCards.get(llm)
            if card:
                self._setCardStatus(card, "done", "완료")
                txt = ev.get("result", "")
                display = txt[:500] + "..." if len(txt) > 500 else txt
                card._responseLabel.setText(display)
            self._completedWorkers += 1
            self._updateMetric(
                "completed", f"{self._completedWorkers} / {self._workerCount}",
            )
            self._appendLog(f"[{llm.upper()}] 응답 수신 완료", "success")

        elif t == "worker_error":
            llm = ev["llm"]
            card = self._responseCards.get(llm)
            if card:
                self._setCardStatus(card, "error", "오류")
                card._responseLabel.setText(ev.get("error", ""))
            self._completedWorkers += 1
            self._updateMetric(
                "completed", f"{self._completedWorkers} / {self._workerCount}",
            )
            self._appendLog(
                f"[{llm.upper()}] 오류: {ev.get('error', '')}", "error",
            )

        elif t == "final_result":
            self._synthesisCard.setVisible(True)
            self._synthesisText.setPlainText(ev["text"])
            self._updateMetric("progress", "100%")
            self._appendLog("오케스트레이션 완료", "success")
            self._finish()

        elif t == "fatal_error":
            self._appendLog(f"오류: {ev['error']}", "error")
            QMessageBox.critical(self, "실행 오류", ev["error"])
            self._finish()

        elif t == "stopped":
            self._appendLog("실행이 중단되었습니다.", "error")
            self._finish()

    # ── 실행 상태 전환 ────────────────────────────────────────────────────────

    def _finish(self):
        """실행 완료/중단 — 타이머 정지 및 UI 복원"""
        self._polling = False
        self._pollTimer.stop()
        self._elapsedTimer.stop()
        self._setRunningState(False)

    def _setRunningState(self, running: bool):
        """실행/대기 상태에 따라 위젯 활성화 전환"""
        self.runButton.setEnabled(not running)
        self.stopButton.setEnabled(running)
        self.stopButton.setCursor(
            Qt.PointingHandCursor if running else Qt.ArrowCursor,
        )
        self.headCombo.setEnabled(not running)
        if running:
            for info in self._workerCheckboxes.values():
                info["checkbox"].setEnabled(False)
            self._updateMetric("completed", f"0 / {self._workerCount}")
        else:
            self._updateWorkerStates()

    # ── 로그 출력 ─────────────────────────────────────────────────────────────

    def _appendLog(self, msg: str, tag: str = None):
        """타임스탬프 + 색상 코딩된 로그 메시지 추가"""
        colorMap = {
            "error": C["error"], "success": C["success"],
            "phase": C["warning"], "info": C["accent"],
        }
        color = colorMap.get(tag, C["text2"])
        ts = time.strftime("%H:%M:%S")
        escaped = htmlLib.escape(msg)
        self.logText.append(
            f'<span style="color:{C["text3"]}">{ts}</span> '
            f'<span style="color:{color}">› {escaped}</span>'
        )

    # ── 설정 저장 ─────────────────────────────────────────────────────────────

    def _saveConfig(self):
        """현재 Head/Worker/geometry를 config.json에 저장"""
        head = self.headCombo.currentData()
        workers = [
            k for k, info in self._workerCheckboxes.items()
            if info["checkbox"].isChecked()
        ]
        g = self.geometry()
        geoStr = f"{g.width()}x{g.height()}+{g.x()}+{g.y()}"
        self.configManager.save(head, workers, geometry=geoStr)

    # ── 윈도우 종료 ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """윈도우 닫기 — 실행 중이면 확인 후 설정 저장"""
        if self._polling:
            reply = QMessageBox.question(
                self, "종료 확인",
                "작업이 진행 중입니다. 종료하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self._stopEvent.set()
            self._pollTimer.stop()
            self._elapsedTimer.stop()
        self._saveConfig()
        event.accept()

    # ── QSS 스타일시트 ────────────────────────────────────────────────────────

    def _applyStyles(self):
        """전체 애플리케이션 QSS 스타일 적용"""
        self.setStyleSheet(f"""
            /* ── 전역 기본 ─────────────────────────────────── */
            * {{
                font-family: "Apple SD Gothic Neo", "맑은 고딕",
                             "Noto Sans CJK KR", sans-serif;
            }}
            QMainWindow {{
                background-color: {C["bg"]};
            }}

            /* ── 사이드바 ──────────────────────────────────── */
            #sidebar {{
                background-color: {C["surface"]};
                border-right: 1px solid {C["border"]};
            }}
            #sidebarHeader {{
                font-size: 18px;
                font-weight: bold;
                color: {C["text"]};
                padding-bottom: 4px;
            }}
            #sectionLabel {{
                font-size: 12px;
                font-weight: bold;
                color: {C["text2"]};
            }}
            #divider {{
                color: {C["border"]};
            }}
            #disabledHint {{
                font-size: 11px;
                color: {C["text3"]};
            }}
            #warningLabel {{
                font-size: 11px;
                color: {C["warning"]};
                padding: 4px 0;
            }}

            /* ── Head LLM 드롭다운 ────────────────────────── */
            #headCombo {{
                padding: 8px 12px;
                border: 1px solid {C["border"]};
                border-radius: 6px;
                background: white;
                font-size: 13px;
                color: {C["text"]};
                min-height: 20px;
            }}
            #headCombo:focus {{
                border-color: {C["borderFocus"]};
            }}
            #headCombo::drop-down {{
                border: none;
                width: 24px;
            }}
            #headCombo QAbstractItemView {{
                border: 1px solid {C["border"]};
                background: white;
                selection-background-color: {C["accent"]};
                selection-color: white;
                padding: 4px;
            }}

            /* ── Worker 체크박스 ───────────────────────────── */
            QCheckBox {{
                font-size: 13px;
                color: {C["text"]};
                spacing: 6px;
            }}
            QCheckBox:disabled {{
                color: {C["text3"]};
            }}

            /* ── 실행 버튼 ────────────────────────────────── */
            #runButton {{
                background-color: {C["accent"]};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 14px;
                font-weight: bold;
                min-height: 20px;
            }}
            #runButton:hover {{
                background-color: #0062CC;
            }}
            #runButton:disabled {{
                background-color: #A0C4FF;
                color: rgba(255, 255, 255, 0.7);
            }}

            /* ── 중지 버튼 ────────────────────────────────── */
            #stopButton {{
                background-color: #E8E9ED;
                color: {C["text2"]};
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 14px;
                min-height: 20px;
            }}
            #stopButton:hover {{
                background-color: #D5D6DA;
            }}
            #stopButton:disabled {{
                color: {C["text3"]};
            }}

            /* ── 지우기 버튼 (사이드바) ───────────────────── */
            #clearAllButton {{
                background-color: #E8E9ED;
                color: {C["text2"]};
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-size: 14px;
                min-height: 20px;
            }}
            #clearAllButton:hover {{
                background-color: #D5D6DA;
            }}

            /* ── 콘텐츠 영역 ─────────────────────────────── */
            #contentArea {{
                background-color: {C["bg"]};
            }}
            #contentSectionTitle {{
                font-size: 15px;
                font-weight: bold;
                color: {C["text"]};
            }}
            #charCount {{
                font-size: 12px;
                color: {C["text3"]};
            }}

            /* ── 프롬프트 입력 ────────────────────────────── */
            #promptEdit {{
                background-color: {C["surface"]};
                border: 1px solid {C["border"]};
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                color: {C["text"]};
            }}
            #promptEdit:focus {{
                border-color: {C["borderFocus"]};
            }}

            /* ── 메트릭 카드 ──────────────────────────────── */
            #metricCard {{
                background-color: #F8F9FC;
                border: 1px solid {C["border"]};
                border-radius: 8px;
            }}
            #metricTitle {{
                font-size: 11px;
                color: {C["text2"]};
            }}
            #metricValue {{
                font-size: 20px;
                font-weight: bold;
                color: {C["text"]};
            }}

            /* ── 뷰 토글 버튼 ────────────────────────────── */
            #viewToggle {{
                border: 1px solid {C["border"]};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                background: {C["surface"]};
                color: {C["text2"]};
            }}
            #viewToggle:checked {{
                background: {C["accent"]};
                color: white;
                border-color: {C["accent"]};
            }}
            #viewToggle:hover {{
                background: #EEF0F4;
            }}
            #viewToggle:checked:hover {{
                background: #0062CC;
            }}

            /* ── 종합 결과 카드 ───────────────────────────── */
            #synthesisCard {{
                background-color: #EEF5FF;
                border: 1px solid {C["accent"]};
                border-radius: 8px;
            }}
            #synthesisTitle {{
                font-size: 14px;
                font-weight: bold;
                color: {C["accent"]};
            }}
            #synthesisTextEdit {{
                background: transparent;
                border: none;
                font-size: 13px;
                color: {C["text"]};
            }}

            /* ── 스크롤 영역 ──────────────────────────────── */
            #responseScroll {{
                border: none;
                background: transparent;
            }}
            #cardsContainer {{
                background: transparent;
            }}

            /* ── 카드 상태 뱃지 ───────────────────────────── */
            #cardStatus {{
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 10px;
            }}
            #cardStatus[status="waiting"] {{
                background-color: #E8E9ED;
                color: {C["text2"]};
            }}
            #cardStatus[status="head"] {{
                background-color: #EEF5FF;
                color: {C["accent"]};
            }}
            #cardStatus[status="running"] {{
                background-color: #FFF3CD;
                color: #856404;
            }}
            #cardStatus[status="done"] {{
                background-color: #D4EDDA;
                color: #155724;
            }}
            #cardStatus[status="error"] {{
                background-color: #F8D7DA;
                color: #721C24;
            }}

            /* ── 소형 버튼 (지우기, 복사) ─────────────────── */
            #smallBtn {{
                border: 1px solid {C["border"]};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                background: {C["surface"]};
                color: {C["text2"]};
            }}
            #smallBtn:hover {{
                background: #D5D6DA;
            }}

            /* ── 로그 텍스트 ──────────────────────────────── */
            #logText {{
                background-color: #F8F9FC;
                border: 1px solid {C["border"]};
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-family: "Menlo", "Consolas", monospace;
                color: {C["text2"]};
            }}

            /* ── 스크롤바 ─────────────────────────────────── */
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {C["border"]};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C["text3"]};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                height: 0;
            }}
        """)
