import importlib.util
import pathlib
import types
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location("kestrel_app_jot", pathlib.Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class JotRouteTests(unittest.TestCase):
    def test_new_supabase_secret_key_is_not_sent_as_bearer_token(self):
        response = MagicMock()
        response.read.return_value = b"[]"
        response.__enter__.return_value = response
        with patch.object(app, "SUPABASE_URL", "https://example.supabase.co"), \
             patch.object(app, "SUPABASE_ANON_KEY", "sb_publishable_example"), \
             patch.object(app, "_urlopen_with_retry", return_value=response) as urlopen:
            app._supabase_table_request(
                "ps_assessments", "GET", "?select=id",
                access_token="sb_secret_example", api_key="sb_secret_example",
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Apikey"), "sb_secret_example")
        self.assertIsNone(request.get_header("Authorization"))

    def test_ps_assessment_saves_page_score_separately(self):
        user = {"id": "11111111-1111-4111-8111-111111111111", "email": "admin@example.com"}
        payload = {
            "topicId": "22222222-2222-4222-8222-222222222222",
            "subtopicId": "33333333-3333-4333-8333-333333333333",
            "pageKey": "page-1",
            "pageTitle": "Introduction",
            "rating": "confident",
        }
        saved = {"id": "44444444-4444-4444-8444-444444444444", "rating": "confident", "score": 100}
        with patch.object(app, "_is_timeline_admin", return_value=True), \
             patch.object(app, "_supabase_table_request", side_effect=[[{"id": payload["subtopicId"]}], [], [saved]]) as request:
            result = app._save_ps_assessment(payload, user, "token")

        self.assertEqual(result, saved)
        posted = request.call_args_list[2].args[3][0]
        self.assertEqual(posted["score"], 100)
        self.assertEqual(posted["rating"], "confident")
        self.assertEqual(posted["user_id"], user["id"])

    def test_update_refreshes_with_authenticated_user_object(self):
        user = {"id": "user-123", "email": "admin@example.com"}
        refreshed = {"topics": [], "subtopics": [], "notes": []}
        handler = types.SimpleNamespace(path="/api/jot-down/topic")
        with patch.object(app, "_bearer_token", return_value="token"), \
             patch.object(app, "_supabase_auth_user", return_value=user), \
             patch.object(app, "_assert_notebook_access"), \
             patch.object(app, "_read_json", return_value={"title": "Generated notebook"}), \
             patch.object(app, "_save_jot_topic"), \
             patch.object(app, "_list_jot_down", return_value=refreshed) as list_jot_down, \
             patch.object(app, "_json_response") as json_response:
            app.Handler.do_POST(handler)

        list_jot_down.assert_called_once_with(user, "token")
        json_response.assert_called_once_with(handler, 200, refreshed)


if __name__ == "__main__":
    unittest.main()
