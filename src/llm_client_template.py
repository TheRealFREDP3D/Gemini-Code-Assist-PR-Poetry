"""
Template for LLM client implementations.
This provides a standard structure for all LLM clients to follow.
"""

import os
import abc
import json
from typing import Dict, Any, Optional, List
import litellm
from src.config import Config

class BaseLLMClient(abc.ABC):
    """Base class for LLM clients."""
    
    def __init__(self, model_name: str):
        """Initialize the LLM client with a model name."""
        self.model_name = model_name
        self.github_token = os.environ.get("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
    
    @abc.abstractmethod
    def extract_poem(self, prompt: str) -> str:
        """Extract a poem from the given prompt using the LLM.
        
        Args:
            prompt: The prompt to send to the LLM.
            
        Returns:
            The extracted poem text or "NO_POEM" if no poem is found.
        """
        pass
    
    def clean_response(self, response: str) -> str:
        """Clean the response from the LLM.
        
        Args:
            response: The raw response from the LLM.
            
        Returns:
            The cleaned response.
        """
        if not response:
            return "NO_POEM"
        
        # Remove any "NO_POEM" markers
        if "NO_POEM" in response:
            return "NO_POEM"
        
        return response.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the client to a dictionary for serialization.
        
        Returns:
            A dictionary representation of the client.
        """
        return {
            "model_name": self.model_name,
            "client_type": self.__class__.__name__
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseLLMClient':
        """Create a client from a dictionary.
        
        Args:
            data: A dictionary representation of the client.
            
        Returns:
            A new client instance.
        """
        # This method might need adjustment depending on how LiteLLMClient is structured
        # For now, assume it can be initialized with model_name like other clients
        if data.get("client_type") == "LiteLLMClient":
            return LiteLLMClient(data["model_name"])
        # Fallback or error handling if other client types were expected
        raise ValueError(f"Unknown client type: {data.get('client_type')}")


class LiteLLMClient(BaseLLMClient):
    """Client for LiteLLM supported models."""

    def __init__(self, model_name: str):
        """Initialize the LiteLLM client.

        Args:
            model_name: The name of the model to use (e.g., "gemini/gemini-1.5-flash").
        """
        super().__init__(model_name)

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
                    {"role": "system", "content": ""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                top_p=0.1,
                max_tokens=2048,
                base_url=Config.OLLAMA_API_URL,
            )
            # Accessing the content correctly based on LiteLLM's response structure
            # LiteLLM typically returns a ModelResponse object, then access message via .choices[0].message.content
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                return self.clean_response(response.choices[0].message.content)
            return "NO_POEM"
        except Exception as e:
            # It's good practice to log the exception or handle it more gracefully
            print(f"Error using LiteLLM client with {self.model_name}: {e}")
            # Check if the exception is due to missing API keys for the specific model
            if "api_key" in str(e).lower():
                print(f"Please ensure the API key for {self.model_name} is set in your environment variables.")
            return "NO_POEM"
