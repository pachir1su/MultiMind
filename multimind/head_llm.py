# Head LLM 핸들러 모듈 — 프롬프트 정제(Phase 1) 및 결과 종합(Phase 3)

import json
import queue
import re

from .llm_driver import LLMDriver
from .prompts import REFINEMENT_TEMPLATE, SYNTHESIS_TEMPLATE
from .worker_llm import WorkerLLMHandler


class HeadLLMHandler(WorkerLLMHandler):
    """Head LLM 전용 핸들러 — 정제 및 종합 기능 포함"""

    def __init__(self, llmName: str, driver: LLMDriver,
                 eventQueue: queue.Queue):
        super().__init__(llmName, driver, eventQueue)
        # 최근 전송/수신 데이터 (디버깅 및 세션 로깅용)
        self.lastSentPrompt = ""
        self.lastRawResponse = ""

    def refinePrompt(self, userPrompt: str, workerNames: list) -> dict:
        """사용자 프롬프트를 각 Worker LLM에 최적화된 형태로 변환"""
        workerList = ", ".join(workerNames)
        jsonTemplate = "{" + ", ".join(
            f'"{n}": "..."' for n in workerNames
        ) + "}"

        # 정제 템플릿에 파라미터 삽입
        prompt = REFINEMENT_TEMPLATE.format(
            user_prompt=userPrompt,
            worker_list=workerList,
            json_template=jsonTemplate,
        )

        self._log(f"[Head: {self.llmName}] 프롬프트 정제 요청 중...")
        self.lastSentPrompt = prompt
        raw = self.sendAndReceive(prompt)
        self.lastRawResponse = raw

        # JSON 파싱 시도, 실패 시 원본 프롬프트 그대로 사용
        refined = self._parseJson(raw, workerNames)
        if refined:
            self._log(f"[Head: {self.llmName}] 정제 완료")
            return refined

        self._log(f"[Head: {self.llmName}] JSON 파싱 실패 → 원본 프롬프트 사용")
        return {name: userPrompt for name in workerNames}

    def synthesize(self, userPrompt: str, workerResults: dict) -> str:
        """Worker 응답들을 종합하여 최종 답변 생성"""
        # 유효한 Worker 응답만 결합
        responsesText = "\n\n".join(
            f"[{name.upper()}]\n{resp}"
            for name, resp in workerResults.items()
            if resp and resp != "[TIMEOUT]"
        )
        if not responsesText:
            return "Worker LLM에서 유효한 응답을 받지 못했습니다."

        # 종합 템플릿에 파라미터 삽입
        prompt = SYNTHESIS_TEMPLATE.format(
            user_prompt=userPrompt,
            worker_responses=responsesText,
        )

        self._log(f"[Head: {self.llmName}] 결과 종합 중...")
        self.lastSentPrompt = prompt
        result = self.sendAndReceive(prompt)
        self.lastRawResponse = result
        self._log(f"[Head: {self.llmName}] 최종 답변 생성 완료")
        return result

    def _parseJson(self, raw: str, workerNames: list) -> dict:
        """LLM 응답 텍스트에서 JSON 객체를 추출하여 파싱"""
        # 전체 텍스트가 유효한 JSON인지 시도
        try:
            data = json.loads(raw.strip())
            if isinstance(data, dict) and any(k in data for k in workerNames):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        # 텍스트 내에서 JSON 블록 추출 시도
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict) and any(k in data for k in workerNames):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        return {}
