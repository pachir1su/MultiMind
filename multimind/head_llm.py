import json
import queue
import re
from pathlib import Path

from .automation import AutomationHelper
from .browser import BrowserController
from .prompts import REFINEMENT_TEMPLATE, SYNTHESIS_TEMPLATE
from .worker_llm import WorkerLLMHandler


class HeadLLMHandler(WorkerLLMHandler):
    def __init__(self, llm_name: str, asset_dir: Path,
                 automation: AutomationHelper,
                 browser: BrowserController,
                 event_queue: queue.Queue):
        super().__init__(llm_name, asset_dir, automation, browser, event_queue)

    def refine_prompt(self, user_prompt: str, worker_names: list) -> dict:
        """사용자 프롬프트를 각 Worker LLM에 최적화된 형태로 변환.
        Head LLM이 JSON으로 응답; 파싱 실패 시 원본 프롬프트로 폴백."""
        worker_list = ", ".join(worker_names)

        # Head LLM에게 각 Worker별 키를 가진 JSON 응답 요청
        json_template = "{" + ", ".join(
            f'"{name}": "..."' for name in worker_names
        ) + "}"

        prompt = REFINEMENT_TEMPLATE.format(
            user_prompt=user_prompt,
            worker_list=worker_list,
            json_template=json_template,
        )

        self._log(f"[Head: {self.llm_name}] 프롬프트 정제 요청 중...")
        raw_response = self.send_and_receive(prompt)

        # JSON 파싱 시도
        refined = self._parse_json(raw_response, worker_names)
        if refined:
            self._log(f"[Head: {self.llm_name}] 정제된 프롬프트 수신 완료")
            return refined

        # 파싱 실패 시 모든 Worker에 원본 프롬프트 사용
        self._log(
            f"[Head: {self.llm_name}] JSON 파싱 실패 → 원본 프롬프트로 대체"
        )
        return {name: user_prompt for name in worker_names}

    def synthesize(self, user_prompt: str, worker_results: dict) -> str:
        """Worker 응답들을 종합하여 최종 답변 생성"""
        worker_responses_text = "\n\n".join(
            f"[{name.upper()}]\n{response}"
            for name, response in worker_results.items()
            if response and response != "[TIMEOUT]"
        )

        if not worker_responses_text:
            return "Worker LLM에서 유효한 응답을 받지 못했습니다."

        prompt = SYNTHESIS_TEMPLATE.format(
            user_prompt=user_prompt,
            worker_responses=worker_responses_text,
        )

        self._log(f"[Head: {self.llm_name}] 결과 종합 중...")
        result = self.send_and_receive(prompt)
        self._log(f"[Head: {self.llm_name}] 최종 답변 생성 완료")
        return result

    def _parse_json(self, raw: str, worker_names: list) -> dict:
        """LLM 응답에서 JSON 객체를 추출하여 파싱"""
        # 1차 시도: 전체 응답을 JSON으로 직접 파싱
        try:
            data = json.loads(raw.strip())
            if isinstance(data, dict) and any(k in data for k in worker_names):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        # 2차 시도: 첫 번째 { ... } 블록 추출 후 파싱
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        return {}
