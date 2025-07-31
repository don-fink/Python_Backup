from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMenuBar, QAction
)
import sys
import subprocess
import os



class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

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

        settings_action = QAction("Exit", self)
        settings_action.triggered.connect(lambda: self.menu_settings())
        file_menu.addAction(settings_action)

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


    def menu_source_folder(self):
        pass

    def menu_destination_folder(self):
        pass

    def menu_settings(self):
        pass

    def browse_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.entry_source.setText(folder)

    def browse_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if folder:
            self.entry_destination.setText(folder)

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

        robocopy_command = f'robocopy "{source_folder}" "{destination_folder}" /e'

        try:
            subprocess.run(robocopy_command, shell=True, check=True)
            self.status_label.setText("Backup completed successfully.")
        except subprocess.CalledProcessError as e:
            self.status_label.setText(f"Backup failed: {e}")
        except Exception as e:
            self.status_label.setText(f"Unexpected error: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())