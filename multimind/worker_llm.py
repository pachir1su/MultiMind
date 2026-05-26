import time
import queue
from pathlib import Path

import pyautogui
import pyperclip

from .automation import AutomationHelper
from .browser import BrowserController
from .exceptions import ImageNotFoundError, ResponseTimeoutError


class WorkerLLMHandler:
    def __init__(self, llmName: str, assetDir: Path,
                 automation: AutomationHelper,
                 browser: BrowserController,
                 eventQueue: queue.Queue):
        # ── 인스턴스 초기화 ────────────────────────────────────────────────────
        self.llmName = llmName
        self.assetDir = assetDir / llmName
        self.automation = automation
        self.browser = browser
        self.eventQueue = eventQueue

    def _img(self, filename: str) -> str:
        """이미지 파일 경로 반환"""
        return str(self.assetDir / filename)

    def _log(self, message: str) -> None:
        """이벤트 큐에 로그 메시지 전송"""
        self.eventQueue.put({"type": "log", "message": message})

    def sendAndReceive(self, prompt: str) -> str:
        """프롬프트 전송 → 응답 대기 → 복사 후 텍스트 반환"""
        lock = self.automation.getLock()

        # ── 입력 단계: UI 조작 락 보유 (다른 Worker와 직렬화) ─────────────────
        with lock:
            self._log(f"[{self.llmName}] 탭 포커스 중...")
            self.browser.focusTab(self.llmName)

            self._log(f"[{self.llmName}] 입력창 클릭 중...")
            self.automation.clickImage(self._img("input_area.png"), self.llmName)

            # 기존 텍스트 초기화
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("delete")
            time.sleep(0.1)

            self._log(f"[{self.llmName}] 프롬프트 입력 중...")
            self.automation.pasteText(prompt)
            time.sleep(0.3)

            self._log(f"[{self.llmName}] 전송 중...")
            self.automation.clickImage(self._img("send_button_active.png"), self.llmName)

        # ── 응답 대기 단계: 락 없이 독립 폴링 (병렬 실행의 실질적 구간) ───────
        self._log(f"[{self.llmName}] 응답 생성 중...")
        self.automation.waitForImageGone(
            self._img("send_button_active.png"), self.llmName, timeout=15
        )
        self.automation.waitForImage(
            self._img("send_button_active.png"), self.llmName, timeout=300
        )

        # ── 복사 단계: 다시 락 보유 ───────────────────────────────────────────
        with lock:
            self._log(f"[{self.llmName}] 응답 복사 중...")
            self.browser.focusTab(self.llmName)
            try:
                # LLM 제공 복사 버튼 우선 사용 (가장 정확한 방법)
                self.automation.clickImage(
                    self._img("copy_button.png"), self.llmName, timeout=10
                )
                time.sleep(0.3)
                result = pyperclip.paste()
            except ImageNotFoundError:
                # 복사 버튼을 못 찾은 경우 전체 선택→복사 폴백
                result = self.automation.copyFromClipboard()

        self._log(f"[{self.llmName}] 응답 수신 완료")
        return result
