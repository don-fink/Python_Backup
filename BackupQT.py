from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMenuBar, QAction, QGroupBox,
    QDialog, QProgressBar, QMessageBox, QCheckBox, QComboBox, QGridLayout
)


import sys
import subprocess
import os
import json
from dirsync import sync
# Import help texts
from help_texts import HELP_LOG_TITLE, HELP_LOG_TEXT, HELP_ACTIONS_TITLE, HELP_ACTIONS_TEXT

# BASE_DIR is the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")




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
            "selected_action": "Sync"
        }
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
            except Exception:
                settings = default_settings
        else:
            settings = default_settings
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f, indent=4)
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
            "selected_action": selected_action
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)

    def closeEvent(self, event):
        self.save_settings()
        event.accept()

    def init_ui(self):
        self.setWindowTitle("Backup Script")
        self.resize(1200, 600)

        # Menu Bar
        menubar = QMenuBar(self)
        file_menu = menubar.addMenu("File")

        # Add Help menu (after menubar is created)
        help_menu = menubar.addMenu("Help")
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
        exit_action.triggered.connect(self.close)
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
        self.button_cancel.clicked.connect(self.close)
    
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
        log_action_row.addWidget(self.checkbox_log, 0, 0, alignment=Qt.AlignRight)
        log_action_row.addWidget(label_actions, 0, 1, alignment=Qt.AlignRight)
        log_action_row.addWidget(self.combo_action, 0, 2, alignment=Qt.AlignLeft)
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

        group_layout.addLayout(log_action_row)
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
            msg.setText("The destination folder path is invalid or does not exist.\n\nPlease select a valid destination folder.")
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
                self.status_label.setText("Backup cancelled by user (log file not available).")
                return
            # If OK, proceed with backup but skip logging
            log_writable = False

        action = self.combo_action.currentText()
        if action == "Sync":
            # Use dirsync to mirror source to destination
            try:
                sync(source_folder, destination_folder, 'sync')
                self.status_label.setText("Sync completed successfully.")
                # Write log file if enabled, path is set, and log_writable
                if getattr(self, 'create_log', False) and self.log_dir and log_writable:
                    try:
                        with open(self.log_dir, 'w', encoding='utf-8') as logf:
                            logf.write(f"Sync completed from {source_folder} to {destination_folder}\n")
                    except Exception as e:
                        self.status_label.setText(f"Could not write log file: {e}")
                        return
            except Exception as e:
                self.status_label.setText(f"Sync failed: {e}")

        elif action == "Copy":
            # Custom file-by-file copy (no delete at destination)
            files_to_copy = []
            for dirpath, dirnames, filenames in os.walk(source_folder):
                for f in filenames:
                    src_fp = os.path.join(dirpath, f)
                    rel_path = os.path.relpath(src_fp, source_folder)
                    dst_fp = os.path.join(destination_folder, rel_path)
                    files_to_copy.append((src_fp, dst_fp))

            total_files = len(files_to_copy)
            if total_files == 0:
                self.status_label.setText("No files to backup.")
                return

            # Progress dialog
            progress_dialog = QDialog(self)
            progress_dialog.setWindowFlags(progress_dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            progress_dialog.setWindowTitle("Backup Progress")
            progress_dialog.setWindowModality(Qt.ApplicationModal)
            progress_dialog.setFixedSize(400, 120)
            vbox = QVBoxLayout(progress_dialog)
            label = QLabel("Copying files...")
            vbox.addWidget(label)
            progress_bar = QProgressBar()
            progress_bar.setMinimum(0)
            progress_bar.setMaximum(total_files)
            vbox.addWidget(progress_bar)
            progress_dialog.show()
            QApplication.processEvents()

            import shutil
            errors = []
            for i, (src_fp, dst_fp) in enumerate(files_to_copy, 1):
                dst_dir = os.path.dirname(dst_fp)
                if not os.path.exists(dst_dir):
                    os.makedirs(dst_dir, exist_ok=True)
                try:
                    shutil.copy2(src_fp, dst_fp)
                except Exception as e:
                    errors.append(f"{src_fp} -> {dst_fp}: {e}")
                progress_bar.setValue(i)
                QApplication.processEvents()

            progress_dialog.close()

            # Write log file if enabled, path is set, and log_writable
            if getattr(self, 'create_log', False) and self.log_dir and log_writable:
                try:
                    with open(self.log_dir, 'w', encoding='utf-8') as logf:
                        for i, (src_fp, dst_fp) in enumerate(files_to_copy, 1):
                            if i <= len(errors):
                                logf.write(f"ERROR: {errors[i-1]}\n")
                            else:
                                logf.write(f"Copied: {src_fp} -> {dst_fp}\n")
                except Exception as e:
                    self.status_label.setText(f"Could not write log file: {e}")
                    return

            if errors:
                self.status_label.setText(f"Copy completed with errors. See log.")
            else:
                self.status_label.setText("Copy completed successfully.")

        elif action == "Archive":
            self.status_label.setText("Archive action not yet implemented.")

    def menu_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        # Set dialog width to 70% of main window
        main_width = self.width()
        main_height = self.height()
        dlg.resize(int(main_width * 0.7), int(main_height * 0.4))
        layout = QVBoxLayout(dlg)

        # Log file path row (styled like main window)
        log_row = QHBoxLayout()
        label = QLabel("Log file path:")
        entry = QLineEdit()
        entry.setText(self.log_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(120)
        browse_btn.setToolTip("Select the log file location")
        def browse():
            path, _ = QFileDialog.getSaveFileName(dlg, "Select Log File", entry.text(), "Text Files (*.txt);;All Files (*)")
            if path:
                entry.setText(path)
        browse_btn.clicked.connect(browse)
        log_row.addWidget(label)
        log_row.addWidget(entry)
        log_row.addWidget(browse_btn)
        layout.addLayout(log_row)

        # OK/Cancel buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(120)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(120)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def accept():
            self.log_dir = entry.text()
            self.save_settings()
            # Enable/disable log checkbox in main window
            if hasattr(self, 'checkbox_log'):
                if self.log_dir:
                    self.checkbox_log.setEnabled(True)
                    self.checkbox_log.setToolTip("Log file will be created at the specified path.")
                else:
                    self.checkbox_log.setEnabled(False)
                    self.checkbox_log.setToolTip("Specify a log file path in Settings to enable logging.")
            dlg.accept()
        def reject():
            dlg.reject()
        ok_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(reject)

        dlg.setLayout(layout)
        dlg.exec_()

    def show_help_dialog(self):
        pass  # This function is now split into two below


    def show_help_log_dialog(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(HELP_LOG_TITLE)
        msg.setTextFormat(Qt.RichText)
        msg.setText(HELP_LOG_TEXT)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()


    def show_help_actions_dialog(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(HELP_ACTIONS_TITLE)
        msg.setTextFormat(Qt.RichText)
        msg.setText(HELP_ACTIONS_TEXT)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()
        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Load stylesheet from external file
    try:
        with open("style.qss", "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print(f"Could not load stylesheet: {e}")
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())