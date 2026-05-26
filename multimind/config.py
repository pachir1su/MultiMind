import json
from datetime import datetime
from pathlib import Path

# ── 설정 파일 경로 및 기본값 ───────────────────────────────────────────────────
CONFIG_PATH = Path("config.json")

DEFAULT_CONFIG = {
    "head": "claude",
    "workers": ["chatgpt", "gemini"],
    "settings": {
        "open_delay": 3.0,
        "response_timeout": 300,
        "image_confidence": 0.85,
        "poll_interval": 0.5,
        "dark_mode": False,
    },
    "window_geometry": "900x700+100+100",
}


class ConfigManager:
    def load(self) -> dict:
        """config.json 로드. 없거나 손상된 경우 기본값 반환."""
        # ── 파일 부재 시 기본값 반환 ─────────────────────────────────────────
        if not CONFIG_PATH.exists():
            return dict(DEFAULT_CONFIG)

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ── 누락된 키를 기본값으로 병합 ──────────────────────────────────
            merged = dict(DEFAULT_CONFIG)
            merged.update(data)
            merged["settings"] = dict(DEFAULT_CONFIG["settings"])
            merged["settings"].update(data.get("settings", {}))
            return merged

        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)

    def save(self, head: str, workers: list, settings: dict = None,
             geometry: str = None) -> None:
        """현재 설정을 config.json에 저장"""
        # ── 기존 설정 로드 후 업데이트 기록 ──────────────────────────────────
        current = self.load()
        current["head"] = head
        current["workers"] = workers
        current["last_updated"] = datetime.now().isoformat()

        if settings:
            current["settings"].update(settings)
        if geometry:
            current["window_geometry"] = geometry

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 설정 저장 실패는 무시
