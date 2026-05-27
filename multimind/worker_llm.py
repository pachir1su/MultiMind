import time
import queue
from pathlib import Path

import pyautogui
import pyperclip

from .automation import AutomationHelper
from .browser import BrowserController
from .exceptions import ImageNotFoundError, ResponseTimeoutError


class WorkerLLMHandler:
    def __init__(self, llm_name: str, asset_dir: Path,
                 automation: AutomationHelper,
                 browser: BrowserController,
                 event_queue: queue.Queue):
        self.llm_name = llm_name
        self.asset_dir = asset_dir / llm_name
        self.automation = automation
        self.browser = browser
        self.event_queue = event_queue

    def _img(self, filename: str) -> str:
        return str(self.asset_dir / filename)

    def _log(self, message: str) -> None:
        self.event_queue.put({"type": "log", "message": message})

    def send_and_receive(self, prompt: str) -> str:
        """프롬프트 전송 → 응답 대기 → 복사 후 텍스트 반환"""
        lock = self.automation.get_lock()

        # 입력 ~ 전송 단계: UI 조작 락 보유 (다른 Worker와 직렬화)
        with lock:
            self._log(f"[{self.llm_name}] 탭 포커스 중...")
            self.browser.focus_tab(self.llm_name)

            self._log(f"[{self.llm_name}] 입력창 클릭 중...")
            self.automation.click_image(
                self._img("input_area.png"), self.llm_name,
                log_fn=self._log
            )
            # 기존 텍스트 초기화
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("delete")
            time.sleep(0.1)

            self._log(f"[{self.llm_name}] 프롬프트 입력 중...")
            self.automation.paste_text(prompt)
            time.sleep(0.3)

            self._log(f"[{self.llm_name}] 전송 중...")
            self.automation.click_image(
                self._img("send_button_active.png"), self.llm_name,
                log_fn=self._log
            )

        # 전송 확인 및 응답 대기: 락 없이 독립 폴링 (진짜 병렬 구간)
        self._log(f"[{self.llm_name}] 응답 생성 중...")
        self.automation.wait_for_image_gone(
            self._img("send_button_active.png"), self.llm_name, timeout=15
        )
        self.automation.wait_for_image(
            self._img("send_button_active.png"), self.llm_name, timeout=300,
            log_fn=self._log
        )

        # 복사 단계: 다시 락 보유
        with lock:
            self._log(f"[{self.llm_name}] 응답 복사 중...")
            self.browser.focus_tab(self.llm_name)
            try:
                # LLM 제공 복사 버튼 사용 (가장 안정적)
                self.automation.click_image(
                    self._img("copy_button.png"), self.llm_name, timeout=10
                )
                time.sleep(0.3)
                result = pyperclip.paste()
            except ImageNotFoundError:
                # 복사 버튼을 못 찾은 경우 전체 선택→복사 폴백
                result = self.automation.copy_from_clipboard()

        self._log(f"[{self.llm_name}] 응답 수신 완료")
        return result
