import subprocess
import time

from .exceptions import BrowserWindowNotFoundError

# ── LLM 사이트 URL 및 창 제목 키워드 ─────────────────────────────────────────
LLM_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini": "https://gemini.google.com/app",
}

LLM_WINDOW_KEYWORDS = {
    "claude": "Claude",
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
}

OPEN_DELAY = 3.0


class BrowserController:
    def __init__(self, openDelay: float = OPEN_DELAY):
        # ── 인스턴스 설정 ──────────────────────────────────────────────────────
        self.openDelay = openDelay

    def openTab(self, llmName: str) -> None:
        """해당 LLM 사이트를 기본 브라우저의 새 탭으로 열기"""
        # ── Windows: start 명령으로 기본 브라우저에 URL 전달 ─────────────────
        url = LLM_URLS.get(llmName)
        if not url:
            return
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        except OSError as e:
            raise BrowserWindowNotFoundError(llmName) from e
        time.sleep(self.openDelay)

    def openAllTabs(self, llmNames: list) -> None:
        """여러 LLM 사이트를 순차적으로 새 탭으로 열기"""
        # ── 목록 순서대로 탭 오픈 ─────────────────────────────────────────────
        for name in llmNames:
            self.openTab(name)

    def focusTab(self, llmName: str) -> bool:
        """해당 LLM의 브라우저 창을 포그라운드로 가져오기.
        pygetwindow 성공 시 True, 실패 시 Alt+Tab 폴백 후 False."""
        keyword = LLM_WINDOW_KEYWORDS.get(llmName, llmName)

        # ── 1차: pygetwindow로 창 제목 검색 후 포커스 ────────────────────────
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(keyword)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True
        except Exception:
            pass

        # ── 2차 폴백: Alt+Tab으로 창 순환 ────────────────────────────────────
        try:
            import pyautogui
            pyautogui.hotkey("alt", "tab")
            time.sleep(0.5)
        except Exception:
            pass

        return False
