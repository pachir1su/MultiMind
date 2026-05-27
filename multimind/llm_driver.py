"""
undetected-chromedriver 기반 LLM 드라이버.
- Cloudflare / 봇 감지 우회
- 기존 Chrome 프로필 쿠키 복사 → 로그인 세션 재사용
- 기존 Chrome이 열려 있든 없든 독립 실행
"""
import os
import re
import sys
import time
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

from .exceptions import LLMDriverError, MissingDependencyError, ResponseTimeoutError

_IMPORT_ERROR: Optional[str] = None

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, StaleElementReferenceException,
    )
    import pyperclip
except ModuleNotFoundError as _e:
    _IMPORT_ERROR = str(_e)

# ── 프로필 경로 ────────────────────────────────────────────────────────────────
if sys.platform == "win32":
    _local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    _CHROME_USER_DATA = _local / "Google" / "Chrome" / "User Data"
    CHROME_PROFILE_DIR = str(_local / "MultiMind" / "ChromeProfile")
elif sys.platform == "darwin":
    _CHROME_USER_DATA = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")
else:
    _CHROME_USER_DATA = Path.home() / ".config" / "google-chrome"
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")

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
        '[data-testid="assistant-message"]',
        '[data-testid="chat-message-text"]',
        'div[class*="font-claude"]',
        'div[class*="prose"]',
        'div[class*="markdown"]',
        ".prose",
        'div[data-testid="user-human-turn"] + div .prose',
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

# CDP URL 매칭용 도메인 맵
_LLM_DOMAINS = {
    "claude": ["claude.ai"],
    "chatgpt": ["chatgpt.com", "chat.openai.com"],
    "gemini": ["gemini.google.com", "accounts.google.com"],
}

ELEMENT_WAIT  = 20
STABLE_SECS   = 3
RESPONSE_TIMEOUT = 300
LOGIN_POLL_INTERVAL = 10  # 로그인 확인 주기 (초)
LOGIN_TIMEOUT  = 300      # 로그인 최대 대기 (초)


_SESSION_FILES = [
    "Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm",
    "Login Data", "Login Data-journal", "Login Data-wal", "Login Data-shm",
    "Login Data For Account",
    "Web Data", "Web Data-journal", "Web Data-wal", "Web Data-shm",
    "Preferences", "Secure Preferences",
]


def _is_profile_locked() -> bool:
    """Chrome User Data 디렉토리가 다른 인스턴스에 잠겨있는지 확인."""
    for name in ["lockfile", "SingletonLock"]:
        p = _CHROME_USER_DATA / name
        try:
            if p.exists() or p.is_symlink():
                return True
        except OSError:
            return True
    return False


def _sync_cookies(log_fn=None) -> None:
    """메인 Chrome 세션을 MultiMind 전용 프로필로 복사 (최초 1회만).
    이미 세션이 존재하면 기존 로그인을 보존하기 위해 건너뜀.
    """
    _log = log_fn or (lambda m: None)
    src_default = _CHROME_USER_DATA / "Default"
    if not src_default.exists():
        _log("Chrome Default 프로필을 찾을 수 없음")
        return

    dst = Path(CHROME_PROFILE_DIR) / "Default"

    # 이미 세션 데이터가 있으면 덮어쓰지 않음 (이전 로그인 보존)
    if (dst / "Cookies").exists() or (dst / "Network" / "Cookies").exists():
        _log("기존 MultiMind 세션 유지 (이전 로그인 보존)")
        return

    # 최초 실행: 메인 Chrome에서 세션 복사
    _log("최초 세션 복사 중 (메인 Chrome에서 복사)...")
    dst.mkdir(parents=True, exist_ok=True)
    copied, failed_names = 0, []

    # Local State (쿠키 암호화 키 포함)
    src_ls = _CHROME_USER_DATA / "Local State"
    dst_ls = Path(CHROME_PROFILE_DIR) / "Local State"
    if src_ls.exists():
        try:
            shutil.copy2(str(src_ls), str(dst_ls))
            copied += 1
        except OSError:
            failed_names.append("Local State")

    # 세션/쿠키 파일 (항상 최신으로 덮어씀)
    for fname in _SESSION_FILES:
        src_file = src_default / fname
        dst_file = dst / fname
        if src_file.exists():
            try:
                shutil.copy2(str(src_file), str(dst_file))
                copied += 1
            except OSError:
                failed_names.append(fname)

    # 세션 관련 디렉토리
    for dirname in ["Local Storage", "Session Storage"]:
        src_dir = src_default / dirname
        dst_dir = dst / dirname
        if src_dir.exists():
            if dst_dir.exists():
                shutil.rmtree(str(dst_dir), ignore_errors=True)
            try:
                shutil.copytree(str(src_dir), str(dst_dir))
                copied += 1
            except OSError:
                failed_names.append(dirname)

    # Network 디렉토리 내 Cookies (최신 Chrome)
    src_net = src_default / "Network"
    dst_net = dst / "Network"
    if src_net.exists():
        dst_net.mkdir(parents=True, exist_ok=True)
        for fname in ["Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm"]:
            src_file = src_net / fname
            dst_file = dst_net / fname
            if src_file.exists():
                try:
                    shutil.copy2(str(src_file), str(dst_file))
                    copied += 1
                except OSError:
                    failed_names.append(f"Network/{fname}")

    msg = f"세션 파일 복사: {copied}개 성공"
    if failed_names:
        msg += f", {len(failed_names)}개 실패 ({', '.join(failed_names)})"
    _log(msg)


