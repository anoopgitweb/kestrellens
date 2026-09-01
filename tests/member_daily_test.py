import json
import unittest
from unittest.mock import patch

import app


class MemberDailyTests(unittest.TestCase):
    def setUp(self):
        app.MEMBER_DAILY_CACHE.clear()
        app.MEMBER_VIDEO_CACHE.clear()

    def test_fallback_has_complete_challenge(self):
        result = app._member_daily_fallback("AI Engineering")
        self.assertEqual(len(result["challenge"]["options"]), 4)
        self.assertIn(result["challenge"]["correctIndex"], range(4))
        self.assertIn("AI Engineering", result["challenge"]["topic"])

    @patch.object(app, "OPENAI_API_KEY", "")
    @patch.object(app, "_list_jot_down")
    def test_daily_learning_uses_safe_fallback_without_openai(self, list_jot):
        list_jot.return_value = {"topics": [{"title": "Vector Databases"}], "subtopics": [], "notes": []}
        result = app._member_daily_learning({"id": "member-1"}, "token")
        self.assertEqual(result["generatedBy"], "KestrelIQ")
        self.assertEqual(result["challenge"]["topic"], "Vector Databases")

    @patch.object(app, "_openai_response_request")
    def test_ai_video_script_reattaches_verified_source(self, openai_request):
        script = {"opening": "Today in AI.", "scenes": [{"articleIndex": 0, "category": "AI models", "title": "A concise title", "whyItMatters": "A grounded implication.", "narration": "A short narration."}], "closing": "That is the briefing."}
        openai_request.return_value = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(script), "annotations": []}]}]}
        result = app._call_openai_member_video([{"headline": "A source headline", "source": "Publisher", "url": "https://example.com/story", "imageUrl": "https://example.com/image.jpg", "displayDate": "29 Aug 2026"}], "member-1")
        self.assertEqual(result["generatedBy"], "OpenAI")
        self.assertEqual(result["scenes"][0]["url"], "https://example.com/story")
        self.assertEqual(result["scenes"][0]["source"], "Publisher")
        self.assertEqual(result["scenes"][0]["imageUrl"], "https://example.com/image.jpg")


if __name__ == "__main__":
    unittest.main()
