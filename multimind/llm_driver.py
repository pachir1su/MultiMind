"""
Selenium Chrome 기반 LLM 드라이버.
각 LLM 사이트를 새 탭으로 열고 DOM 요소를 직접 제어합니다.
이미지 매칭 불필요 — CSS 셀렉터로 입력창/버튼을 찾습니다.
"""
import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    StaleElementReferenceException,
)
import pyperclip

from .exceptions import LLMDriverError, ResponseTimeoutError

# ── Chrome 전용 프로필 (메인 Chrome과 충돌 방지) ────────────────────────────────
if sys.platform == "win32":
    _local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    CHROME_PROFILE_DIR = str(_local / "MultiMind" / "ChromeProfile")
else:
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")

# ── LLM 사이트 URL ────────────────────────────────────────────────────────────
LLM_URLS = {
    "claude":  "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini":  "https://gemini.google.com/app",
}

# ── CSS 셀렉터 목록 (앞에서부터 순서대로 시도) ──────────────────────────────────
_INPUT = {
    "claude":  [
        'div.ProseMirror[contenteditable="true"]',
        'fieldset div[contenteditable="true"]',
        'div[contenteditable="true"]',
    ],
    "chatgpt": [
        "#prompt-textarea",
        'div[contenteditable="true"]',
    ],
    "gemini":  [
        "div.ql-editor",
        'rich-textarea div[contenteditable="true"]',
        'div[contenteditable="true"]',
    ],
}

_SEND = {
    "claude":  [
        'button[aria-label="Send Message"]',
        'button[aria-label="Send message"]',
        'button[data-testid="send-message-button"]',
    ],
    "chatgpt": [
        'button[data-testid="send-button"]',
        'button[aria-label="Send prompt"]',
        'button[aria-label="Send message"]',
    ],
    "gemini":  [
        'button[aria-label="Send message"]',
        "button.send-button",
    ],
}

_RESPONSE = {
    "claude":  [
        'div[data-testid="user-human-turn"] + div .prose',
        ".prose",
        'div[data-is-streaming]',
        '[data-testid="assistant-message"]',
    ],
    "chatgpt": [
        'div[data-message-author-role="assistant"] .markdown',
        'div[data-message-author-role="assistant"]',
        "article .markdown",
    ],
    "gemini":  [
        "model-response",
        ".response-content",
        "message-content",
        ".model-response-text",
    ],
}

ELEMENT_WAIT = 25    # 요소 탐색 최대 대기 (초)
STABLE_SECS  = 3     # 텍스트가 이 초 동안 변하지 않으면 완료
RESPONSE_TIMEOUT = 300


class LLMDriver:
    """멀티탭 Chrome 드라이버."""

    def __init__(self, log_fn=None):
        self._log = log_fn or (lambda m: None)
        self._send_lock = threading.Lock()
        self.driver: Optional[webdriver.Chrome] = None
        self._tabs: dict[str, str] = {}

    # ── 초기화 ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Chrome 시작 (전용 프로필로 로그인 세션 유지)"""
        Path(CHROME_PROFILE_DIR).mkdir(parents=True, exist_ok=True)

        opts = Options()
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches",
                                     ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)

        try:
            self.driver = webdriver.Chrome(options=opts)
        except WebDriverException as e:
            if "cannot find Chrome binary" in str(e).lower():
                raise LLMDriverError("chrome", "Chrome이 설치되어 있지 않거나 경로를 찾을 수 없습니다.")
            raise LLMDriverError("chrome", f"Chrome 시작 실패: {e}")

        self.driver.set_page_load_timeout(60)
        self._log("Chrome 시작됨")

    def open_tabs(self, llm_names: list) -> None:
        """각 LLM을 새 탭으로 열기"""
        for i, name in enumerate(llm_names):
            url = LLM_URLS[name]
            if i == 0:
                self.driver.get(url)
            else:
                self.driver.execute_script(f"window.open('{url}', '_blank');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
            self._tabs[name] = self.driver.current_window_handle
            self._log(f"[{name}] 탭 열림")
            time.sleep(2.0)

    def switch_to(self, llm_name: str) -> None:
        handle = self._tabs.get(llm_name)
        if handle and self.driver.current_window_handle != handle:
            self.driver.switch_to.window(handle)

    # ── 핵심 작업 ──────────────────────────────────────────────────────────────

    def send_prompt(self, llm_name: str, prompt: str) -> None:
        """입력창에 프롬프트를 입력하고 전송 (전송 직렬화)"""
        with self._send_lock:
            self.switch_to(llm_name)

            # 입력창 찾기
            input_el = self._find_any(_INPUT[llm_name], ELEMENT_WAIT)
            if input_el is None:
                raise LLMDriverError(
                    llm_name,
                    "입력창을 찾을 수 없습니다. 해당 LLM 탭에서 로그인되어 있는지 확인하세요."
                )

            input_el.click()
            time.sleep(0.3)

            # 기존 내용 전체 선택 후 삭제
            input_el.send_keys(Keys.CONTROL, "a")
            time.sleep(0.1)
            input_el.send_keys(Keys.DELETE)
            time.sleep(0.1)

            # 클립보드 붙여넣기 (한글/특수문자 안전)
            pyperclip.copy(prompt)
            input_el.send_keys(Keys.CONTROL, "v")
            time.sleep(0.5)

            # 전송 버튼 클릭 (못 찾으면 Enter 폴백)
            send_el = self._find_any(_SEND[llm_name], 10)
            if send_el:
                try:
                    send_el.click()
                except Exception:
                    input_el.send_keys(Keys.RETURN)
            else:
                input_el.send_keys(Keys.RETURN)

            self._log(f"[{llm_name}] 전송 완료")

    def wait_response(self, llm_name: str,
                      timeout: int = RESPONSE_TIMEOUT,
                      log_fn=None) -> str:
        """응답 텍스트가 안정될 때까지 대기 후 반환 (락 없이 병렬 가능)"""
        _log = log_fn or self._log
        selectors = _RESPONSE[llm_name]
        deadline = time.time() + timeout

        # 전송 직후 잠시 대기
        time.sleep(3.0)

        last_text = ""
        stable_count = 0
        last_log_time = time.time()

        while time.time() < deadline:
            self.switch_to(llm_name)
            text = self._get_last_text(selectors)

            if text and text == last_text:
                stable_count += 1
                if stable_count >= STABLE_SECS:
                    _log(f"[{llm_name}] 응답 완료 ({len(text)}자)")
                    return text
            else:
                stable_count = 0
                last_text = text

            now = time.time()
            if now - last_log_time >= 10:
                elapsed = int(now - (deadline - timeout))
                _log(f"[{llm_name}] 응답 대기 중... ({elapsed}초 경과)")
                last_log_time = now

            time.sleep(1.0)

        # 타임아웃 — 마지막으로 받은 텍스트라도 반환
        if last_text:
            _log(f"[{llm_name}] 타임아웃 — 부분 응답 반환")
            return last_text
        raise ResponseTimeoutError(llm_name, timeout)

    def quit(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _find_any(self, selectors: list, timeout: float):
        """셀렉터 목록을 순서대로 시도해 처음 찾은 요소 반환"""
        per = max(timeout / len(selectors), 2.0)
        for sel in selectors:
            try:
                return WebDriverWait(self.driver, per).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
            except (TimeoutException, NoSuchElementException):
                continue
        return None

    def _get_last_text(self, selectors: list) -> str:
        """가장 마지막 응답 요소의 텍스트 반환"""
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    return els[-1].text.strip()
            except (StaleElementReferenceException, Exception):
                continue
        return ""
