"""
멀티 브라우저 LLM 드라이버 모듈.
- Chrome (undetected-chromedriver): Cloudflare/봇 감지 우회 지원
- Edge (selenium): Chrome 미설치 시 폴백 브라우저
- 기존 Chrome 프로필 쿠키 복사로 로그인 세션 재사용
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

from .exceptions import (
    LLMDriverError, MissingDependencyError,
    ResponseTimeoutError, BrowserNotFoundError,
)

# ── 외부 패키지 임포트 (selenium 공통 + uc 선택적) ────────────────────────────

_IMPORT_ERROR: Optional[str] = None
_UC_AVAILABLE = False

# Selenium 공통 모듈 임포트
try:
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

# undetected-chromedriver 임포트 (Chrome 전용, 봇 감지 우회)
try:
    import undetected_chromedriver as uc
    _UC_AVAILABLE = True
except ModuleNotFoundError:
    pass

# OS별 단축키 수정자 키 (macOS: Cmd, Windows/Linux: Ctrl)
_MOD_KEY = None
if _IMPORT_ERROR is None:
    _MOD_KEY = Keys.COMMAND if sys.platform == "darwin" else Keys.CONTROL

# ── Chrome 프로필 경로 ────────────────────────────────────────────────────────
if sys.platform == "win32":
    _local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    _CHROME_USER_DATA = _local / "Google" / "Chrome" / "User Data"
    CHROME_PROFILE_DIR = str(_local / "MultiMind" / "ChromeProfile")
    _EDGE_USER_DATA = _local / "Microsoft" / "Edge" / "User Data"
    EDGE_PROFILE_DIR = str(_local / "MultiMind" / "EdgeProfile")
elif sys.platform == "darwin":
    _CHROME_USER_DATA = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")
    _EDGE_USER_DATA = Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    EDGE_PROFILE_DIR = str(Path.home() / ".multimind" / "edge-profile")
else:
    _CHROME_USER_DATA = Path.home() / ".config" / "google-chrome"
    CHROME_PROFILE_DIR = str(Path.home() / ".multimind" / "chrome-profile")
    _EDGE_USER_DATA = Path.home() / ".config" / "microsoft-edge"
    EDGE_PROFILE_DIR = str(Path.home() / ".multimind" / "edge-profile")

# ── LLM URL ───────────────────────────────────────────────────────────────────
LLM_URLS = {
    "claude":  "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini":  "https://gemini.google.com/app",
    "grok":    "https://grok.com/",
    "perplexity": "https://www.perplexity.ai/",
}

# ── CSS 셀렉터 (앞에서부터 순서대로 시도) ────────────────────────────────────
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
        "div.ql-editor.textarea",
        "div.ql-editor",
        'rich-textarea div[contenteditable="true"]',
        'div[contenteditable="true"][aria-label*="rompt"]',
        'div[contenteditable="true"][aria-label*="essage"]',
        'div[contenteditable="true"]',
    ],
    "grok": [
        'textarea[aria-label]',
        'textarea[placeholder]',
        'textarea',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
    ],
    "perplexity": [
        'textarea[placeholder]',
        'textarea[autofocus]',
        'textarea',
        'div[contenteditable="true"][role="textbox"]',
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
        'button[aria-label="보내기"]',
        'button[aria-label="메시지 전송"]',
        'button[aria-label="전송"]',
        'button[aria-label="Send"]',
        "button.send-button",
        'button[data-testid="send-button"]',
        '.trailing-icon-button',
        '.input-area-container button[aria-label]',
    ],
    "grok": [
        'button[aria-label="Send"]',
        'button[aria-label="Send message"]',
        'button[aria-label="전송"]',
        'button[type="submit"]',
        'button[data-testid="send-button"]',
    ],
    "perplexity": [
        'button[aria-label="Submit"]',
        'button[aria-label="Send"]',
        'button[aria-label="전송"]',
        'button[type="submit"]',
        'button[data-testid="submit-button"]',
        'button[data-testid="send-button"]',
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
        "model-response .response-content",
        "model-response",
        "message-content .text-content",
        "message-content",
        ".response-content",
        ".model-response-text",
    ],
    "grok": [
        'div[class*="message-bubble"]',
        'div[class*="response"]',
        'div[class*="markdown"]',
        'div[class*="prose"]',
        '.message-text',
        'div[data-testid*="message"]',
    ],
    "perplexity": [
        'div[class*="prose"]',
        'div[class*="markdown"]',
        'div[class*="answer"]',
        '.prose',
        'div[dir="auto"]',
        'div[data-testid*="answer"]',
    ],
}

# 로그인 페이지 URL 키워드
_LOGIN_URL_KEYWORDS = ["login", "signin", "sign-in", "auth", "accounts.google"]

# CDP URL 매칭용 LLM 도메인
_LLM_DOMAINS = {
    "claude": ["claude.ai"],
    "chatgpt": ["chatgpt.com", "chat.openai.com"],
    "gemini": ["gemini.google.com", "accounts.google.com"],
    "grok": ["grok.com", "x.com"],
    "perplexity": ["perplexity.ai"],
}

# ── 타임아웃 상수 ─────────────────────────────────────────────────────────────
ELEMENT_WAIT  = 20
STABLE_SECS   = 3
RESPONSE_TIMEOUT = 300
LOGIN_POLL_INTERVAL = 10
LOGIN_TIMEOUT  = 300

# ── JavaScript: Shadow DOM 관통 입력 ──────────────────────────────────────────
_JS_SET_TEXT = """
var text = arguments[0];
function findInput() {
    var rt = document.querySelector('rich-textarea');
    if (rt) {
        var root = rt.shadowRoot || rt;
        var ed = root.querySelector('.ql-editor')
              || root.querySelector('[contenteditable="true"]');
        if (ed) return ed;
    }
    var sels = ['div.ql-editor', '#prompt-textarea',
                'div.ProseMirror[contenteditable="true"]',
                '[contenteditable="true"][aria-label]',
                'div[contenteditable="true"]'];
    for (var s of sels) {
        var el = document.querySelector(s);
        if (el && el.offsetParent !== null) return el;
    }
    return null;
}
var input = findInput();
if (!input) return false;
input.focus();
input.innerHTML = '';
document.execCommand('insertText', false, text);
input.dispatchEvent(new Event('input', {bubbles: true}));
return true;
"""

# JavaScript: 전송 버튼 탐색
_JS_FIND_SEND = """
var sels = ['button[aria-label="Send message"]',
            'button[aria-label="Send Message"]',
            'button[aria-label="Send"]',
            'button[aria-label="보내기"]',
            'button[aria-label="메시지 전송"]',
            'button[aria-label="전송"]',
            'button.send-button',
            'button[data-testid="send-button"]',
            'button[data-testid="send-message-button"]',
            '.trailing-icon-button',
            '.input-area-container button[aria-label]'];
