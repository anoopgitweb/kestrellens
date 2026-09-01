import unittest
from unittest.mock import patch

import app


class UserFeedbackTests(unittest.TestCase):
    @patch.object(app, "_supabase_table_request")
    def test_feedback_is_tied_to_authenticated_user(self, table_request):
        table_request.return_value = [{"id": "feedback-1"}]
        result = app._save_user_feedback(
            {"message": "Please add more guided learning.", "category": "learning", "rating": 5},
            {"id": "user-1", "email": "learner@example.com"},
            "access-token",
        )
        self.assertEqual(result["id"], "feedback-1")
        record = table_request.call_args.args[3][0]
        self.assertEqual(record["user_id"], "user-1")
        self.assertEqual(record["user_email"], "learner@example.com")
        self.assertEqual(record["rating"], 5)

    def test_short_feedback_is_rejected(self):
        with self.assertRaises(ValueError):
            app._save_user_feedback({"message": "No"}, {"id": "user-1"}, "token")

    def test_non_admin_cannot_read_all_feedback(self):
        with self.assertRaises(PermissionError):
            app._admin_feedback({"email": "learner@example.com"})


if __name__ == "__main__":
    unittest.main()
