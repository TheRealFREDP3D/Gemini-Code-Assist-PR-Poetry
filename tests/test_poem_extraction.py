import os
import sys
import unittest
import json
from pathlib import Path

# Add parent directory to path so we can import the main script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from get_new_flowers import (
    extract_poem_from_comment,
    load_custom_llm_models,
    is_ollama_running,
    get_poem_with_client,
    create_poem_entry,
    is_duplicate,
    get_next_log_file
)

class TestPoemExtraction(unittest.TestCase):
    def setUp(self):
        # Create test data directory if it doesn't exist
        self.test_data_dir = Path("test_data")
        self.test_data_dir.mkdir(exist_ok=True)

        # Sample comment with a poem
        self.poem_comment = """
I've reviewed your PR and here are my thoughts:

> A system's context,
> Diagrams draw the clear path,
> Code's intent shown.

<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>

The changes look good, but please consider adding more documentation.
"""

        # Sample comment without a poem
        self.non_poem_comment = """
I've reviewed your PR and here are my thoughts:

The changes look good, but please consider adding more documentation.

<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>
"""

    def test_extract_poem_traditional(self):
        """Test extracting a poem using the traditional method."""
        poem_lines, link = extract_poem_from_comment(self.poem_comment)

        self.assertIsNotNone(poem_lines)
        self.assertIsNotNone(link)
        self.assertEqual(len(poem_lines), 4)  # 3 poem lines + 1 empty line
        self.assertEqual(poem_lines[0], "> A system's context,")
        self.assertEqual(link, "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>")

    def test_load_custom_llm_models(self):
        """Test loading custom LLM models from JSON."""
        # Since we can't easily test the actual function in isolation,
        # we'll just create a simple test that verifies the function exists
        # and returns a list (even if empty)
        models = load_custom_llm_models()
        self.assertIsInstance(models, list)

    def test_is_ollama_running(self):
        """Test checking if Ollama server is running."""
        # This test just verifies the function runs without errors
        result = is_ollama_running()
        self.assertIsInstance(result, bool)

    def test_create_poem_entry(self):
        """Test creating a poem entry."""
        poem_lines = ["> A system's context,", "> Diagrams draw the clear path,", "> Code's intent shown."]
        link = "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>"
        owner = "TheRealFREDP3D"
        repo = "Making-BanditGUI"
        pr_number = 10

        entry = create_poem_entry(poem_lines, link, owner, repo, pr_number)

        self.assertIsInstance(entry, dict)
        self.assertIn("poem", entry)
        self.assertIn("link", entry)
        self.assertIn("repository", entry)
        self.assertIn("pr_number", entry)
        self.assertIn("collected_at", entry)

        # The link might be normalized in the entry creation process
        self.assertTrue(entry["link"] == link or entry["link"] == link.strip('<>') or link == f"<{entry['link']}>")
        self.assertEqual(entry["repository"], f"{owner}/{repo}")
        self.assertEqual(entry["pr_number"], pr_number)

    def test_is_duplicate(self):
        """Test checking for duplicate poems."""
        poem1 = {
            "poem": ["A system's context,", "Diagrams draw the clear path,", "Code's intent shown."],
            "link": "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>",
            "repository": "TheRealFREDP3D/Making-BanditGUI",
            "pr_number": 10
        }

        poem2 = {
            "poem": ["A different poem,", "With different lines,", "But same meaning."],
            "link": "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/11#pullrequestreview-2809083427>",
            "repository": "TheRealFREDP3D/Making-BanditGUI",
            "pr_number": 11
        }

        # Create a duplicate of poem1 with slight differences
        poem3 = {
            "poem": ["A system's context,", "Diagrams draw the clear path,", "Code's intent shown!"],
            "link": "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/10#pullrequestreview-2809083426>",
            "repository": "TheRealFREDP3D/Making-BanditGUI",
            "pr_number": 10
        }

        existing_poems = [poem1, poem2]

        # Test with a duplicate
        self.assertTrue(is_duplicate(poem3, existing_poems))

        # Test with a non-duplicate
        poem4 = {
            "poem": ["Yet another poem,", "With unique lines,", "And a new link."],
            "link": "<https://github.com/TheRealFREDP3D/Making-BanditGUI/pull/12#pullrequestreview-2809083428>",
            "repository": "TheRealFREDP3D/Making-BanditGUI",
            "pr_number": 12
        }

        self.assertFalse(is_duplicate(poem4, existing_poems))

    def test_get_next_log_file(self):
        """Test getting the next log file name."""
        # Create a test log directory
        test_logs_dir = Path("test_logs")
        test_logs_dir.mkdir(exist_ok=True)

        # Create a test log file
        test_log_file = test_logs_dir / "log.md"
        with open(test_log_file, 'w') as f:
            f.write("# Test Log\n\nThis is a test log file.\n")

        # Temporarily override the LOGS_DIR constant
        import get_new_flowers
        original_logs_dir = get_new_flowers.LOGS_DIR
        get_new_flowers.LOGS_DIR = str(test_logs_dir)

        try:
            # Test getting the next log file
            next_log_file = get_next_log_file()
            self.assertEqual(os.path.basename(next_log_file), "log.md")

            # Make the log file larger than the max size
            with open(test_log_file, 'w') as f:
                f.write("X" * (get_new_flowers.MAX_LOG_SIZE_BYTES + 1))

            # Test getting the next log file again
            next_log_file = get_next_log_file()
            self.assertEqual(os.path.basename(next_log_file), "log1.md")
        finally:
            # Restore the original LOGS_DIR
            get_new_flowers.LOGS_DIR = original_logs_dir

            # Clean up test files
            if test_log_file.exists():
                test_log_file.unlink()

            # Try to remove the test directory
            try:
                test_logs_dir.rmdir()
            except Exception:
                pass

if __name__ == "__main__":
    unittest.main()
