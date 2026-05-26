class ImageNotFoundError(Exception):
    """locateOnScreen이 타임아웃 내에 이미지를 찾지 못한 경우"""
    def __init__(self, image_path: str, llm_name: str = ""):
        self.image_path = image_path
        self.llm_name = llm_name
        super().__init__(f"[{llm_name}] 이미지를 찾을 수 없음: {image_path}")


class ResponseTimeoutError(Exception):
    """LLM 응답 대기가 제한 시간을 초과한 경우"""
    def __init__(self, llm_name: str, timeout: float):
        self.llm_name = llm_name
        self.timeout = timeout
        super().__init__(f"[{llm_name}] 응답 타임아웃: {timeout}초 초과")


class LoginRequiredError(Exception):
    """LLM 사이트에 로그인이 필요한 경우"""
    def __init__(self, llm_name: str):
        self.llm_name = llm_name
        super().__init__(f"[{llm_name}] 로그인이 필요합니다. 브라우저에서 먼저 로그인해주세요.")


class BrowserWindowNotFoundError(Exception):
    """해당 LLM 브라우저 창을 찾을 수 없는 경우"""
    def __init__(self, llm_name: str):
        self.llm_name = llm_name
        super().__init__(f"[{llm_name}] 브라우저 창을 찾을 수 없습니다.")
