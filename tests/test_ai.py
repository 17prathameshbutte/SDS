import os
import unittest
from unittest.mock import patch

from services.gemini_service import get_ticket_ai_suggestions


class GeminiTests(unittest.TestCase):
    def test_ai_failure_handling_when_key_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            result = get_ticket_ai_suggestions("Broken outlet", "The socket is sparking.")
            self.assertEqual(result["status"], "not_configured")

    @patch("services.gemini_service.genai")
    def test_ai_handles_invalid_json(self, mock_genai):
        class FakeResponse:
            text = "not valid json"

        mock_client = mock_genai.Client.return_value
        mock_client.models.generate_content.return_value = FakeResponse()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            result = get_ticket_ai_suggestions("Broken outlet", "The socket is sparking.")
            self.assertEqual(result["status"], "error")
            mock_client.models.generate_content.assert_called_once()
            self.assertEqual(
                mock_client.models.generate_content.call_args.kwargs["model"],
                "gemini-3.5-flash-lite",
            )

    @patch("services.gemini_service.genai")
    def test_ai_returns_valid_suggestions(self, mock_genai):
        class FakeResponse:
            text = (
                '{"category": "Electrical", "priority": "Critical", '
                '"explanation": "The socket is sparking."}'
            )

        mock_client = mock_genai.Client.return_value
        mock_client.models.generate_content.return_value = FakeResponse()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            result = get_ticket_ai_suggestions("Sparking socket", "The socket is sparking.")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["category"], "Electrical")
        self.assertEqual(result["priority"], "Critical")

    @patch("services.gemini_service.genai")
    def test_ai_client_is_created_with_a_timeout(self, mock_genai):
        class FakeResponse:
            text = '{"category": "Other", "priority": "Low", "explanation": "Minor."}'

        mock_genai.Client.return_value.models.generate_content.return_value = FakeResponse()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            get_ticket_ai_suggestions("Loose handle", "The handle is loose.")
        options = mock_genai.Client.call_args.kwargs["http_options"]
        self.assertGreater(options["timeout"], 0)
        self.assertLessEqual(options["timeout"], 30000)

    @patch("services.gemini_service.genai")
    def test_ai_accepts_cleaning_category_and_new_priority_levels(self, mock_genai):
        class FakeResponse:
            text = (
                '{"category": "Cleaning", "priority": "Important", '
                '"explanation": "The area needs timely cleaning."}'
            )

        mock_client = mock_genai.Client.return_value
        mock_client.models.generate_content.return_value = FakeResponse()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            result = get_ticket_ai_suggestions("Dirty hallway", "The hallway needs cleaning.")

        self.assertEqual(result["category"], "Cleaning")
        self.assertEqual(result["priority"], "Important")


if __name__ == "__main__":
    unittest.main()
