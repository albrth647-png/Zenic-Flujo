"""Installation step functions for the Workflow Determinista installer.

These are module-level functions that get bound to InstallerWizard
as methods via monkey-patching (preserving the original pattern).
Each function receives 'self' as the InstallerWizard instance.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from installer.config import IS_WINDOWS, PROJECT_ROOT, logger


class InstallError(Exception):
    """Raised when an installation step fails."""
    pass


def _install_step_create_dirs(self):
    """Step 1: Create the installation directory structure."""
    self._update_progress(5, self._txt("progress_creating_dirs"))

    install_path = Path(self.install_dir.get())
    subdirs = [
        "src/web/templates", "src/web/static", "src/data",
        "src/license", "src/utils", "src/workflow", "src/events",
        "src/tools/crm", "src/tools/inventory", "src/tools/invoice",
        "src/tools/notification", "src/tools/autopilot", "src/tools/logic_gate",
        "src/nlp", "src/tests", "backups",
    ]

    try:
        for subdir in subdirs:
            (install_path / subdir).mkdir(parents=True, exist_ok=True)
        data_dir = Path.home() / ".workflow_determinista"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "backups").mkdir(parents=True, exist_ok=True)
        self._update_progress(15, self._txt("progress_creating_dirs"))
    except OSError as exc:
        raise InstallError(f"{self._txt('error_create_dirs')}: {exc}") from exc


def _install_step_copy_files(self):
    """Step 2: Copy all source files to the installation directory."""
    from installer.config import INSTALLER_DIR

    self._update_progress(15, self._txt("progress_copying_files"))
    src_dir = PROJECT_ROOT / "src"
    install_path = Path(self.install_dir.get())

    if not src_dir.exists():
        raise InstallError(f"{self._txt('error_copy_files')}: source dir not found at {src_dir}")

    try:
        dest_src = install_path / "src"
        if dest_src.exists():
            shutil.rmtree(dest_src)
        shutil.copytree(src_dir, dest_src, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".git"))
        for config_file in ["requirements.txt", "README.md"]:
            src_file = PROJECT_ROOT / config_file
            if src_file.exists():
                shutil.copy2(src_file, install_path / config_file)
        installer_src = INSTALLER_DIR / "installer_main.py"
        if installer_src.exists():
            dest_installer = install_path / "installer" / "installer_main.py"
            dest_installer.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(installer_src, dest_installer)
        self._update_progress(35, self._txt("progress_copying_files"))
    except OSError as exc:
        raise InstallError(f"{self._txt('error_copy_files')}: {exc}") from exc


def _install_step_create_database(self):
    """Step 3: Create the SQLite database at ~/.workflow_determinista/."""
    self._update_progress(40, self._txt("progress_creating_db"))
    try:
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()
        db.get_connection()
        db.close_all()
        self._update_progress(55, self._txt("progress_creating_db"))
    except Exception as exc:
        raise InstallError(f"{self._txt('error_database')}: {exc}") from exc


def _install_step_save_password(self):
    """Step 4: Hash and store the admin password with bcrypt (cost=12)."""
    self._update_progress(55, self._txt("progress_hashing_password"))
    try:
        import bcrypt
    except ImportError:
        raise InstallError(self._txt("error_bcrypt")) from None

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
        raise InstallError(f"{self._txt('error_password')}: {exc}") from exc


def _install_step_configure_license(self):
    """Step 5: Store the license key or start a 30-day trial."""
    self._update_progress(70, self._txt("progress_configuring_license"))
    try:
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()
        key = self.license_key.get().strip().upper()
        if key and key.startswith("WFD-") and "XXXX" not in key:
            from src.license.validator import LicenseValidator
            validator = LicenseValidator()
            result = validator.validate(key)
            if result["valid"]:
                validator.activate_key(key, result.get("type", "individual"), result.get("client_name", ""))
                self._log_progress(self._txt("license_activated"))
            else:
                self._log_progress(f"License validation failed ({result.get('reason', 'unknown')}), falling back to trial mode.")
                validator._start_trial()
                self._log_progress(self._txt("trial_activated"))
        else:
            from src.license.validator import LicenseValidator
            validator = LicenseValidator()
            validator._start_trial()
            self._log_progress(self._txt("trial_activated"))
        db.audit("installer.license_configured", "License configured during installation")
        db.close_all()
        self._update_progress(82, self._txt("progress_configuring_license"))
    except Exception as exc:
        raise InstallError(f"{self._txt('error_license')}: {exc}") from exc


def _install_step_configure_autostart(self):
    """Step 6: Configure auto-start on boot (Windows Registry or Linux .desktop)."""
    self._update_progress(82, self._txt("progress_configuring_autostart"))
    try:
        install_path = Path(self.install_dir.get())
        python_executable = sys.executable
        if IS_WINDOWS:
            _configure_autostart_windows(self, install_path, python_executable)
        else:
            _configure_autostart_linux(self, install_path, python_executable)
        self._update_progress(90, self._txt("progress_configuring_autostart"))
    except Exception as exc:
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
    desktop_file.chmod(0o755)
    self._log_progress(f"Linux auto-start configured ({desktop_file})")


def _install_step_start_server(self):
    """Step 7: Start the web server and open the browser."""
    self._update_progress(95, self._txt("progress_starting_server"))
    try:
        from installer.config import PROJECT_ROOT

        install_path = Path(self.install_dir.get())
        main_script = install_path / "src" / "main.py"
        python_executable = sys.executable
        if not main_script.exists():
            main_script = PROJECT_ROOT / "src" / "main.py"
        env = os.environ.copy()
        env["WFD_DATA_DIR"] = str(Path.home() / ".workflow_determinista")
        if IS_WINDOWS:
            subprocess.Popen(
                [python_executable, str(main_script)],
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [python_executable, str(main_script)],
                env=env, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        import time
        time.sleep(2)
        from contextlib import suppress
        with suppress(OSError):
            import webbrowser
            webbrowser.open("http://localhost:8080")
        self._update_progress(100, self._txt("progress_done"))
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError(f"{self._txt('error_server')}: {exc}") from exc
