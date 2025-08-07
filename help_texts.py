# help_texts.py

HELP_LOG_TITLE = "How to Specify Log File"
HELP_LOG_TEXT = (
    "<b>How to Specify Log File:</b><br><br>"
    "Open the Settings dialog from the File menu.<br>"
    "Click the 'Browse...' button to choose a folder and enter a file name for your log file. "
    "You must provide a file name (e.g., backup_log.txt).<br>"
    "After selecting or entering the file name, click OK to save your choice."
)

HELP_ACTIONS_TITLE = "Backup Actions"
HELP_ACTIONS_TEXT = (
    "<b>Backup Actions:</b><br><br>"
    "<b>Sync:</b> Makes the destination an exact mirror of the source. Files/folders not in the source are deleted from the destination.<br>"
    "<b>Copy:</b> Copies all files from source to destination, but does not delete anything at the destination.<br>"
    "<b>Archive:</b> (Not yet implemented) Will eventually move replaced or deleted files to an archive folder before syncing."
)
