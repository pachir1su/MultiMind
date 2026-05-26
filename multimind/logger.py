from datetime import datetime

# ── 로그 파일 경로 ─────────────────────────────────────────────────────────────
LOG_FILE = "multimind.log"


def writeLog(event: str) -> None:
    """타임스탬프와 함께 로그 파일에 이벤트 기록"""
    # ── 타임스탬프 포맷 및 파일 추가 기록 ────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {event}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass  # 로그 실패는 메인 흐름을 방해하지 않음
