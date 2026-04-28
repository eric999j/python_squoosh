from tkinterdnd2 import TkinterDnD
from gui import ImageCompressorApp

if __name__ == "__main__":
    # 使用 TkinterDnD.Tk() 替代 tk.Tk()
    root = TkinterDnD.Tk()
    app = ImageCompressorApp(root)
    root.mainloop()
