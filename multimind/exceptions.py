class MissingDependencyError(Exception):
    """필수 패키지가 설치되지 않았을 때"""
    def __init__(self, package: str, install_cmd: str = None):
        self.package = package
        self.install_cmd = install_cmd or f"pip install {package}"
        super().__init__(
            f"필수 패키지 '{package}'가 설치되지 않았습니다.\n"
            f"설치 명령어: {self.install_cmd}"
        )


class LLMDriverError(Exception):
    """LLM 드라이버 오류 (요소 탐색 실패, 로그인 필요 등)"""
    def __init__(self, llm_name: str, reason: str):
        self.llm_name = llm_name
        super().__init__(f"[{llm_name}] {reason}")


class ResponseTimeoutError(Exception):
    """LLM 응답 대기 타임아웃"""
    def __init__(self, llm_name: str, timeout: float):
        self.llm_name = llm_name
        self.timeout = timeout
        super().__init__(f"[{llm_name}] 응답 타임아웃: {timeout}초 초과")
