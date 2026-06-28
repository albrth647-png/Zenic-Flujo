"""UI builder and navigation functions for the InstallerWizard.

These are module-level functions that get bound to InstallerWizard
as methods via monkey-patching (preserving the original pattern).
Each function receives 'self' as the InstallerWizard instance.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def _init_window(self):
    """Initialize the main window geometry and behavior."""
    self.title("Workflow Determinista — Installer")
    self.geometry("640x520")
    self.resizable(False, False)
    self.protocol("WM_DELETE_WINDOW", self._on_cancel)
    self.update_idletasks()
    x = (self.winfo_screenwidth() - 640) // 2
    y = (self.winfo_screenheight() - 520) // 2
    self.geometry(f"640x520+{x}+{y}")


def _build_ui(self):
    """Build the navigation UI structure."""
    self.header_frame = ttk.Frame(self, padding=10)
    self.header_frame.pack(fill="x")
    self.header_label = ttk.Label(self.header_frame, text="Workflow Determinista", font=("Segoe UI", 16, "bold"))
    self.header_label.pack()
    self.step_indicator = ttk.Label(self.header_frame, text="", font=("Segoe UI", 9))
    self.step_indicator.pack()
    self.top_progress = ttk.Progressbar(self, mode="determinate", maximum=self.TOTAL_STEPS)
    self.top_progress.pack(fill="x", padx=20)
    self.content_frame = ttk.Frame(self, padding=20)
    self.content_frame.pack(fill="both", expand=True)
    self.nav_frame = ttk.Frame(self, padding=(20, 5, 20, 10))
    self.nav_frame.pack(fill="x")
    self.btn_back = ttk.Button(self.nav_frame, text="\u2190 Atr\u00e1s", command=self._go_back)
    self.btn_back.pack(side="left")
    self.btn_cancel = ttk.Button(self.nav_frame, text="Cancelar", command=self._on_cancel)
    self.btn_cancel.pack(side="left", padx=(10, 0))
    self.btn_next = ttk.Button(self.nav_frame, text="Siguiente \u2192", command=self._go_next)
    self.btn_next.pack(side="right")


def _show_step(self, step: int):
    """Show the specified step and update navigation."""
    self.current_step.set(step)
    self.top_progress["value"] = step + 1
    self._clear_content()
    step_names = [
        self._txt("step_language"), self._txt("step_directory"),
        self._txt("step_license"), self._txt("step_password"),
        self._txt("step_progress"), self._txt("step_complete"),
    ]
    self.step_indicator.config(text=f"Paso {step + 1} de {self.TOTAL_STEPS} \u2014 {step_names[step]}")
    builders = [
        self._build_step_language, self._build_step_directory,
        self._build_step_license, self._build_step_password,
        self._build_step_progress, self._build_step_complete,
    ]
    builders[step]()
    self.btn_back.config(state="normal" if step > 0 else "disabled")
    if step == self.TOTAL_STEPS - 1:
        self.btn_next.config(text=self._txt("btn_finish"), command=self._on_finish)
    elif step == self.TOTAL_STEPS - 2:
        self.btn_next.config(text=self._txt("btn_install"), command=self._start_install)
    else:
        self.btn_next.config(text=self._txt("btn_next"), command=self._go_next)
    if step == 4:
        self.btn_next.config(state="disabled")
        self.btn_back.config(state="disabled")


def _go_next(self):
    """Advance to the next step with validation."""
    step = self.current_step.get()
    if step == 3 and not self._validate_password():
        return
    if step == 1 and not self.install_dir.get().strip():
        messagebox.showwarning(self._txt("error_title"), self._txt("error_create_dirs"))
        return
    if step < self.TOTAL_STEPS - 1:
        self._show_step(step + 1)


def _go_back(self):
    """Go back to the previous step."""
    step = self.current_step.get()
    if step > 0:
        self._show_step(step - 1)


def _on_cancel(self):
    """Handle cancel button or window close."""
    if messagebox.askyesno(self._txt("btn_cancel"), self._txt("confirm_cancel")):
        import logging
        logger = logging.getLogger("installer")
        logger.info("Installation cancelled by user")
        self.destroy()


def _on_finish(self):
    """Handle finish button click."""
    import logging
    logger = logging.getLogger("installer")
    logger.info("Installer closed by user (Finish)")
    self.destroy()


def _open_browser(self):
    """Open the app URL in the default browser."""
    import webbrowser
    from contextlib import suppress
    with suppress(OSError):
        webbrowser.open("http://localhost:8080")


def _on_language_change(self):
    """Re-render current step when language changes."""
    self._show_step(self.current_step.get())


def _browse_directory(self):
    """Open directory browser dialog."""
    chosen = filedialog.askdirectory(title=self._txt("dir_label"), initialdir=self.install_dir.get())
    if chosen:
        self.install_dir.set(chosen)


def _on_license_focus_in(self, event):
    """Clear placeholder text when license field gains focus."""
    if self.license_entry.get() == self._txt("license_key_placeholder"):
        self.license_entry.delete(0, "end")
        self.license_entry.config(foreground="black")


def _on_license_focus_out(self, event):
    """Restore placeholder text when license field loses focus."""
    if not self.license_entry.get().strip():
        self.license_entry.insert(0, self._txt("license_key_placeholder"))
        self.license_entry.config(foreground="gray")


def _validate_password(self) -> bool:
    """Validate password fields."""
    pw = self.admin_password.get()
    pw2 = self.admin_password_confirm.get()
    if len(pw) < 6:
        self.pw_validation_label.config(text=self._txt("password_too_short"))
        return False
    if pw != pw2:
        self.pw_validation_label.config(text=self._txt("password_mismatch"))
        return False
    self.pw_validation_label.config(text="")
    return True


# ── Step content builders ─────────────────────────────────────────────────


def _build_step_language(self):
    """Build language selection step."""
    ttk.Label(self.content_frame, text=self._txt("lang_label"), font=("Segoe UI", 11)).pack(anchor="w", pady=(10, 15))
    for code, label in [("es", "Espa\u00f1ol"), ("en", "English")]:
        ttk.Radiobutton(self.content_frame, text=label, variable=self.selected_lang, value=code, command=self._on_language_change).pack(anchor="w", padx=30, pady=5)
    ttk.Label(self.content_frame, text=self._txt("welcome"), font=("Segoe UI", 10), foreground="gray").pack(anchor="w", pady=(30, 0))


def _build_step_directory(self):
    """Build directory selection step."""
    ttk.Label(self.content_frame, text=self._txt("dir_label"), font=("Segoe UI", 11)).pack(anchor="w", pady=(10, 5))
    dir_frame = ttk.Frame(self.content_frame)
    dir_frame.pack(fill="x", pady=5)
    self.dir_entry = ttk.Entry(dir_frame, textvariable=self.install_dir, width=50)
    self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
    ttk.Button(dir_frame, text=self._txt("dir_browse"), command=self._browse_directory).pack(side="right")
    default_dir = self._txt("dir_default_win") if self._is_windows else self._txt("dir_default_linux")
    ttk.Label(self.content_frame, text=f"Por defecto: {default_dir}", font=("Segoe UI", 9), foreground="gray").pack(anchor="w", pady=(5, 0))
    ttk.Label(self.content_frame, text="Se requieren aproximadamente 100 MB de espacio libre.", font=("Segoe UI", 9), foreground="gray").pack(anchor="w", pady=(15, 0))


def _build_step_license(self):
    """Build license entry step."""
    ttk.Label(self.content_frame, text=self._txt("license_label"), font=("Segoe UI", 11)).pack(anchor="w", pady=(10, 15))
    self.license_entry = ttk.Entry(self.content_frame, textvariable=self.license_key, width=40)
    self.license_entry.pack(anchor="w", padx=20, pady=5)
    self.license_entry.insert(0, self._txt("license_key_placeholder"))
    self.license_entry.bind("<FocusIn>", self._on_license_focus_in)
    self.license_entry.bind("<FocusOut>", self._on_license_focus_out)
    self.license_entry.config(foreground="gray")
    ttk.Label(self.content_frame, text=self._txt("license_hint"), font=("Segoe UI", 9), foreground="gray").pack(anchor="w", padx=20, pady=(10, 0))


def _build_step_password(self):
    """Build password entry step."""
    ttk.Label(self.content_frame, text=self._txt("password_label"), font=("Segoe UI", 11)).pack(anchor="w", pady=(10, 5))
    self.pw_entry = ttk.Entry(self.content_frame, textvariable=self.admin_password, show="*", width=40)
    self.pw_entry.pack(anchor="w", padx=20, pady=5)
    ttk.Label(self.content_frame, text=self._txt("password_confirm"), font=("Segoe UI", 11)).pack(anchor="w", pady=(15, 5))
    self.pw_confirm_entry = ttk.Entry(self.content_frame, textvariable=self.admin_password_confirm, show="*", width=40)
    self.pw_confirm_entry.pack(anchor="w", padx=20, pady=5)
    self.pw_validation_label = ttk.Label(self.content_frame, text="", font=("Segoe UI", 9), foreground="red")
    self.pw_validation_label.pack(anchor="w", padx=20, pady=(10, 0))


def _build_step_progress(self):
    """Build installation progress step."""
    self.progress_label = ttk.Label(self.content_frame, text=self._txt("progress_creating_dirs"), font=("Segoe UI", 11))
    self.progress_label.pack(anchor="w", pady=(20, 10))
    self.progress_bar = ttk.Progressbar(self.content_frame, mode="determinate", maximum=100)
    self.progress_bar.pack(fill="x", pady=10)
    self.log_text = tk.Text(self.content_frame, height=8, state="disabled", font=("Consolas", 9), bg="#f5f5f5")
    self.log_text.pack(fill="both", expand=True, pady=(10, 0))


def _build_step_complete(self):
    """Build installation completion step."""
    ttk.Label(self.content_frame, text="\u2713", font=("Segoe UI", 48), foreground="green").pack(pady=(10, 5))
    ttk.Label(self.content_frame, text=self._txt("complete_message"), font=("Segoe UI", 12)).pack(pady=(0, 10))
    ttk.Label(self.content_frame, text=self._txt("complete_url"), font=("Segoe UI", 10), foreground="gray").pack()
    ttk.Label(self.content_frame, text="http://localhost:8080", font=("Segoe UI", 11, "bold"), foreground="#0066cc").pack(pady=(5, 15))
    ttk.Button(self.content_frame, text=self._txt("btn_open_browser"), command=self._open_browser).pack(pady=5)
    if hasattr(self, 'install_error') and self.install_error:
        ttk.Label(self.content_frame, text=f"\u26a0 {self.install_error}", font=("Segoe UI", 9), foreground="red").pack(pady=(10, 0))
