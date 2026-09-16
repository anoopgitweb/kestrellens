"""Voice providers for simulated and explicitly configured outbound calls."""
import base64
import json
import os
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class VoiceProvider(Protocol):
    def call(self, purpose: str, prompt: str) -> dict: ...


class SimulatedVoiceProvider:
    def call(self, purpose: str, prompt: str) -> dict:
        return {"provider": "simulated", "purpose": purpose, "prompt": prompt,
                "status": "awaiting_response"}


class VapiAdapter:
    """Optional integration boundary: implement credentials, calls and verified webhooks."""
    def call(self, purpose: str, prompt: str) -> dict:
        raise NotImplementedError("Vapi is not configured. Use simulated mode.")


class TwilioAdapter:
    """Small Twilio REST adapter; secrets and phone numbers stay server-side."""
    api_root = "https://api.twilio.com/2010-04-01"

    def __init__(self):
        self.sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        self.to_number = os.environ.get("TWILIO_TO_NUMBER", "")
        self.destinations = {
            "reseller_call": os.environ.get("TWILIO_RESELLER_NUMBER", self.to_number),
            "installer_call": os.environ.get("TWILIO_INSTALLER_NUMBER", self.to_number),
            "maya_call": os.environ.get("TWILIO_MAYA_NUMBER", self.to_number),
        }
        self.twiml_url = os.environ.get("TWILIO_TWIML_URL", "")
        self.status_callback = os.environ.get("TWILIO_STATUS_CALLBACK_URL", "")

    @property
    def configured(self):
        return all((self.sid, self.token, self.from_number, self.twiml_url)) and any(self.destinations.values())

    def public_status(self):
        return {
            "provider": "twilio",
            "configured": self.configured,
            "destinations": {key: ("••••" + value[-4:]) if value else None for key, value in self.destinations.items()},
            "custom_flow": "webhooks.twilio.com/v1/Voice/Template/" not in self.twiml_url,
        }

    def call(self, purpose: str, prompt: str) -> dict:
        if not self.configured:
            raise RuntimeError("Twilio is not configured. Add the five TWILIO_* settings from the README.")
        destination = self.destinations.get(purpose, self.to_number)
        if not destination:
            raise RuntimeError(f"No Twilio destination is configured for {purpose.replace('_', ' ')}.")
        fields = {"To": destination, "From": self.from_number, "Url": self.twiml_url,
                  "Method": "POST", "Timeout": "20"}
        if self.status_callback:
            fields.update(StatusCallback=self.status_callback,
                          StatusCallbackMethod="POST",
                          StatusCallbackEvent="initiated ringing answered completed")
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        request = Request(f"{self.api_root}/Accounts/{self.sid}/Calls.json",
                          data=urlencode(fields).encode(), method="POST",
                          headers={"Authorization": f"Basic {auth}",
                                   "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=15) as response:
                result = json.load(response)
        except HTTPError as exc:
            try:
                message = json.load(exc).get("message", "Twilio rejected the call")
            except Exception:
                message = "Twilio rejected the call"
            raise RuntimeError(message) from exc
        return {"provider": "twilio", "purpose": purpose, "status": result.get("status", "queued"),
                "call_sid": result.get("sid"), "destination": "••••" + destination[-4:]}
