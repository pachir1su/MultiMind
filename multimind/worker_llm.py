import queue
from .llm_driver import LLMDriver


class WorkerLLMHandler:
    def __init__(self, llm_name: str, driver: LLMDriver,
                 event_queue: queue.Queue):
        self.llm_name = llm_name
        self.driver = driver
        self.event_queue = event_queue

    def _log(self, message: str) -> None:
        self.event_queue.put({"type": "log", "message": message})

    def send_and_receive(self, prompt: str) -> str:
        """프롬프트 전송 후 응답 텍스트 반환"""
        self._log(f"[{self.llm_name}] 프롬프트 전송 중...")
        self.driver.send_prompt(self.llm_name, prompt)

        self._log(f"[{self.llm_name}] 응답 대기 중...")
        return self.driver.wait_response(self.llm_name, log_fn=self._log)
