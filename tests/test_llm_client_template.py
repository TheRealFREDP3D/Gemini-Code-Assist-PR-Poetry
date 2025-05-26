import unittest
import os
import sys
from unittest.mock import patch

# Adjust sys.path to include the src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from llm_client_template import (
    AzureLLMClient,
    OpenAILLMClient,
    MistralLLMClient,
    get_client_for_model,
    list_available_clients,
    SUPPORTED_MODEL_NAMES,
    CLIENT_MAPPINGS 
    # BaseLLMClient might be needed if we were to test its methods directly,
    # but for now, we are testing functions that return instances of its children.
)

class TestLLMClientTemplate(unittest.TestCase):

    def setUp(self):
        """Set up the test environment by mocking GITHUB_TOKEN."""
        self.env_patcher = patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up the test environment."""
        self.env_patcher.stop()

    def test_get_client_for_model_azure(self):
        """Test get_client_for_model for Azure-compatible models."""
        azure_models = [
            "openai/gpt-4.1", 
            "meta/Meta-Llama-3.1-8B-Instruct", 
            "deepseek/DeepSeek-V3-0324", 
            "microsoft/Phi-4"
        ]
        for model_name in azure_models:
            with self.subTest(model_name=model_name):
                client = get_client_for_model(model_name)
                self.assertIsInstance(client, AzureLLMClient)
                self.assertEqual(client.model_name, model_name)

    def test_get_client_for_model_openai(self):
        """Test get_client_for_model for OpenAI-compatible models."""
        model_name = "gpt-4o"
        client = get_client_for_model(model_name)
        self.assertIsInstance(client, OpenAILLMClient)
        self.assertEqual(client.model_name, model_name)

    def test_get_client_for_model_mistral(self):
        """Test get_client_for_model for Mistral-compatible models."""
        model_name = "Mistral-large-2407"
        client = get_client_for_model(model_name)
        self.assertIsInstance(client, MistralLLMClient)
        self.assertEqual(client.model_name, model_name)

    def test_get_client_for_model_unknown(self):
        """Test get_client_for_model for an unknown model."""
        model_name = "unknown-model/some-variant"
        client = get_client_for_model(model_name)
        self.assertIsNone(client)

    def test_list_available_clients_returns_list(self):
        """Test that list_available_clients returns a list."""
        clients = list_available_clients()
        self.assertIsInstance(clients, list)

    def test_list_available_clients_content(self):
        """Test the content of the list returned by list_available_clients."""
        clients_list = list_available_clients()
        
        # Expected number of clients is the number of models in SUPPORTED_MODEL_NAMES
        # that have a valid mapping in CLIENT_MAPPINGS.
        expected_count = 0
        for model_name in SUPPORTED_MODEL_NAMES:
            if get_client_for_model(model_name) is not None:
                expected_count += 1
        
        self.assertEqual(len(clients_list), expected_count)

        for client_dict in clients_list:
            self.assertIsInstance(client_dict, dict)
            self.assertIn("model_name", client_dict)
            self.assertIn("client_type", client_dict)

            # Verify the client_type is correct based on get_client_for_model
            model_name = client_dict["model_name"]
            expected_client_instance = get_client_for_model(model_name)
            self.assertIsNotNone(expected_client_instance, f"No client found for {model_name} listed in list_available_clients")
            self.assertEqual(client_dict["client_type"], expected_client_instance.__class__.__name__)
            self.assertIn(model_name, SUPPORTED_MODEL_NAMES)

    def test_list_available_clients_model_names_are_supported(self):
        """Test that all model names in list_available_clients are in SUPPORTED_MODEL_NAMES."""
        clients_list = list_available_clients()
        for client_dict in clients_list:
            self.assertIn(client_dict["model_name"], SUPPORTED_MODEL_NAMES)

if __name__ == '__main__':
    unittest.main()
