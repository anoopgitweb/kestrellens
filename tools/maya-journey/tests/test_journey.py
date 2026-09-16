import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import main

class JourneyTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); main.DB=Path(self.tmp.name)/"test.sqlite3"; self.client=TestClient(main.app); self.client.__enter__()
    def tearDown(self): self.client.__exit__(None,None,None); self.tmp.cleanup()
    def act(self,action,**kwargs):
        r=self.client.post("/api/action",json={"action":action,**kwargs}); self.assertEqual(r.status_code,200,r.text); return r.json()
    def to_reseller(self):
        self.act("start")
        for _ in range(4): s=self.act("tick")
        self.assertEqual(s["phase"],"reseller_call"); return s
    def to_maya(self):
        self.to_reseller(); self.act("simulate_call"); self.act("tick"); self.act("simulate_call"); return self.act("tick")
    def test_full_ecosystem_journey_both_slots(self):
        for slot in ("10am","2pm"):
            self.act("reset"); s=self.to_reseller()
            self.assertEqual(s["systems"]["inventory"]["internal_available"],0)
            s=self.act("simulate_call"); self.assertEqual(s["systems"]["reseller"]["status"],"confirmed")
            self.assertEqual(s["systems"]["resolution"]["status"],"resolved")
            self.assertLess(s["systems"]["quote"]["total"],s["systems"]["quote"]["threshold"])
            self.act("tick"); s=self.act("simulate_call"); self.assertEqual(len(s["systems"]["slots"]),2)
            self.act("tick"); self.act("choose_slot",slot=slot); s=self.act("complete")
            self.assertEqual(s["phase"],"complete"); self.assertEqual(s["selected_slot"],slot)
            self.assertEqual(s["systems"]["monitoring"]["status"],"active")
            self.assertTrue(all(a["status"]=="done" for a in s["agents"]))
    def test_calls_are_gated_and_maya_defaults_to_10am(self):
        self.assertEqual(self.client.post("/api/action",json={"action":"simulate_call"}).status_code,409)
        s=self.to_maya(); self.assertEqual(s["phase"],"maya_call")
        s=self.act("simulate_call"); self.assertEqual(s["selected_slot"],"10am"); self.assertTrue(s["approved"])
    def test_invalid_slot_and_completion_gate(self):
        self.assertEqual(self.client.post("/api/action",json={"action":"complete"}).status_code,409)
        self.to_maya(); self.assertEqual(self.client.post("/api/action",json={"action":"choose_slot","slot":"midnight"}).status_code,422)
    def test_real_call_requires_configuration(self):
        self.to_reseller(); r=self.client.post("/api/action",json={"action":"real_call"}); self.assertEqual(r.status_code,503)
        state=self.client.get("/api/state").json(); self.assertFalse(state["real_voice"]["configured"]); self.assertIn("destinations",state["real_voice"])

if __name__=="__main__": unittest.main()