for (var s of sels) {
    var btn = document.querySelector(s);
    if (btn && !btn.disabled) return btn;
}
var buttons = document.querySelectorAll('button[aria-label]');
for (var b of buttons) {
    var label = (b.getAttribute('aria-label') || '').toLowerCase();
    if ((label.includes('send') || label.includes('전송') || label.includes('보내'))
        && !b.disabled && b.offsetParent !== null) {
        return b;
    }
}
var allBtns = document.querySelectorAll('button');
for (var b of allBtns) {
    var cl = (b.className || '').toLowerCase();
    if ((cl.includes('send') || cl.includes('submit'))
        && !b.disabled && b.offsetParent !== null) {
        return b;
    }
}
return null;
"""

# 세션 복사 대상 파일 목록
_SESSION_FILES = [
    "Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm",
    "Login Data", "Login Data-journal", "Login Data-wal", "Login Data-shm",
    "Login Data For Account",
    "Web Data", "Web Data-journal", "Web Data-wal", "Web Data-shm",
    "Preferences", "Secure Preferences",
]


# ── 모듈 레벨 유틸리티 함수 ───────────────────────────────────────────────────

def _isProfileLocked() -> bool:
    """Chrome User Data 디렉토리가 다른 인스턴스에 잠겨있는지 확인"""
    for name in ["lockfile", "SingletonLock"]:
        p = _CHROME_USER_DATA / name
        try:
            if p.exists() or p.is_symlink():
                return True
        except OSError:
            return True
    return False


def _syncCookies(logFn=None) -> None:
    """메인 Chrome 세션을 MultiMind 전용 프로필로 복사 (최초 1회만 실행)"""
    _log = logFn or (lambda m: None)
    srcDefault = _CHROME_USER_DATA / "Default"
    if not srcDefault.exists():
        _log("Chrome Default 프로필을 찾을 수 없음")
        return

    dst = Path(CHROME_PROFILE_DIR) / "Default"

    # 이미 세션 데이터가 있으면 덮어쓰지 않음 (이전 로그인 보존)
    if (dst / "Cookies").exists() or (dst / "Network" / "Cookies").exists():
        _log("기존 MultiMind 세션 유지 (이전 로그인 보존)")
        return

    # 최초 실행: 메인 Chrome에서 세션 파일 복사
    _log("최초 세션 복사 중 (메인 Chrome에서 복사)...")
    dst.mkdir(parents=True, exist_ok=True)
    copied, failedNames = 0, []

    # Local State 파일 복사 (쿠키 암호화 키 포함)
    srcLs = _CHROME_USER_DATA / "Local State"
    dstLs = Path(CHROME_PROFILE_DIR) / "Local State"
    if srcLs.exists():
        try:
            shutil.copy2(str(srcLs), str(dstLs))
            copied += 1
        except OSError:
            failedNames.append("Local State")

    # 세션/쿠키 파일 복사
    for fname in _SESSION_FILES:
        srcFile = srcDefault / fname
        dstFile = dst / fname
        if srcFile.exists():
            try:
                shutil.copy2(str(srcFile), str(dstFile))
                copied += 1
            except OSError:
                failedNames.append(fname)

    # 세션 관련 디렉토리 복사 (Local Storage, Session Storage)
    for dirname in ["Local Storage", "Session Storage"]:
        srcDir = srcDefault / dirname
        dstDir = dst / dirname
        if srcDir.exists():
            if dstDir.exists():
                shutil.rmtree(str(dstDir), ignore_errors=True)
            try:
                shutil.copytree(str(srcDir), str(dstDir))
                copied += 1
            except OSError:
                failedNames.append(dirname)

    # Network 디렉토리 내 쿠키 파일 복사 (최신 Chrome 구조)
    srcNet = srcDefault / "Network"
    dstNet = dst / "Network"
    if srcNet.exists():
        dstNet.mkdir(parents=True, exist_ok=True)
        for fname in ["Cookies", "Cookies-journal", "Cookies-wal", "Cookies-shm"]:
            srcFile = srcNet / fname
            dstFile = dstNet / fname
            if srcFile.exists():
                try:
                    shutil.copy2(str(srcFile), str(dstFile))
                    copied += 1
                except OSError:
                    failedNames.append(f"Network/{fname}")

    msg = f"세션 파일 복사: {copied}개 성공"
    if failedNames:
        msg += f", {len(failedNames)}개 실패 ({', '.join(failedNames)})"
    _log(msg)


def _detectChromeVersion() -> Optional[int]:
    """설치된 Chrome의 메이저 버전 번호를 감지"""
    if sys.platform == "win32":
        # Windows 레지스트리에서 버전 확인
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
        # Linux/macOS: CLI로 버전 확인
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


def _detectEdgeVersion() -> Optional[int]:
    """설치된 Edge의 메이저 버전 번호를 감지"""
    if sys.platform == "win32":
        # Windows 레지스트리에서 Edge 버전 확인
        try:
            result = subprocess.run(
                ["reg", "query",
                 r"HKEY_CURRENT_USER\Software\Microsoft\Edge\BLBeacon",
                 "/v", "version"],
                capture_output=True, text=True, timeout=10,
            )
            m = re.search(r"(\d+)\.", result.stdout)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        # 실행 파일 직접 확인
        for edgePath in [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.exists(edgePath):
                return 1
    elif sys.platform == "darwin":
        # macOS: Edge 실행 파일 확인
        edgePath = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        if os.path.exists(edgePath):
            try:
                result = subprocess.run(
                    [edgePath, "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                m = re.search(r"(\d+)\.", result.stdout)
                if m:
                    return int(m.group(1))
            except Exception:
                return 1
    else:
        # Linux: CLI로 Edge 버전 확인
        for cmd in ["microsoft-edge-stable", "microsoft-edge", "microsoft-edge-dev"]:
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


def _detectBrowser() -> tuple:
    """사용 가능한 브라우저 탐지 (Chrome 우선, Edge 폴백)"""
    chromeVer = _detectChromeVersion()
    if chromeVer:
        return ("chrome", chromeVer)

    edgeVer = _detectEdgeVersion()
    if edgeVer:
        return ("edge", edgeVer)

    return (None, None)


def _parseVersionFromError(errorMsg: str) -> Optional[int]:
    """버전 불일치 에러 메시지에서 실제 Chrome 버전을 추출"""
    m = re.search(r"Current browser version is (\d+)", errorMsg)
    return int(m.group(1)) if m else None


# ── LLM 드라이버 클래스 ──────────────────────────────────────────────────────

class LLMDriver:
    """멀티탭 브라우저 기반 LLM 드라이버 (Chrome/Edge 지원)"""

    def __init__(self, logFn=None):
        self._log = logFn or (lambda m: None)
        self._sendLock = threading.Lock()
        self._baselines: dict[str, str] = {}
        self.driver = None
        self._tabs: dict[str, str] = {}
        # 현재 사용 중인 브라우저 종류 ("chrome" 또는 "edge")
        self._browserType = "chrome"

    # ── 브라우저 초기화 ───────────────────────────────────────────────────────

    def start(self) -> None:
        """브라우저 시작 — Chrome 우선, Edge 폴백"""
        # 필수 패키지 확인
        if _IMPORT_ERROR is not None:
            pkg = _IMPORT_ERROR.replace("No module named ", "").strip("'\"")
            raise MissingDependencyError(
                pkg,
                "pip install selenium undetected-chromedriver pyperclip",
            )

        # 사용 가능한 브라우저 탐지
        browserType, browserVersion = _detectBrowser()

        if browserType == "chrome" and _UC_AVAILABLE:
            # Chrome + undetected-chromedriver: 봇 감지 우회 모드
            self._startChrome(browserVersion)
        elif browserType == "edge":
            # Edge 폴백: 봇 감지 우회 없음
            self._log(
                "Chrome이 설치되어 있지 않습니다.\n"
                "  → Edge 브라우저로 대체 실행합니다.\n"
                "  → 주의: 봇 감지 우회가 비활성화되어 일부 사이트에서 제한될 수 있습니다."
            )
            self._startEdge()
        elif browserType == "chrome" and not _UC_AVAILABLE:
            # Chrome은 있으나 undetected-chromedriver 미설치
            raise MissingDependencyError(
                "undetected-chromedriver",
                "pip install undetected-chromedriver",
            )
        else:
            # 지원 브라우저 없음
            raise BrowserNotFoundError()

        self.driver.set_page_load_timeout(60)

    def _startChrome(self, versionMain: Optional[int]) -> None:
        """Chrome 브라우저 시작 (undetected-chromedriver, 봇 감지 우회)"""
        self._browserType = "chrome"

        if versionMain:
            self._log(f"Chrome 버전 {versionMain} 감지됨")

        # Chrome 옵션 생성 헬퍼
        def _buildOptions(dataDir):
            opts = uc.ChromeOptions()
            opts.add_argument(f"--user-data-dir={dataDir}")
            opts.add_argument("--profile-directory=Default")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--disable-popup-blocking")
            return opts

        # Chrome 실행 시도 헬퍼
        def _tryLaunch(dataDir, ver=versionMain):
            kwargs = dict(options=_buildOptions(dataDir), use_subprocess=True)
            if ver:
                kwargs["version_main"] = ver
            return uc.Chrome(**kwargs)

        profileLocked = _isProfileLocked()

        # 프로필 잠금 없음 → 기존 Chrome 프로필 직접 사용
        if not profileLocked:
            self._log("기존 Chrome 프로필로 시작 중...")
            try:
                self.driver = _tryLaunch(str(_CHROME_USER_DATA))
                self._log("기존 Chrome 프로필 연결 성공 (로그인 세션 유지)")
            except Exception as e:
                self.driver = None
                parsedVer = _parseVersionFromError(str(e))
                if parsedVer and parsedVer != versionMain:
                    try:
                        self.driver = _tryLaunch(str(_CHROME_USER_DATA), parsedVer)
                        versionMain = parsedVer
                        self._log("기존 Chrome 프로필 연결 성공 (로그인 세션 유지)")
                    except Exception:
                        pass

        # 프로필 잠김 또는 기존 프로필 실패 → 별도 프로필 사용
        if self.driver is None:
            if profileLocked:
                self._log(
                    "Chrome이 실행 중 — 별도 프로필로 시작합니다\n"
                    "  → 팁: Chrome을 완전히 종료(시스템 트레이 포함)한 후 실행하면 자동 로그인됩니다."
                )
            else:
                self._log("기존 프로필 사용 실패 — 별도 프로필로 시작합니다")
            Path(CHROME_PROFILE_DIR).mkdir(parents=True, exist_ok=True)
            _syncCookies(logFn=self._log)
            try:
                self.driver = _tryLaunch(CHROME_PROFILE_DIR)
            except Exception as e:
                parsedVer = _parseVersionFromError(str(e))
                if parsedVer and parsedVer != versionMain:
                    try:
                        self.driver = _tryLaunch(CHROME_PROFILE_DIR, parsedVer)
                    except Exception as e2:
                        raise LLMDriverError("chrome", f"Chrome 시작 실패: {e2}")
                else:
                    raise LLMDriverError("chrome", f"Chrome 시작 실패: {e}")

        self._log("Chrome 시작됨 (봇 감지 우회 활성화)")

    def _startEdge(self) -> None:
        """Edge 브라우저 시작 (selenium 표준 WebDriver, 봇 감지 우회 없음)"""
        self._browserType = "edge"

        try:
            from selenium.webdriver import Edge
            from selenium.webdriver.edge.options import Options as EdgeOptions
        except ImportError:
            raise LLMDriverError("edge", "selenium Edge 드라이버를 로드할 수 없습니다.")

        # Edge 옵션 설정 (Chromium 기반으로 Chrome과 동일한 옵션 지원)
        opts = EdgeOptions()
        edgeProfileDir = EDGE_PROFILE_DIR
        Path(edgeProfileDir).mkdir(parents=True, exist_ok=True)
        opts.add_argument(f"--user-data-dir={edgeProfileDir}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-popup-blocking")

        try:
            self.driver = Edge(options=opts)
        except Exception as e:
            raise LLMDriverError("edge", f"Edge 시작 실패: {e}")

        self._log(
            "Edge 브라우저 시작됨\n"
            "  → 각 LLM에 직접 로그인이 필요합니다."
        )

    # ── 탭 관리 ───────────────────────────────────────────────────────────────

    def openTabs(self, llmNames: list) -> None:
        """각 LLM을 새 탭으로 열고 페이지 로드 대기"""
        for i, name in enumerate(llmNames):
            url = LLM_URLS[name]
            if i == 0:
                self.driver.get(url)
            else:
                self.driver.switch_to.new_window("tab")
                self.driver.get(url)
            self._tabs[name] = self.driver.current_window_handle
            # 페이지 로드 완료 대기
            try:
                WebDriverWait(self.driver, 30).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except (TimeoutException, Exception):
                pass
            self._log(f"[{name}] 탭 열림 — {self.driver.title}")
            time.sleep(1.5)

    def switchToTab(self, llmName: str) -> None:
        """지정된 LLM의 탭으로 전환"""
        handle = self._tabs.get(llmName)
        if handle and self.driver.current_window_handle != handle:
            self.driver.switch_to.window(handle)

    # ── 로그인 확인 ───────────────────────────────────────────────────────────

    def _checkLoginCdp(self, llmNames: list) -> Optional[list]:
        """CDP로 탭 전환 없이 로그인 상태 확인, 로그인 필요한 LLM 목록 반환"""
        try:
            targets = self.driver.execute_cdp_cmd("Target.getTargets", {})
        except Exception:
            return None

        pageUrls: dict[str, str] = {}
        for info in targets.get("targetInfos", []):
            if info.get("type") == "page":
                url = info.get("url", "").lower()
                for name, domains in _LLM_DOMAINS.items():
                    if any(d in url for d in domains):
                        pageUrls[name] = url

        pending = []
        for name in llmNames:
            url = pageUrls.get(name, "")
            if not url or any(k in url for k in _LOGIN_URL_KEYWORDS):
                pending.append(name)
        return pending

    def waitForLogin(self, llmNames: list) -> None:
        """로그인 필요한 LLM을 감지하고 모두 로그인될 때까지 대기"""
        deadline = time.time() + LOGIN_TIMEOUT

        # CDP로 로그인 상태 확인 (탭 전환 없이)
        pending = self._checkLoginCdp(llmNames)
        if pending is None:
            pending = [n for n in llmNames if not self._checkLoggedIn(n)]

        if not pending:
            self._log("모든 LLM 로그인 확인 완료")
            self._verifyReady(llmNames)
            return

        self._log(
            f"로그인 필요: {', '.join(pending)}\n"
            "  → 브라우저에서 직접 로그인해주세요. 자동으로 감지합니다.\n"
            "  → 탭이 전환되지 않으니 편하게 로그인하세요."
        )

        lastStatusLog = time.time()
        while time.time() < deadline:
            time.sleep(LOGIN_POLL_INTERVAL)

            # 주기적으로 로그인 상태 재확인
            pending = self._checkLoginCdp(llmNames)
            if pending is None:
                pending = [n for n in llmNames if not self._checkLoggedIn(n)]

            if not pending:
                self._log("모든 LLM 로그인 확인 완료")
                self._verifyReady(llmNames)
                return

            # 30초마다 상태 로그 출력
            now = time.time()
            if now - lastStatusLog >= 30:
                remaining = int(deadline - now)
                self._log(f"로그인 대기 중: {', '.join(pending)} (남은 시간: {remaining}초)")
                lastStatusLog = now

        self._log("일부 LLM이 아직 로그인되지 않았습니다. 계속 진행합니다.")

    def _verifyReady(self, llmNames: list) -> None:
        """각 LLM 탭의 입력창이 준비될 때까지 대기, 미발견 시 새로고침"""
        self._log("각 LLM 입력창 확인 중...")
        for name in llmNames:
            self.switchToTab(name)
            if self._findAny(_INPUT[name], 15):
                self._log(f"[{name}] 입력창 준비 완료")
                continue
            # 입력창 미발견 → 새로고침 후 재시도
            self._log(f"[{name}] 입력창 미발견 — 페이지 새로고침")
            self.driver.refresh()
            try:
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except (TimeoutException, Exception):
                pass
            if self._findAny(_INPUT[name], 20):
                self._log(f"[{name}] 새로고침 후 준비 완료")
            else:
                self._log(f"[{name}] 입력창 없음 — 프롬프트 전송 시 재시도 예정")

    # ── 프롬프트 전송 ─────────────────────────────────────────────────────────

    def sendPrompt(self, llmName: str, prompt: str) -> None:
        """프롬프트 입력 및 전송 (직렬화, CSS → JS 폴백 → 새로고침 재시도)"""
        with self._sendLock:
            self.switchToTab(llmName)
            self._baselines[llmName] = self._getLastText(_RESPONSE[llmName])

            # 최대 2회 시도 (실패 시 JS 폴백 → 새로고침 후 재시도)
            for attempt in range(2):
                try:
                    self._doSend(llmName, prompt)
                    self._log(f"[{llmName}] 전송 완료")
                    return
                except (NoSuchElementException, StaleElementReferenceException):
                    if attempt == 0:
                        self._log(f"[{llmName}] 요소 접근 실패 — JS 폴백 시도")
                        if self._doSendJs(llmName, prompt):
                            self._log(f"[{llmName}] JS 전송 완료")
                            return
                        self._log(f"[{llmName}] JS 폴백 실패 — 새로고침 후 재시도")
                        self.driver.refresh()
                        time.sleep(3)

            raise LLMDriverError(
                llmName,
                "입력창을 찾을 수 없습니다. 해당 LLM 탭에서 로그인되어 있는지 확인하세요."
            )

    def _doSend(self, llmName: str, prompt: str) -> None:
        """CSS 셀렉터 기반 프롬프트 입력 및 전송"""
        inputEl = self._findAny(_INPUT[llmName], ELEMENT_WAIT)

        # Gemini: Shadow DOM 내부 입력창 탐색
        if inputEl is None and llmName == "gemini":
            inputEl = self.driver.execute_script("""
                var rt = document.querySelector('rich-textarea');
                if (!rt) return null;
                var root = rt.shadowRoot || rt;
                return root.querySelector('.ql-editor.textarea')
                    || root.querySelector('.ql-editor')
                    || root.querySelector('[contenteditable="true"]');
            """)

        if inputEl is None:
            raise NoSuchElementException("입력창 미발견")

        # textarea 요소는 send_keys로 직접 입력 (Grok, Perplexity 등)
        tagName = inputEl.tag_name.lower()
        if tagName == "textarea":
            inputEl.click()
            time.sleep(0.3)
            inputEl.clear()
            time.sleep(0.1)
            inputEl.send_keys(prompt)
            time.sleep(0.5)
        else:
            # contenteditable 요소: 전체 선택 → 삭제 → 클립보드 붙여넣기
            inputEl.click()
            time.sleep(0.3)
            inputEl.send_keys(_MOD_KEY, "a")
            time.sleep(0.1)
            inputEl.send_keys(Keys.DELETE)
            time.sleep(0.1)
            pyperclip.copy(prompt)
            inputEl.send_keys(_MOD_KEY, "v")
            time.sleep(0.5)

        # Gemini: CDP Enter 키로 전송 (버튼 클릭이 안정적이지 않음)
        if llmName == "gemini":
            inputEl.click()
            time.sleep(0.2)
            if not self._sendEnterCdp():
                inputEl.send_keys(Keys.RETURN)
            return

        # 전송 버튼 클릭
        sendEl = self._findAny(_SEND[llmName], 10)
        if sendEl is None:
            sendEl = self.driver.execute_script(_JS_FIND_SEND)

        if sendEl:
            from selenium.webdriver.common.action_chains import ActionChains
            try:
                ActionChains(self.driver).move_to_element(sendEl).pause(0.2).click().perform()
            except Exception:
                inputEl.send_keys(Keys.RETURN)
        else:
            inputEl.send_keys(Keys.RETURN)

    def _doSendJs(self, llmName: str, prompt: str) -> bool:
        """JavaScript 폴백 — 텍스트 입력 + 전송"""
        try:
            if not self.driver.execute_script(_JS_SET_TEXT, prompt):
                return False
            time.sleep(1.0)

            # Gemini: CDP Enter 키로 전송
            if llmName == "gemini":
                if self._sendEnterCdp():
                    return True
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).send_keys(Keys.RETURN).perform()
                return True

            from selenium.webdriver.common.action_chains import ActionChains

            # 전송 버튼 클릭 시도
            sendBtn = self.driver.execute_script(_JS_FIND_SEND)
            if sendBtn:
                ActionChains(self.driver).move_to_element(sendBtn).pause(0.3).click().perform()
                return True

            sendEl = self._findAny(_SEND.get(llmName, []), 5)
            if sendEl:
                ActionChains(self.driver).move_to_element(sendEl).pause(0.3).click().perform()
                return True

            # 최후 수단: Enter 키 전송
            ActionChains(self.driver).send_keys(Keys.RETURN).perform()
            return True
        except Exception:
            return False

    # ── 응답 대기 ─────────────────────────────────────────────────────────────

    def waitResponse(self, llmName: str,
                     timeout: int = RESPONSE_TIMEOUT,
                     logFn=None) -> str:
        """응답 텍스트가 안정(STABLE_SECS초 동안 변동 없음)될 때까지 대기 후 반환"""
        _log = logFn or self._log
        selectors = _RESPONSE[llmName]
        baseline = self._baselines.pop(llmName, "")
        deadline = time.time() + timeout

        # 초기 대기 (LLM 응답 생성 시작 시간 확보)
        time.sleep(3.0)

        lastText = ""
        stableCount = 0
        lastLogTime = time.time()
        textEverFound = False

        while time.time() < deadline:
            self.switchToTab(llmName)
            text = self._getLastText(selectors)

            # 베이스라인(이전 응답)과 동일하면 무시
            if text and text == baseline:
                text = ""

            # 최초 응답 감지 로그
            if text and not textEverFound:
                textEverFound = True
                _log(f"[{llmName}] 응답 감지 시작 ({len(text)}자)")

            # 텍스트 안정성 판단 (STABLE_SECS초 연속 동일 → 완료)
            if text and text == lastText:
                stableCount += 1
                if stableCount >= STABLE_SECS:
                    _log(f"[{llmName}] 응답 완료 ({len(text)}자)")
                    return text
            else:
                stableCount = 0
                lastText = text

            # 10초마다 진행 상황 로그
            now = time.time()
            if now - lastLogTime >= 10:
                elapsed = int(now - (deadline - timeout))
                if textEverFound:
                    _log(f"[{llmName}] 응답 생성 중... ({elapsed}초, 현재 {len(lastText)}자)")
                else:
                    _log(f"[{llmName}] 응답 텍스트 미감지 ({elapsed}초) — 셀렉터: {selectors[0]}")
                lastLogTime = now

            time.sleep(1.0)

        # 타임아웃: 부분 응답이 있으면 반환, 없으면 예외
        if lastText:
            _log(f"[{llmName}] 타임아웃 — 부분 응답 반환 ({len(lastText)}자)")
            return lastText
        raise ResponseTimeoutError(llmName, timeout)

    # ── 드라이버 종료 ─────────────────────────────────────────────────────────

    def quit(self) -> None:
        """브라우저 드라이버 종료"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _sendEnterCdp(self) -> bool:
        """Chrome DevTools Protocol로 Enter 키 전송 (OS 레벨 입력)"""
        try:
            self.driver.execute_cdp_cmd('Input.dispatchKeyEvent', {
                'type': 'keyDown',
                'key': 'Enter',
                'code': 'Enter',
                'windowsVirtualKeyCode': 13,
                'nativeVirtualKeyCode': 13,
            })
            time.sleep(0.05)
            self.driver.execute_cdp_cmd('Input.dispatchKeyEvent', {
                'type': 'keyUp',
                'key': 'Enter',
                'code': 'Enter',
                'windowsVirtualKeyCode': 13,
                'nativeVirtualKeyCode': 13,
            })
            return True
        except Exception:
            return False

    def _checkLoggedIn(self, llmName: str) -> bool:
        """해당 LLM 탭이 로그인된 상태인지 URL 및 입력창으로 확인"""
        try:
            self.switchToTab(llmName)
            url = self.driver.current_url.lower()

            # 로그인 페이지 URL이면 미로그인
            if any(k in url for k in _LOGIN_URL_KEYWORDS):
                return False

            # 입력창 존재 여부로 로그인 판단
            for sel in _INPUT[llmName]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    return True
        except Exception:
            pass
        return False

    def _findAny(self, selectors: list, timeout: float):
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

    def _getLastText(self, selectors: list) -> str:
        """가장 마지막 응답 요소의 텍스트를 반환 (CSS 실패 시 JS 폴백)"""
        # CSS 셀렉터로 직접 탐색
        for sel in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    text = els[-1].text.strip()
                    if text:
                        return text
            except (StaleElementReferenceException, Exception):
                continue
        # JS 폴백: 범용 셀렉터로 응답 텍스트 추출
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
