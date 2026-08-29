import importlib.util
import pathlib
import types
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("kestrel_app_jot", pathlib.Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class JotRouteTests(unittest.TestCase):
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
