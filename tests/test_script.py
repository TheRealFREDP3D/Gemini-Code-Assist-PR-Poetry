import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Adjust sys.path to include the project root directory if 'src' and 'get_new_flowers.py' are there
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Config after sys.path modification, before attempting to import get_new_flowers
from src.config import Config
# We need to import the main function from get_new_flowers or the module itself
# and then call main, or mock parts of it.
import get_new_flowers

class TestGetNewFlowersScript(unittest.TestCase):

    def setUp(self):
        """Set up for each test."""
        # Store original sys.argv
        self.original_argv = sys.argv
        # Mock GITHUB_TOKEN environment variable for Config loading
        self.env_patcher = patch.dict(os.environ, {"GITHUB_TOKEN": "fake_github_token"})
        self.env_patcher.start()

        # It's crucial to mock functions that perform external actions
        # like API calls or file system operations if we are not testing them directly.
        # Here, we are testing if the model_name is correctly passed.
        self.mock_collect_poems = patch('get_new_flowers.collect_poems_from_repo').start()
        # Mock other functions that main calls that are not relevant to this specific test
        patch('get_new_flowers.load_existing_poems', return_value=[]).start()
        patch('get_new_flowers.save_poems_to_json').start()
        patch('get_new_flowers.write_log_summary').start()
        patch('get_new_flowers.search_public_repos', return_value=[]).start() # if --search is not used, this might not be strictly needed

    def tearDown(self):
        """Clean up after each test."""
        sys.argv = self.original_argv
        self.env_patcher.stop()
        patch.stopall()

    def test_main_with_model_arg(self):
        """Test if main uses the model from --model argument."""
        custom_model_name = "myprovider/mycoolmodel"
        # Simulate command line arguments: script_name --model <custom_model_name>
        sys.argv = ['get_new_flowers.py', '--owner', 'testowner', '--repo', 'testrepo', '--model', custom_model_name]

        get_new_flowers.main() # Call the main function of the script

        # Assert that collect_poems_from_repo was called with the custom_model_name
        self.mock_collect_poems.assert_called_once()
        # Check the call arguments. The exact args depend on collect_poems_from_repo's signature
        # and how main processes args. Assuming (owner, repo, model_name_to_use, max_prs, ollama_only)
        args, kwargs = self.mock_collect_poems.call_args
        self.assertEqual(args[0], 'testowner')
        self.assertEqual(args[1], 'testrepo')
        self.assertEqual(args[2], custom_model_name) # Key assertion: model_name_to_use

    def test_main_without_model_arg(self):
        """Test if main uses the default model when --model is not provided."""
        # Simulate command line arguments: script_name (without --model)
        sys.argv = ['get_new_flowers.py', '--owner', 'testowner', '--repo', 'testrepo']

        get_new_flowers.main() # Call the main function of the script

        # Assert that collect_poems_from_repo was called with Config.DEFAULT_MODEL
        self.mock_collect_poems.assert_called_once()
        args, kwargs = self.mock_collect_poems.call_args
        self.assertEqual(args[0], 'testowner')
        self.assertEqual(args[1], 'testrepo')
        self.assertEqual(args[2], Config.DEFAULT_MODEL) # Key assertion: model_name_to_use is default

    @patch('get_new_flowers.LiteLLMClient') # Mock the LiteLLMClient constructor
    def test_extract_poem_uses_correct_model(self, MockLiteLLMClient):
        """Test that extract_poem_from_comment instantiates LiteLLMClient with the correct model."""
        # This test is more focused on extract_poem_from_comment, but useful to ensure model propagation
        mock_instance = MockLiteLLMClient.return_value
        mock_instance.extract_poem.return_value = "A mock poem"

        test_model = "test/model"
        # Need to call extract_poem_from_comment directly or via a path that sets model_name_to_use
        # For simplicity, calling it directly here. In an integration test, this would be via main.
        get_new_flowers.extract_poem_from_comment("Some comment body", model_name_to_use=test_model)

        MockLiteLLMClient.assert_called_once_with(model_name=test_model)
        mock_instance.extract_poem.assert_called_once()

if __name__ == '__main__':
    unittest.main()
