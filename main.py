import tkinter as tk
from multimind.app import MultiMindApp


def main():
    root = tk.Tk()
    root.minsize(800, 650)
    MultiMindApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
