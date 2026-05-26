import time
import threading

import pyautogui
import pyperclip

from .exceptions import ImageNotFoundError, ResponseTimeoutError

# pyautogui 페일세이프: 마우스를 화면 좌상단 구석으로 이동하면 강제 중단
pyautogui.FAILSAFE = True

# Worker 스레드들이 UI 조작 버스트(포커스→입력→전송)를 직렬화하기 위한 락
_automation_lock = threading.Lock()

POLL_INTERVAL = 0.5
DEFAULT_CONFIDENCE = 0.85
DEFAULT_CLICK_TIMEOUT = 30.0
DEFAULT_WAIT_TIMEOUT = 300.0
DEFAULT_GONE_TIMEOUT = 30.0
COPY_MAX_RETRIES = 3


class AutomationHelper:
    def __init__(self, confidence: float = DEFAULT_CONFIDENCE,
                 poll_interval: float = POLL_INTERVAL):
        self.confidence = confidence
        self.poll_interval = poll_interval

    def paste_text(self, text: str) -> None:
        """한글 포함 텍스트를 클립보드→Ctrl+V 방식으로 입력 (typewrite 대신)"""
        pyperclip.copy(text)
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)

    def click_image(self, image_path: str, llm_name: str = "",
                    timeout: float = DEFAULT_CLICK_TIMEOUT) -> tuple:
        """이미지가 화면에 나타날 때까지 폴링 후 클릭. 타임아웃 시 ImageNotFoundError."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(image_path, confidence=self.confidence)
            except pyautogui.ImageNotFoundException:
                loc = None
            except OSError:
                # 이미지 파일이 없거나 읽을 수 없는 경우 즉시 예외
                raise ImageNotFoundError(image_path, llm_name)

            if loc is not None:
                center = pyautogui.center(loc)
                pyautogui.click(center)
                return (center.x, center.y)
            time.sleep(self.poll_interval)

        raise ImageNotFoundError(image_path, llm_name)

    def wait_for_image(self, image_path: str, llm_name: str = "",
                       timeout: float = DEFAULT_WAIT_TIMEOUT) -> bool:
        """이미지가 화면에 나타날 때까지 폴링 (응답 완료 감지)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(image_path, confidence=self.confidence)
            except (pyautogui.ImageNotFoundException, OSError):
                loc = None

            if loc is not None:
                return True
            time.sleep(self.poll_interval)

        raise ResponseTimeoutError(llm_name, timeout)

    def wait_for_image_gone(self, image_path: str, llm_name: str = "",
                            timeout: float = DEFAULT_GONE_TIMEOUT) -> bool:
        """이미지가 화면에서 사라질 때까지 폴링 (전송 시작 확인)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                loc = pyautogui.locateOnScreen(image_path, confidence=self.confidence)
            except (pyautogui.ImageNotFoundException, OSError):
                loc = None

            if loc is None:
                return True
            time.sleep(self.poll_interval)

        # 타임아웃이 나도 계속 진행 (전송이 됐을 수도 있음)
        return False

    def copy_from_clipboard(self) -> str:
        """Ctrl+A, Ctrl+C 후 클립보드에서 텍스트 반환. 비어있으면 최대 3회 재시도."""
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

    def get_lock(self) -> threading.Lock:
        """UI 조작 락 반환 (Worker 스레드가 직접 사용)"""
        return _automation_lock
