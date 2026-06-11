#!/usr/bin/env python3
"""
Workflow Determinista — GUI Installer Wizard
One-click installer with tkinter for Windows and Linux.
Works 100% offline — uses only stdlib + project imports.
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

# ── Ensure project root is on sys.path so we can import src.* ──────────────
INSTALLER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = INSTALLER_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── i18n strings ──────────────────────────────────────────────────────────
LANG = {
    "es": {
        "title": "Workflow Determinista — Instalador",
        "welcome": "Bienvenido al instalador de Workflow Determinista",
        "step_language": "Idioma",
        "step_directory": "Directorio de instalación",
        "step_license": "Licencia",
        "step_password": "Contraseña de administrador",
        "step_progress": "Instalando...",
        "step_complete": "Instalación completada",
        "lang_label": "Selecciona el idioma de la instalación:",
        "dir_label": "Directorio de instalación:",
        "dir_browse": "Examinar...",
        "dir_default_win": r"C:\WorkflowDeterminista",
        "dir_default_linux": "/opt/workflow-determinista",
        "license_label": "Introduce tu clave de licencia (opcional):",
        "license_hint": "Deja vacío para prueba gratuita de 30 días",
        "license_key_placeholder": "WFD-XXXX-XXXX-XXXX-XXXX",
        "password_label": "Contraseña de administrador:",
        "password_confirm": "Confirmar contraseña:",
        "password_mismatch": "Las contraseñas no coinciden",
        "password_too_short": "La contraseña debe tener al menos 6 caracteres",
        "btn_next": "Siguiente",
        "btn_back": "Atrás",
        "btn_install": "Instalar",
        "btn_finish": "Finalizar",
        "btn_cancel": "Cancelar",
        "btn_open_browser": "Abrir en el navegador",
        "progress_creating_dirs": "Creando directorios...",
        "progress_copying_files": "Copiando archivos...",
        "progress_creating_db": "Creando base de datos...",
        "progress_hashing_password": "Guardando contraseña...",
        "progress_configuring_license": "Configurando licencia...",
        "progress_configuring_autostart": "Configurando inicio automático...",
        "progress_starting_server": "Iniciando servidor...",
        "progress_done": "¡Instalación completada!",
        "complete_message": "Workflow Determinista se ha instalado correctamente.",
        "complete_url": "La aplicación estará disponible en:",
        "error_title": "Error de instalación",
        "error_create_dirs": "No se pudieron crear los directorios",
        "error_copy_files": "No se pudieron copiar los archivos",
        "error_database": "Error al crear la base de datos",
        "error_password": "Error al guardar la contraseña",
        "error_license": "Error al configurar la licencia",
        "error_autostart": "Error al configurar inicio automático",
        "error_server": "Error al iniciar el servidor",
        "error_bcrypt": "bcrypt no está instalado. Instala: pip install bcrypt",
        "confirm_cancel": "¿Seguro que deseas cancelar la instalación?",
        "trial_activated": "Modo prueba activado (30 días)",
        "license_activated": "Licencia activada correctamente",
    },
    "en": {
        "title": "Workflow Determinista — Installer",
        "welcome": "Welcome to the Workflow Determinista installer",
        "step_language": "Language",
        "step_directory": "Installation directory",
        "step_license": "License",
        "step_password": "Admin password",
        "step_progress": "Installing...",
        "step_complete": "Installation complete",
        "lang_label": "Select the installation language:",
        "dir_label": "Installation directory:",
        "dir_browse": "Browse...",
        "dir_default_win": r"C:\WorkflowDeterminista",
        "dir_default_linux": "/opt/workflow-determinista",
        "license_label": "Enter your license key (optional):",
        "license_hint": "Leave empty for a 30-day free trial",
        "license_key_placeholder": "WFD-XXXX-XXXX-XXXX-XXXX",
        "password_label": "Admin password:",
        "password_confirm": "Confirm password:",
        "password_mismatch": "Passwords do not match",
        "password_too_short": "Password must be at least 6 characters",
        "btn_next": "Next",
        "btn_back": "Back",
        "btn_install": "Install",
        "btn_finish": "Finish",
        "btn_cancel": "Cancel",
        "btn_open_browser": "Open in browser",
        "progress_creating_dirs": "Creating directories...",
        "progress_copying_files": "Copying files...",
        "progress_creating_db": "Creating database...",
        "progress_hashing_password": "Saving password...",
        "progress_configuring_license": "Configuring license...",
        "progress_configuring_autostart": "Configuring auto-start...",
        "progress_starting_server": "Starting server...",
        "progress_done": "Installation complete!",
        "complete_message": "Workflow Determinista has been installed successfully.",
        "complete_url": "The application will be available at:",
        "error_title": "Installation Error",
        "error_create_dirs": "Could not create directories",
        "error_copy_files": "Could not copy files",
        "error_database": "Error creating database",
        "error_password": "Error saving password",
        "error_license": "Error configuring license",
        "error_autostart": "Error configuring auto-start",
        "error_server": "Error starting server",
        "error_bcrypt": "bcrypt is not installed. Install: pip install bcrypt",
        "confirm_cancel": "Are you sure you want to cancel the installation?",
        "trial_activated": "Trial mode activated (30 days)",
        "license_activated": "License activated successfully",
    },
}

IS_WINDOWS = platform.system() == "Windows"
APP_URL = "http://localhost:8080"


# ── Logging ───────────────────────────────────────────────────────────────
def _setup_installer_logging():
    log_dir = Path.home() / ".workflow_determinista"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "installer.log"
    logging.basicConfig(
        filename=str(log_file),
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("installer")


logger = _setup_installer_logging()


# ═══════════════════════════════════════════════════════════════════════════
#  InstallerWizard — Main tkinter application
# ═══════════════════════════════════════════════════════════════════════════
class InstallerWizard(tk.Tk):
    """Multi-step installation wizard for Workflow Determinista."""

    TOTAL_STEPS = 6

    def __init__(self):
        super().__init__()
        self.selected_lang = tk.StringVar(value="es")
        self.install_dir = tk.StringVar(
            value=LANG["es"]["dir_default_win"] if IS_WINDOWS else LANG["es"]["dir_default_linux"]
        )
        self.license_key = tk.StringVar(value="")
        self.admin_password = tk.StringVar(value="")
        self.admin_password_confirm = tk.StringVar(value="")
        self.current_step = tk.IntVar(value=0)
        self.install_error = None

        self._init_window()
        self._build_ui()
        self._show_step(0)
        logger.info("Installer wizard started")

    # ── Window setup ───────────────────────────────────────────────────────

    def _init_window(self):
        self.title("Workflow Determinista — Installer")
        self.geometry("640x520")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 640) // 2
        y = (self.winfo_screenheight() - 520) // 2
        self.geometry(f"640x520+{x}+{y}")

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top header ─────────────────────────────────────────────────
        self.header_frame = ttk.Frame(self, padding=10)
        self.header_frame.pack(fill="x")

        self.header_label = ttk.Label(
            self.header_frame,
            text="Workflow Determinista",
            font=("Segoe UI", 16, "bold"),
        )
        self.header_label.pack()

        self.step_indicator = ttk.Label(
            self.header_frame,
            text="",
            font=("Segoe UI", 9),
        )
        self.step_indicator.pack()

        # ── Progress bar at the top of the content area ────────────────
        self.top_progress = ttk.Progressbar(
            self,
            mode="determinate",
            maximum=self.TOTAL_STEPS,
        )
        self.top_progress.pack(fill="x", padx=20)

        # ── Content frame ──────────────────────────────────────────────
        self.content_frame = ttk.Frame(self, padding=20)
        self.content_frame.pack(fill="both", expand=True)

        # ── Navigation buttons ─────────────────────────────────────────
        self.nav_frame = ttk.Frame(self, padding=(20, 5, 20, 10))
        self.nav_frame.pack(fill="x")

        self.btn_back = ttk.Button(
            self.nav_frame,
            text="← Atrás",
            command=self._go_back,
        )
        self.btn_back.pack(side="left")

        self.btn_cancel = ttk.Button(
            self.nav_frame,
            text="Cancelar",
            command=self._on_cancel,
        )
        self.btn_cancel.pack(side="left", padx=(10, 0))

        self.btn_next = ttk.Button(
            self.nav_frame,
            text="Siguiente →",
            command=self._go_next,
        )
        self.btn_next.pack(side="right")

    # ── Step containers ────────────────────────────────────────────────────

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _txt(self, key):
        """Get localized text for the current language."""
        return LANG[self.selected_lang.get()].get(key, key)

    def _show_step(self, step: int):
        self.current_step.set(step)
        self.top_progress["value"] = step + 1
        self._clear_content()

        # Update step indicator
        step_names = [
            self._txt("step_language"),
            self._txt("step_directory"),
            self._txt("step_license"),
            self._txt("step_password"),
            self._txt("step_progress"),
            self._txt("step_complete"),
        ]
        self.step_indicator.config(text=f"Paso {step + 1} de {self.TOTAL_STEPS} — {step_names[step]}")

        # Dispatch to step builder
        builders = [
            self._build_step_language,
            self._build_step_directory,
            self._build_step_license,
            self._build_step_password,
            self._build_step_progress,
            self._build_step_complete,
        ]
        builders[step]()

        # Navigation button state
        self.btn_back.config(state="normal" if step > 0 else "disabled")
        if step == self.TOTAL_STEPS - 1:
            self.btn_next.config(text=self._txt("btn_finish"), command=self._on_finish)
        elif step == self.TOTAL_STEPS - 2:
            self.btn_next.config(text=self._txt("btn_install"), command=self._start_install)
        elif step == 0:
            self.btn_next.config(text=self._txt("btn_next"), command=self._go_next)
        else:
            self.btn_next.config(text=self._txt("btn_next"), command=self._go_next)

        # Disable next on progress step
        if step == 4:
            self.btn_next.config(state="disabled")
            self.btn_back.config(state="disabled")

    # ── Step 1: Language ───────────────────────────────────────────────────

    def _build_step_language(self):
        ttk.Label(
            self.content_frame,
            text=self._txt("lang_label"),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(10, 15))

        for code, label in [("es", "Español"), ("en", "English")]:
            ttk.Radiobutton(
                self.content_frame,
                text=label,
                variable=self.selected_lang,
                value=code,
                command=self._on_language_change,
            ).pack(anchor="w", padx=30, pady=5)

        ttk.Label(
            self.content_frame,
            text=self._txt("welcome"),
            font=("Segoe UI", 10),
            foreground="gray",
        ).pack(anchor="w", pady=(30, 0))

    def _on_language_change(self):
        """Re-render current step when language changes."""
        # Update default install dir label
        self._show_step(self.current_step.get())

    # ── Step 2: Installation directory ─────────────────────────────────────

    def _build_step_directory(self):
        ttk.Label(
            self.content_frame,
            text=self._txt("dir_label"),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(10, 5))

        dir_frame = ttk.Frame(self.content_frame)
        dir_frame.pack(fill="x", pady=5)

        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.install_dir, width=50)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        ttk.Button(
            dir_frame,
            text=self._txt("dir_browse"),
            command=self._browse_directory,
        ).pack(side="right")

        # Info label
        default_dir = self._txt("dir_default_win") if IS_WINDOWS else self._txt("dir_default_linux")
        ttk.Label(
            self.content_frame,
            text=f"Por defecto: {default_dir}",
            font=("Segoe UI", 9),
            foreground="gray",
        ).pack(anchor="w", pady=(5, 0))

        # Disk space warning (informational)
        ttk.Label(
            self.content_frame,
            text="Se requieren aproximadamente 100 MB de espacio libre.",
            font=("Segoe UI", 9),
            foreground="gray",
        ).pack(anchor="w", pady=(15, 0))

    def _browse_directory(self):
        chosen = filedialog.askdirectory(
            title=self._txt("dir_label"),
            initialdir=self.install_dir.get(),
        )
        if chosen:
            self.install_dir.set(chosen)

    # ── Step 3: License key ────────────────────────────────────────────────

    def _build_step_license(self):
        ttk.Label(
            self.content_frame,
            text=self._txt("license_label"),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(10, 15))

        self.license_entry = ttk.Entry(
            self.content_frame,
            textvariable=self.license_key,
            width=40,
        )
        self.license_entry.pack(anchor="w", padx=20, pady=5)

        # Placeholder style
        self.license_entry.insert(0, self._txt("license_key_placeholder"))
        self.license_entry.bind("<FocusIn>", self._on_license_focus_in)
        self.license_entry.bind("<FocusOut>", self._on_license_focus_out)
        self.license_entry.config(foreground="gray")

        ttk.Label(
            self.content_frame,
            text=self._txt("license_hint"),
            font=("Segoe UI", 9),
            foreground="gray",
        ).pack(anchor="w", padx=20, pady=(10, 0))

    def _on_license_focus_in(self, event):
        if self.license_entry.get() == self._txt("license_key_placeholder"):
            self.license_entry.delete(0, "end")
            self.license_entry.config(foreground="black")

    def _on_license_focus_out(self, event):
        if not self.license_entry.get().strip():
            self.license_entry.insert(0, self._txt("license_key_placeholder"))
            self.license_entry.config(foreground="gray")

    # ── Step 4: Admin password ─────────────────────────────────────────────

    def _build_step_password(self):
        ttk.Label(
            self.content_frame,
            text=self._txt("password_label"),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(10, 5))

        self.pw_entry = ttk.Entry(
            self.content_frame,
            textvariable=self.admin_password,
            show="*",
            width=40,
        )
        self.pw_entry.pack(anchor="w", padx=20, pady=5)

        ttk.Label(
            self.content_frame,
            text=self._txt("password_confirm"),
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(15, 5))

        self.pw_confirm_entry = ttk.Entry(
            self.content_frame,
            textvariable=self.admin_password_confirm,
            show="*",
            width=40,
        )
        self.pw_confirm_entry.pack(anchor="w", padx=20, pady=5)

        # Validation label
        self.pw_validation_label = ttk.Label(
            self.content_frame,
            text="",
            font=("Segoe UI", 9),
            foreground="red",
        )
        self.pw_validation_label.pack(anchor="w", padx=20, pady=(10, 0))

    def _validate_password(self) -> bool:
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

    # ── Step 5: Progress ───────────────────────────────────────────────────

    def _build_step_progress(self):
        self.progress_label = ttk.Label(
            self.content_frame,
            text=self._txt("progress_creating_dirs"),
            font=("Segoe UI", 11),
        )
        self.progress_label.pack(anchor="w", pady=(20, 10))

        self.progress_bar = ttk.Progressbar(
            self.content_frame,
            mode="determinate",
            maximum=100,
        )
        self.progress_bar.pack(fill="x", pady=10)

        # Log area
        self.log_text = tk.Text(
            self.content_frame,
            height=8,
            state="disabled",
            font=("Consolas", 9),
            bg="#f5f5f5",
        )
        self.log_text.pack(fill="both", expand=True, pady=(10, 0))

    def _log_progress(self, message: str):
        """Append a message to the progress log area."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        logger.info(message)

    def _update_progress(self, percent: int, message: str):
        self.progress_bar["value"] = percent
        self.progress_label.config(text=message)
        self._log_progress(message)
        self.update_idletasks()

    # ── Step 6: Completion ─────────────────────────────────────────────────

    def _build_step_complete(self):
        # Success icon + message
        ttk.Label(
            self.content_frame,
            text="✓",
            font=("Segoe UI", 48),
            foreground="green",
        ).pack(pady=(10, 5))

        ttk.Label(
            self.content_frame,
            text=self._txt("complete_message"),
            font=("Segoe UI", 12),
        ).pack(pady=(0, 10))

        ttk.Label(
            self.content_frame,
            text=self._txt("complete_url"),
            font=("Segoe UI", 10),
            foreground="gray",
        ).pack()

        ttk.Label(
            self.content_frame,
            text=APP_URL,
            font=("Segoe UI", 11, "bold"),
            foreground="#0066cc",
        ).pack(pady=(5, 15))

        # Open browser button
        ttk.Button(
            self.content_frame,
            text=self._txt("btn_open_browser"),
            command=self._open_browser,
        ).pack(pady=5)

        if self.install_error:
            ttk.Label(
                self.content_frame,
                text=f"⚠ {self.install_error}",
                font=("Segoe UI", 9),
                foreground="red",
            ).pack(pady=(10, 0))

    # ── Navigation ─────────────────────────────────────────────────────────

    def _go_next(self):
        step = self.current_step.get()

        # Validate password on step 3 → 4
        if step == 3:
            if not self._validate_password():
                return

        # Validate directory on step 1 → 2
        if step == 1:
            if not self.install_dir.get().strip():
                messagebox.showwarning(
                    self._txt("error_title"),
                    self._txt("error_create_dirs"),
                )
                return

        if step < self.TOTAL_STEPS - 1:
            self._show_step(step + 1)

    def _go_back(self):
        step = self.current_step.get()
        if step > 0:
            self._show_step(step - 1)

    def _on_cancel(self):
        if messagebox.askyesno(
            self._txt("btn_cancel"),
            self._txt("confirm_cancel"),
        ):
            logger.info("Installation cancelled by user")
            self.destroy()

    def _on_finish(self):
        logger.info("Installer closed by user (Finish)")
        self.destroy()

    def _open_browser(self):
        try:
            webbrowser.open(APP_URL)
        except OSError:
            pass

    # ═══════════════════════════════════════════════════════════════════════
    #  Installation logic — runs in a background thread
    # ═══════════════════════════════════════════════════════════════════════

    def _start_install(self):
        """Kick off the installation in a background thread."""
        # Validate password one last time
        if not self._validate_password():
            return

        self.btn_next.config(state="disabled")
        self.btn_back.config(state="disabled")
        self.btn_cancel.config(state="disabled")

        thread = threading.Thread(target=self._run_install, daemon=True)
        thread.start()

    def _run_install(self):
        """Perform all installation steps. Updates the GUI from the main thread."""
        try:
            self._install_step_create_dirs()
            self._install_step_copy_files()
            self._install_step_create_database()
            self._install_step_save_password()
            self._install_step_configure_license()
            self._install_step_configure_autostart()
            self._install_step_start_server()

            # Success — go to completion screen
            self._update_progress(100, self._txt("progress_done"))
            self.after(0, lambda: self._show_step(self.TOTAL_STEPS - 1))

        except InstallError as exc:
            self.install_error = str(exc)
            logger.error(f"Installation failed: {exc}")
            self._log_progress(f"ERROR: {exc}")
            self.after(0, lambda: self._show_step(self.TOTAL_STEPS - 1))

        except Exception as exc:
            self.install_error = str(exc)
            logger.exception("Unexpected installation error")
            self._log_progress(f"FATAL ERROR: {exc}")
            self.after(0, lambda: self._show_step(self.TOTAL_STEPS - 1))


