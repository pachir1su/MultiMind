# 커스텀 예외 클래스 정의 모듈


class MissingDependencyError(Exception):
    """필수 패키지가 설치되지 않았을 때 발생하는 예외"""
    def __init__(self, package: str, installCmd: str = None):
        self.package = package
        self.installCmd = installCmd or f"pip install {package}"
        super().__init__(
            f"필수 패키지 '{package}'가 설치되지 않았습니다.\n"
            f"설치 명령어: {self.installCmd}"
        )


class LLMDriverError(Exception):
    """LLM 드라이버 오류 (요소 탐색 실패, 로그인 필요 등)"""
    def __init__(self, llmName: str, reason: str):
        self.llmName = llmName
        super().__init__(f"[{llmName}] {reason}")


class BrowserNotFoundError(Exception):
    """지원 브라우저(Chrome/Edge)를 찾을 수 없을 때 발생하는 예외"""
    def __init__(self):
        super().__init__(
            "지원되는 브라우저를 찾을 수 없습니다.\n"
            "Chrome 또는 Edge 브라우저를 설치해주세요.\n"
            "Chrome 다운로드: https://www.google.com/chrome/\n"
            "Edge 다운로드: https://www.microsoft.com/edge/"
        )


class ResponseTimeoutError(Exception):
    """LLM 응답 대기 타임아웃"""
    def __init__(self, llmName: str, timeout: float):
        self.llmName = llmName
        self.timeout = timeout
        super().__init__(f"[{llmName}] 응답 타임아웃: {timeout}초 초과")
