"""
undetected-chromedriver 기반 LLM 드라이버.
- Cloudflare / 봇 감지 우회
- 기존 Chrome 프로필 쿠키 복사 → 로그인 세션 재사용
- 기존 Chrome이 열려 있든 없든 독립 실행
"""
import os
import sys
import time
import shutil
import threading
from pathlib import Path
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
)
import pyperclip

from .exceptions import LLMDriverError, ResponseTimeoutError

# ── 프로필 경로 ────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    _local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    CHROME_PROFILE_DIR = str(_local / "MultiMind" / "ChromeProfile")
    _MAIN_CHROME_DEFAULT = _local / "Google" / "Chrome" / "User Data" / "Default"
    _MAIN_CHROME_LOCAL_STATE = _local / "Google" / "Chrome" / "User Data" / "Local State"
else:
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")
    _MAIN_CHROME_DEFAULT = None
    _MAIN_CHROME_LOCAL_STATE = None

# ── LLM URL ───────────────────────────────────────────────────────────────────
LLM_URLS = {
    "claude":  "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini":  "https://gemini.google.com/app",
}

# ── CSS 셀렉터 (앞에서부터 순서대로 시도) ────────────────────────────────────────
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
        ".prose",
        'div[data-testid="user-human-turn"] + div .prose',
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

# 로그인 페이지로 판단하는 URL 키워드
_LOGIN_URL_KEYWORDS = ["login", "signin", "sign-in", "auth", "accounts.google"]

ELEMENT_WAIT  = 20
STABLE_SECS   = 3
RESPONSE_TIMEOUT = 300
LOGIN_POLL_INTERVAL = 5   # 로그인 확인 주기 (초)
LOGIN_TIMEOUT  = 300      # 로그인 최대 대기 (초)


def _sync_cookies() -> None:
    """기존 Chrome Default 프로필의 세션 파일을 MultiMind 프로필로 복사.
    이미 복사된 파일은 건너뜀. Chrome이 실행 중이면 일부 파일은 잠겨 실패할 수 있음.
    """
    if _MAIN_CHROME_DEFAULT is None or not _MAIN_CHROME_DEFAULT.exists():
        return

    dst = Path(CHROME_PROFILE_DIR) / "Default"
    dst.mkdir(parents=True, exist_ok=True)

    # Local State (암호화 키 포함) — 최상위 User Data 폴더에 있음
    if _MAIN_CHROME_LOCAL_STATE and _MAIN_CHROME_LOCAL_STATE.exists():
        dst_ls = Path(CHROME_PROFILE_DIR) / "Local State"
        if not dst_ls.exists():
            try:
                shutil.copy2(str(_MAIN_CHROME_LOCAL_STATE), str(dst_ls))
            except OSError:
                pass

    # 세션/쿠키 파일
    for fname in ["Cookies", "Login Data", "Login Data For Account",
                  "Web Data", "Preferences"]:
        src_file = _MAIN_CHROME_DEFAULT / fname
        dst_file = dst / fname
        if src_file.exists() and not dst_file.exists():
            try:
                shutil.copy2(str(src_file), str(dst_file))
            except OSError:
                pass


class LLMDriver:
    """undetected-chromedriver 기반 멀티탭 LLM 드라이버."""

    def __init__(self, log_fn=None):
        self._log = log_fn or (lambda m: None)
        self._send_lock = threading.Lock()
        self.driver: Optional[uc.Chrome] = None
        self._tabs: dict[str, str] = {}

    # ── 초기화 ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Chrome 시작 (봇 감지 우회 + 기존 세션 복사)"""
        Path(CHROME_PROFILE_DIR).mkdir(parents=True, exist_ok=True)

        self._log("기존 Chrome 세션 파일 복사 중...")
        _sync_cookies()

        opts = uc.ChromeOptions()
        opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")

        try:
            self.driver = uc.Chrome(options=opts, use_subprocess=True)
        except Exception as e:
            raise LLMDriverError("chrome", f"Chrome 시작 실패: {e}")

        self.driver.set_page_load_timeout(60)
        self._log("Chrome 시작됨 (봇 감지 우회 활성화)")

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

    def wait_for_login(self, llm_names: list) -> None:
        """로그인이 필요한 LLM을 감지하고, 모두 로그인될 때까지 대기."""
        deadline = time.time() + LOGIN_TIMEOUT
        while time.time() < deadline:
            pending = [n for n in llm_names if not self._check_logged_in(n)]
            if not pending:
                self._log("모든 LLM 로그인 확인 완료 ✓")
                return
            self._log(
                f"로그인 필요: {', '.join(pending)}\n"
                "  → 브라우저 창에서 직접 로그인해주세요. 로그인하면 자동으로 계속됩니다."
            )
            time.sleep(LOGIN_POLL_INTERVAL)

        self._log("⚠ 일부 LLM이 아직 로그인되지 않았습니다. 계속 진행합니다.")

    def switch_to(self, llm_name: str) -> None:
        handle = self._tabs.get(llm_name)
        if handle and self.driver.current_window_handle != handle:
            self.driver.switch_to.window(handle)

    # ── 핵심 작업 ──────────────────────────────────────────────────────────────

    def send_prompt(self, llm_name: str, prompt: str) -> None:
        """프롬프트 입력 및 전송 (직렬화)"""
        with self._send_lock:
            self.switch_to(llm_name)

            input_el = self._find_any(_INPUT[llm_name], ELEMENT_WAIT)
            if input_el is None:
                raise LLMDriverError(
                    llm_name,
                    "입력창을 찾을 수 없습니다. 해당 LLM 탭에서 로그인되어 있는지 확인하세요."
                )

            input_el.click()
            time.sleep(0.3)
            input_el.send_keys(Keys.CONTROL, "a")
            time.sleep(0.1)
            input_el.send_keys(Keys.DELETE)
            time.sleep(0.1)

            pyperclip.copy(prompt)
            input_el.send_keys(Keys.CONTROL, "v")
            time.sleep(0.5)

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
        """응답 텍스트가 안정될 때까지 대기 후 반환"""
        _log = log_fn or self._log
        selectors = _RESPONSE[llm_name]
        deadline = time.time() + timeout

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

    def _check_logged_in(self, llm_name: str) -> bool:
        """해당 LLM 탭이 로그인된 상태인지 확인"""
        try:
            self.switch_to(llm_name)
            url = self.driver.current_url.lower()

            # 로그인 페이지 URL이면 False
            if any(k in url for k in _LOGIN_URL_KEYWORDS):
                return False

            # 입력창이 있으면 로그인된 것으로 판단
            for sel in _INPUT[llm_name]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    return True
        except Exception:
            pass
        return False

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