class InstallError(Exception):
    """Raised when an installation step fails."""

    pass


# ═══════════════════════════════════════════════════════════════════════════
#  Installation step implementations (methods added to InstallerWizard)
# ═══════════════════════════════════════════════════════════════════════════


def _install_step_create_dirs(self):
    """Step 1: Create the installation directory structure."""
    self._update_progress(5, self._txt("progress_creating_dirs"))

    install_path = Path(self.install_dir.get())
    subdirs = [
        "src/web/templates",
        "src/web/static",
        "src/data",
        "src/license",
        "src/utils",
        "src/workflow",
        "src/events",
        "src/tools/crm",
        "src/tools/inventory",
        "src/tools/invoice",
        "src/tools/notification",
        "src/tools/autopilot",
        "src/tools/logic_gate",
        "src/nlp",
        "src/tests",
        "backups",
    ]

    try:
        for subdir in subdirs:
            (install_path / subdir).mkdir(parents=True, exist_ok=True)

        # Also create the data directory in user home
        data_dir = Path.home() / ".workflow_determinista"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "backups").mkdir(parents=True, exist_ok=True)

        self._update_progress(15, self._txt("progress_creating_dirs"))
    except OSError as exc:
        raise InstallError(f"{self._txt('error_create_dirs')}: {exc}")


