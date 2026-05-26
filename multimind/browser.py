import subprocess
import time

from .exceptions import BrowserWindowNotFoundError

LLM_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini": "https://gemini.google.com/app",
}

# 창 제목에서 검색할 키워드
LLM_WINDOW_KEYWORDS = {
    "claude": "Claude",
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
}

OPEN_DELAY = 3.0


class BrowserController:
    def __init__(self, open_delay: float = OPEN_DELAY):
        self.open_delay = open_delay

    def open_tab(self, llm_name: str) -> None:
        """해당 LLM 사이트를 기본 브라우저의 새 탭으로 열기"""
        url = LLM_URLS.get(llm_name)
        if not url:
            return
        # Windows: start 명령으로 기본 브라우저 실행
        subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
        time.sleep(self.open_delay)

    def open_all_tabs(self, llm_names: list) -> None:
        """여러 LLM 사이트를 순차적으로 새 탭으로 열기"""
        for name in llm_names:
            self.open_tab(name)

    def focus_tab(self, llm_name: str) -> bool:
        """해당 LLM의 브라우저 창을 포그라운드로 가져오기.
        pygetwindow를 사용하고, 실패하면 Alt+Tab 폴백."""
        keyword = LLM_WINDOW_KEYWORDS.get(llm_name, llm_name)
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

        # pygetwindow 실패 시 Alt+Tab으로 순환 (폴백)
        import pyautogui
        pyautogui.hotkey("alt", "tab")
        time.sleep(0.5)
        return False
