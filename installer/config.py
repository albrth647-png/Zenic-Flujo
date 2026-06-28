"""Configuration constants, i18n strings, and logging setup for the installer.

Extracted from installer/installer_main.py to keep the main file slim.
"""

import logging
import platform
import sys
from pathlib import Path

# ── Ensure project root is on sys.path so we can import src.* ──────────────
INSTALLER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = INSTALLER_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IS_WINDOWS = platform.system() == "Windows"
APP_URL = "http://localhost:8080"

# ── i18n strings ──────────────────────────────────────────────────────────
LANG = {
    "es": {
        "title": "Workflow Determinista — Instalador",
        "welcome": "Bienvenido al instalador de Workflow Determinista",
        "step_language": "Idioma",
        "step_directory": "Directorio de instalaci\u00f3n",
        "step_license": "Licencia",
        "step_password": "Contrase\u00f1a de administrador",
        "step_progress": "Instalando...",
        "step_complete": "Instalaci\u00f3n completada",
        "lang_label": "Selecciona el idioma de la instalaci\u00f3n:",
        "dir_label": "Directorio de instalaci\u00f3n:",
        "dir_browse": "Examinar...",
        "dir_default_win": r"C:\WorkflowDeterminista",
        "dir_default_linux": "/opt/workflow-determinista",
        "license_label": "Introduce tu clave de licencia (opcional):",
        "license_hint": "Deja vac\u00edo para prueba gratuita de 30 d\u00edas",
        "license_key_placeholder": "WFD-XXXX-XXXX-XXXX-XXXX",
        "password_label": "Contrase\u00f1a de administrador:",
        "password_confirm": "Confirmar contrase\u00f1a:",
        "password_mismatch": "Las contrase\u00f1as no coinciden",
        "password_too_short": "La contrase\u00f1a debe tener al menos 6 caracteres",
        "btn_next": "Siguiente",
        "btn_back": "Atr\u00e1s",
        "btn_install": "Instalar",
        "btn_finish": "Finalizar",
        "btn_cancel": "Cancelar",
        "btn_open_browser": "Abrir en el navegador",
        "progress_creating_dirs": "Creando directorios...",
        "progress_copying_files": "Copiando archivos...",
        "progress_creating_db": "Creando base de datos...",
        "progress_hashing_password": "Guardando contrase\u00f1a...",
        "progress_configuring_license": "Configurando licencia...",
        "progress_configuring_autostart": "Configurando inicio autom\u00e1tico...",
        "progress_starting_server": "Iniciando servidor...",
        "progress_done": "\u00a1Instalaci\u00f3n completada!",
        "complete_message": "Workflow Determinista se ha instalado correctamente.",
        "complete_url": "La aplicaci\u00f3n estar\u00e1 disponible en:",
        "error_title": "Error de instalaci\u00f3n",
        "error_create_dirs": "No se pudieron crear los directorios",
        "error_copy_files": "No se pudieron copiar los archivos",
        "error_database": "Error al crear la base de datos",
        "error_password": "Error al guardar la contrase\u00f1a",
        "error_license": "Error al configurar la licencia",
        "error_autostart": "Error al configurar inicio autom\u00e1tico",
        "error_server": "Error al iniciar el servidor",
        "error_bcrypt": "bcrypt no est\u00e1 instalado. Instala: pip install bcrypt",
        "confirm_cancel": "\u00bfSeguro que deseas cancelar la instalaci\u00f3n?",
        "trial_activated": "Modo prueba activado (30 d\u00edas)",
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


def setup_installer_logging() -> logging.Logger:
    """Set up logging for the installer to ~/.workflow_determinista/installer.log."""
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


logger = setup_installer_logging()