def _install_step_copy_files(self):
    """Step 2: Copy all source files to the installation directory."""
    self._update_progress(15, self._txt("progress_copying_files"))

    src_dir = PROJECT_ROOT / "src"
    install_path = Path(self.install_dir.get())

    if not src_dir.exists():
        raise InstallError(f"{self._txt('error_copy_files')}: source dir not found at {src_dir}")

    try:
        # Copy entire src/ tree
        dest_src = install_path / "src"
        if dest_src.exists():
            shutil.rmtree(dest_src)
        shutil.copytree(
            src_dir,
            dest_src,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.pyo",
                ".git",
            ),
        )

        # Copy config files
        for config_file in ["requirements.txt", "README.md"]:
            src_file = PROJECT_ROOT / config_file
            if src_file.exists():
                shutil.copy2(src_file, install_path / config_file)

        # Copy installer itself
        installer_src = INSTALLER_DIR / "installer_main.py"
        if installer_src.exists():
            dest_installer = install_path / "installer" / "installer_main.py"
            dest_installer.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(installer_src, dest_installer)

        self._update_progress(35, self._txt("progress_copying_files"))
    except OSError as exc:
        raise InstallError(f"{self._txt('error_copy_files')}: {exc}")


def _install_step_create_database(self):
    """Step 3: Create the SQLite database at ~/.workflow_determinista/."""
    self._update_progress(40, self._txt("progress_creating_db"))

    try:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        # The DatabaseManager singleton creates all tables on __init__
        # Just confirm it's accessible
        db.get_connection()
        db.close_all()
        self._update_progress(55, self._txt("progress_creating_db"))
    except Exception as exc:
        raise InstallError(f"{self._txt('error_database')}: {exc}")


