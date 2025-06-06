"""
LLM client implementation using LiteLLM.
"""

import os
# import abc # No longer needed
# import json # No longer needed
# from typing import Dict, Any, Optional, List # No longer needed for this simplified client
import litellm

# BaseLLMClient class removed

class LiteLLMClient:
    """Client for LiteLLM supported models."""

    def __init__(self, model_name: str):
        """Initialize the LiteLLM client.

        Args:
            model_name: The name of the model to use (e.g., "gemini/gemini-1.5-flash", "ollama/llama2").
        """
        self.model_name = model_name

    def _clean_response(self, response: str) -> str:
        """Clean the response from the LLM.
        
        Args:
            response: The raw response from the LLM.
            
        Returns:
            The cleaned response.
        """
        if not response:
            return "NO_POEM"
        
        # Remove any "NO_POEM" markers
        # Checking for "NO_POEM" as a substring is more robust
        if "NO_POEM" in response:
            return "NO_POEM"
        
        return response.strip()

    def extract_poem(self, prompt: str) -> str:
        """Extract a poem using LiteLLM.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The extracted poem text or "NO_POEM" if no poem is found.
        """
        try:
            response = litellm.completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": ""}, # System prompt can be empty or customized
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7, # Adjusted temperature slightly
                max_tokens=2048
            )
            # Accessing the content correctly based on LiteLLM's response structure
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                return self._clean_response(response.choices[0].message.content)
            return "NO_POEM"
        except Exception as e:
            print(f"Error using LiteLLM client with {self.model_name}: {e}")
            if "api_key" in str(e).lower() or "auth" in str(e).lower(): # Broader check for auth issues
                print(f"Please ensure the API key and any other necessary credentials for {self.model_name} are correctly set in your environment variables (e.g., OPENAI_API_KEY, GOOGLE_API_KEY, etc.).")
            # Re-raise the exception if it's not a simple "NO_POEM" scenario,
            # to be caught by the error handler in get_new_flowers.py
            raise

    # to_dict and from_dict methods removed as they are no longer used.
