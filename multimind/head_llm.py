import json
import queue
import re
from pathlib import Path

from .automation import AutomationHelper
from .browser import BrowserController
from .prompts import REFINEMENT_TEMPLATE, SYNTHESIS_TEMPLATE
from .worker_llm import WorkerLLMHandler


class HeadLLMHandler(WorkerLLMHandler):
    def __init__(self, llmName: str, assetDir: Path,
                 automation: AutomationHelper,
                 browser: BrowserController,
                 eventQueue: queue.Queue):
        # ── 부모 클래스 초기화 (send_and_receive 등 공통 기능 상속) ───────────
        super().__init__(llmName, assetDir, automation, browser, eventQueue)

    def refinePrompt(self, userPrompt: str, workerNames: list) -> dict:
        """사용자 프롬프트를 각 Worker LLM에 최적화된 형태로 변환.
        Head LLM이 JSON으로 응답; 파싱 실패 시 원본 프롬프트로 폴백."""
        # ── 정제 프롬프트 구성 ─────────────────────────────────────────────────
        workerList = ", ".join(workerNames)
        jsonTemplate = "{" + ", ".join(
            f'"{name}": "..."' for name in workerNames
        ) + "}"

        prompt = REFINEMENT_TEMPLATE.format(
            user_prompt=userPrompt,
            worker_list=workerList,
            json_template=jsonTemplate,
        )

        # ── Head LLM에 전송 및 응답 수신 ─────────────────────────────────────
        self._log(f"[Head: {self.llmName}] 프롬프트 정제 요청 중...")
        rawResponse = self.sendAndReceive(prompt)

        # ── JSON 파싱 시도 ─────────────────────────────────────────────────────
        refined = self._parseJson(rawResponse, workerNames)
        if refined:
            self._log(f"[Head: {self.llmName}] 정제된 프롬프트 수신 완료")
            return refined

        # 파싱 실패 시 모든 Worker에 원본 프롬프트 사용 (graceful degradation)
        self._log(f"[Head: {self.llmName}] JSON 파싱 실패 → 원본 프롬프트로 대체")
        return {name: userPrompt for name in workerNames}

    def synthesize(self, userPrompt: str, workerResults: dict) -> str:
        """Worker 응답들을 종합하여 최종 답변 생성"""
        # ── 유효한 Worker 응답만 합산 ─────────────────────────────────────────
        workerResponsesText = "\n\n".join(
            f"[{name.upper()}]\n{response}"
            for name, response in workerResults.items()
            if response and response != "[TIMEOUT]"
        )

        if not workerResponsesText:
            return "Worker LLM에서 유효한 응답을 받지 못했습니다."

        # ── 종합 프롬프트 구성 및 전송 ────────────────────────────────────────
        prompt = SYNTHESIS_TEMPLATE.format(
            user_prompt=userPrompt,
            worker_responses=workerResponsesText,
        )

        self._log(f"[Head: {self.llmName}] 결과 종합 중...")
        result = self.sendAndReceive(prompt)
        self._log(f"[Head: {self.llmName}] 최종 답변 생성 완료")
        return result

    def _parseJson(self, raw: str, workerNames: list) -> dict:
        """LLM 응답에서 JSON 객체를 추출하여 파싱 (2단계 폴백)"""
        # ── 1차: 전체 응답을 JSON으로 직접 파싱 ─────────────────────────────
        try:
            data = json.loads(raw.strip())
            if isinstance(data, dict) and any(k in data for k in workerNames):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

        # ── 2차: 정규식으로 { ... } 블록 추출 후 파싱 ───────────────────────
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        return {}
