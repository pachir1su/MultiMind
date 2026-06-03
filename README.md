# MultiMind — 멀티 LLM 오케스트레이터

2026 한국기술교육대학교 컴퓨팅사고 27분반 개인 프로젝트<br>
API 없이 pyautogui로 여러 LLM 브라우저를 동시에 조작하고 Head LLM이 결과를 종합하는 RPA 기반 자동화 프로그램

---

## 버전 기록
v0.1.16 QA 통과<br>
v0.2.5 QA 통과

---

## 동작 방식

```
사용자 프롬프트 입력
    ↓
Head LLM → 프롬프트 정제 (각 Worker에 최적화된 형태로 변환)
    ↓
Worker LLM-1  Worker LLM-2  Worker LLM-N  ← threading 병렬 실행
    ↓
Head LLM → 결과 종합 → 최종 답변 출력
```

---

## 설치

```bash
pip install -r requirements.txt
```

**지원 OS:** Windows (pyautogui 브라우저 조작)

---

## 실행 전 준비 (필수)

### 브라우저 로그인
Chrome/Edge에서 사용할 LLM 사이트에 미리 로그인해두세요:
<br> Chrome 브라우저를 추천합니다.
- Claude: https://claude.ai
- ChatGPT: https://chatgpt.com
- Gemini: https://gemini.google.com

---

## 실행

```bash
python main.py
```

---

## 프로젝트 구조

```
MultiMind/
├── main.py                     # 진입점
├── requirements.txt
├── config.json                 # 자동 생성 - 설정 저장
├── multimind.log               # 자동 생성 - 실행 로그
├── multimind/
│   ├── app.py                  # tkinter GUI
│   ├── orchestrator.py         # 3단계 오케스트레이션 로직
│   ├── head_llm.py             # Head LLM: 정제 + 종합
│   ├── worker_llm.py           # Worker LLM: 단일 자동화
│   ├── automation.py           # pyautogui/pyperclip 래퍼
│   ├── browser.py              # 브라우저 탭 제어
│   ├── config.py               # JSON 설정 관리
│   ├── prompts.py              # 프롬프트 템플릿
│   ├── exceptions.py           # 커스텀 예외
│   └── logger.py               # 로그 파일 기록
└── assets/screenshots/
    ├── claude/                 # locateOnScreen 참조 PNG (교체 필요)
    ├── chatgpt/
    └── gemini/
```

---

## 한계 및 참고사항

- **응답 속도**: API 방식보다 느림 (브라우저 UI 경유)
- **이미지 교체 필요**: 브라우저 UI 업데이트 시 스크린샷 재캡처
- **마우스 간섭 금지**: 실행 중 마우스 조작 자제 (pyautogui 자동화 방해)
- **마우스 긴급 중단**: 화면 좌상단 구석으로 이동하면 강제 종료 (FAILSAFE)
