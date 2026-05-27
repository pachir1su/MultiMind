#!/usr/bin/env python3
"""
MultiMind 초기 설정 마법사 — assets/screenshots 이미지를 자동으로 캡처합니다.
main.py 실행 시 assets가 없으면 자동으로 이 마법사가 열립니다.
직접 실행: python setup_assets.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import pyautogui
from PIL import Image, ImageTk

ASSETS_DIR = Path("assets/screenshots")
LLMS = ["claude", "chatgpt", "gemini"]
LLM_DISPLAY = {"claude": "Claude", "chatgpt": "ChatGPT", "gemini": "Gemini"}
LLM_URLS = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
    "gemini": "https://gemini.google.com/app",
}

ELEMENTS = [
    (
        "input_area",
        "텍스트 입력창",
        "메시지를 입력하는 텍스트 박스 전체 영역을 선택하세요.",
    ),
    (
        "send_button_active",
        "전송 버튼 (활성화)",
        "전송 버튼이 활성화된 상태(클릭 가능할 때)를 선택하세요.\n"
        "입력창에 아무 글자나 입력하면 버튼이 활성화됩니다.",
    ),
    (
        "copy_button",
        "복사 버튼",
        "LLM 응답 옆에 나타나는 복사 버튼을 선택하세요.\n"
        "미리 아무 질문이나 해서 응답을 받아두세요.",
    ),
]

COUNTDOWN_SEC = 3


def assets_complete() -> bool:
    """모든 필수 이미지가 존재하는지 확인"""
    for llm in LLMS:
        for key, _, _ in ELEMENTS:
            if not (ASSETS_DIR / llm / f"{key}.png").exists():
                return False
    return True


def _has_content(img: Image.Image) -> bool:
    """이미지가 공백/단색이 아닌지 확인 (픽셀 표준편차 기반)"""
    import statistics
    gray = img.convert("L")
    pixels = list(gray.getdata())
    if len(pixels) < 50:
        return False
    try:
        return statistics.stdev(pixels) > 8.0
    except statistics.StatisticsError:
        return False


def _preview_confirm(parent: tk.Tk, crop: Image.Image, name: str) -> bool:
    """캡처된 이미지 미리보기 후 사용자 확인. 저장이면 True, 다시 선택이면 False."""
    win = tk.Toplevel(parent)
    win.title(f"미리보기 — {name}")
    win.resizable(False, False)
    win.grab_set()

    ttk.Label(win, text=f"이 이미지가 맞나요?  [{name}]",
              font=("맑은 고딕", 10, "bold")).pack(pady=(10, 4))

    # 너무 작은 이미지는 확대해서 보여주기
    pw, ph = crop.width, crop.height
    max_side = 320
    scale = min(max_side / max(pw, ph, 1), 6.0)
    scale = max(scale, 1.0)
    disp = crop.resize((int(pw * scale), int(ph * scale)), Image.NEAREST)
    photo = ImageTk.PhotoImage(disp)

    lbl = tk.Label(win, image=photo, relief="sunken", borderwidth=2)
    lbl.image = photo
    lbl.pack(padx=16, pady=8)

    ttk.Label(win, text=f"크기: {pw} × {ph} px", foreground="#888").pack()

    confirmed = tk.BooleanVar(value=False)
    btn = ttk.Frame(win)
    btn.pack(pady=(8, 12))
    ttk.Button(btn, text="다시 선택",
               command=lambda: (confirmed.set(False), win.destroy())).pack(side="left", padx=10)
    ttk.Button(btn, text="저장 ✓",
               command=lambda: (confirmed.set(True), win.destroy())).pack(side="left", padx=10)

    win.bind("<Return>", lambda _: (confirmed.set(True), win.destroy()))
    win.bind("<Escape>", lambda _: (confirmed.set(False), win.destroy()))

    parent.wait_window(win)
    return confirmed.get()


# ── 영역 선택 창 ───────────────────────────────────────────────────────────────

class RegionSelector(tk.Toplevel):
    """스크린샷 위에서 드래그해 영역을 선택하는 창"""

    def __init__(self, parent, screenshot: Image.Image, title: str):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight() - 80
        scale = min(sw / screenshot.width, sh / screenshot.height, 1.0)
        self.scale = scale

        dw = int(screenshot.width * scale)
        dh = int(screenshot.height * scale)
        disp = screenshot.resize((dw, dh), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(disp)

        ttk.Label(self, text="드래그로 영역 선택 후 Enter 또는 [저장] 버튼").pack(pady=3)

        self.canvas = tk.Canvas(self, width=dw, height=dh, cursor="crosshair")
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        btn = ttk.Frame(self)
        btn.pack(pady=4)
        ttk.Button(btn, text="다시 그리기", command=self._reset).pack(side="left", padx=6)
        ttk.Button(btn, text="저장 (Enter)", command=self._confirm).pack(side="left", padx=6)

        self._start = self._end = self._rect_id = None
        self.result = None

        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", self._confirm)
        self.bind("<Escape>", lambda _: self.destroy())

        self.geometry(f"{dw}x{dh + 65}+0+0")
        self.focus_set()
        self.grab_set()

    def _press(self, e):
        self._start = (e.x, e.y)
        self._end = None
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _drag(self, e):
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        if self._start:
            self._rect_id = self.canvas.create_rectangle(
                *self._start, e.x, e.y, outline="red", width=2, dash=(5, 3)
            )
            self._end = (e.x, e.y)

    def _release(self, e):
        self._end = (e.x, e.y)

    def _reset(self):
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        self._start = self._end = self._rect_id = None

    def _confirm(self, _=None):
        if not self._start or not self._end:
            messagebox.showwarning("선택 필요", "영역을 드래그해서 선택해주세요.", parent=self)
            return
        x1 = int(min(self._start[0], self._end[0]) / self.scale)
        y1 = int(min(self._start[1], self._end[1]) / self.scale)
        x2 = int(max(self._start[0], self._end[0]) / self.scale)
        y2 = int(max(self._start[1], self._end[1]) / self.scale)
        if x2 - x1 < 8 or y2 - y1 < 8:
            messagebox.showwarning("너무 작음", "더 크게 드래그해주세요.", parent=self)
            return
        self.result = (x1, y1, x2, y2)
        self.destroy()


# ── 설정 마법사 ────────────────────────────────────────────────────────────────

class SetupWizard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MultiMind 초기 설정 마법사")
        self.root.resizable(False, False)

        for llm in LLMS:
            (ASSETS_DIR / llm).mkdir(parents=True, exist_ok=True)

        self.steps = [
            (llm, key, name, desc)
            for llm in LLMS
            for key, name, desc in ELEMENTS
        ]
        self.step_idx = 0
        self.captured: dict = {}

        self._build_frame()
        self._show_intro()

    # ── UI 뼈대 ────────────────────────────────────────────────────────────────

    def _build_frame(self):
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="MultiMind 초기 설정 마법사",
                  font=("맑은 고딕", 13, "bold")).pack(pady=(0, 6))

        self.prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(outer, variable=self.prog_var, length=480).pack(pady=(0, 12))

        self.content = ttk.Frame(outer)
        self.content.pack(fill="both", expand=True)

        self.btn_row = ttk.Frame(outer)
        self.btn_row.pack(fill="x", pady=(14, 0))

    def _clear(self):
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.btn_row.winfo_children():
            w.destroy()

    # ── 화면 전환 ──────────────────────────────────────────────────────────────

    def _show_intro(self):
        self._clear()

        lines = (
            "각 LLM 사이트를 브라우저에서 미리 열고 로그인해 두세요.\n\n"
            "캡처할 항목 (LLM별 3개 = 총 9개):\n"
            "  1. 텍스트 입력창\n"
            "  2. 전송 버튼 (활성화 상태)\n"
            "  3. 복사 버튼 (응답 후 나타나는 버튼)\n\n"
            "각 항목마다:\n"
            "  ① 해당 LLM 탭으로 전환\n"
            f"  ② [캡처 시작] 클릭 → {COUNTDOWN_SEC}초 카운트다운\n"
            "  ③ 화면에서 해당 요소를 드래그해 선택\n\n"
            "준비되면 [시작]을 누르세요."
        )
        ttk.Label(self.content, text=lines, justify="left").pack(anchor="w")

        for llm, url in LLM_URLS.items():
            ttk.Label(self.content,
                      text=f"  • {LLM_DISPLAY[llm]}: {url}",
                      foreground="#0055cc").pack(anchor="w")

        ttk.Button(self.btn_row, text="시작 ▶",
                   command=self._show_step).pack(side="right")

    def _show_step(self):
        if self.step_idx >= len(self.steps):
            self._show_done()
            return

        self._clear()
        llm, key, name, desc = self.steps[self.step_idx]

        self.prog_var.set(self.step_idx / len(self.steps) * 100)

        ttk.Label(self.content,
                  text=f"단계 {self.step_idx + 1} / {len(self.steps)}",
                  foreground="#888").pack(anchor="w")
        ttk.Label(self.content,
                  text=f"[{LLM_DISPLAY[llm]}]  {name}",
                  font=("맑은 고딕", 11, "bold")).pack(anchor="w", pady=(4, 6))
        ttk.Label(self.content, text=desc, justify="left",
                  foreground="#444").pack(anchor="w", padx=8)

        ttk.Separator(self.content).pack(fill="x", pady=10)
        ttk.Label(self.content,
                  text=f"➤  {LLM_DISPLAY[llm]} 탭으로 전환한 뒤 [캡처 시작]을 누르세요.",
                  justify="left").pack(anchor="w")

        self.countdown_lbl = ttk.Label(self.content, text="",
                                        foreground="red",
                                        font=("맑은 고딕", 20, "bold"))
        self.countdown_lbl.pack(pady=6)

        if self.step_idx > 0:
            ttk.Button(self.btn_row, text="← 이전",
                       command=self._prev).pack(side="left")
        ttk.Button(self.btn_row, text="캡처 시작",
                   command=self._begin_countdown).pack(side="right")

    def _prev(self):
        self.step_idx -= 1
        self._show_step()

    def _show_done(self):
        self._clear()
        self.prog_var.set(100)

        ttk.Label(self.content, text="설정 완료! ✓",
                  font=("맑은 고딕", 14, "bold"),
                  foreground="green").pack(pady=(8, 4))

        msg = f"총 {len(self.captured)}개 이미지가 저장되었습니다.\n\n"
        for (llm, key), path in self.captured.items():
            msg += f"  • {path}\n"
        msg += "\n이제 main.py를 실행하면 MultiMind가 바로 작동합니다."

        ttk.Label(self.content, text=msg, justify="left").pack(anchor="w", pady=6)
        ttk.Button(self.btn_row, text="닫기",
                   command=self.root.destroy).pack(side="right")

    # ── 캡처 흐름 ──────────────────────────────────────────────────────────────

    def _begin_countdown(self):
        for w in self.btn_row.winfo_children():
            w.configure(state="disabled")
        self._tick(COUNTDOWN_SEC)

    def _tick(self, n: int):
        if n > 0:
            self.countdown_lbl.configure(text=str(n))
            self.root.after(1000, self._tick, n - 1)
        else:
            self.countdown_lbl.configure(text="📸")
            self.root.after(150, self._capture)

    def _capture(self):
        # 마법사 창 숨기기 → 스크린샷
        self.root.withdraw()
        self.root.after(300, self._take)

    def _take(self):
        screenshot = pyautogui.screenshot()
        self.root.deiconify()
        self._select(screenshot)

    def _select(self, screenshot: Image.Image):
        llm, key, name, _ = self.steps[self.step_idx]
        sel = RegionSelector(self.root, screenshot,
                             f"{LLM_DISPLAY[llm]} — {name} 영역 선택")
        self.root.wait_window(sel)

        if sel.result is None:
            for w in self.btn_row.winfo_children():
                w.configure(state="normal")
            self.countdown_lbl.configure(text="취소됨. 다시 시도하세요.")
            return

        x1, y1, x2, y2 = sel.result
        crop = screenshot.crop((x1, y1, x2, y2))

        # 공백/단색 이미지 검증
        if not _has_content(crop):
            messagebox.showwarning(
                "이미지 품질 경고",
                "선택 영역이 너무 단순하거나 공백입니다.\n"
                "버튼·텍스트·아이콘이 포함된 영역을 선택해주세요.",
                parent=self.root,
            )
            for w in self.btn_row.winfo_children():
                w.configure(state="normal")
            self.countdown_lbl.configure(text="다시 시도하세요.")
            return

        # 미리보기 확인
        if not _preview_confirm(self.root, crop, name):
            for w in self.btn_row.winfo_children():
                w.configure(state="normal")
            self.countdown_lbl.configure(text="다시 시도하세요.")
            return

        save_path = ASSETS_DIR / llm / f"{key}.png"
        crop.save(save_path)

        self.captured[(llm, key)] = save_path
        self.step_idx += 1
        self._show_step()


# ── 진입점 ─────────────────────────────────────────────────────────────────────

def run_wizard():
    root = tk.Tk()
    root.geometry("520x400")
    SetupWizard(root)
    root.mainloop()


if __name__ == "__main__":
    run_wizard()
