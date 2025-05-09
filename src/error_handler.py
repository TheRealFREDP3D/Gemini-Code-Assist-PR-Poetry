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
    
    def __init__(self, run_stats, failed_litellm_models=None, failed_clients=None):
        """Initialize the error handler with runtime statistics and failure tracking."""
        self.run_stats = run_stats
        self.failed_litellm_models = failed_litellm_models or []
        self.failed_clients = failed_clients or []
    
    def handle_api_error(self, error, context="API request"):
        """Handle errors from API requests."""
        error_msg = f"Error in {context}: {error}"
        logger.error(error_msg)
        self.run_stats["errors"].append(error_msg)
        return None
    
    def handle_litellm_error(self, error, model_name):
        """Handle errors from LiteLLM models."""
        error_str = str(error)
        error_msg = f"Error using {model_name}: {error}"
        logger.error(error_msg)
        self.run_stats["errors"].append(error_msg)
        
        # Add this model to the failed models list
        self.failed_litellm_models.append(model_name)
        
        # Check if it's a rate limit error
        rate_limit_error = False
        wait_time = 0
        if "rate limit" in error_str.lower() or "429" in error_str:
            rate_limit_error, wait_time = self.handle_rate_limit(error_str, model_name)
        
        return rate_limit_error, wait_time
    
    def handle_client_error(self, error, client_filename, error_type=""):
        """Handle errors in client execution and log them appropriately."""
        error_prefix = error_type or "Error using client"
        error_msg = f"{error_prefix} {client_filename}: {error}"
        logger.error(error_msg)
        self.run_stats["errors"].append(error_msg)
        
        # Only add to failed_clients if not already there
        if client_filename not in self.failed_clients:
            self.failed_clients.append(client_filename)
        
        return None
    
    def handle_rate_limit(self, error_str, model_name):
        """Handle rate limit errors with exponential backoff."""
        rate_limit_error = True
        base_wait_time = 5  # Default wait time in seconds
        
        # Try to extract wait time from error message
        if wait_match := re.search(r"wait (\d+) seconds", error_str):
            base_wait_time = int(wait_match[1])
        
        # Apply exponential backoff based on how many times this model has failed
        # Count how many times this model appears in failed_litellm_models
        failure_count = self.failed_litellm_models.count(model_name)
        wait_time = base_wait_time * (2 ** failure_count)
        
        logger.warning(f"Rate limit detected for {model_name}. Waiting {wait_time} seconds before retry.")
        time.sleep(wait_time)  # Actually wait here to respect rate limits
        
        return rate_limit_error, wait_time
    
    def check_all_models_failed(self, primary_models, custom_models, llm_clients):
        """Check if all available models have failed and exit if necessary."""
        if (len(self.failed_litellm_models) >= len(primary_models) + len(custom_models) and
            len(self.failed_clients) >= len(llm_clients)):
            logger.critical("All available LLM models have failed. Exiting program.")
            sys.exit(1)
    
    def log_errors_to_file(self, file_handle):
        """Write errors to a log file."""
        if self.run_stats["errors"]:
            file_handle.write("## Errors\n")
            for error in self.run_stats["errors"]:
                file_handle.write(f"- {error}\n")
            file_handle.write("\n")
