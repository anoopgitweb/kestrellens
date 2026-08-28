import importlib.util
import json
import pathlib
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("kestrel_app", pathlib.Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class PlainExplanationTests(unittest.TestCase):
    def test_safe_error_messages(self):
        for status, code, expected in [(401, "invalid_api_key", "rejected the API key"), (429, "insufficient_quota", "quota"), (429, "rate_limit_exceeded", "rate limit"), (404, "model_not_found", "model is unavailable"), (400, "bad_request", "request settings")]:
            error = app.OpenAIRequestError("secret key or private input must not be echoed", status, code)
            message = app._plain_explanation_error_message(error)
            self.assertIn(expected, message)
            self.assertNotIn("secret", message)
        self.assertIn("too long", app._plain_explanation_error_message(TimeoutError()))

    def test_request_and_output(self):
        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Simple explanation."}]}]}
        with patch.object(app, "_openai_response_request", return_value=response) as request:
            result = app._call_openai_plain_explanation("Title", "Source description")
            body = request.call_args.args[0]
            self.assertFalse(body["store"])
            self.assertNotIn("tools", body)
            self.assertEqual(json.loads(body["input"])["description"], "Source description")
            self.assertEqual(result["explanation"], "Simple explanation.")
        with patch.object(app, "_openai_response_request", return_value={"status": "incomplete"}):
            with self.assertRaises(RuntimeError):
                app._call_openai_plain_explanation("Title", "Description")

    def route(self, payload, **overrides):
        defaults = dict(_read_json=payload, _bearer_token="token", _supabase_auth_user={"id": "user"},
                        _assert_owned_jot_subtopic=None, _openai_discovery_rate_allowed=(True, 0),
                        _call_openai_plain_explanation={"explanation": "Draft"})
        defaults.update(overrides)
        from contextlib import ExitStack
        with ExitStack() as stack:
            mocks = {}
            for key, value in defaults.items():
                mocks[key] = stack.enter_context(patch.object(app, key, **({"side_effect": value} if isinstance(value, Exception) else {"return_value": value})))
            stack.enter_context(patch.object(app, "OPENAI_API_KEY", "test-not-a-real-key"))
            output = stack.enter_context(patch.object(app, "_json_response"))
            app.Handler.do_POST(types.SimpleNamespace(path="/api/discover-learn/plain-explanation"))
            return output.call_args.args[1:], mocks["_call_openai_plain_explanation"].call_count

    def test_route_guards_and_success(self):
        valid = {"title": "T", "description": "Description", "consent": True, "subtopic_id": "chapter"}
        self.assertEqual(self.route(valid)[0][0], 200)
        for payload, overrides, expected in [
            ({**valid, "consent": False}, {}, 400),
            ({**valid, "description": "x" * 20001}, {}, 400),
            (valid, {"_supabase_auth_user": PermissionError()}, 403),
            (valid, {"_assert_owned_jot_subtopic": PermissionError()}, 403),
            (valid, {"_openai_discovery_rate_allowed": (False, 3600)}, 429),
        ]:
            result, calls = self.route(payload, **overrides)
            self.assertEqual(result[0], expected)
            self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
