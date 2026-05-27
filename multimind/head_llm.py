import json
import queue
import re

from .llm_driver import LLMDriver
from .prompts import REFINEMENT_TEMPLATE, SYNTHESIS_TEMPLATE
from .worker_llm import WorkerLLMHandler


class HeadLLMHandler(WorkerLLMHandler):
    def __init__(self, llm_name: str, driver: LLMDriver,
                 event_queue: queue.Queue):
        super().__init__(llm_name, driver, event_queue)

    def refine_prompt(self, user_prompt: str, worker_names: list) -> dict:
        """사용자 프롬프트를 각 Worker LLM에 최적화된 형태로 변환."""
        worker_list = ", ".join(worker_names)
        json_template = "{" + ", ".join(
            f'"{n}": "..."' for n in worker_names
        ) + "}"

        prompt = REFINEMENT_TEMPLATE.format(
            user_prompt=user_prompt,
            worker_list=worker_list,
            json_template=json_template,
        )

        self._log(f"[Head: {self.llm_name}] 프롬프트 정제 요청 중...")
        raw = self.send_and_receive(prompt)

        refined = self._parse_json(raw, worker_names)
        if refined:
            self._log(f"[Head: {self.llm_name}] 정제 완료")
            return refined

        self._log(f"[Head: {self.llm_name}] JSON 파싱 실패 → 원본 프롬프트 사용")
        return {name: user_prompt for name in worker_names}

    def synthesize(self, user_prompt: str, worker_results: dict) -> str:
        """Worker 응답들을 종합하여 최종 답변 생성"""
        responses_text = "\n\n".join(
            f"[{name.upper()}]\n{resp}"
            for name, resp in worker_results.items()
            if resp and resp != "[TIMEOUT]"
        )
        if not responses_text:
            return "Worker LLM에서 유효한 응답을 받지 못했습니다."

        prompt = SYNTHESIS_TEMPLATE.format(
            user_prompt=user_prompt,
            worker_responses=responses_text,
        )

        self._log(f"[Head: {self.llm_name}] 결과 종합 중...")
        result = self.send_and_receive(prompt)
        self._log(f"[Head: {self.llm_name}] 최종 답변 생성 완료")
        return result

    def _parse_json(self, raw: str, worker_names: list) -> dict:
        """LLM 응답에서 JSON 객체를 추출하여 파싱"""
        try:
            data = json.loads(raw.strip())
            if isinstance(data, dict) and any(k in data for k in worker_names):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and any(k in data for k in worker_names):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        return {}
