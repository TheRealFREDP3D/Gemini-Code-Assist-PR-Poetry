"""
Logging module for the Gemini Code Assist PR Poetry collection script.
This provides a centralized logging system with file rotation.
"""

import os
import logging
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
        self.log_file_path = os.path.join(self.logs_dir, "collection_activity.log")
        file_handler = RotatingFileHandler(
            self.log_file_path,
            maxBytes=self.max_log_size_bytes,
            backupCount=10 # Keeps up to 10 backup files
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

    def write_run_summary(self, run_stats, repository_url, model_name_to_use):
        """Write a simplified summary of the run to the log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        summary_lines = []
        summary_lines.append(f"# Run Summary - {timestamp}")
        summary_lines.append(f"- Repository Processed: {repository_url}")
        summary_lines.append(f"- Model Used: {model_name_to_use}")
        summary_lines.append(f"- New poems found: {run_stats.get('new_poems', 0)}")
        summary_lines.append(f"- Total poems in collection (after run): {run_stats.get('total_poems', 0)}")
        
        duplicates = run_stats.get("duplicates", [])
        if duplicates:
            summary_lines.append("\n## Duplicates Found During This Run")
            for dup in duplicates:
                summary_lines.append(f"- Link: {dup.get('link', 'N/A')}")
                if 'repository' in dup and 'pr_number' in dup:
                    summary_lines.append(f"  (From: {dup['repository']} PR #{dup['pr_number']})")
        
        errors = run_stats.get("errors", [])
        if errors:
            summary_lines.append("\n## Errors")
            for error in errors:
                summary_lines.append(f"- {error}")
        
        summary_lines.append("\n---\n")
        
        # Log each line of the summary
        # To maintain the multi-line format in the log, we can log it as a single block
        # or iterate and log. Iterating might be cleaner with standard logger format.
        # However, for a distinct block, logging a pre-formatted string is common.
        summary_message = "\n" + "\n".join(summary_lines) # Add a leading newline for separation
        self.logger.info(summary_message)
        
        self.logger.info(f"Run summary appended to {self.log_file_path}")
        return self.log_file_path
