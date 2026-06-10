# Worker LLM 핸들러 모듈 — 단일 LLM에 프롬프트 전송 및 응답 수신

import queue
from .llm_driver import LLMDriver


class WorkerLLMHandler:
    """Worker LLM 프롬프트 전송/응답 수신 핸들러"""

    def __init__(self, llmName: str, driver: LLMDriver,
                 eventQueue: queue.Queue):
        self.llmName = llmName
        self.driver = driver
        self.eventQueue = eventQueue

    def _log(self, message: str) -> None:
        """UI 이벤트 큐에 로그 메시지 전송"""
        self.eventQueue.put({"type": "log", "message": message})

    def sendAndReceive(self, prompt: str) -> str:
        """프롬프트 전송 후 응답 텍스트 반환"""
        self._log(f"[{self.llmName}] 프롬프트 전송 중...")
        self.driver.sendPrompt(self.llmName, prompt)

        self._log(f"[{self.llmName}] 응답 대기 중...")
        return self.driver.waitResponse(self.llmName, logFn=self._log)