def _detect_chrome_version() -> Optional[int]:
    """설치된 Chrome의 메이저 버전 번호를 감지."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["reg", "query",
                 r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
                 "/v", "version"],
                capture_output=True, text=True, timeout=10,
            )
            m = re.search(r"(\d+)\.", result.stdout)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    else:
        for cmd in ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]:
            try:
                result = subprocess.run(
                    [cmd, "--version"], capture_output=True, text=True, timeout=10,
                )
                m = re.search(r"(\d+)\.", result.stdout)
                if m:
                    return int(m.group(1))
            except Exception:
                continue
    return None


def _parse_version_from_error(error_msg: str) -> Optional[int]:
    """버전 불일치 에러 메시지에서 실제 Chrome 버전을 추출."""
    m = re.search(r"Current browser version is (\d+)", error_msg)
    return int(m.group(1)) if m else None


class LLMDriver:
    """undetected-chromedriver 기반 멀티탭 LLM 드라이버."""

    def __init__(self, log_fn=None):
        self._log = log_fn or (lambda m: None)
        self._send_lock = threading.Lock()
        self.driver = None  # uc.Chrome when running
        self._tabs: dict[str, str] = {}

    # ── 초기화 ─────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Chrome 시작 (기존 프로필 우선 사용, 봇 감지 우회)"""
        if _IMPORT_ERROR is not None:
            pkg = _IMPORT_ERROR.replace("No module named ", "").strip("'\"")
            raise MissingDependencyError(
                pkg,
                "pip install selenium undetected-chromedriver pyperclip",
            )

        version_main = _detect_chrome_version()
        if version_main:
            self._log(f"Chrome 버전 {version_main} 감지됨")

        def _build_options(data_dir):
            opts = uc.ChromeOptions()
            opts.add_argument(f"--user-data-dir={data_dir}")
            opts.add_argument("--profile-directory=Default")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-popup-blocking")
            return opts

        def _try_launch(data_dir, ver=version_main):
            kwargs = dict(options=_build_options(data_dir), use_subprocess=True)
            if ver:
                kwargs["version_main"] = ver
            return uc.Chrome(**kwargs)

        profile_locked = _is_profile_locked()

        if not profile_locked:
            # 프로필 잠금 없음 → 기존 프로필 직접 사용
            self._log("기존 Chrome 프로필로 시작 중...")
            try:
                self.driver = _try_launch(str(_CHROME_USER_DATA))
                self._log("기존 Chrome 프로필 연결 성공 (로그인 세션 유지)")
            except Exception as e:
                self.driver = None
                parsed_ver = _parse_version_from_error(str(e))
                if parsed_ver and parsed_ver != version_main:
                    try:
                        self.driver = _try_launch(str(_CHROME_USER_DATA), parsed_ver)
                        version_main = parsed_ver
                        self._log("기존 Chrome 프로필 연결 성공 (로그인 세션 유지)")
                    except Exception:
                        pass

        if self.driver is None:
            # 프로필 잠김 or 기존 프로필 실패 → 별도 프로필 + 세션 복사
            if profile_locked:
                self._log(
                    "Chrome이 실행 중 — 별도 프로필로 시작합니다\n"
                    "  → 팁: Chrome을 완전히 종료(시스템 트레이 포함)한 후 실행하면 자동 로그인됩니다."
                )
            else:
                self._log("기존 프로필 사용 실패 — 별도 프로필로 시작합니다")
            Path(CHROME_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
            _sync_cookies(log_fn=self._log)
            try:
                self.driver = _try_launch(CHROME_PROFILE_DIR)
            except Exception as e:
                parsed_ver = _parse_version_from_error(str(e))
                if parsed_ver and parsed_ver != version_main:
                    try:
                        self.driver = _try_launch(CHROME_PROFILE_DIR, parsed_ver)
                    except Exception as e2:
                        raise LLMDriverError("chrome", f"Chrome 시작 실패: {e2}")
                else:
                    raise LLMDriverError("chrome", f"Chrome 시작 실패: {e}")

        self.driver.set_page_load_timeout(60)
        self._log("Chrome 시작됨 (봇 감지 우회 활성화)")

    def open_tabs(self, llm_names: list) -> None:
        """각 LLM을 새 탭으로 열기 (Selenium WebDriver 기반, 페이지 로드 대기)"""
        for i, name in enumerate(llm_names):
            url = LLM_URLS[name]
            if i == 0:
                self.driver.get(url)
            else:
                self.driver.switch_to.new_window("tab")
                self.driver.get(url)
            self._tabs[name] = self.driver.current_window_handle
            try:
                WebDriverWait(self.driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except (TimeoutException, Exception):
                pass
            self._log(f"[{name}] 탭 열림 — {self.driver.title}")
            time.sleep(1.5)

    def _check_login_cdp(self, llm_names: list) -> Optional[list]:
        """CDP로 탭 전환 없이 로그인 상태 확인. 로그인 필요한 LLM 목록 반환.
        CDP 미지원 시 None 반환.
        """
        try:
            targets = self.driver.execute_cdp_cmd("Target.getTargets", {})
        except Exception:
            return None

        page_urls: dict[str, str] = {}
        for info in targets.get("targetInfos", []):
            if info.get("type") == "page":
                url = info.get("url", "").lower()
                for name, domains in _LLM_DOMAINS.items():
                    if any(d in url for d in domains):
                        page_urls[name] = url

        pending = []
        for name in llm_names:
            url = page_urls.get(name, "")
            if not url or any(k in url for k in _LOGIN_URL_KEYWORDS):
                pending.append(name)
        return pending

    def wait_for_login(self, llm_names: list) -> None:
        """로그인이 필요한 LLM을 감지하고, 모두 로그인될 때까지 대기.
        CDP를 사용하여 탭 전환 없이 URL만 확인 — 브라우저 깜빡임 방지.
        """
        deadline = time.time() + LOGIN_TIMEOUT

        pending = self._check_login_cdp(llm_names)
        if pending is None:
            pending = [n for n in llm_names if not self._check_logged_in(n)]

        if not pending:
            self._log("모든 LLM 로그인 확인 완료 ✓")
            self._verify_ready(llm_names)
            return

        self._log(
            f"로그인 필요: {', '.join(pending)}\n"
            "  → 브라우저에서 직접 로그인해주세요. 자동으로 감지합니다.\n"
            "  → 탭이 전환되지 않으니 편하게 로그인하세요."
        )

        last_status_log = time.time()
        while time.time() < deadline:
            time.sleep(LOGIN_POLL_INTERVAL)

            pending = self._check_login_cdp(llm_names)
            if pending is None:
                pending = [n for n in llm_names if not self._check_logged_in(n)]

            if not pending:
                self._log("모든 LLM 로그인 확인 완료 ✓")
                self._verify_ready(llm_names)
                return

            now = time.time()
            if now - last_status_log >= 30:
                remaining = int(deadline - now)
                self._log(f"로그인 대기 중: {', '.join(pending)} (남은 시간: {remaining}초)")
                last_status_log = now

        self._log("⚠ 일부 LLM이 아직 로그인되지 않았습니다. 계속 진행합니다.")

    def _verify_ready(self, llm_names: list) -> None:
        """각 LLM 탭의 입력창이 실제로 준비될 때까지 대기. 미발견 시 새로고침."""
        self._log("각 LLM 입력창 확인 중...")
        for name in llm_names:
            self.switch_to(name)
            if self._find_any(_INPUT[name], 15):
                self._log(f"[{name}] 입력창 준비 완료")
                continue
            self._log(f"[{name}] 입력창 미발견 — 페이지 새로고침")
            self.driver.refresh()
            try:
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except (TimeoutException, Exception):
                pass
            if self._find_any(_INPUT[name], 20):
                self._log(f"[{name}] 새로고침 후 준비 완료")
            else:
                self._log(f"[{name}] ⚠ 입력창 없음 — 프롬프트 전송 시 재시도 예정")

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
                self._log(f"[{llm_name}] 입력창 미발견 — 새로고침 후 재시도")
                self.driver.refresh()
                time.sleep(3)
                input_el = self._find_any(_INPUT[llm_name], 30)
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
        text_ever_found = False

        while time.time() < deadline:
            self.switch_to(llm_name)
            text = self._get_last_text(selectors)

            if text and not text_ever_found:
                text_ever_found = True
                _log(f"[{llm_name}] 응답 감지 시작 ({len(text)}자)")

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
                if text_ever_found:
                    _log(f"[{llm_name}] 응답 생성 중... ({elapsed}초, 현재 {len(last_text)}자)")
                else:
                    _log(f"[{llm_name}] ⚠ 응답 텍스트 미감지 ({elapsed}초) — 셀렉터: {selectors[0]}")
                last_log_time = now

            time.sleep(1.0)

        if last_text:
            _log(f"[{llm_name}] 타임아웃 — 부분 응답 반환 ({len(last_text)}자)")
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
        """가장 마지막 응답 요소의 텍스트 반환. CSS 실패 시 JS 폴백."""
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    text = els[-1].text.strip()
                    if text:
                        return text
            except (StaleElementReferenceException, Exception):
                continue
        try:
            return self.driver.execute_script("""
                var sels = ['[class*="prose"]', '[class*="markdown"]',
                            '[data-testid*="message"]', '[class*="response"]',
                            '[class*="Message"]'];
                for (var s of sels) {
                    var els = document.querySelectorAll(s);
                    if (els.length) {
                        var t = els[els.length-1].innerText.trim();
                        if (t.length > 20) return t;
                    }
                }
                return '';
            """) or ""
        except Exception:
            return ""
