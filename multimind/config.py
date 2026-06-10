# 설정 파일(config.json) 관리 모듈

import copy
import json
from datetime import datetime
from pathlib import Path

# 설정 파일 경로
CONFIG_PATH = Path("config.json")

# 기본 설정값 (config.json 미존재 또는 파싱 실패 시 사용)
DEFAULT_CONFIG = {
    "head": "claude",
    "workers": ["chatgpt", "gemini"],
    "settings": {
        "open_delay": 3.0,
        "response_timeout": 300,
        "poll_interval": 0.5,
        "dark_mode": False,
    },
    "window_geometry": "900x700+100+100",
}


class ConfigManager:
    """설정 파일 로드/저장 관리 클래스"""

    def load(self) -> dict:
        """설정 파일을 로드하여 딕셔너리로 반환 (없으면 기본값 사용)"""
        if not CONFIG_PATH.exists():
            return copy.deepcopy(DEFAULT_CONFIG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 누락된 최상위 키는 기본값으로 채움
            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(data)
            merged["settings"] = copy.deepcopy(DEFAULT_CONFIG["settings"])
            merged["settings"].update(data.get("settings", {}))
            return merged
        except (json.JSONDecodeError, OSError):
            return copy.deepcopy(DEFAULT_CONFIG)

    def save(self, head: str, workers: list, settings: dict = None,
             geometry: str = None) -> None:
        """현재 설정을 config.json에 저장"""
        current = self.load()
        current["head"] = head
        current["workers"] = workers
        current["last_updated"] = datetime.now().isoformat()
        if settings:
            current["settings"].update(settings)
        if geometry:
            current["window_geometry"] = geometry
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
