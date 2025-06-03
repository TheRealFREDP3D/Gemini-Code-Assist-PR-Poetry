import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Adjust sys.path to include the src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm_client_template import LiteLLMClient
from src.config import Config # Needed for DEFAULT_MODEL if used by LiteLLMClient directly

# Mock litellm.completion response structure
class MockLiteLLMResponse:
    def __init__(self, content=None, error=None):
        if error:
            # Simulate an error scenario if needed by raising it or returning a specific structure
            # For simplicity here, we assume 'completion' itself might raise or return a response
            # that indicates an error through its structure, which LiteLLMClient handles.
            # This mock focuses on the `choices[0].message.content` path.
            pass

        self.choices = []
        if content is not None:
            message_mock = MagicMock()
            message_mock.message = MagicMock()
            message_mock.message.content = content
            self.choices.append(message_mock)

class TestLiteLLMClient(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        # Mock GITHUB_TOKEN environment variable
        self.env_patcher = patch.dict(os.environ, {"GITHUB_TOKEN": "fake_github_token"})
        self.env_patcher.start()

        # Patch litellm.completion
        self.mock_litellm_completion = patch('litellm.completion').start()

        # Instantiate the client
        self.client = LiteLLMClient(model_name="test_model/test_variant")

    def tearDown(self):
        """Clean up the test environment."""
        self.env_patcher.stop()
        patch.stopall() # Stops all patches started with patch.start()

    def test_extract_poem_success(self):
        """Test successful poem extraction."""
        expected_poem = "This is a test poem.\nWith multiple lines."
        # Configure the mock to return a successful response object
        self.mock_litellm_completion.return_value = MockLiteLLMResponse(content=expected_poem)

        prompt = "Extract a poem from this text."
        actual_poem = self.client.extract_poem(prompt)

        self.assertEqual(actual_poem, expected_poem.strip())
        self.mock_litellm_completion.assert_called_once_with(
            model="test_model/test_variant",
            messages=[
                {"role": "system", "content": ""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8, # Assuming these are the defaults in LiteLLMClient
            top_p=0.1,
            max_tokens=2048,
        )

    def test_extract_poem_no_poem(self):
        """Test when the LLM returns 'NO_POEM'."""
        # Configure the mock to return "NO_POEM"
        self.mock_litellm_completion.return_value = MockLiteLLMResponse(content="NO_POEM")

        prompt = "Extract a poem from this text that has no poem."
        actual_response = self.client.extract_poem(prompt)

        self.assertEqual(actual_response, "NO_POEM")
        self.mock_litellm_completion.assert_called_once()

    def test_extract_poem_api_error(self):
        """Test when litellm.completion raises an API error."""
        # Configure the mock to raise an exception
        self.mock_litellm_completion.side_effect = Exception("Simulated API Error")
        
        prompt = "Extract a poem, but an error occurs."
        actual_response = self.client.extract_poem(prompt)
        
        self.assertEqual(actual_response, "NO_POEM")
        self.mock_litellm_completion.assert_called_once()
        # Optionally, check if the error was logged if LiteLLMClient has logging

    def test_extract_poem_empty_response_content(self):
        """Test when the LLM returns a response with empty content."""
        self.mock_litellm_completion.return_value = MockLiteLLMResponse(content="")
        prompt = "Test prompt"
        actual_response = self.client.extract_poem(prompt)
        self.assertEqual(actual_response, "NO_POEM") # Based on clean_response logic

    def test_extract_poem_none_response_content(self):
        """Test when the LLM returns a response with None content."""
        # Mocking a response where choices[0].message.content might be None
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        self.mock_litellm_completion.return_value = mock_response

        prompt = "Test prompt for None content"
        actual_response = self.client.extract_poem(prompt)
        self.assertEqual(actual_response, "NO_POEM")

    def test_extract_poem_no_choices_in_response(self):
        """Test when the LLM returns a response with no choices."""
        mock_response = MagicMock()
        mock_response.choices = [] # No choices
        self.mock_litellm_completion.return_value = mock_response

        prompt = "Test prompt for no choices"
        actual_response = self.client.extract_poem(prompt)
        self.assertEqual(actual_response, "NO_POEM")

if __name__ == '__main__':
    unittest.main()
