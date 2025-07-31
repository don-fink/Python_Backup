import subprocess
import os
import datetime

def run_backup_robocopy(source_dir, destination_dir, log_dir=None):
    """
    Performs a data backup using Robocopy.

    Args:
        source_dir (str): The path to the source directory.
        destination_dir (str): The path to the destination directory.
        log_dir (str, optional): Directory to store Robocopy logs.
                                 If None, logs are printed to console.
    """
    # 1. Input Validation: Check if the source directory exists
    if not os.path.isdir(source_dir):
        print(f"Error: Source directory '{source_dir}' does not exist.")
        return

    # 2. Prepare Destination: Create destination directory if it doesn't exist
    if not os.path.exists(destination_dir):
        try:
            os.makedirs(destination_dir)
            print(f"Created destination directory: {destination_dir}")
        except OSError as e:
            print(f"Error creating destination directory: {e}")
            return

    # 3. Define Robocopy Command and Options
    # Robocopy options:
    # /MIR: Mirrors a directory tree (equivalent to /E /PURGE). This will copy new/changed files
    #       and delete files from the destination that are no longer in the source.
    #       USE WITH CAUTION! If source content is accidentally deleted, /MIR will replicate that deletion to destination.
    # /DCOPY:T: Copies directory timestamps.
    # /NP: No Progress - Don't display percentage copied.
    # /ZB: Restartable mode; if access denied, use backup mode.
    # /R:3: Retry 3 times on failed copies.
    # /W:5: Wait 5 seconds between retries.
    # /MT:8: Use 8 threads for multi-threaded copying (can speed up transfers).
    robocopy_command = [
        "robocopy",       # The Robocopy executable
        source_dir,       # Your source directory
        destination_dir,  # Your destination directory
        "/MIR",           # Mirror mode (copy new/changed, delete missing from source)
        "/DCOPY:T",       # Copy directory timestamps
        "/NP",            # No progress indicator in output
        "/ZB",            # Restartable mode + Backup mode
        "/R:3",           # Retry 3 times on failed copies
        "/W:5",           # Wait 5 seconds between retries
        "/MT:8"           # Multi-threaded copying with 8 threads
    ]

    # 4. Handle Logging (optional)
    log_file_path = None
    if log_dir:
        # Create log directory if it doesn't exist
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
                print(f"Created log directory: {log_dir}")
            except OSError as e:
                print(f"Error creating log directory: {e}")
                # Decide if you want to proceed without logging or exit
                log_dir = None # Disable logging if directory creation fails
        
        if log_dir: # Only proceed with log file if log_dir is successfully created/exists
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file_path = os.path.join(log_dir, f"backup_log_{timestamp}.txt")
            # /LOG+: Appends output to log file (use /LOG: to overwrite)
            robocopy_command.append(f"/LOG+:{log_file_path}") 

    print(f"Starting backup from '{source_dir}' to '{destination_dir}'...")
    print(f"Robocopy command: {' '.join(robocopy_command)}") # Shows the exact command being run

    # 5. Execute Robocopy Command
    try:
        # subprocess.run executes the command and waits for it to complete.
        # capture_output=True: Captures stdout and stderr.
        # text=True: Decodes stdout/stderr as text (UTF-8 by default).
        # check=False: Prevents a CalledProcessError for non-zero exit codes (Robocopy uses non-zero for success with minor issues).
        result = subprocess.run(robocopy_command, capture_output=True, text=True, check=False)

        # 6. Process Robocopy Output
        if log_file_path:
            print(f"Robocopy output logged to: {log_file_path}")
            # Optional: You can read and print the log file content here if desired,
            # but usually, you'd just check the file directly after the script runs.
            # with open(log_file_path, 'r') as f:
            #     print(f.read())
        else: # If no log file is specified, print output to console
            print("\n--- Robocopy Output ---")
            print(result.stdout)
            if result.stderr:
                print("\n--- Robocopy Error Output ---")
                print(result.stderr)

        # 7. Interpret Robocopy Exit Codes
        # Robocopy exit codes are bit flags, meaning combinations of success and warnings.
        # 0: No files copied. No failures. No unmatched files.
        # 1: One or more files copied successfully.
        # 2: Some extra files or directories were detected. No failures.
        # 3: Some files were copied. Some extra files were detected. No failures. (1+2)
        # 4: Some mismatch between source and destination files detected. No failures.
        # 5: Some files copied. Some mismatch. No failures. (1+4)
        # 6: Some files copied. Some extra files. Some mismatch. No failures. (1+2+4)
        # 7: Some files copied. Some extra files. Some mismatch. Some failures. (1+2+4+8)
        # 8: At least one file failed to copy. (This is a true error requiring attention)
        # Higher codes indicate more severe errors or specific issues.

        if result.returncode <= 7: # All codes from 0 to 7 indicate success or minor non-critical issues
            print("\nBackup completed successfully (or with minor issues, check log/output for details).")
        else: # Codes 8 or higher indicate critical failures
            print(f"\nBackup completed with errors. Robocopy exit code: {result.returncode}")
            print("Please review the log/output for details on failures.")

    except FileNotFoundError:
        print("Error: 'robocopy' command not found. Ensure Robocopy (part of Windows) is available in your system PATH.")
    except Exception as e:
        print(f"An unexpected error occurred during the backup process: {e}")

# This block ensures the code below only runs when the script is executed directly,
# not when imported as a module into another Python script.
if __name__ == "__main__":
    # --- IMPORTANT: Configure your backup paths here ---
    # Use 'r' before the string for raw strings to avoid issues with backslashes in Windows paths.
    source = r"E:\Lightroom Catalogs" # REPLACE THIS with the actual path to the folder you want to back up
    destination = r"F:\Lightroom Catalogs"       # REPLACE THIS with the actual path where you want the backup to be saved
    log_output_dir = r"F:\BackupLogs"
    # Call the backup function with your specified paths
    run_backup_robocopy(source, destination, log_output_dir)