import queue
import threading
from pathlib import Path

import pyautogui

from .automation import AutomationHelper
from .browser import BrowserController
from .head_llm import HeadLLMHandler
from .worker_llm import WorkerLLMHandler
from .logger import writeLog
from .exceptions import ImageNotFoundError, ResponseTimeoutError, BrowserWindowNotFoundError

# ── 상수 ──────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path("assets/screenshots")
MAX_PARALLEL_TIMEOUT = 360  # Worker 병렬 실행 전체 최대 대기 시간 (초)

FAILSAFE_MSG = (
    "PyAutoGUI 페일세이프 동작: 실행 중 마우스를 화면 구석으로 이동하지 마세요.\n"
    "프로그램을 다시 실행하고, 실행 중에는 마우스를 움직이지 마세요."
)


class Orchestrator:
    def __init__(self, head: str, workers: list, userPrompt: str,
                 eventQueue: queue.Queue, settings: dict = None):
        # ── 오케스트레이터 초기화 ──────────────────────────────────────────────
        self.head = head
        self.workers = workers
        self.userPrompt = userPrompt
        self.eventQueue = eventQueue
        self.settings = settings or {}

    def run(self) -> None:
        """오케스트레이션 전체 흐름 실행 (백그라운드 스레드에서 호출)"""
        # ── 설정값 로드 ────────────────────────────────────────────────────────
        confidence = self.settings.get("image_confidence", 0.85)
        pollInterval = self.settings.get("poll_interval", 0.5)
        openDelay = self.settings.get("open_delay", 3.0)

        # ── 핵심 객체 초기화 ───────────────────────────────────────────────────
        automation = AutomationHelper(confidence=confidence, pollInterval=pollInterval)
        browser = BrowserController(openDelay=openDelay)

        headHandler = HeadLLMHandler(
            self.head, ASSETS_DIR, automation, browser, self.eventQueue
        )
        workerHandlers = {
            name: WorkerLLMHandler(
                name, ASSETS_DIR, automation, browser, self.eventQueue
            )
            for name in self.workers
        }

        # ── Phase 1: Head LLM 프롬프트 정제 ──────────────────────────────────
        self._put({"type": "phase", "phase": 1,
                   "description": "Head LLM이 프롬프트를 정제 중..."})
        writeLog(f"Phase 1 시작 | Head={self.head} | Workers={self.workers}")

        try:
            refinedPrompts = headHandler.refinePrompt(self.userPrompt, self.workers)
        except pyautogui.FailSafeException:
            self._fatal(FAILSAFE_MSG)
            return
        except (ImageNotFoundError, ResponseTimeoutError, BrowserWindowNotFoundError) as e:
            self._fatal(str(e))
            return
        except Exception as e:
            self._fatal(f"Phase 1 예상치 못한 오류: {e}")
            return

        # ── Phase 2: Worker LLM 병렬 실행 ─────────────────────────────────────
        self._put({"type": "phase", "phase": 2,
                   "description": "Worker LLM들이 응답 생성 중..."})
        writeLog("Phase 2 시작 | Worker 병렬 실행")

        workerResults = self._runWorkersParallel(workerHandlers, refinedPrompts)

        if not any(v and v != "[TIMEOUT]" for v in workerResults.values()):
            self._fatal("모든 Worker LLM에서 유효한 응답을 받지 못했습니다.")
            return

        # ── Phase 3: Head LLM 결과 종합 ───────────────────────────────────────
        self._put({"type": "phase", "phase": 3,
                   "description": "Head LLM이 결과를 종합 중..."})
        writeLog("Phase 3 시작 | 결과 종합")

        try:
            finalAnswer = headHandler.synthesize(self.userPrompt, workerResults)
        except pyautogui.FailSafeException:
            self._fatal(FAILSAFE_MSG)
            return
        except (ImageNotFoundError, ResponseTimeoutError, BrowserWindowNotFoundError) as e:
            self._fatal(str(e))
            return
        except Exception as e:
            self._fatal(f"Phase 3 예상치 못한 오류: {e}")
            return

        # ── 완료 처리 ──────────────────────────────────────────────────────────
        writeLog("오케스트레이션 완료")
        self._put({"type": "final_result", "text": finalAnswer})

    def _runWorkersParallel(self, handlers: dict, prompts: dict) -> dict:
        """모든 Worker에 병렬로 프롬프트 전송 후 결과 수집"""
        # ── 스레드 생성 및 시작 ────────────────────────────────────────────────
        results = {}
        resultsLock = threading.Lock()
        threads = []

        for name, handler in handlers.items():
            prompt = prompts.get(name, self.userPrompt)
            t = threading.Thread(
                target=self._workerTask,
                args=(name, handler, prompt, results, resultsLock),
                daemon=True,
            )
            threads.append(t)

        for t in threads:
            t.start()

        # ── 전체 완료 대기 ─────────────────────────────────────────────────────
        for t in threads:
            t.join(timeout=MAX_PARALLEL_TIMEOUT)

        return results

    def _workerTask(self, name: str, handler: WorkerLLMHandler,
                    prompt: str, results: dict, resultsLock: threading.Lock) -> None:
        """단일 Worker 스레드 실행 로직"""
        try:
            response = handler.sendAndReceive(prompt)
            with resultsLock:
                results[name] = response
            self._put({"type": "worker_done", "llm": name, "result": response})
            writeLog(f"Worker 완료: {name}")

        except pyautogui.FailSafeException:
            # 페일세이프는 Worker 오류로 처리 (다른 Worker는 계속 실행)
            with resultsLock:
                results[name] = ""
            self._put({"type": "worker_error", "llm": name, "error": FAILSAFE_MSG})
            writeLog(f"Worker 페일세이프: {name}")

        except ResponseTimeoutError as e:
            with resultsLock:
                results[name] = "[TIMEOUT]"
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            writeLog(f"Worker 타임아웃: {name}")

        except (ImageNotFoundError, BrowserWindowNotFoundError) as e:
            with resultsLock:
                results[name] = ""
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            writeLog(f"Worker 오류: {name} | {e}")

        except Exception as e:
            with resultsLock:
                results[name] = ""
            self._put({"type": "worker_error", "llm": name, "error": f"예상치 못한 오류: {e}"})
            writeLog(f"Worker 예외: {name} | {e}")

    def _put(self, event: dict) -> None:
        """이벤트 큐에 메시지 전송"""
        self.eventQueue.put(event)

    def _fatal(self, message: str) -> None:
        """치명적 오류 처리 — 로그 기록 후 GUI에 알림"""
        writeLog(f"치명적 오류: {message}")
        self._put({"type": "fatal_error", "error": message})
