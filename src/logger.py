"""
Logging module for the Gemini Code Assist PR Poetry collection script.
This provides a centralized logging system with file rotation.
"""

import os
import logging
import glob
from logging.handlers import RotatingFileHandler
from datetime import datetime

class PoemLogger:
    """Logger for the Gemini Code Assist PR Poetry collection script."""
    
    def __init__(self, logs_dir="logs", max_log_size_bytes=1024*1024):
        """Initialize the logger with directory and size limit."""
        self.logs_dir = logs_dir
        self.max_log_size_bytes = max_log_size_bytes
        
        # Create logs directory if it doesn't exist
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Configure logger
        self.logger = logging.getLogger("gemini-poetry")
        self.logger.setLevel(logging.INFO)
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Add file handler with rotation
        log_file = self._get_log_file()
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_log_size_bytes,
            backupCount=10
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
    
    def _get_log_file(self):
        """Get the next available log file name."""
        # Check for existing log files
        existing_logs = glob.glob(os.path.join(self.logs_dir, "log*.md"))
        
        if not existing_logs:
            return os.path.join(self.logs_dir, "log.md")
        
        # Check if the latest log file is under the size limit
        latest_log = max(existing_logs, key=os.path.getctime)
        
        if os.path.getsize(latest_log) < self.max_log_size_bytes:
            return latest_log
        
        # Create a new log file with incremented number
        if latest_log == os.path.join(self.logs_dir, "log.md"):
            return os.path.join(self.logs_dir, "log1.md")
        
        # Extract number from log file name
        base_name = os.path.basename(latest_log)
        num = int(base_name[3:-3]) + 1
        return os.path.join(self.logs_dir, f"log{num}.md")
    
    def write_run_summary(self, run_stats):
        """Write a summary of the run to the log file."""
        log_file = self._get_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"# Run Summary - {timestamp}\n\n")
            
            # Write statistics
            f.write("## Statistics\n")
            f.write(f"- New poems: {run_stats['new_poems']}\n")
            f.write(f"- Total poems: {run_stats['total_poems']}\n")
            f.write(f"- Repositories checked: {len(run_stats['repositories_checked'])}\n")
            f.write(f"- PRs checked: {run_stats['prs_checked']}\n")
            f.write(f"- Models used: {', '.join(run_stats['models_used'])}\n\n")
            
            # Write duplicates
            if run_stats["duplicates"]:
                f.write("## Duplicates\n")
                for dup in run_stats["duplicates"]:
                    f.write(f"- {dup['repository']} PR #{dup['pr_number']} - {dup['link']}\n")
                f.write("\n")
            
            # Write errors
            if run_stats["errors"]:
                f.write("## Errors\n")
                for error in run_stats["errors"]:
                    f.write(f"- {error}\n")
                f.write("\n")
            
            f.write("---\n\n")
        
        self.logger.info(f"Run summary written to {log_file}")
        return log_file
