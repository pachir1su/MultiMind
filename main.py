import sys


def main():
    # tkinter 모듈 로드 시도
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print(
            "오류: tkinter를 찾을 수 없습니다.\n"
            "Python에 tkinter 모듈을 포함하여 재설치해주세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    # MultiMind 앱 모듈 로드 시도
    try:
        from multimind.app import MultiMindApp
    except ModuleNotFoundError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "패키지 오류",
            f"{e}\n\n필요한 패키지를 설치한 뒤 다시 실행해주세요:\n"
            "pip install selenium undetected-chromedriver pyperclip",
        )
        root.destroy()
        sys.exit(1)

    # Tkinter 루트 윈도우 생성 및 앱 실행
    root = tk.Tk()
    root.minsize(900, 700)
    MultiMindApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
