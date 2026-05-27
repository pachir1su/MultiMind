import json
import os
from datetime import datetime
from pathlib import Path

LOG_FILE = "multimind.log"
LOG_DIR = Path("logs")


def write_log(event: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {event}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


class SessionLogger:
    """한 오케스트레이션 세션의 프롬프트·응답·오류를 모두 기록."""

    def __init__(self, head: str, workers: list, user_prompt: str):
        self.start_time = datetime.now()
        self.session_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.head = head
        self.workers = workers
        self.user_prompt = user_prompt

        self.refinement_prompt = ""
        self.head_raw_refinement = ""
        self.refined_prompts: dict = {}

        self.worker_data: dict = {}

        self.synthesis_prompt = ""
        self.final_answer = ""
        self.end_time = None
        self.error = None

    def log_refinement(self, prompt_to_head: str, raw_response: str,
                       refined_prompts: dict) -> None:
        self.refinement_prompt = prompt_to_head
        self.head_raw_refinement = raw_response
        self.refined_prompts = dict(refined_prompts)

    def log_worker(self, name: str, prompt: str, response: str = None,
                   error: str = None, duration: float = None) -> None:
        self.worker_data[name] = {
            "prompt": prompt,
            "response": response,
            "error": error,
            "duration_seconds": round(duration, 1) if duration is not None else None,
        }

    def log_synthesis(self, prompt_to_head: str, final_answer: str) -> None:
        self.synthesis_prompt = prompt_to_head
        self.final_answer = final_answer

    def log_error(self, error: str) -> None:
        self.error = error

    def save(self) -> str:
        """JSON + TXT 세션 로그 저장. JSON 경로 반환."""
        self.end_time = datetime.now()
        try:
            LOG_DIR.mkdir(exist_ok=True)
            base = LOG_DIR / f"session_{self.session_id}"
            self._save_json(base.with_suffix(".json"))
            self._save_text(base.with_suffix(".txt"))
            return str(base.with_suffix(".json"))
        except OSError:
            return ""

    def _to_dict(self) -> dict:
        duration = None
        if self.end_time:
            duration = round((self.end_time - self.start_time).total_seconds(), 1)
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(timespec="seconds"),
            "end_time": self.end_time.isoformat(timespec="seconds") if self.end_time else None,
            "duration_seconds": duration,
            "head": self.head,
            "workers": self.workers,
            "user_prompt": self.user_prompt,
            "phase1_refinement": {
                "prompt_to_head": self.refinement_prompt,
                "head_raw_response": self.head_raw_refinement,
                "refined_prompts": self.refined_prompts,
            },
            "phase2_workers": self.worker_data,
            "phase3_synthesis": {
                "prompt_to_head": self.synthesis_prompt,
                "final_answer": self.final_answer,
            },
            "error": self.error,
        }

    def _save_json(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._to_dict(), f, ensure_ascii=False, indent=2)

    def _save_text(self, path: Path) -> None:
        lines = []
        sep = "=" * 70
        thin = "-" * 70

        duration = self._to_dict()["duration_seconds"]
        dur_str = ""
        if duration:
            m, s = divmod(int(duration), 60)
            dur_str = f"  총 소요시간: {m}분 {s}초"

        lines.append(sep)
        lines.append("  MultiMind Session Log")
        lines.append(f"  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Head: {self.head} | Workers: {', '.join(self.workers)}")
        if dur_str:
            lines.append(dur_str)
        lines.append(sep)
        lines.append("")

        lines.append("[User Prompt]")
        lines.append(thin)
        lines.append(self.user_prompt)
        lines.append("")

        lines.append(f"[Phase 1: Prompt Refinement — Head({self.head})]")
        lines.append(thin)
        if self.refinement_prompt:
            lines.append(">> Head에게 보낸 정제 요청:")
            lines.append(self.refinement_prompt)
            lines.append("")
        if self.head_raw_refinement:
            lines.append(">> Head 원본 응답:")
            lines.append(self.head_raw_refinement)
            lines.append("")
        if self.refined_prompts:
            lines.append(">> 정제된 Worker별 프롬프트:")
            for name, prompt in self.refined_prompts.items():
                lines.append(f"  [{name}]")
                lines.append(f"  {prompt}")
                lines.append("")

        lines.append("[Phase 2: Worker Responses]")
        lines.append(thin)
        for name, data in self.worker_data.items():
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

        lines.append(f"[Phase 3: Synthesis — Head({self.head})]")
        lines.append(thin)
        if self.synthesis_prompt:
            lines.append(">> Head에게 보낸 종합 요청:")
            lines.append(self.synthesis_prompt)
            lines.append("")
        if self.final_answer:
            lines.append(">> 최종 답변:")
            lines.append(self.final_answer)
            lines.append("")

        if self.error:
            lines.append("[오류]")
            lines.append(thin)
            lines.append(self.error)
            lines.append("")

        lines.append(thin)
        success = [n for n, d in self.worker_data.items() if d.get("response")]
        failed = [n for n, d in self.worker_data.items() if d.get("error")]
        lines.append(f"Worker 성공: {', '.join(success) if success else '없음'}")
        lines.append(f"Worker 실패: {', '.join(failed) if failed else '없음'}")
        lines.append(sep)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