def _install_step_save_password(self):
    """Step 4: Hash and store the admin password with bcrypt (cost=12)."""
    self._update_progress(55, self._txt("progress_hashing_password"))

    try:
        import bcrypt
    except ImportError:
        raise InstallError(self._txt("error_bcrypt"))

    try:
        password = self.admin_password.get().encode("utf-8")
        hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)).decode("utf-8")

        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        db.set_setting("admin_password_hash", hashed)
        db.audit("installer.password_set", "Admin password configured during installation")
        db.close_all()

        self._update_progress(70, self._txt("progress_hashing_password"))
    except Exception as exc:
        raise InstallError(f"{self._txt('error_password')}: {exc}")


def _install_step_configure_license(self):
    """Step 5: Store the license key or start a 30-day trial."""
    self._update_progress(70, self._txt("progress_configuring_license"))

    try:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()

        key = self.license_key.get().strip().upper()
        # Filter out placeholder text
        if key and key.startswith("WFD-") and "XXXX" not in key:
            # Validate and activate the license key
            from src.license.validator import LicenseValidator

            validator = LicenseValidator()
            result = validator.validate(key)
            if result["valid"]:
                validator.activate_key(
                    key,
                    result.get("type", "individual"),
                    result.get("client_name", ""),
                )
                self._log_progress(self._txt("license_activated"))
            else:
                # Key didn't validate — fall back to trial
                self._log_progress(
                    f"License validation failed ({result.get('reason', 'unknown')}), falling back to trial mode."
                )
                validator._start_trial()
                self._log_progress(self._txt("trial_activated"))
        else:
            # No valid key — start trial
            from src.license.validator import LicenseValidator

            validator = LicenseValidator()
            validator._start_trial()
            self._log_progress(self._txt("trial_activated"))

        db.audit("installer.license_configured", "License configured during installation")
        db.close_all()

        self._update_progress(82, self._txt("progress_configuring_license"))
    except Exception as exc:
        raise InstallError(f"{self._txt('error_license')}: {exc}")


