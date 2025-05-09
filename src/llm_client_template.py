"""
Template for LLM client implementations.
This provides a standard structure for all LLM clients to follow.
"""

import os
import abc
import json
from typing import Dict, Any, Optional, List

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
        return cls(data["model_name"])


class AzureLLMClient(BaseLLMClient):
    """Client for Azure AI Inference models."""
    
    def __init__(self, model_name: str, endpoint: str = "https://models.github.ai/inference"):
        """Initialize the Azure LLM client.
        
        Args:
            model_name: The name of the model to use.
            endpoint: The Azure endpoint to use.
        """
        super().__init__(model_name)
        self.endpoint = endpoint
    
    def extract_poem(self, prompt: str) -> str:
        """Extract a poem using Azure AI Inference.
        
        Args:
            prompt: The prompt to send to the LLM.
            
        Returns:
            The extracted poem text or "NO_POEM" if no poem is found.
        """
        try:
            from azure.ai.inference import ChatCompletionsClient
            from azure.ai.inference.models import SystemMessage, UserMessage
            from azure.core.credentials import AzureKeyCredential
            
            client = ChatCompletionsClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.github_token),
            )
            
            response = client.complete(
                messages=[
                    SystemMessage(""),
                    UserMessage(prompt),
                ],
                temperature=0.8,
                top_p=0.1,
                max_tokens=2048,
                model=self.model_name
            )
            
            return self.clean_response(response.choices[0].message.content)
        except Exception as e:
            print(f"Error using Azure LLM client with {self.model_name}: {e}")
            return "NO_POEM"


class OpenAILLMClient(BaseLLMClient):
    """Client for OpenAI models."""
    
    def __init__(self, model_name: str, base_url: str = "https://models.github.ai/inference"):
        """Initialize the OpenAI LLM client.
        
        Args:
            model_name: The name of the model to use.
            base_url: The base URL for the OpenAI API.
        """
        super().__init__(model_name)
        self.base_url = base_url
    
    def extract_poem(self, prompt: str) -> str:
        """Extract a poem using OpenAI.
        
        Args:
            prompt: The prompt to send to the LLM.
            
        Returns:
            The extracted poem text or "NO_POEM" if no poem is found.
        """
        try:
            from openai import OpenAI
            
            client = OpenAI(
                base_url=self.base_url,
                api_key=self.github_token,
            )
            
            response = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=self.model_name,
                temperature=0.8,
                max_tokens=2048,
                top_p=0.1
            )
            
            return self.clean_response(response.choices[0].message.content)
        except Exception as e:
            print(f"Error using OpenAI LLM client with {self.model_name}: {e}")
            return "NO_POEM"


class MistralLLMClient(BaseLLMClient):
    """Client for Mistral models."""
    
    def __init__(self, model_name: str, server_url: str = "https://models.github.ai/inference"):
        """Initialize the Mistral LLM client.
        
        Args:
            model_name: The name of the model to use.
            server_url: The server URL for the Mistral API.
        """
        super().__init__(model_name)
        self.server_url = server_url
    
    def extract_poem(self, prompt: str) -> str:
        """Extract a poem using Mistral.
        
        Args:
            prompt: The prompt to send to the LLM.
            
        Returns:
            The extracted poem text or "NO_POEM" if no poem is found.
        """
        try:
            from mistralai import Mistral, UserMessage, SystemMessage
            
            client = Mistral(
                api_key=self.github_token,
                server_url=self.server_url
            )
            
            response = client.chat(
                model=self.model_name,
                messages=[
                    SystemMessage(""),
                    UserMessage(prompt),
                ],
                temperature=0.8,
                max_tokens=2048,
                top_p=0.1
            )
            
            return self.clean_response(response.choices[0].message.content)
        except Exception as e:
            print(f"Error using Mistral LLM client with {self.model_name}: {e}")
            return "NO_POEM"


def get_client_for_model(model_name: str) -> Optional[BaseLLMClient]:
    """Get the appropriate client for a given model.
    
    Args:
        model_name: The name of the model to use.
        
    Returns:
        A client instance for the model, or None if no client is available.
    """
    # Azure models
    if model_name.startswith(("openai/", "meta/", "deepseek/", "microsoft/")):
        return AzureLLMClient(model_name)
    
    # OpenAI models
    if model_name in ["gpt-4o"]:
        return OpenAILLMClient(model_name)
    
    # Mistral models
    if model_name.startswith("Mistral-"):
        return MistralLLMClient(model_name)
    
    return None


def list_available_clients() -> List[Dict[str, Any]]:
    """List all available LLM clients.
    
    Returns:
        A list of dictionaries with client information.
    """
    clients = [
        AzureLLMClient("openai/gpt-4.1"),
        OpenAILLMClient("gpt-4o"),
        AzureLLMClient("deepseek/DeepSeek-V3-0324"),
        AzureLLMClient("meta/Meta-Llama-3.1-8B-Instruct"),
        AzureLLMClient("meta/Llama-4-Maverick-17B-128E-Instruct-FP8"),
        MistralLLMClient("Mistral-large-2407"),
        AzureLLMClient("microsoft/Phi-4")
    ]
    
    return [client.to_dict() for client in clients]
