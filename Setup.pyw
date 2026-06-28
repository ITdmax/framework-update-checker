# Setup.pyw  -  one-click installer for Framework Update Checker.
#
# Double-click this file. It installs the Python packages the app needs, puts a
# "Framework Update Checker" icon on your desktop, optionally starts it with
# Windows, and launches it into your system tray. No console, no batch files,
# no commands to type.
import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
NOWIN = 0x08000000 if os.name == "nt" else 0
REQS = os.path.join(HERE, "requirements.txt")
LAUNCHER = os.path.join(HERE, "Framework Update Checker.pyw")
ICON = os.path.join(HERE, "icon.ico")


def _pythonw() -> str:
    """The windowless interpreter, so shortcuts launch without a console."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        return exe
    cand = exe.replace("python.exe", "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def install_deps():
    base = [sys.executable, "-m", "pip", "install", "-r", REQS,
            "--disable-pip-version-check"]
    try:
        p = subprocess.run(base, capture_output=True, text=True, timeout=900,
                           creationflags=NOWIN)
        if p.returncode != 0:
            # Retry into the per-user location (handles a system-wide Python).
            p = subprocess.run(base + ["--user"], capture_output=True, text=True,
                               timeout=900, creationflags=NOWIN)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


def _make_shortcut(lnk_path: str) -> bool:
    ico = "$s.IconLocation='{}';".format(ICON) if os.path.exists(ICON) else ""
    ps = (
        "$w=New-Object -ComObject WScript.Shell;"
        "$s=$w.CreateShortcut('{lnk}');"
        "$s.TargetPath='{t}';"
        "$s.Arguments='{a}';"
        "$s.WorkingDirectory='{wd}';"
        "{ico}$s.Save()"
    ).format(lnk=lnk_path, t=_pythonw(), a='"{}"'.format(LAUNCHER), wd=HERE, ico=ico)
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=30, creationflags=NOWIN)
        return os.path.exists(lnk_path)
    except Exception:
        return False


def desktop_shortcut() -> bool:
    lnk = os.path.join(os.path.expanduser("~"), "Desktop", "Framework Update Checker.lnk")
    return _make_shortcut(lnk)


def startup_shortcut(enable: bool) -> bool:
    appdata = os.environ.get("APPDATA", "")
    lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs",
                       "Startup", "FrameworkUpdateChecker.lnk")
    if not enable:
        try:
            if os.path.exists(lnk):
                os.remove(lnk)
        except Exception:
            pass
        return True
    return _make_shortcut(lnk)


def launch_app() -> bool:
    try:
        subprocess.Popen([_pythonw(), LAUNCHER], cwd=HERE, creationflags=NOWIN)
        return True
    except Exception:
        return False


def main():
    root = tk.Tk()
    root.title("Install Framework Update Checker")
    root.resizable(False, False)
    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="Framework Update Checker",
              font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(frm, text="Installs the required components, adds a desktop icon, and starts the app.",
              foreground="#555").grid(row=1, column=0, sticky="w", pady=(2, 10))

    startup_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="Start automatically when I log in",
                    variable=startup_var).grid(row=2, column=0, sticky="w")

    status = tk.StringVar(value="Ready to install.")
    ttk.Label(frm, textvariable=status, foreground="#222").grid(
        row=3, column=0, sticky="w", pady=(12, 6))
    bar = ttk.Progressbar(frm, mode="indeterminate", length=380)
    bar.grid(row=4, column=0, sticky="we")

    details = tk.Text(frm, height=8, width=58, wrap="word")
    # hidden unless something goes wrong

    btns = ttk.Frame(frm)
    btns.grid(row=6, column=0, sticky="e", pady=(14, 0))
    install_btn = ttk.Button(btns, text="Install")
    close_btn = ttk.Button(btns, text="Cancel", command=root.destroy)
    install_btn.grid(row=0, column=0, padx=6)
    close_btn.grid(row=0, column=1, padx=6)

    def ui(fn):
        root.after(0, fn)

    def show_details(text):
        details.grid(row=5, column=0, sticky="we", pady=(8, 0))
        details.delete("1.0", "end")
        details.insert("1.0", text[-4000:])

    def fail(out):
        bar.stop()
        status.set("Couldn't install the components. Details below.")
        show_details(
            "pip could not install the dependencies.\n\n"
            "Most likely Python isn't fully set up. Try opening a terminal and "
            "running:  py -m pip install -r requirements.txt\n\n--- output ---\n" + out)
        install_btn.config(state="normal", text="Retry")
        close_btn.config(text="Close")

    def done():
        bar.stop()
        status.set("Done. The app is running in your system tray (near the clock).")
        install_btn.grid_remove()
        close_btn.config(text="Close")

    def worker():
        ok, out = install_deps()
        if not ok:
            ui(lambda: fail(out))
            return
        ui(lambda: status.set("Creating desktop shortcut..."))
        desktop_shortcut()
        startup_shortcut(startup_var.get())
        ui(lambda: status.set("Starting the app..."))
        launch_app()
        ui(done)

    def on_install():
        install_btn.config(state="disabled")
        close_btn.config(text="Cancel")
        bar.start(12)
        status.set("Installing components (this can take a minute)...")
        threading.Thread(target=worker, daemon=True).start()

    install_btn.config(command=on_install)
    root.mainloop()


if __name__ == "__main__":
    main()