def _install_step_configure_autostart(self):
    """Step 6: Configure auto-start on boot (Windows Registry or Linux .desktop)."""
    self._update_progress(82, self._txt("progress_configuring_autostart"))

    try:
        install_path = Path(self.install_dir.get())
        python_executable = sys.executable

        if IS_WINDOWS:
            self._configure_autostart_windows(install_path, python_executable)
        else:
            self._configure_autostart_linux(install_path, python_executable)

        self._update_progress(90, self._txt("progress_configuring_autostart"))
    except Exception as exc:
        # Auto-start is non-critical; log the error but don't abort
        self._log_progress(f"WARNING: {self._txt('error_autostart')}: {exc}")
        logger.warning(f"Auto-start configuration failed (non-critical): {exc}")


def _configure_autostart_windows(self, install_path: Path, python_executable: str):
    """Add a Registry entry to start the app on login (Windows)."""
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_value = f'"{python_executable}" "{install_path / "src" / "main.py"}"'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as reg_key:
            winreg.SetValueEx(reg_key, "WorkflowDeterminista", 0, winreg.REG_SZ, app_value)
        self._log_progress("Windows auto-start configured (Registry)")
    except ImportError:
        self._log_progress("winreg not available — skipping Windows auto-start")
    except OSError as exc:
        self._log_progress(f"Could not write to Windows Registry: {exc}")


