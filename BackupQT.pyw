from PyQt5.QtCore import QThread, pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMenuBar, QAction, QGroupBox,
    QDialog, QProgressBar, QMessageBox, QCheckBox, QComboBox, QGridLayout, QMenu
)
from typing import cast, List
import sys
import subprocess
import os
import json
import shutil
import re
import stat
from datetime import datetime
import traceback

# Import help texts
from help_texts import HELP_LOG_TITLE, HELP_LOG_TEXT, HELP_ACTIONS_TITLE, HELP_ACTIONS_TEXT

# BASE_DIR is the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Resolve configuration directory with preference for project root when writable,
# otherwise fall back to per-user AppData. This makes the app portable outside
# protected locations like Program Files, while still working there without admin.
def _is_writable_directory(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        test_path = os.path.join(d, ".perm_test.tmp")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
        return True
    except Exception:
        return False

def _get_appdata_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    cfg_dir = os.path.join(appdata, "Python_Backup")
    try:
        os.makedirs(cfg_dir, exist_ok=True)
    except Exception:
        import tempfile
        cfg_dir = os.path.join(tempfile.gettempdir(), "Python_Backup")
        os.makedirs(cfg_dir, exist_ok=True)
    return cfg_dir

APPDATA_DIR = _get_appdata_dir()
if _is_writable_directory(BASE_DIR):
    CONFIG_DIR = BASE_DIR
    ALT_CONFIG_DIR = APPDATA_DIR
else:
    CONFIG_DIR = APPDATA_DIR
    ALT_CONFIG_DIR = BASE_DIR

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
ALT_SETTINGS_FILE = os.path.join(ALT_CONFIG_DIR, "settings.json")
CRASH_LOG = os.path.join(CONFIG_DIR, "last_crash.log")

# Windows long-path helper (for Python-side file ops). Avoid passing \\?\ to Robocopy.
def _to_long_path(path: str) -> str:
    p = os.path.normpath(path)
    if len(p) >= 248 or len(os.path.basename(p)) >= 255:
        # Apply only for Python internal access if path is long
        if p.startswith("\\\\"):  # UNC path \\server\share
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + p
    return p

# Worker class for running copy in a background thread
class CopyWorker(QObject):
    finished = pyqtSignal(list, list)
    error = pyqtSignal(Exception)

    def __init__(self, files_to_copy):
        super().__init__()
        self.files_to_copy = files_to_copy
        self.errors = []

    def run(self):
        for i, (src_fp, dst_fp) in enumerate(self.files_to_copy, 1):
            dst_dir = os.path.dirname(dst_fp)
            if not os.path.exists(dst_dir):
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                except Exception as e:
                    # Record directory creation failure and skip this file
                    self.errors.append(f"{src_fp} -> {dst_fp}: cannot create destination folder '{dst_dir}': {e}")
                    continue
            try:
                shutil.copy2(src_fp, dst_fp)
            except Exception as e:
                self.errors.append(f"{src_fp} -> {dst_fp}: {e}")
        self.finished.emit(self.files_to_copy, self.errors)
    # ...existing code...

# Helper function to convert Windows path to WSL path
def win_to_wsl_path(win_path):
    # Normalize slashes
    path = win_path.replace('\\', '/')
    # Match drive letter
    match = re.match(r'^([A-Za-z]):/(.*)', path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2)
        return f"/mnt/{drive}/{rest}"
    return path

# Worker class for running sync in a background thread using Robocopy
class SyncWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    progress = pyqtSignal(str)

    def __init__(self, source_folder: str, destination_folder: str, log_enabled: bool = False, log_path: str | None = None):
        super().__init__()
        self.source_folder = source_folder
        self.destination_folder = destination_folder
        self.log_enabled = log_enabled
        self.log_path = log_path
        self._exception: Exception | None = None
        self._rc: int | None = None

    def run(self):
        try:
            if not os.path.isdir(self.source_folder):
                raise Exception(f"Source folder not found or not a directory: {self.source_folder}")
            if not os.path.isdir(self.destination_folder):
                raise Exception(f"Destination folder not found or not a directory: {self.destination_folder}")
            # Normalize to Windows-style backslashes for Robocopy (no \\?\ prefix)
            src = os.path.normpath(self.source_folder)
            dst = os.path.normpath(self.destination_folder)
            # Robocopy returns codes < 8 for success, >= 8 for failure
            cmd = [
                "robocopy",
                src,
                dst,
                "/MIR",
                "/COPY:DAT",
                "/DCOPY:T",
                "/R:3",
                "/W:5",
                "/MT:16",
                "/NP",
                "/NFL",
                "/NDL",
                "/NJS",
                "/NJH",
            ]
            if self.log_enabled and self.log_path:
                log_arg = os.path.normpath(self.log_path)
                cmd += ["/TEE", f"/LOG:{log_arg}"]
            # Optional: write the command to the log for diagnostics
            if self.log_enabled and self.log_path:
                try:
                    with open(self.log_path, 'a', encoding='utf-8') as f:
                        f.write("\n[Sync cmd] " + " ".join(cmd) + "\n")
                except Exception:
                    pass

            # Helper: quick verification summary similar to Copy
            def _verify(src_root_in: str, dst_root_in: str) -> str:
                try:
                    src_root_abs = os.path.abspath(src_root_in)
                    dst_root_abs = os.path.abspath(dst_root_in)
                    # Robocopy /MIR will mirror the source leaf under destination
                    src_leaf = os.path.basename(os.path.normpath(src_root_abs))
                    dst_effective = os.path.join(dst_root_abs, src_leaf)
                    if os.path.isdir(dst_effective):
                        dst_root_abs = dst_effective
                    src_files: dict[str, int] = {}
                    for dp, dn, fn in os.walk(src_root_abs):
                        for f in fn:
                            p = os.path.join(dp, f)
                            rel = os.path.relpath(p, src_root_abs)
                            try:
                                src_files[rel] = os.stat(p).st_size
                            except Exception:
                                src_files[rel] = -1
                    dst_files: dict[str, int] = {}
                    for dp, dn, fn in os.walk(dst_root_abs):
                        for f in fn:
                            p = os.path.join(dp, f)
                            rel = os.path.relpath(p, dst_root_abs)
                            try:
                                dst_files[rel] = os.stat(p).st_size
                            except Exception:
                                dst_files[rel] = -1
                    missing = [r for r in src_files.keys() if r not in dst_files]
                    extra = [r for r in dst_files.keys() if r not in src_files]
                    mismatch = [r for r in src_files.keys() if r in dst_files and src_files[r] != dst_files[r]]
                    summary = (
                        f"Verify: src={len(src_files)} dst={len(dst_files)}; missing={len(missing)}; extra={len(extra)}; size-mismatch={len(mismatch)}"
                    )
                    if self.log_enabled and self.log_path and (missing or extra or mismatch):
                        try:
                            with open(self.log_path, 'a', encoding='utf-8') as f:
                                def _dump(label: str, items: list[str]):
                                    f.write(f"\n{label} (first 10):\n")
                                    for it in items[:10]:
                                        f.write(f"  {it}\n")
                                _dump("Missing", missing)
                                _dump("Extra", extra)
                                _dump("Size-mismatch", mismatch)
                        except Exception:
                            pass
                    return summary
                except Exception:
                    return "Verify skipped (error during verification)"

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            assert proc.stdout is not None
            robolog: list[str] = []
            for line in proc.stdout:
                line = line.strip()
                if line:
                    robolog.append(line)
                    self.progress.emit(line)
            proc.wait()
            self._rc = proc.returncode
            if proc.returncode is None:
                self._exception = Exception("Robocopy did not return a code.")
                self.error.emit(self._exception)
            elif proc.returncode >= 8:
                # Failure but still append verification summary to log if enabled
                ver = _verify(src, dst)
                if self.log_enabled and self.log_path:
                    try:
                        with open(self.log_path, 'a', encoding='utf-8') as f:
                            f.write(
                                f"\nSync completed (with failures) from {self.source_folder} to {self.destination_folder} (rc={proc.returncode})\n{ver}\n"
                            )
                    except Exception:
                        pass
                tail = "\n".join(robolog[-10:]) if robolog else ""
                self._exception = Exception((f"Robocopy failed with code {proc.returncode}.\n" + tail).strip())
                self.error.emit(self._exception)
            else:
                self._exception = None
                # Append a brief summary to the log (if enabled)
                ver = _verify(src, dst)
                if self.log_enabled and self.log_path:
                    try:
                        with open(self.log_path, 'a', encoding='utf-8') as f:
                            f.write(
                                f"\nSync completed from {self.source_folder} to {self.destination_folder} (rc={self._rc})\n{ver}\n"
                            )
                    except Exception:
                        pass
        except Exception as e:
            self._exception = e
            self.error.emit(e)
        finally:
            self.finished.emit()
    # ...existing code...

# ADB features removed

class ArchiveMirrorWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    progress = pyqtSignal(str)

    def __init__(self, source_folder: str, destination_folder: str, log_enabled: bool = False, log_path: str | None = None, keep_archive_sessions: int = 5):
        super().__init__()
        self.source_folder = source_folder
        self.destination_folder = destination_folder
        self.log_enabled = log_enabled
        self.log_path = log_path
        self.keep_archive_sessions = keep_archive_sessions

    def _files_differ(self, src_fp: str, dst_fp: str) -> bool:
        try:
            s1 = os.stat(src_fp)
            s2 = os.stat(dst_fp)
            if s1.st_size != s2.st_size:
                return True
            # Compare mtimes with small tolerance using float seconds (avoid int truncation)
            return abs(s1.st_mtime - s2.st_mtime) > 1.0
        except FileNotFoundError:
            return True

    def _ensure_writable(self, path: str) -> None:
        try:
            os.chmod(path, stat.S_IWRITE)
        except Exception:
            pass

    def _append_log(self, line: str) -> None:
        if self.log_enabled and self.log_path:
            try:
                with open(self.log_path, 'a', encoding='utf-8') as f:
                    f.write(line.rstrip("\n") + "\n")
            except Exception:
                pass

    def _prune_old_sessions(self, archive_dir: str, base: str) -> None:
        """Keep only the most recent N archive sessions for this base."""
        try:
            entries = []
            for name in os.listdir(archive_dir):
                full = os.path.join(archive_dir, name)
                if os.path.isdir(full) and name.startswith(base + "-"):
                    entries.append(name)
            if len(entries) <= self.keep_archive_sessions:
                return
            entries.sort(reverse=True)  # Newest first due to ISO-like timestamp in name
            to_remove = entries[self.keep_archive_sessions:]
            removed = 0
            for name in to_remove:
                full = os.path.join(archive_dir, name)
                def _onerror(func, path, exc_info):
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(full, onerror=_onerror)
                    removed += 1
                    self._append_log(f"Pruned old archive session: {name}")
                except Exception as e:
                    self._append_log(f"ERROR pruning archive session {name}: {e}")
            kept = len(entries) - removed
            self._append_log(f"Archive retention: kept={min(kept, self.keep_archive_sessions)} removed={removed}")
        except Exception as e:
            self._append_log(f"ERROR during archive pruning: {e}")

    def run(self):
        try:
            src_root = os.path.abspath(self.source_folder)
            dst_root = os.path.abspath(self.destination_folder)
            if not os.path.isdir(src_root):
                raise Exception(f"Source folder not found or not a directory: {src_root}")
            if not os.path.isdir(dst_root):
                raise Exception(f"Destination folder not found or not a directory: {dst_root}")
            dest_dir = dst_root.rstrip('\\/')
            base = os.path.basename(dest_dir)
            archive_dir = dest_dir + "-Archive"
            os.makedirs(archive_dir, exist_ok=True)
            session = datetime.now().strftime("%Y-%m-%d_%H-%M")
            session_dir = os.path.join(archive_dir, f"{base}-{session}")
            os.makedirs(session_dir, exist_ok=True)

            self.progress.emit("Scanning source and destination...")
            # Build sets of relative file paths
            src_files: set[str] = set()
            for dp, dn, fn in os.walk(src_root):
                for f in fn:
                    abs_fp = os.path.join(dp, f)
                    rel = os.path.relpath(abs_fp, src_root)
                    src_files.add(rel)

            dst_files: set[str] = set()
            for dp, dn, fn in os.walk(dst_root):
                # Skip archive folder
                if os.path.commonpath([dp, archive_dir]) == archive_dir:
                    continue
                for f in fn:
                    abs_fp = os.path.join(dp, f)
                    rel = os.path.relpath(abs_fp, dst_root)
                    dst_files.add(rel)

            # Determine overwrites and deletions
            overwrites = [rel for rel in src_files.intersection(dst_files)
                          if self._files_differ(os.path.join(src_root, rel), os.path.join(dst_root, rel))]
            deletes = list(dst_files.difference(src_files))

            total_moves = len(overwrites) + len(deletes)
            moved = 0
            for rel in overwrites:
                dst_fp = os.path.join(dst_root, rel)
                arch_fp = os.path.join(session_dir, rel)
                os.makedirs(os.path.dirname(arch_fp), exist_ok=True)
                self._ensure_writable(dst_fp)
                try:
                    shutil.move(dst_fp, arch_fp)
                except Exception as e:
                    self._append_log(f"ERROR archiving overwrite {rel}: {e}")
                    raise
                moved += 1
                msg = f"Archived overwrite: {rel} ({moved}/{total_moves})"
                self.progress.emit(msg)
                self._append_log(msg)

            for rel in deletes:
                dst_fp = os.path.join(dst_root, rel)
                arch_fp = os.path.join(session_dir, rel)
                os.makedirs(os.path.dirname(arch_fp), exist_ok=True)
                self._ensure_writable(dst_fp)
                try:
                    shutil.move(dst_fp, arch_fp)
                except Exception as e:
                    self._append_log(f"ERROR archiving delete {rel}: {e}")
                    raise
                moved += 1
                msg = f"Archived delete: {rel} ({moved}/{total_moves})"
                self.progress.emit(msg)
                self._append_log(msg)

            # Now mirror using robocopy
            self.progress.emit("Running Robocopy /MIR...")
            # Use standard paths for Robocopy
            src_root = os.path.normpath(src_root)
            dst_root = os.path.normpath(dst_root)
            cmd = [
                "robocopy",
                src_root,
                dst_root,
                "/MIR",
                "/COPY:DAT",
                "/DCOPY:T",
                "/R:3",
                "/W:5",
                "/MT:16",
                "/NP",
                "/NFL",
                "/NDL",
                "/NJS",
                "/NJH",
            ]
            if self.log_enabled and self.log_path:
                log_arg = os.path.normpath(self.log_path)
                cmd += ["/TEE", f"/LOG:{log_arg}"]
            if self.log_enabled and self.log_path:
                try:
                    with open(self.log_path, 'a', encoding='utf-8') as f:
                        f.write("\n[Archive cmd] " + " ".join(cmd) + "\n")
                except Exception:
                    pass
            # Simple verify similar to Copy/Sync
            def _verify(src_root_in: str, dst_root_in: str) -> str:
                try:
                    src_root_abs = os.path.abspath(src_root_in)
                    dst_root_abs = os.path.abspath(dst_root_in)
                    src_leaf = os.path.basename(os.path.normpath(src_root_abs))
                    dst_effective = os.path.join(dst_root_abs, src_leaf)
                    if os.path.isdir(dst_effective):
                        dst_root_abs = dst_effective
                    src_files: dict[str, int] = {}
                    for dp, dn, fn in os.walk(src_root_abs):
                        for f in fn:
                            p = os.path.join(dp, f)
                            rel = os.path.relpath(p, src_root_abs)
                            try:
                                src_files[rel] = os.stat(p).st_size
                            except Exception:
                                src_files[rel] = -1
                    dst_files: dict[str, int] = {}
                    for dp, dn, fn in os.walk(dst_root_abs):
                        for f in fn:
                            p = os.path.join(dp, f)
                            rel = os.path.relpath(p, dst_root_abs)
                            try:
                                dst_files[rel] = os.stat(p).st_size
                            except Exception:
                                dst_files[rel] = -1
                    missing = [r for r in src_files.keys() if r not in dst_files]
                    extra = [r for r in dst_files.keys() if r not in src_files]
                    mismatch = [r for r in src_files.keys() if r in dst_files and src_files[r] != dst_files[r]]
                    summary = (
                        f"Verify: src={len(src_files)} dst={len(dst_files)}; missing={len(missing)}; extra={len(extra)}; size-mismatch={len(mismatch)}"
                    )
                    if self.log_enabled and self.log_path and (missing or extra or mismatch):
                        try:
                            with open(self.log_path, 'a', encoding='utf-8') as f:
                                def _dump(label: str, items: list[str]):
                                    f.write(f"\n{label} (first 10):\n")
                                    for it in items[:10]:
                                        f.write(f"  {it}\n")
                                _dump("Missing", missing)
                                _dump("Extra", extra)
                                _dump("Size-mismatch", mismatch)
                        except Exception:
                            pass
                    return summary
                except Exception:
                    return "Verify skipped (error during verification)"

            # Run Robocopy with streaming output and log tail on failure
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            assert proc.stdout is not None
            robolog: list[str] = []
            for line in proc.stdout:
                line = line.strip()
                if line:
                    robolog.append(line)
                    self.progress.emit(line)
            proc.wait()
            if proc.returncode >= 8:
                tail = "\n".join(robolog[-10:]) if robolog else ""
                raise Exception((f"Robocopy /MIR failed with code {proc.returncode}.\n" + tail).strip())

            ver = _verify(src_root, dst_root)
            self._append_log("Archive mirror completed successfully.")
            if self.log_enabled and self.log_path:
                try:
                    with open(self.log_path, 'a', encoding='utf-8') as f:
                        f.write(ver + "\n")
                except Exception:
                    pass
            # Prune older sessions if configured
            try:
                self._prune_old_sessions(archive_dir, base)
            except Exception:
                pass
            self.finished.emit()
        except Exception as e:
            self.error.emit(e)

class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.create_log = False  # Ensure attribute exists before any method uses it
        self.log_dir = ""
        self.mirror = False
        self.selected_action = "Sync"  # Default value
        self.settings = self.load_settings()
        self.create_log = self.settings.get("create_log", False)
        self.log_dir = self.settings.get("log_dir", "")
        self.mirror = self.settings.get("mirror", False)
        self.selected_action = self.settings.get("selected_action", "Sync")
        self.keep_archive_sessions = int(self.settings.get("keep_archive_sessions", 5))
    # ADB features removed
        self.init_ui()
        self.resize(*self.settings["window_size"])
        self.entry_source.setText(self.settings["source_dir"])
        self.entry_destination.setText(self.settings["destination_dir"])
        # Set combo_action after UI is initialized
        if hasattr(self, "combo_action"):
            self.combo_action.setCurrentText(self.selected_action)

    def load_settings(self):
        default_settings = {
            "window_size": [1200, 600],
            "source_dir": "",
            "destination_dir": "",
            "create_log": False,
            "log_dir": "",
            "mirror": False,
            "selected_action": "Sync",
            "keep_archive_sessions": 5
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
            except Exception:
                settings = default_settings
        else:
            # Migration between locations: if an alt settings file exists, import it
            if os.path.exists(ALT_SETTINGS_FILE):
                try:
                    with open(ALT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                except Exception:
                    settings = default_settings
            else:
                settings = default_settings
            # Persist into chosen CONFIG_DIR if possible
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=4)
            except Exception:
                # If we cannot create in CONFIG_DIR, keep using in-memory defaults
                pass
        # Ensure selected_action is present
        if "selected_action" not in settings:
            settings["selected_action"] = "Sync"
        return settings
    
    def save_settings(self):
        # Get current action from combo_action if available
        selected_action = "Sync"
        if hasattr(self, "combo_action"):
            selected_action = self.combo_action.currentText()
        settings = {
            "window_size": [self.width(), self.height()],
            "source_dir": self.entry_source.text(),
            "destination_dir": self.entry_destination.text(),
            "create_log": getattr(self, "create_log", False),
            "log_dir": getattr(self, "log_dir", ""),
            "mirror": getattr(self, "mirror", False),
            "selected_action": selected_action,
            "keep_archive_sessions": int(getattr(self, "keep_archive_sessions", 5))
        }
        # Atomic write to avoid partial files on crash
        tmp_path = SETTINGS_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, SETTINGS_FILE)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def init_ui(self):
        self.setWindowTitle("Backup Script")
        self.resize(1200, 600)

        # Menu Bar
        menubar = QMenuBar(self)
        file_menu = cast(QMenu, menubar.addMenu("File"))

        # Add Help menu (after menubar is created)
        help_menu = cast(QMenu, menubar.addMenu("Help"))
        help_log_action = QAction("How to Specify Log File", self)
        help_log_action.triggered.connect(self.show_help_log_dialog)
        help_menu.addAction(help_log_action)
        help_actions_action = QAction("Backup Actions", self)
        help_actions_action.triggered.connect(self.show_help_actions_dialog)
        help_menu.addAction(help_actions_action)
    
        source_action = QAction("Source Folder", self)
        source_action.triggered.connect(self.browse_source)
        file_menu.addAction(source_action)
    
        dest_action = QAction("Destination Folder", self)
        dest_action.triggered.connect(self.browse_destination)
        file_menu.addAction(dest_action)
    
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(lambda: self.menu_settings())
        file_menu.addAction(settings_action)
    
        exit_action = QAction("Exit", self)
        def _on_exit_clicked() -> None:
            self.close()
        exit_action.triggered.connect(_on_exit_clicked)
        file_menu.addAction(exit_action)
    
        # Widget creation
        #Source and Destination Labels and Entries
        self.label_source = QLabel("Source Folder:")
        self.entry_source = QLineEdit()
        # Style is now loaded globally from style.qss
        self.button_browse_source = QPushButton("Select Source")
        self.button_browse_source.setFixedWidth(200)
        # Style is now loaded globally from style.qss
        self.button_browse_source.setToolTip("Select the source folder for backup")
        self.button_browse_source.clicked.connect(self.browse_source)
        # Destination Labels and Entries
        self.label_destination = QLabel("Destination Folder:")
        self.entry_destination = QLineEdit()
        # Style is now loaded globally from style.qss
        self.button_browse_destination = QPushButton("Select Destination")
        self.button_browse_destination.setFixedWidth(200)
        # Style is now loaded globally from style.qss
        self.button_browse_destination.setToolTip("Select the destination folder for backup")
        self.button_browse_destination.clicked.connect(self.browse_destination)

        # Create Backup Action Button
        self.button_backup = QPushButton("Backup")
        self.button_backup.setFixedWidth(120)
        # Style is now loaded globally from style.qss
        self.button_backup.setToolTip("Start the backup process")
        self.button_backup.clicked.connect(self.backup)

        # Create Cancel button
        self.button_cancel = QPushButton("Quit") 
        # Object name for Styling
        self.button_cancel.setObjectName("button_cancel")
        self.button_cancel.setFixedWidth(120)
        # Style is now loaded globally from style.qss
        self.button_cancel.setToolTip("Exit the application")
        def _on_quit_clicked() -> None:
            self.close()
        self.button_cancel.clicked.connect(_on_quit_clicked)
    
        self.status_label = QLabel("")
    
        layout = QVBoxLayout()
        layout.setMenuBar(menubar)
    
        # Source row
        source_row = QHBoxLayout()
        source_row.addWidget(self.label_source)
        source_row.addWidget(self.entry_source)
        source_row.addWidget(self.button_browse_source)
        layout.addLayout(source_row)

        layout.addSpacing(15)
    
        # Destination row
        dest_row = QHBoxLayout()
        dest_row.addWidget(self.label_destination)
        dest_row.addWidget(self.entry_destination)
        dest_row.addWidget(self.button_browse_destination)
        layout.addLayout(dest_row)

        layout.addSpacing(100)

        # Add vertical spacer for extra space between destination row and group box
        #from PyQt5.QtWidgets import QSpacerItem, QSizePolicy
        #layout.addSpacerItem(QSpacerItem(40, 60, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # Group box for backup actions
        group_box = QGroupBox("Actions")
        # Style is now loaded globally from style.qss
        # Create a horizontal layout for Backup and Cancel buttons
        button_row = QHBoxLayout()
        button_row.addWidget(self.button_backup)
        button_row.addWidget(self.button_cancel)

        # Center the button row in the group box
        group_layout = QVBoxLayout()

        # Create widgets first
        self.checkbox_log = QCheckBox("Create log file")
        self.checkbox_log.setChecked(self.create_log)
        label_actions = QLabel("Backup Actions:")
        label_actions.setObjectName("label_actions")
        self.combo_action = QComboBox()
        self.combo_action.addItems(["Sync", "Copy", "Archive"])
        # Set initial value from settings
        self.combo_action.setCurrentText(getattr(self, "selected_action", "Sync"))
        self.combo_action.setToolTip("Select the backup action: Sync, Copy, or Archive.")
        self.combo_action.setObjectName("combo_action")  # For style.qss styling

        # Now create the layout and add widgets
        log_action_row = QGridLayout()
        log_action_row.addWidget(self.checkbox_log, 0, 0)
        log_action_row.addWidget(label_actions, 0, 1)
        log_action_row.addWidget(self.combo_action, 0, 2)
        group_layout.addLayout(log_action_row)

        # Disable if no log file path is set
        if not self.log_dir:
            self.checkbox_log.setEnabled(False)
            self.checkbox_log.setToolTip("Specify a log file path in Settings to enable logging.")
        else:
            self.checkbox_log.setEnabled(True)
            self.checkbox_log.setToolTip("Log file will be created at the specified path.")
        def on_log_checkbox_changed(state):
            self.create_log = bool(state)
            self.save_settings()
        self.checkbox_log.stateChanged.connect(on_log_checkbox_changed)

        group_layout.addSpacing(25)
        group_layout.addLayout(button_row)
        # Add more widgets here in the future as needed
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def browse_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.entry_source.setText(folder)

    def browse_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.entry_destination.setText(folder)

    def update_current_folder_labels(self):
        self.current_source_label.setText(f"Current Source: {self.entry_source.text()}")
        self.current_destination_label.setText(f"Current Destination: {self.entry_destination.text()}")


    def backup(self):
        source_folder = self.entry_source.text()
        destination_folder = self.entry_destination.text()


        # Validate paths with dialog
        if not os.path.exists(source_folder) or not os.path.isdir(source_folder):
            msg = QMessageBox(self)
            msg.setWindowTitle("Invalid Source Folder")
            msg.setIcon(QMessageBox.Critical)
            msg.setText("The source folder path is invalid or does not exist.\n\nPlease select a valid source folder.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            return
        if not os.path.exists(destination_folder) or not os.path.isdir(destination_folder):
            msg = QMessageBox(self)
            msg.setWindowTitle("Invalid Destination Folder")
            msg.setIcon(QMessageBox.Critical)
            msg.setText("The destination folder path is invalid or does not exist.\n\nPlease select a valid destination folder or create it first in File Explorer.")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            return

        # Check log file path availability if logging is enabled
        log_writable = True
        log_error = None
        if getattr(self, 'create_log', False) and self.log_dir:
            log_dirname = os.path.dirname(self.log_dir) or '.'
            if not os.path.exists(log_dirname):
                log_writable = False
                log_error = f"The log file directory does not exist: {log_dirname}"
            else:
                try:
                    # Try to open for writing (will not erase file, just test)
                    with open(self.log_dir, 'a', encoding='utf-8'):
                        pass
                except Exception as e:
                    log_writable = False
                    log_error = f"Cannot write to log file: {e}"

        if getattr(self, 'create_log', False) and self.log_dir and not log_writable:
            msg = QMessageBox(self)
            msg.setWindowTitle("Log File Not Available")
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"The log file cannot be created or written to.\n\n{log_error}\n\nDo you want to continue the backup without logging?")
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Ok)
            result = msg.exec_()
            if result == QMessageBox.Cancel:
                return
            # If OK, proceed with backup but skip logging
            log_writable = False

        action = self.combo_action.currentText()
        if action == "Sync":
            # Show streaming progress from Robocopy
            progress_dialog = QDialog(self)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # type: ignore[attr-defined]
            progress_dialog.setWindowTitle("Sync Progress")
            progress_dialog.setWindowModality(Qt.ApplicationModal)  # type: ignore[attr-defined]
            progress_dialog.setFixedSize(900, 180)
            vbox = QVBoxLayout(progress_dialog)
            label = QLabel("Mirroring with Robocopy...")
            vbox.addWidget(label)
            current_line = QLabel("")
            current_line.setWordWrap(True)
            vbox.addWidget(current_line)
            progress_dialog.show()
            QApplication.processEvents()

            # Set up worker and thread
            log_enabled = (getattr(self, 'create_log', False) and bool(self.log_dir) and bool(log_writable))
            log_path = self.log_dir if log_enabled else None
            self.sync_thread = QThread()
            self.sync_worker = SyncWorker(source_folder, destination_folder, log_enabled, log_path)
            self.sync_worker.moveToThread(self.sync_thread)

            def on_sync_finished():
                progress_dialog.close()
                self.sync_thread.quit()
                self.sync_thread.wait()
                # If there was an error, it will be handled by error signal
                if not hasattr(self.sync_worker, '_exception') or self.sync_worker._exception is None:
                    # Robocopy codes 1–7 indicate success with copies/extra files etc.
                    rc = getattr(self.sync_worker, '_rc', 0) or 0
                    note = ""
                    if rc in (1, 2, 3, 5, 6, 7):
                        note = f" (Robocopy code {rc}: changes were made)"
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Sync Completed")
                    msg.setIcon(QMessageBox.Information)
                    msg.setText("Sync completed successfully." + note)
                    msg.setStandardButtons(QMessageBox.Ok)
                    msg.exec_()

            def on_sync_error(e):
                progress_dialog.close()
                self.sync_thread.quit()
                self.sync_thread.wait()
                msg = QMessageBox(self)
                msg.setWindowTitle("Sync Failed")
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"Sync failed: {e}")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

            def on_sync_progress(text: str):
                current_line.setText(text)
                QApplication.processEvents()

            self.sync_thread.started.connect(self.sync_worker.run)
            self.sync_worker.finished.connect(on_sync_finished)
            self.sync_worker.error.connect(on_sync_error)
            self.sync_worker.progress.connect(on_sync_progress)
            self.sync_worker.finished.connect(self.sync_worker.deleteLater)
            self.sync_thread.finished.connect(self.sync_thread.deleteLater)
            self.sync_thread.start()

        elif action == "Copy":
            # Robocopy copy (no /MIR). Copies new/changed files, preserves attrs/timestamps.
            progress_dialog = QDialog(self)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # type: ignore[attr-defined]
            progress_dialog.setWindowTitle("Copy Progress")
            progress_dialog.setWindowModality(Qt.ApplicationModal)  # type: ignore[attr-defined]
            progress_dialog.setFixedSize(900, 180)
            vbox = QVBoxLayout(progress_dialog)
            label = QLabel("Copying with Robocopy (no mirror)...")
            vbox.addWidget(label)
            current_line = QLabel("")
            current_line.setWordWrap(True)
            vbox.addWidget(current_line)
            error_label = QLabel("Errors: 0")
            vbox.addWidget(error_label)
            progress_dialog.show()
            QApplication.processEvents()

            class CopyRobocopyWorker(QObject):
                finished = pyqtSignal()
                error = pyqtSignal(Exception)
                progress = pyqtSignal(str)
                stats = pyqtSignal(int)  # emits current error count

                def __init__(self, src: str, dst: str, log_enabled: bool = False, log_path: str | None = None):
                    super().__init__()
                    self.src = src
                    self.dst = dst
                    self.log_enabled = log_enabled
                    self.log_path = log_path
                    self._rc: int | None = None
                    self.error_count: int = 0
                    self._verify_summary: str | None = None
                    self.sample_errors: list[str] = []

                def _verify(self) -> str:
                    try:
                        src_root = os.path.abspath(self.src)
                        dst_root = os.path.abspath(self.dst)
                        # Robocopy typically creates the source leaf folder under dst.
                        # If that folder exists, verify against dst/leaf instead of dst.
                        src_leaf = os.path.basename(os.path.normpath(src_root))
                        dst_effective = os.path.join(dst_root, src_leaf)
                        if os.path.isdir(dst_effective):
                            dst_root = dst_effective
                        src_files: dict[str, int] = {}
                        for dp, dn, fn in os.walk(src_root):
                            for f in fn:
                                p = os.path.join(dp, f)
                                rel = os.path.relpath(p, src_root)
                                try:
                                    src_files[rel] = os.stat(p).st_size
                                except Exception:
                                    src_files[rel] = -1
                        dst_files: dict[str, int] = {}
                        for dp, dn, fn in os.walk(dst_root):
                            for f in fn:
                                p = os.path.join(dp, f)
                                rel = os.path.relpath(p, dst_root)
                                try:
                                    dst_files[rel] = os.stat(p).st_size
                                except Exception:
                                    dst_files[rel] = -1
                        missing = [r for r in src_files.keys() if r not in dst_files]
                        extra = [r for r in dst_files.keys() if r not in src_files]
                        mismatch = [r for r in src_files.keys() if r in dst_files and src_files[r] != dst_files[r]]
                        summary = (
                            f"Verify: src={len(src_files)} dst={len(dst_files)}; missing={len(missing)}; extra={len(extra)}; size-mismatch={len(mismatch)}"
                        )
                        if self.log_enabled and self.log_path and (missing or extra or mismatch):
                            try:
                                with open(self.log_path, 'a', encoding='utf-8') as f:
                                    def _dump(label: str, items: list[str]):
                                        f.write(f"\n{label} (first 10):\n")
                                        for it in items[:10]:
                                            f.write(f"  {it}\n")
                                    _dump("Missing", missing)
                                    _dump("Extra", extra)
                                    _dump("Size-mismatch", mismatch)
                            except Exception:
                                pass
                        return summary
                    except Exception:
                        return "Verify skipped (error during verification)"

                def run(self):
                    try:
                        if not os.path.isdir(self.src):
                            raise Exception(f"Source folder not found or not a directory: {self.src}")
                        if not os.path.isdir(self.dst):
                            raise Exception(f"Destination folder not found or not a directory: {self.dst}")
                        # Use standard Windows paths for Robocopy
                        src = os.path.normpath(self.src)
                        dst = os.path.normpath(self.dst)
                        cmd = [
                            "robocopy",
                            src,
                            dst,
                            "/E",
                            "/COPY:DAT",
                            "/DCOPY:T",
                            "/R:3",
                            "/W:5",
                            "/MT:16",
                            "/NP",
                            "/NFL",
                            "/NDL",
                            "/NJS",
                            "/NJH",
                        ]
                        if self.log_enabled and self.log_path:
                            log_arg = os.path.normpath(self.log_path)
                            cmd += ["/TEE", f"/LOG:{log_arg}"]
                        if self.log_enabled and self.log_path:
                            try:
                                with open(self.log_path, 'a', encoding='utf-8') as f:
                                    f.write("\n[Copy cmd] " + " ".join(cmd) + "\n")
                            except Exception:
                                pass
                        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            stdin=subprocess.DEVNULL,
                            creationflags=creationflags,
                        )
                        assert proc.stdout is not None
                        robolog: list[str] = []
                        for line in proc.stdout:
                            line = line.strip()
                            if line:
                                # Track error lines so UI can show a count
                                if "ERROR " in line:
                                    try:
                                        self.error_count += 1
                                        self.stats.emit(self.error_count)
                                        if len(self.sample_errors) < 10:
                                            self.sample_errors.append(line)
                                    except Exception:
                                        pass
                                robolog.append(line)
                                self.progress.emit(line)
                        proc.wait()
                        self._rc = proc.returncode
                        if proc.returncode is None:
                            raise Exception("Robocopy did not return a code.")
                        if proc.returncode >= 8:
                            # Treat as failure but still verify and log
                            ver = self._verify()
                            self._verify_summary = ver
                            if self.log_enabled and self.log_path:
                                try:
                                    with open(self.log_path, 'a', encoding='utf-8') as f:
                                        f.write(
                                            f"\nCopy completed (with failures) from {self.src} to {self.dst} (rc={self._rc}); errors={self.error_count}\n{ver}\n"
                                        )
                                except Exception:
                                    pass
                            tail = "\n".join(robolog[-10:]) if robolog else ""
                            raise Exception((f"Robocopy failed with code {proc.returncode}.\n" + tail).strip())
                        # Success; append summary
                        ver = self._verify()
                        self._verify_summary = ver
                        if self.log_enabled and self.log_path:
                            try:
                                with open(self.log_path, 'a', encoding='utf-8') as f:
                                    f.write(
                                        f"\nCopy completed from {self.src} to {self.dst} (rc={self._rc}); errors={self.error_count}\n{ver}\n"
                                    )
                            except Exception:
                                pass
                        self.finished.emit()
                    except Exception as e:
                        self.error.emit(e)

            log_enabled = (getattr(self, 'create_log', False) and bool(self.log_dir) and bool(log_writable))
            log_path = self.log_dir if log_enabled else None

            self.copy_thread = QThread()
            self.copy_worker = CopyRobocopyWorker(source_folder, destination_folder, log_enabled, log_path)
            self.copy_worker.moveToThread(self.copy_thread)

            def on_copy_finished():
                progress_dialog.close()
                self.copy_thread.quit()
                self.copy_thread.wait()
                msg = QMessageBox(self)
                msg.setWindowTitle("Copy Completed")
                msg.setIcon(QMessageBox.Information)
                # Include a brief note if errors occurred (e.g., file in use)
                errs = getattr(self.copy_worker, 'error_count', 0) or 0
                note = f" with {errs} errors (see log)" if errs else ""
                text = "Copy completed successfully" + note + "."
                # If logging disabled and there were errors, include a few sample lines
                if errs and not (getattr(self, 'create_log', False) and bool(self.log_dir)):
                    samples = getattr(self.copy_worker, 'sample_errors', [])
                    if samples:
                        text += "\n\nSample errors:" + "\n" + "\n".join(samples[:5])
                else:
                    text += "\n\nA quick verification summary was written to the log."
                msg.setText(text)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

            def on_copy_error(e: Exception):
                progress_dialog.close()
                self.copy_thread.quit()
                self.copy_thread.wait()
                msg = QMessageBox(self)
                msg.setWindowTitle("Copy Failed")
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"Copy failed: {e}")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

            def on_copy_progress(text: str):
                current_line.setText(text)
                QApplication.processEvents()

            def on_copy_stats(count: int):
                error_label.setText(f"Errors: {count}")

            self.copy_thread.started.connect(self.copy_worker.run)
            self.copy_worker.finished.connect(on_copy_finished)
            self.copy_worker.error.connect(on_copy_error)
            self.copy_worker.progress.connect(on_copy_progress)
            self.copy_worker.stats.connect(on_copy_stats)
            self.copy_worker.finished.connect(self.copy_worker.deleteLater)
            self.copy_thread.finished.connect(self.copy_thread.deleteLater)
            self.copy_thread.start()

        elif action == "Archive":
            # Show a dialog while archiving & mirroring
            progress_dialog = QDialog(self)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # type: ignore[attr-defined]
            progress_dialog.setWindowTitle("Archive Progress")
            progress_dialog.setWindowModality(Qt.ApplicationModal)  # type: ignore[attr-defined]
            progress_dialog.setFixedSize(700, 160)
            vbox = QVBoxLayout(progress_dialog)
            label = QLabel("Archiving changed/deleted files and mirroring with Robocopy...")
            vbox.addWidget(label)
            current_label = QLabel("")
            current_label.setWordWrap(True)
            vbox.addWidget(current_label)
            progress_dialog.show()
            QApplication.processEvents()

            log_enabled = (getattr(self, 'create_log', False) and bool(self.log_dir) and bool(log_writable))
            log_path = self.log_dir if log_enabled else None

            self.archive_thread = QThread()
            self.archive_worker = ArchiveMirrorWorker(source_folder, destination_folder, log_enabled, log_path, getattr(self, 'keep_archive_sessions', 5))
            self.archive_worker.moveToThread(self.archive_thread)

            def on_finished():
                progress_dialog.close()
                self.archive_thread.quit()
                self.archive_thread.wait()
                msg = QMessageBox(self)
                msg.setWindowTitle("Archive Completed Successfully")
                msg.setIcon(QMessageBox.Information)
                msg.setText("Archive completed successfully.")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

            def on_error(e: Exception):
                progress_dialog.close()
                self.archive_thread.quit()
                self.archive_thread.wait()
                msg = QMessageBox(self)
                msg.setWindowTitle("Archive Failed")
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"Archive failed: {e}")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

            def on_progress(text: str):
                current_label.setText(text)
                QApplication.processEvents()

            self.archive_thread.started.connect(self.archive_worker.run)
            self.archive_worker.finished.connect(on_finished)
            self.archive_worker.error.connect(on_error)
            self.archive_worker.progress.connect(on_progress)
            self.archive_worker.finished.connect(self.archive_worker.deleteLater)
            self.archive_thread.finished.connect(self.archive_thread.deleteLater)
            self.archive_thread.start()

    def menu_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        # Set dialog size relative to main window
        main_width = self.width()
        main_height = self.height()
        dlg.resize(int(main_width * 0.7), int(main_height * 0.4))

        layout = QVBoxLayout(dlg)

        # Log file path controls
        path_row = QHBoxLayout()
        lbl = QLabel("Log file path:")
        entry = QLineEdit()
        entry.setText(self.log_dir)
        btn_browse = QPushButton("Browse…")
        path_row.addWidget(lbl)
        path_row.addWidget(entry, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        # Buttons
        btns = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btns.addStretch(1)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        def on_browse():
            initial_dir = os.path.dirname(entry.text().strip()) if entry.text().strip() else os.path.expanduser("~")
            fname, _ = QFileDialog.getSaveFileName(self, "Select Log File", initial_dir, "Text files (*.txt);;All files (*)")
            if fname:
                entry.setText(fname)

        def on_save():
            path = entry.text().strip()
            self.log_dir = path
            # Update main window checkbox enablement and tooltip
            if hasattr(self, 'checkbox_log'):
                if path:
                    self.checkbox_log.setEnabled(True)
                    self.checkbox_log.setToolTip("Log file will be created at the specified path.")
                else:
                    # No path => disable logging
                    self.checkbox_log.setChecked(False)
                    self.create_log = False
                    self.checkbox_log.setEnabled(False)
                    self.checkbox_log.setToolTip("Specify a log file path in Settings to enable logging.")
            # Persist and close (guard against filesystem errors)
            try:
                self.save_settings()
            except Exception as e:
                msg = QMessageBox(self)
                msg.setWindowTitle("Settings Save Failed")
                msg.setIcon(QMessageBox.Critical)
                msg.setText(f"Could not save settings.json.\n\n{e}")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
                return  # keep dialog open
            dlg.accept()

        def on_cancel():
            dlg.reject()

        btn_browse.clicked.connect(on_browse)
        btn_save.clicked.connect(on_save)
        btn_cancel.clicked.connect(on_cancel)

        dlg.exec_()

    def show_help_log_dialog(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(HELP_LOG_TITLE)
        msg.setTextFormat(Qt.RichText)  # type: ignore[attr-defined]
        msg.setText(HELP_LOG_TEXT)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()

    def show_help_actions_dialog(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(HELP_ACTIONS_TITLE)
        msg.setTextFormat(Qt.RichText)  # type: ignore[attr-defined]
        msg.setText(HELP_ACTIONS_TEXT)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()


if __name__ == "__main__":
    # Create the Qt application and main window
    app = None
    try:
        # Install a simple exception hook to surface errors when launched via pythonw.exe
        def _excepthook(exc_type, exc_value, exc_tb):
            try:
                text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
                with open(CRASH_LOG, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== Crash at {datetime.now().isoformat()} ===\n{text}\n")
            except Exception:
                pass
            try:
                m = QMessageBox()
                m.setWindowTitle("Unexpected Error")
                m.setIcon(QMessageBox.Critical)
                m.setText("The application encountered an unexpected error and needs to close. A crash log was written to last_crash.log.")
                m.setDetailedText("".join(traceback.format_exception_only(exc_type, exc_value)))
                m.exec_()
            except Exception:
                pass
        sys.excepthook = _excepthook

        app = QApplication(sys.argv)

        # Apply optional stylesheet if present
        try:
            qss_path = os.path.join(BASE_DIR, "style.qss")
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
        except Exception:
            # Ignore stylesheet errors
            pass

        window = BackupApp()
        window.show()
        rc = app.exec_()
        sys.exit(rc)
    except KeyboardInterrupt:
        # Graceful exit when launched from a console and user presses Ctrl+C
        if app is not None:
            try:
                app.quit()
            except Exception:
                pass
        sys.exit(0)