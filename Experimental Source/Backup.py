import subprocess
import os
import tkinter as tk
from tkinter import filedialog

def is_valid_path(path):
    return os.path.exists(path) and os.path.isdir(path)

def get_folder_path():
    folder_path = filedialog.askdirectory()
    return folder_path

def backup():
    source_folder = entry_source.get()
    destination_folder = entry_destination.get()

    # Check if the provided paths are valid
    if not is_valid_path(source_folder):
        status_label.config(text="Invalid source folder path.")
        return

    if not is_valid_path(destination_folder):
        status_label.config(text="Invalid destination folder path.")
        return

    # Construct the robocopy command
    robocopy_command = f'robocopy "{source_folder}" "{destination_folder}" /e'

    try:
        # Run the robocopy command
        subprocess.run(robocopy_command, shell=True, check=True)
        status_label.config(text="Backup completed successfully.")
    except subprocess.CalledProcessError as e:
        status_label.config(text=f"Backup failed with error: {e}")
    except Exception as e:
        status_label.config(text=f"An unexpected error occurred: {e}")

# Create the main window
window = tk.Tk()
window.title("Backup Script")

# Create and pack source folder widgets
label_source = tk.Label(window, text="Source Folder:")
label_source.pack(pady=5)
entry_source = tk.Entry(window, width=40)
entry_source.pack(pady=5)
button_browse_source = tk.Button(window, text="Browse", command=lambda: entry_source.insert(tk.END, get_folder_path()))
button_browse_source.pack(pady=5)

# Create and pack destination folder widgets
label_destination = tk.Label(window, text="Destination Folder:")
label_destination.pack(pady=5)
entry_destination = tk.Entry(window, width=40)
entry_destination.pack(pady=5)
button_browse_destination = tk.Button(window, text="Browse", command=lambda: entry_destination.insert(tk.END, get_folder_path()))
button_browse_destination.pack(pady=5)

# Create and pack backup button
button_backup = tk.Button(window, text="Backup", command=backup)
button_backup.pack(pady=10)

# Create and pack status label
status_label = tk.Label(window, text="")
status_label.pack(pady=10)

# Run the Tkinter event loop
window.mainloop()