def _configure_autostart_linux(self, install_path: Path, python_executable: str):
    """Create a .desktop file in ~/.config/autostart/ (Linux)."""
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)

    desktop_entry = f"""[Desktop Entry]
Type=Application
Name=Workflow Determinista
Comment=Workflow Automation Engine
Exec={python_executable} {install_path / "src" / "main.py"}
Icon=workflow-determinista
Terminal=false
Categories=Office;Network;
X-GNOME-Autostart-enabled=true
"""
    desktop_file = autostart_dir / "workflow-determinista.desktop"
    desktop_file.write_text(desktop_entry, encoding="utf-8")
    # Make it executable
    desktop_file.chmod(0o755)
    self._log_progress(f"Linux auto-start configured ({desktop_file})")


def _install_step_start_server(self):
    """Step 7: Start the web server and open the browser."""
    self._update_progress(95, self._txt("progress_starting_server"))

    try:
        # We start the server as a subprocess so the installer GUI can close
        # without killing the server. Use the installed copy of the app.
        install_path = Path(self.install_dir.get())
        main_script = install_path / "src" / "main.py"
        python_executable = sys.executable

        if not main_script.exists():
            # Fall back to the project source (dev mode)
            main_script = PROJECT_ROOT / "src" / "main.py"

        # Set WFD_DATA_DIR to ensure correct data location
        env = os.environ.copy()
        env["WFD_DATA_DIR"] = str(Path.home() / ".workflow_determinista")

        # Start the server as a detached process
        if IS_WINDOWS:
            # On Windows, use CREATE_NEW_PROCESS_GROUP to detach
            subprocess.Popen(
                [python_executable, str(main_script)],
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # On Linux, start with nohup-like behavior
            subprocess.Popen(
                [python_executable, str(main_script)],
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Give the server a moment to start, then open browser
        import time

        time.sleep(2)
        try:
            webbrowser.open(APP_URL)
        except OSError:
            pass

        self._update_progress(100, self._txt("progress_done"))
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError(f"{self._txt('error_server')}: {exc}")


# Bind the install step methods to the class
InstallerWizard._install_step_create_dirs = _install_step_create_dirs
InstallerWizard._install_step_copy_files = _install_step_copy_files
InstallerWizard._install_step_create_database = _install_step_create_database
InstallerWizard._install_step_save_password = _install_step_save_password
InstallerWizard._install_step_configure_license = _install_step_configure_license
InstallerWizard._install_step_configure_autostart = _install_step_configure_autostart
InstallerWizard._configure_autostart_windows = _configure_autostart_windows
InstallerWizard._configure_autostart_linux = _configure_autostart_linux
InstallerWizard._install_step_start_server = _install_step_start_server


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════


def main():
    """Launch the installer wizard."""
    logger.info("=" * 60)
    logger.info("Workflow Determinista Installer starting")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info("=" * 60)

    try:
        app = InstallerWizard()
        app.mainloop()
    except Exception as exc:
        logger.exception("Fatal installer error")
        try:
            messagebox.showerror("Fatal Error", str(exc))
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
