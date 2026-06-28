"""Settings window (standalone).

Run directly (`python settings_gui.py`) or via the tray "Settings..." item. Edits
the same config file the checker reads, then exits. Kept as its own process on
purpose -- mixing a Tk loop into the tray loop is fragile.
"""
import tkinter as tk
from tkinter import ttk, messagebox

import config


def main():
    cfg = config.load()
    root = tk.Tk()
    root.title("Framework Update Checker - Settings")
    root.resizable(False, False)

    pad = {"padx": 10, "pady": 6}
    frm = ttk.Frame(root, padding=14)
    frm.grid(row=0, column=0, sticky="nsew")
    row = 0

    ttk.Label(frm, text="Check every (hours)").grid(row=row, column=0, sticky="w", **pad)
    interval_var = tk.IntVar(value=int(cfg["check_interval_hours"]))
    ttk.Spinbox(frm, from_=1, to=168, textvariable=interval_var, width=8).grid(
        row=row, column=1, sticky="w", **pad
    )
    row += 1

    autodl_var = tk.BooleanVar(value=cfg.get("auto_download", True))
    ttk.Checkbutton(
        frm, text="Automatically download the installer when an update is found",
        variable=autodl_var,
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    beta_var = tk.BooleanVar(value=cfg["include_beta"])
    ttk.Checkbutton(
        frm, text="Include beta releases (otherwise stable only)", variable=beta_var
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    ttk.Separator(frm, orient="horizontal").grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=8
    )
    row += 1

    ttk.Label(frm, text="Check for:").grid(row=row, column=0, sticky="w", **pad)
    row += 1

    bios_var = tk.BooleanVar(value=cfg["watch_bios"])
    ttk.Checkbutton(frm, text="BIOS", variable=bios_var).grid(
        row=row, column=0, columnspan=2, sticky="w", **pad
    )
    row += 1

    drivers_var = tk.BooleanVar(value=cfg["watch_drivers"])
    ttk.Checkbutton(frm, text="Driver bundle (Windows)", variable=drivers_var).grid(
        row=row, column=0, columnspan=2, sticky="w", **pad
    )
    row += 1

    keyboard_var = tk.BooleanVar(value=cfg.get("watch_keyboard", True))
    ttk.Checkbutton(
        frm, text="Keyboard / input-module firmware", variable=keyboard_var
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    uptodate_var = tk.BooleanVar(value=cfg["notify_when_up_to_date"])
    ttk.Checkbutton(
        frm, text="On a manual check, tell me even when up to date", variable=uptodate_var
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    ttk.Separator(frm, orient="horizontal").grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=8
    )
    row += 1

    ttk.Label(frm, text="App self-update (from GitHub):").grid(row=row, column=0, sticky="w", **pad)
    row += 1

    ttk.Label(frm, text="GitHub repo (owner/name)").grid(row=row, column=0, sticky="w", **pad)
    repo_var = tk.StringVar(value=cfg.get("app_repo", ""))
    ttk.Entry(frm, textvariable=repo_var, width=40).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    autoupd_var = tk.BooleanVar(value=cfg.get("auto_update", True))
    ttk.Checkbutton(
        frm, text="Check GitHub for new versions of this app", variable=autoupd_var
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    silentupd_var = tk.BooleanVar(value=cfg.get("auto_install_app_updates", False))
    ttk.Checkbutton(
        frm, text="Install app updates silently (no prompt)", variable=silentupd_var
    ).grid(row=row, column=0, columnspan=2, sticky="w", **pad)
    row += 1

    ttk.Separator(frm, orient="horizontal").grid(
        row=row, column=0, columnspan=2, sticky="ew", pady=8
    )
    row += 1

    ttk.Label(frm, text="Advanced: forum search URL").grid(row=row, column=0, sticky="w", **pad)
    search_var = tk.StringVar(value=cfg["sources"].get("community_search_url", ""))
    ttk.Entry(frm, textvariable=search_var, width=54).grid(row=row, column=1, sticky="w", **pad)
    row += 1

    note = (
        "The app downloads installers straight from Framework and notifies you;\n"
        "you run them yourself. It never flashes firmware automatically."
    )
    ttk.Label(frm, text=note, foreground="#666", justify="left").grid(
        row=row, column=0, columnspan=2, sticky="w", **pad
    )
    row += 1

    def on_save():
        cfg["check_interval_hours"] = max(1, int(interval_var.get()))
        cfg["auto_download"] = bool(autodl_var.get())
        cfg["include_beta"] = bool(beta_var.get())
        cfg["watch_bios"] = bool(bios_var.get())
        cfg["watch_drivers"] = bool(drivers_var.get())
        cfg["watch_keyboard"] = bool(keyboard_var.get())
        cfg["notify_when_up_to_date"] = bool(uptodate_var.get())
        cfg["app_repo"] = repo_var.get().strip()
        cfg["auto_update"] = bool(autoupd_var.get())
        cfg["auto_install_app_updates"] = bool(silentupd_var.get())
        cfg["sources"]["community_search_url"] = search_var.get().strip()
        config.save(cfg)
        messagebox.showinfo("Saved", "Settings saved. They take effect on the next check.")
        root.destroy()

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))
    ttk.Button(btns, text="Cancel", command=root.destroy).grid(row=0, column=0, padx=6)
    ttk.Button(btns, text="Save", command=on_save).grid(row=0, column=1, padx=6)

    root.mainloop()


if __name__ == "__main__":
    main()
