"""Optional unprivileged desktop interface using Tk."""
import os
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox

from .hardware import Hardware, MAX_WARNING, POWER_WARNING

BACKGROUND = "#0a1020"
PANEL = "#141f34"
TEXT = "#e9f5ff"
CYAN = "#58e9ff"
MUTED = "#a8bdd7"
RED = "#bf344d"
INSTALL = "/usr/local/bin/luo-max"


def confirm(root, profile):
    dialog = tk.Toplevel(root, bg=PANEL)
    dialog.title("Confirmar perfil")
    dialog.transient(root)
    dialog.resizable(False, False)
    maximum = profile == "maximo"
    title = "⚠ ATENCIÓN: PERFIL MÁXIMO" if maximum else "Confirmar perfil Extremo"
    body = MAX_WARNING.split("\n\n", 1)[1] if maximum else POWER_WARNING
    body += "\n\nEl servicio volverá a aplicar este perfil en futuros arranques."
    tk.Label(dialog, text=title, bg=RED if maximum else BACKGROUND, fg=TEXT,
             font=("TkDefaultFont", 15, "bold"), padx=24, pady=14, anchor="w").pack(fill="x")
    tk.Label(dialog, text=body, bg=PANEL, fg=TEXT, wraplength=505,
             justify="left", padx=24, pady=18, anchor="w").pack(fill="x")
    actions = tk.Frame(dialog, bg=PANEL, padx=24, pady=14)
    actions.pack(fill="x")
    accepted = False

    def accept():
        nonlocal accepted
        accepted = True
        dialog.destroy()

    tk.Button(actions, text="Comprendo los riesgos y quiero aplicar", bg=RED if maximum else BACKGROUND,
              fg=TEXT, command=accept, padx=9, pady=6).pack(side="right")
    cancel = tk.Button(actions, text="Cancelar", bg=BACKGROUND, fg=TEXT,
                       command=dialog.destroy, padx=9, pady=6)
    cancel.pack(side="right", padx=(0, 8))
    dialog.bind("<Escape>", lambda _: dialog.destroy())
    dialog.update_idletasks()
    x = max(0, root.winfo_rootx() + (root.winfo_width() - dialog.winfo_reqwidth()) // 2)
    y = max(0, root.winfo_rooty() + (root.winfo_height() - dialog.winfo_reqheight()) // 2)
    dialog.geometry(f"+{x}+{y}")
    dialog.wait_visibility()
    dialog.grab_set()
    cancel.focus_set()
    root.wait_window(dialog)
    return accepted


def launch():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f'No se pudo abrir el escritorio: {error}') from error
    root.title("LUO-MAX")
    root.geometry("820x640")
    root.minsize(640, 620)
    root.configure(bg=BACKGROUND)
    content = tk.Frame(root, bg=BACKGROUND, padx=32, pady=24)
    content.pack(expand=True, fill="both")
    brand = Path(__file__).resolve().parent.parent / "assets/logo-oscuro.png"
    logo = tk.PhotoImage(file=brand)
    icon = tk.PhotoImage(width=64, height=64)
    icon.tk.call(str(icon), "copy", str(logo), "-from", 7, 7, 71, 71)
    root.iconphoto(True, icon)
    tk.Label(content, image=logo, bg=BACKGROUND).pack(anchor="w")
    tk.Label(content, text="Políticas de rendimiento Linux", fg=MUTED, bg=BACKGROUND,
             font=("TkDefaultFont", 13)).pack(anchor="w", pady=(0, 22))

    hardware = Hardware()
    metrics = tk.Frame(content, bg=BACKGROUND)
    metrics.pack(fill="x")
    values = {}
    for index, label in enumerate(("CPU", "GPU", "RAM", "TEMPERATURA")):
        panel = tk.Frame(metrics, bg=PANEL, padx=14, pady=12)
        panel.grid(row=index // 2, column=index % 2, sticky="nsew", padx=4, pady=4)
        metrics.columnconfigure(index % 2, weight=1, uniform="metric")
        tk.Label(panel, text=label, fg=CYAN, bg=PANEL, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        values[label] = tk.StringVar(value="Consultando…")
        tk.Label(panel, textvariable=values[label], fg=TEXT, bg=PANEL, wraplength=235,
                 justify="left", font=("TkDefaultFont", 12)).pack(anchor="w", pady=(5, 0))

    notice = tk.StringVar(value="Inicia el monitor para aplicar perfiles de rendimiento.")
    controls = tk.Frame(content, bg=BACKGROUND)
    controls.pack(fill="x", pady=(24, 8))
    buttons = []
    task = None
    executor = ThreadPoolExecutor(max_workers=1)

    def refresh():
        try:
            data = hardware.status()
            values["CPU"].set(data["cpu"])
            values["GPU"].set(", ".join(data["gpu"]) or "Sin GPU detectada")
            ram = data["ram_gib"]
            available = data["ram_available_gib"]
            values["RAM"].set(f"{available:g} / {ram:g} GiB disponibles"
                              if available is not None and ram is not None else "Sin lectura")
            temp = data["temperature_c"]
            values["TEMPERATURA"].set(f"{temp:g} °C · máxima detectada" if temp is not None else "Sin lectura")
            power.set(f"Alimentación · {data['power']}")
        except (OSError, ValueError) as error:
            power.set(f"Error de inventario · {error}")
        root.after(2500, refresh)

    def complete():
        nonlocal task
        if not task.done():
            root.after(200, complete)
            return
        try:
            result = task.result()
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"Código de salida {result.returncode}")
            notice.set(result.stdout.splitlines()[0] if result.stdout else "Operación completada.")
        except (OSError, RuntimeError) as error:
            notice.set("La operación falló.")
            messagebox.showerror("LUO-MAX", str(error), parent=root)
        task = None
        for button in buttons:
            button.configure(state="normal")

    def run(profile=None):
        nonlocal task
        if task is not None:
            return
        if not os.access(INSTALL, os.X_OK):
            notice.set("Instala LUO-MAX para habilitar las operaciones de administrador.")
            return
        args = ["apply", profile] if profile else ["restore"]
        if profile in {"extremo", "maximo"}:
            if not confirm(root, profile):
                return
            args.append("--confirm-risks")
        task = executor.submit(subprocess.run, ["/usr/bin/pkexec", INSTALL, *args],
                               capture_output=True, text=True)
        notice.set("Esperando autorización y resultado…")
        for button in buttons:
            button.configure(state="disabled")
        root.after(200, complete)

    for index, (label, profile, color) in enumerate((
        ("Equilibrado", "equilibrado", PANEL), ("Alto rendimiento", "alto", PANEL),
        ("Extremo", "extremo", PANEL), ("Máximo", "maximo", RED),
    )):
        button = tk.Button(controls, text=label, bg=color, fg=TEXT, activebackground=CYAN,
                           activeforeground=BACKGROUND, relief="flat", padx=12, pady=10,
                           command=lambda selected=profile: run(selected))
        controls.columnconfigure(index, weight=1)
        button.grid(row=0, column=index, sticky="ew", padx=4)
        buttons.append(button)
    restore = tk.Button(content, text="Restaurar valores originales", bg=PANEL, fg=CYAN,
                        relief="flat", padx=12, pady=8, command=run)
    restore.pack(anchor="w", pady=8, padx=4)
    buttons.append(restore)
    power = tk.StringVar()
    for variable in (power, notice):
        tk.Label(content, textvariable=variable, fg=MUTED, bg=BACKGROUND, wraplength=530,
                 justify="left").pack(anchor="w", padx=4, pady=4)
    def close():
        if task is None:
            executor.shutdown(wait=False)
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    refresh()
    root.mainloop()
    return 0
