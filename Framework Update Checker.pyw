# Double-click this file to start Framework Update Checker.
# The .pyw extension runs it through pyw.exe -> no console window, no batch files.
# (First time? Double-click "Setup" instead -- it installs everything for you.)
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import app
except ImportError:
    # Dependencies aren't installed yet -- point the user at the one-click setup.
    import tkinter as tk
    from tkinter import messagebox
    r = tk.Tk()
    r.withdraw()
    messagebox.showinfo(
        "Framework Update Checker",
        "Almost there - the required components aren't installed yet.\n\n"
        "Double-click \"Setup\" (Setup.pyw) in this folder once to finish "
        "installation, then this launcher will work.",
    )
    r.destroy()
    sys.exit(1)

app.main()
