import os
from datetime import datetime

LOG_FILE = "multimind.log"


def write_log(event: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {event}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
