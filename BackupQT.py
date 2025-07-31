from PyQt5.QtCore import Qt 
QApplication, QWidget, QLabel, QLineEdit, QPushButton,
QVBoxLayout, QHBoxLayout, QFileDialog, QMenuBar, QAction

import sys
import subprocess
import os
import json
from dirsync import sync

SETTINGS_FILE = "settings.json"




class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.init_ui()
        self.resize(*self.settings["window_size"])
        self.entry_source.setText(self.settings["source_dir"])
        self.entry_destination.setText(self.settings["destination_dir"])
        self.create_log = self.settings.get("create_log", False)
        self.log_dir = self.settings.get("log_dir", "")
        self.mirror = self.settings.get("mirror", False)

    def load_settings(self):
        default_settings = {
            "window_size": [1200, 600],
            "source_dir": "",
            "destination_dir": "",
            "create_log": False,
            "log_dir": "",
            "mirror": False
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
        return settings
    
    def save_settings(self):
        settings = {
            "window_size": [self.width(), self.height()],
            "source_dir": self.entry_source.text(),
            "destination_dir": self.entry_destination.text(),
            "create_log": getattr(self, "create_log", False),
            "log_dir": getattr(self, "log_dir", ""),
            "mirror": getattr(self, "mirror", False)
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

        source_action = QAction("Source Folder", self)
        source_action.triggered.connect(self.browse_source)
        #source_action.triggered.connect(lambda: self.menu_source_folder())
        file_menu.addAction(source_action)

        dest_action = QAction("Destination Folder", self)
        dest_action.triggered.connect(self.browse_destination)
        #dest_action.triggered.connect(lambda: self.menu_destination_folder())
        file_menu.addAction(dest_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(lambda: self.menu_settings())
        file_menu.addAction(settings_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Widget creation (move these inside init_ui)
        self.label_source = QLabel("Source Folder:")
        self.entry_source = QLineEdit()
        self.button_browse_source = QPushButton("?")
        self.button_browse_source.setFixedWidth(40) # Set fixed width for the button
        #self.button_browse_source.setFixedWidth(self.button_browse_source.sizeHint().width())
        self.button_browse_source.clicked.connect(self.browse_source)

        self.label_destination = QLabel("Destination Folder:")
        self.entry_destination = QLineEdit()
        self.button_browse_destination = QPushButton("?")
        self.button_browse_destination.setFixedWidth(40)
        #self.button_browse_destination.setFixedWidth(self.button_browse_destination.sizeHint().width())
        self.button_browse_destination.clicked.connect(self.browse_destination)

        self.button_backup = QPushButton("Backup")
        self.button_backup.clicked.connect(self.backup)

        self.status_label = QLabel("")
  

        layout = QVBoxLayout()
        layout.setMenuBar(menubar)

        # Source row
        source_row =QHBoxLayout()
        source_row.addWidget(self.label_source)
        source_row.addWidget(self.entry_source)
        source_row.addWidget(self.button_browse_source)
        layout.addLayout(source_row)
        
        # Destination row
        dest_row = QHBoxLayout()
        dest_row.addWidget(self.label_destination)
        dest_row.addWidget(self.entry_destination)
        dest_row.addWidget(self.button_browse_destination)
        layout.addLayout(dest_row)

        layout.addWidget(self.button_backup, alignment=Qt.AlignCenter)
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
  

        # Validate paths
        if not os.path.exists(source_folder) or not os.path.isdir(source_folder):
            self.status_label.setText("Invalid source folder path.")
            return
        if not os.path.exists(destination_folder) or not os.path.isdir(destination_folder):
            self.status_label.setText("Invalid destination folder path.")
            return
        
        # Show working message and refresh GUI
        self.status_label.setText("Backup in progress...")
        QApplication.processEvents()  # Force GUI update        

        # Use dirsync for backup
        try:
            # Mirror mode if self.mirror is True, otherwise just sync
            sync(
                source_folder,
                destination_folder,
                'sync',
                purge=self.mirror  # purge=True will mirror (delete extraneous files)
            )
            self.status_label.setText("Backup completed successfully.")
        except Exception as e:
            self.status_label.setText(f"Backup failed: {e}")





if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())