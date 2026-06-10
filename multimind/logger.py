# 세션 로깅 모듈 — 파일 로그 기록 및 세션별 JSON/TXT 보고서 생성

import json
import os
from datetime import datetime
from pathlib import Path

# 전역 로그 파일 경로
LOG_FILE = "multimind.log"
# 세션 로그 저장 디렉토리
LOG_DIR = Path("logs")


def writeLog(event: str) -> None:
    """이벤트 메시지를 타임스탬프와 함께 전역 로그 파일에 기록"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {event}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


class SessionLogger:
    """한 오케스트레이션 세션의 프롬프트/응답/오류를 모두 기록하는 클래스"""

    def __init__(self, head: str, workers: list, userPrompt: str):
        # 세션 기본 정보 초기화
        self.startTime = datetime.now()
        self.sessionId = self.startTime.strftime("%Y%m%d_%H%M%S")
        self.head = head
        self.workers = workers
        self.userPrompt = userPrompt

        # Phase 1 정제 데이터
        self.refinementPrompt = ""
        self.headRawRefinement = ""
        self.refinedPrompts: dict = {}

        # Phase 2 Worker 응답 데이터
        self.workerData: dict = {}

        # Phase 3 종합 데이터
        self.synthesisPrompt = ""
        self.finalAnswer = ""

        # 종료 및 오류 정보
        self.endTime = None
        self.error = None

    def logRefinement(self, promptToHead: str, rawResponse: str,
                      refinedPrompts: dict) -> None:
        """Phase 1 정제 결과 기록"""
        self.refinementPrompt = promptToHead
        self.headRawRefinement = rawResponse
        self.refinedPrompts = dict(refinedPrompts)

    def logWorker(self, name: str, prompt: str, response: str = None,
                  error: str = None, duration: float = None) -> None:
        """Phase 2 개별 Worker 응답/오류 기록"""
        self.workerData[name] = {
            "prompt": prompt,
            "response": response,
            "error": error,
            "duration_seconds": round(duration, 1) if duration is not None else None,
        }

    def logSynthesis(self, promptToHead: str, finalAnswer: str) -> None:
        """Phase 3 종합 결과 기록"""
        self.synthesisPrompt = promptToHead
        self.finalAnswer = finalAnswer

    def logError(self, error: str) -> None:
        """치명적 오류 기록"""
        self.error = error

    def save(self) -> str:
        """JSON + TXT 세션 로그 파일 저장, JSON 경로 반환"""
        self.endTime = datetime.now()
        try:
            LOG_DIR.mkdir(exist_ok=True)
            base = LOG_DIR / f"session_{self.sessionId}"
            self._saveJson(base.with_suffix(".json"))
            self._saveText(base.with_suffix(".txt"))
            return str(base.with_suffix(".json"))
        except OSError:
            return ""

    def _toDict(self) -> dict:
        """세션 데이터를 직렬화 가능한 딕셔너리로 변환"""
        duration = None
        if self.endTime:
            duration = round((self.endTime - self.startTime).total_seconds(), 1)
        return {
            "session_id": self.sessionId,
            "start_time": self.startTime.isoformat(timespec="seconds"),
            "end_time": self.endTime.isoformat(timespec="seconds") if self.endTime else None,
            "duration_seconds": duration,
            "head": self.head,
            "workers": self.workers,
            "user_prompt": self.userPrompt,
            "phase1_refinement": {
                "prompt_to_head": self.refinementPrompt,
                "head_raw_response": self.headRawRefinement,
                "refined_prompts": self.refinedPrompts,
            },
            "phase2_workers": self.workerData,
            "phase3_synthesis": {
                "prompt_to_head": self.synthesisPrompt,
                "final_answer": self.finalAnswer,
            },
            "error": self.error,
        }

    def _saveJson(self, path: Path) -> None:
        """세션 데이터를 JSON 파일로 저장"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._toDict(), f, ensure_ascii=False, indent=2)

    def _saveText(self, path: Path) -> None:
        """세션 데이터를 사람이 읽기 쉬운 TXT 형식으로 저장"""
        lines = []
        sep = "=" * 70
        thin = "-" * 70

        duration = self._toDict()["duration_seconds"]
        durStr = ""
        if duration:
            m, s = divmod(int(duration), 60)
            durStr = f"  총 소요시간: {m}분 {s}초"

        # 헤더 섹션
        lines.append(sep)
        lines.append("  MultiMind Session Log")
        lines.append(f"  {self.startTime.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Head: {self.head} | Workers: {', '.join(self.workers)}")
        if durStr:
            lines.append(durStr)
        lines.append(sep)
        lines.append("")

        # 사용자 프롬프트 섹션
        lines.append("[User Prompt]")
        lines.append(thin)
        lines.append(self.userPrompt)
        lines.append("")

        # Phase 1: 프롬프트 정제 섹션
        lines.append(f"[Phase 1: Prompt Refinement — Head({self.head})]")
        lines.append(thin)
        if self.refinementPrompt:
            lines.append(">> Head에게 보낸 정제 요청:")
            lines.append(self.refinementPrompt)
            lines.append("")
        if self.headRawRefinement:
            lines.append(">> Head 원본 응답:")
            lines.append(self.headRawRefinement)
            lines.append("")
        if self.refinedPrompts:
            lines.append(">> 정제된 Worker별 프롬프트:")
            for name, prompt in self.refinedPrompts.items():
                lines.append(f"  [{name}]")
                lines.append(f"  {prompt}")
                lines.append("")

        # Phase 2: Worker 응답 섹션
        lines.append("[Phase 2: Worker Responses]")
        lines.append(thin)
        for name, data in self.workerData.items():
            dur = f" ({data['duration_seconds']}초)" if data.get("duration_seconds") else ""
            lines.append(f"── {name}{dur} ──")
            if data.get("prompt"):
                lines.append("  >> 보낸 프롬프트:")
                lines.append(f"  {data['prompt']}")
                lines.append("")
            if data.get("response"):
                lines.append("  >> 받은 응답:")
                lines.append(f"  {data['response']}")
                lines.append("")
            if data.get("error"):
                lines.append(f"  >> 오류: {data['error']}")
                lines.append("")

        # Phase 3: 결과 종합 섹션
        lines.append(f"[Phase 3: Synthesis — Head({self.head})]")
        lines.append(thin)
        if self.synthesisPrompt:
            lines.append(">> Head에게 보낸 종합 요청:")
            lines.append(self.synthesisPrompt)
            lines.append("")
        if self.finalAnswer:
            lines.append(">> 최종 답변:")
            lines.append(self.finalAnswer)
            lines.append("")

        # 오류 섹션
        if self.error:
            lines.append("[오류]")
            lines.append(thin)
            lines.append(self.error)
            lines.append("")

        # 요약 섹션
        lines.append(thin)
        success = [n for n, d in self.workerData.items() if d.get("response")]
        failed = [n for n, d in self.workerData.items() if d.get("error")]
        lines.append(f"Worker 성공: {', '.join(success) if success else '없음'}")
        lines.append(f"Worker 실패: {', '.join(failed) if failed else '없음'}")
        lines.append(sep)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
