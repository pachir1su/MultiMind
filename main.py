import tkinter as tk

from setup_assets import assets_complete, run_wizard
from multimind.app import MultiMindApp


def main():
    # assets가 없으면 초기 설정 마법사 먼저 실행
    if not assets_complete():
        run_wizard()

    root = tk.Tk()
    root.minsize(800, 650)
    MultiMindApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
