# 오케스트레이션 모듈 — 3단계 LLM 파이프라인 제어
# Phase 0: 브라우저 시작 → Phase 1: 프롬프트 정제 → Phase 2: Worker 병렬 실행 → Phase 3: 결과 종합

import queue
import threading
import time

from .llm_driver import LLMDriver
from .head_llm import HeadLLMHandler
from .worker_llm import WorkerLLMHandler
from .logger import writeLog, SessionLogger
from .exceptions import LLMDriverError, MissingDependencyError, ResponseTimeoutError

# Worker 전체 타임아웃 (초)
MAX_WORKER_TIMEOUT = 360


class Orchestrator:
    """멀티 LLM 오케스트레이터 — 정제/병렬실행/종합 3단계 파이프라인"""

    def __init__(self, head: str, workers: list, userPrompt: str,
                 eventQueue: queue.Queue, settings: dict = None,
                 stopEvent: threading.Event = None):
        self.head = head
        self.workers = workers
        self.userPrompt = userPrompt
        self.eventQueue = eventQueue
        self.settings = settings or {}
        self.sessionLog = SessionLogger(head, workers, userPrompt)
        # 사용자 중단 이벤트 (UI 중단 버튼에서 설정됨)
        self.stopEvent = stopEvent or threading.Event()

    def run(self) -> None:
        """오케스트레이션 전체 흐름 실행 (백그라운드 스레드에서 호출)"""
        allLlms = [self.head] + [w for w in self.workers if w != self.head]
        driver = LLMDriver(
            logFn=lambda m: self._put({"type": "log", "message": m})
        )

        try:
            # ── Phase 0: 브라우저 시작 및 탭 열기 ────────────────────────────
            self._put({"type": "phase", "phase": 0,
                       "description": "브라우저 시작 중..."})
            try:
                driver.start()
                driver.openTabs(allLlms)
                driver.waitForLogin(allLlms)
            except MissingDependencyError as e:
                self._fatal(str(e)); return
            except LLMDriverError as e:
                self._fatal(str(e)); return
            except Exception as e:
                self._fatal(f"브라우저 시작 실패: {e}"); return

            # 사용자 중단 확인
            if self.stopEvent.is_set():
                self._put({"type": "stopped"}); return

            headHandler = HeadLLMHandler(self.head, driver, self.eventQueue)
            workerHandlers = {
                name: WorkerLLMHandler(name, driver, self.eventQueue)
                for name in self.workers
            }

            # ── Phase 1: Head LLM 프롬프트 정제 ─────────────────────────────
            self._put({"type": "phase", "phase": 1,
                       "description": "Head LLM이 프롬프트를 정제 중..."})
            writeLog(f"Phase 1 시작 | Head={self.head} | Workers={self.workers}")

            try:
                refinedPrompts = headHandler.refinePrompt(
                    self.userPrompt, self.workers
                )
            except (LLMDriverError, ResponseTimeoutError) as e:
                self._fatal(str(e)); return
            except Exception as e:
                self._fatal(f"예상치 못한 오류: {e}"); return

            self.sessionLog.logRefinement(
                headHandler.lastSentPrompt,
                headHandler.lastRawResponse,
                refinedPrompts,
            )

            # 사용자 중단 확인
            if self.stopEvent.is_set():
                self._put({"type": "stopped"}); return

            # ── Phase 2: Worker LLM 병렬 실행 ───────────────────────────────
            self._put({"type": "phase", "phase": 2,
                       "description": "Worker LLM들이 응답 생성 중..."})
            writeLog("Phase 2 시작 | Worker 병렬 실행")

            workerResults = self._runWorkersParallel(
                workerHandlers, refinedPrompts
            )

            # 유효한 응답이 하나도 없으면 종료
            if not any(v and v != "[TIMEOUT]" for v in workerResults.values()):
                self._fatal("모든 Worker LLM에서 유효한 응답을 받지 못했습니다.")
                return

            # 사용자 중단 확인
            if self.stopEvent.is_set():
                self._put({"type": "stopped"}); return

            # ── Phase 3: Head LLM 결과 종합 ─────────────────────────────────
            self._put({"type": "phase", "phase": 3,
                       "description": "Head LLM이 결과를 종합 중..."})
            writeLog("Phase 3 시작 | 결과 종합")

            try:
                finalAnswer = headHandler.synthesize(
                    self.userPrompt, workerResults
                )
            except (LLMDriverError, ResponseTimeoutError) as e:
                self._fatal(str(e)); return
            except Exception as e:
                self._fatal(f"종합 중 오류: {e}"); return

            self.sessionLog.logSynthesis(
                headHandler.lastSentPrompt,
                finalAnswer,
            )

            writeLog("오케스트레이션 완료")
            self._put({"type": "final_result", "text": finalAnswer})

        finally:
            # 세션 로그 저장 및 드라이버 종료
            logPath = self.sessionLog.save()
            if logPath:
                writeLog(f"세션 로그 저장: {logPath}")
                self._put({"type": "log",
                           "message": f"세션 로그 저장됨: {logPath}"})
            driver.quit()

    def _runWorkersParallel(self, handlers: dict, prompts: dict) -> dict:
        """모든 Worker LLM을 병렬 스레드로 실행하고 결과 수집"""
        results = {}
        resultsLock = threading.Lock()
        threads = []

        # 각 Worker별 스레드 생성
        for name, handler in handlers.items():
            prompt = prompts.get(name, self.userPrompt)
            t = threading.Thread(
                target=self._workerTask,
                args=(name, handler, prompt, results, resultsLock),
                daemon=True,
            )
            threads.append(t)

        # 모든 스레드 시작 후 타임아웃까지 대기
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=MAX_WORKER_TIMEOUT)

        # 타임아웃된 Worker 처리
        for name, t in zip(handlers.keys(), threads):
            if t.is_alive():
                with resultsLock:
                    results.setdefault(name, "[TIMEOUT]")
                self._put({"type": "worker_error", "llm": name,
                           "error": f"전체 타임아웃 ({MAX_WORKER_TIMEOUT}s)"})
                writeLog(f"Worker 전체 타임아웃: {name}")
                self.sessionLog.logWorker(
                    name, prompts.get(name, self.userPrompt),
                    error=f"전체 타임아웃 ({MAX_WORKER_TIMEOUT}s)",
                )

        return results

    def _workerTask(self, name: str, handler: WorkerLLMHandler,
                    prompt: str, results: dict,
                    resultsLock: threading.Lock) -> None:
        """단일 Worker LLM 실행 태스크 (병렬 스레드에서 호출)"""
        startTime = time.time()
        try:
            response = handler.sendAndReceive(prompt)
            duration = time.time() - startTime
            with resultsLock:
                results[name] = response
            self.sessionLog.logWorker(name, prompt, response=response,
                                      duration=duration)
            self._put({"type": "worker_done", "llm": name, "result": response})
            writeLog(f"Worker 완료: {name}")
        except ResponseTimeoutError as e:
            duration = time.time() - startTime
            with resultsLock:
                results[name] = "[TIMEOUT]"
            self.sessionLog.logWorker(name, prompt, error=str(e),
                                      duration=duration)
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            writeLog(f"Worker 타임아웃: {name}")
        except Exception as e:
            duration = time.time() - startTime
            with resultsLock:
                results[name] = ""
            self.sessionLog.logWorker(name, prompt, error=str(e),
                                      duration=duration)
            self._put({"type": "worker_error", "llm": name, "error": str(e)})
            writeLog(f"Worker 오류: {name} | {e}")

    def _put(self, event: dict) -> None:
        """이벤트 큐에 UI 업데이트 이벤트 전송"""
        self.eventQueue.put(event)

    def _fatal(self, message: str) -> None:
        """치명적 오류 처리 — 로그 기록 및 UI에 오류 이벤트 전송"""
        writeLog(f"치명적 오류: {message}")
        self.sessionLog.logError(message)
        self._put({"type": "fatal_error", "error": message})
