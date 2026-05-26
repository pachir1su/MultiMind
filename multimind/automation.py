import time
import threading

import pyautogui
import pyperclip

from .exceptions import ImageNotFoundError, ResponseTimeoutError

# ── pyautogui 전역 설정 ────────────────────────────────────────────────────────
# FAILSAFE: 마우스를 화면 좌상단 구석으로 이동하면 FailSafeException 발생 → 강제 중단
pyautogui.FAILSAFE = True

# ── UI 조작 직렬화 락 ──────────────────────────────────────────────────────────
# Worker 스레드들이 포커스→입력→전송 버스트를 순서대로 실행하도록 직렬화
_automationLock = threading.Lock()

# ── 기본 상수 ──────────────────────────────────────────────────────────────────
POLL_INTERVAL = 0.5
DEFAULT_CONFIDENCE = 0.85
DEFAULT_CLICK_TIMEOUT = 30.0
DEFAULT_WAIT_TIMEOUT = 300.0
DEFAULT_GONE_TIMEOUT = 30.0
COPY_MAX_RETRIES = 3


class AutomationHelper:
    def __init__(self, confidence: float = DEFAULT_CONFIDENCE,
                 pollInterval: float = POLL_INTERVAL):
        # ── 인스턴스 설정 ──────────────────────────────────────────────────────
        self.confidence = confidence
        self.pollInterval = pollInterval

    def pasteText(self, text: str) -> None:
        """클립보드→Ctrl+V 방식으로 텍스트 입력 (한글 지원, typewrite 대신)"""
        # ── 클립보드에 텍스트 올린 후 붙여넣기 ───────────────────────────────
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)

    def clickImage(self, imagePath: str, llmName: str = "",
                   timeout: float = DEFAULT_CLICK_TIMEOUT) -> tuple:
        """이미지가 화면에 나타날 때까지 폴링 후 클릭. 타임아웃 시 ImageNotFoundError."""
        # ── 폴링 루프: 이미지 등장까지 반복 탐색 ─────────────────────────────
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(imagePath, confidence=self.confidence)
            except pyautogui.ImageNotFoundException:
                loc = None
            except OSError:
                # 이미지 파일 자체를 읽을 수 없는 경우 즉시 예외
                raise ImageNotFoundError(imagePath, llmName)

            if loc is not None:
                center = pyautogui.center(loc)
                pyautogui.click(center)
                return (center.x, center.y)

            time.sleep(self.pollInterval)

        raise ImageNotFoundError(imagePath, llmName)

    def waitForImage(self, imagePath: str, llmName: str = "",
                     timeout: float = DEFAULT_WAIT_TIMEOUT) -> bool:
        """이미지가 화면에 나타날 때까지 폴링 (LLM 응답 완료 감지용)."""
        # ── 이미지 등장 폴링 ──────────────────────────────────────────────────
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(imagePath, confidence=self.confidence)
            except (pyautogui.ImageNotFoundException, OSError):
                loc = None

            if loc is not None:
                return True

            time.sleep(self.pollInterval)

        raise ResponseTimeoutError(llmName, timeout)

    def waitForImageGone(self, imagePath: str, llmName: str = "",
                         timeout: float = DEFAULT_GONE_TIMEOUT) -> bool:
        """이미지가 화면에서 사라질 때까지 폴링 (전송 시작 확인용)."""
        # ── 이미지 소멸 폴링 ──────────────────────────────────────────────────
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(imagePath, confidence=self.confidence)
            except (pyautogui.ImageNotFoundException, OSError):
                loc = None

            if loc is None:
                return True

            time.sleep(self.pollInterval)

        # 타임아웃 후에도 전송됐을 수 있으므로 False 반환 후 계속 진행
        return False

    def copyFromClipboard(self) -> str:
        """Ctrl+A → Ctrl+C 후 클립보드 내용 반환. 비어있으면 최대 3회 재시도."""
        # ── 재시도 루프: 클립보드가 채워질 때까지 반복 ───────────────────────
        for attempt in range(COPY_MAX_RETRIES):
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.3)
            text = pyperclip.paste()
            if text.strip():
                return text
            if attempt < COPY_MAX_RETRIES - 1:
                time.sleep(1.0)
        return ""

    def getLock(self) -> threading.Lock:
        """UI 조작 락 반환 (Worker 스레드가 직접 사용)"""
        return _automationLock
