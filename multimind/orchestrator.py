import queue
import threading
import time
from pathlib import Path

from .automation import AutomationHelper
from .browser import BrowserController
from .config import ConfigManager
from .head_llm import HeadLLMHandler
from .worker_llm import WorkerLLMHandler
from .logger import write_log
from .exceptions import ImageNotFoundError, ResponseTimeoutError, BrowserWindowNotFoundError

ASSETS_DIR = Path("assets/screenshots")
MAX_PARALLEL_TIMEOUT = 360  # 전체 Worker 병렬 실행 최대 대기 시간 (초)


class Orchestrator:
    def __init__(self, head: str, workers: list, user_prompt: str,
                 event_queue: queue.Queue, settings: dict = None):
        self.head = head
        self.workers = workers
        self.user_prompt = user_prompt
        self.event_queue = event_queue
        self.settings = settings or {}

    def run(self) -> None:
        """오케스트레이션 전체 흐름 실행 (백그라운드 스레드에서 호출)"""
        confidence = self.settings.get("image_confidence", 0.85)
        poll_interval = self.settings.get("poll_interval", 0.5)
        open_delay = self.settings.get("open_delay", 3.0)

        automation = AutomationHelper(confidence=confidence, poll_interval=poll_interval)
        browser = BrowserController(open_delay=open_delay)

        head_handler = HeadLLMHandler(
            self.head, ASSETS_DIR, automation, browser, self.event_queue
        )
        worker_handlers = {
            name: WorkerLLMHandler(
                name, ASSETS_DIR, automation, browser, self.event_queue
            )
            for name in self.workers
        }

        # ── Phase 1: Head LLM 프롬프트 정제 ──────────────────────────────────
        self._put({"type": "phase", "phase": 1,
                   "description": "Head LLM이 프롬프트를 정제 중..."})
        write_log(f"Phase 1 시작 | Head={self.head} | Workers={self.workers}")

        try:
            refined_prompts = head_handler.refine_prompt(
                self.user_prompt, self.workers
            )
        except (ImageNotFoundError, ResponseTimeoutError,
                BrowserWindowNotFoundError) as e:
            self._fatal(str(e))
            return
        except Exception as e:
            self._fatal(f"예상치 못한 오류: {e}")
            return

        # ── Phase 2: Worker LLM 병렬 실행 ────────────────────────────────────
        self._put({"type": "phase", "phase": 2,
                   "description": "Worker LLM들이 응답 생성 중..."})
        write_log("Phase 2 시작 | Worker 병렬 실행")

        worker_results = self._run_workers_parallel(
            worker_handlers, refined_prompts
        )

        if not any(v and v != "[TIMEOUT]" for v in worker_results.values()):
            self._fatal("모든 Worker LLM에서 유효한 응답을 받지 못했습니다.")
            return

        # ── Phase 3: Head LLM 결과 종합 ──────────────────────────────────────
        self._put({"type": "phase", "phase": 3,
                   "description": "Head LLM이 결과를 종합 중..."})
        write_log("Phase 3 시작 | 결과 종합")

        try:
            final_answer = head_handler.synthesize(
                self.user_prompt, worker_results
            )
        except (ImageNotFoundError, ResponseTimeoutError,
                BrowserWindowNotFoundError) as e:
            self._fatal(str(e))
            return
        except Exception as e:
            self._fatal(f"종합 중 오류: {e}")
            return

        write_log("오케스트레이션 완료")
        self._put({"type": "final_result", "text": final_answer})

    def _run_workers_parallel(self, handlers: dict, prompts: dict) -> dict:
        """모든 Worker에 병렬로 프롬프트 전송 후 결과 수집"""
        results = {}
        results_lock = threading.Lock()
        threads = []

        for name, handler in handlers.items():
            prompt = prompts.get(name, self.user_prompt)
            t = threading.Thread(
                target=self._worker_task,
                args=(name, handler, prompt, results, results_lock),
                daemon=True,
            )
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=MAX_PARALLEL_TIMEOUT)

        return results

    def _worker_task(self, name: str, handler: WorkerLLMHandler,
                     prompt: str, results: dict, results_lock: threading.Lock) -> None:
        """단일 Worker 스레드가 실행하는 작업"""
        try:
            response = handler.send_and_receive(prompt)
            with results_lock:
                results[name] = response
            self._put({"type": "worker_done", "llm": name, "result": response})
            write_log(f"Worker 완료: {name}")
        except ResponseTimeoutError as e:
            with results_lock:
                results[name] = "[TIMEOUT]"
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            write_log(f"Worker 타임아웃: {name}")
        except Exception as e:
            with results_lock:
                results[name] = ""
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            write_log(f"Worker 오류: {name} | {e}")

    def _put(self, event: dict) -> None:
        self.event_queue.put(event)

    def _fatal(self, message: str) -> None:
        write_log(f"치명적 오류: {message}")
        self._put({"type": "fatal_error", "error": message})
