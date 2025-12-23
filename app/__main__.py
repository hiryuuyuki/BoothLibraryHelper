import tkinter as tk

from app.ui_main import MainUI


def main():
    root = tk.Tk()
    MainUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
