"""
Error handling module for the Gemini Code Assist PR Poetry collection script.
This centralizes error handling logic for better consistency and maintainability.
"""

import re
import sys
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
    ]
)

logger = logging.getLogger("gemini-poetry")

class ErrorHandler:
    """Centralized error handling for the Gemini Code Assist PR Poetry collection script."""
    
    def __init__(self, run_stats):
        """Initialize the error handler with runtime statistics and failure tracking."""
        self.run_stats = run_stats
        self.failed_models_this_run = {} # Tracks models that fail in the current session
    
    def handle_api_error(self, error, context="API request"):
        """Handle errors from API requests."""
        error_msg = f"Error in {context}: {error}"
        logger.error(error_msg)
        self.run_stats["errors"].append(error_msg)
        return None
    
    def handle_litellm_error(self, error, model_name):
        """Handle errors from LiteLLM models.
        Tracks failures for the given model_name in the current run.
        If a model fails multiple times, it might implement backoff or eventually give up for this session.
        """
        error_str = str(error)
        error_msg = f"Error using {model_name}: {error_str}"
        logger.error(error_msg)
        self.run_stats["errors"].append(error_msg)
        
        # Track failure count for this specific model in this run
        self.failed_models_this_run[model_name] = self.failed_models_this_run.get(model_name, 0) + 1
        
        rate_limit_error = False
        wait_time = 0
        if "rate limit" in error_str.lower() or "429" in error_str:
            rate_limit_error, wait_time = self._handle_rate_limit_internally(error_str, model_name)
        
        # If a model fails too many times, we might decide to stop trying it for this run.
        # For now, this is mainly for rate limiting, but could be expanded.
        if self.failed_models_this_run.get(model_name, 0) > 5: # Arbitrary threshold
             logger.warning(f"Model {model_name} has failed {self.failed_models_this_run[model_name]} times. Consider stopping retries for this session.")
             # For now, we don't explicitly stop, just log. The calling code decides whether to retry.

        return rate_limit_error, wait_time
    
    # Removed handle_client_error as client implementations are removed.

    def _handle_rate_limit_internally(self, error_str, model_name):
        """Handle rate limit errors with exponential backoff. Internal helper."""
        base_wait_time = 5  # Default wait time in seconds
        
        # Try to extract wait time from error message
        if wait_match := re.search(r"wait (\d+) seconds", error_str):
            base_wait_time = int(wait_match.group(1))
        
        # Apply exponential backoff based on how many times this model has failed in this run
        failure_count = self.failed_models_this_run.get(model_name, 1) # Default to 1 if not found, for the first failure
        wait_time = base_wait_time * (2 ** (failure_count -1)) # Exponential backoff
        
        logger.warning(f"Rate limit detected for {model_name}. Failure count: {failure_count}. Waiting {wait_time} seconds.")
        time.sleep(wait_time)
        
        return True, wait_time # Indicates it was a rate limit error and wait time applied
    
    # Removed check_all_models_failed method.
    # The script now uses only one model; if it fails, the script might not be able to proceed for that item.
    # The decision to exit entirely would be in the main script logic if the single model is unusable.
    
    def log_errors_to_file(self, file_handle):
        """Write errors to a log file."""
        if self.run_stats["errors"]:
            file_handle.write("## Errors\n")
            for error in self.run_stats["errors"]:
                file_handle.write(f"- {error}\n")
            file_handle.write("\n")
