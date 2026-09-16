from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json, os, sqlite3, threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.voice import SimulatedVoiceProvider, TwilioAdapter

ROOT=Path(__file__).resolve().parent.parent
DB=Path(os.environ.get("MAYA_DB",str(ROOT/"data"/"maya.sqlite3")))
LOCK=threading.RLock(); VOICE=SimulatedVoiceProvider()
AGENTS=[("context","Customer context","Understands Maya’s offices and standards"),("solution","AI plan","Turns the goal into coordinated work"),("inventory","Sourcing","Checks internal stock and reseller supply"),("commercial","Commercial","Controls price and delegated spend"),("installation","Installation","Coordinates the delivery partner"),("supplies","Supplies","Arranges toner replenishment"),("maintenance","Maintenance","Extends warranty and support"),("monitoring","Monitoring","Activates proactive device signals"),("communication","Customer communication","Calls each person at the right moment")]

@contextmanager
def database():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with LOCK:
        conn=sqlite3.connect(DB); conn.row_factory=sqlite3.Row
        try:
            with conn: yield conn
        finally: conn.close()

def event(c,agent,message): c.execute("INSERT INTO events(agent,message,time) VALUES(?,?,?)",(agent,message,datetime.now(timezone.utc).isoformat()))
def get(c,name): return json.loads(c.execute("SELECT payload FROM systems WHERE name=?",(name,)).fetchone()[0])
def put(c,name,value): c.execute("INSERT OR REPLACE INTO systems VALUES(?,?)",(name,json.dumps(value)))
def reset(c):
    for table in ("events","agents","systems","journey"): c.execute(f"DELETE FROM {table}")
    c.execute("INSERT INTO journey VALUES(1,'idle',0,NULL,0,NULL)")
    c.executemany("INSERT INTO agents VALUES(?,?,?,'waiting',?)",[(a,n,d,"Ready when you are") for a,n,d in AGENTS])
    systems={
      "customer":{"name":"Maya Chen","company":"Maya Studio","offices":2,"deadline":"Before Monday","goal":"Open a second office next week without coordinating everyone herself."},
      "existing_setup":{"model":"Model X","quantity":2,"profile":"Maya Studio standard","support":"Managed care"},
      "inventory":{"model":"Model X","required":2,"internal_available":0,"status":"not_checked"},
      "reseller":{"name":"Northstar Office Solutions","status":"not_contacted"},
      "quote":{"equipment":2500,"delivery":0,"installation":300,"total":2800,"currency":"USD","threshold":3000,"status":"not_created"},
      "slots":[],"installation":{"status":"not_booked"},"supplies":{"status":"not_scheduled"},"maintenance":{"status":"not_scheduled"},"monitoring":{"status":"not_configured"},
      "resolution":{"trigger":"Internal stock unavailable","action":"Source through approved reseller","status":"planned"}}
    for name,value in systems.items(): put(c,name,value)
    event(c,"Orchestrator","Workspace ready for Maya’s second-office request.")

def init():
    with database() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS journey(id INTEGER PRIMARY KEY,phase TEXT,step INTEGER,selected_slot TEXT,approved INTEGER,call TEXT);CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY,name TEXT,description TEXT,status TEXT,detail TEXT);CREATE TABLE IF NOT EXISTS systems(name TEXT PRIMARY KEY,payload TEXT);CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,agent TEXT,message TEXT,time TEXT);""")
        if not c.execute("SELECT 1 FROM journey").fetchone(): reset(c)

@asynccontextmanager
async def lifespan(app): init(); yield
app=FastAPI(title="Agentic AI Customer Operations - Maya Journey",lifespan=lifespan)
app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
@app.get("/")
def index(): return FileResponse(ROOT/"static"/"index.html")

def snapshot(c):
    state=dict(c.execute("SELECT * FROM journey").fetchone()); state["call"]=json.loads(state["call"]) if state["call"] else None
    state["agents"]=[dict(r) for r in c.execute("SELECT * FROM agents ORDER BY rowid")]
    state["systems"]={r["name"]:json.loads(r["payload"]) for r in c.execute("SELECT * FROM systems")}
    state["events"]=[dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
    state["real_voice"]=TwilioAdapter().public_status(); return state
@app.get("/api/state")
def state():
    with database() as c: return snapshot(c)
def mark(c,agent,detail,status="done"):
    c.execute("UPDATE agents SET status=?,detail=? WHERE id=?",(status,detail,agent)); event(c,agent.title(),detail)
def call(c,purpose,party,prompt):
    payload=VOICE.call(purpose,prompt); payload["party"]=party
    c.execute("UPDATE journey SET phase=?,call=?",(purpose,json.dumps(payload))); mark(c,"communication",f"Calling {party} · {prompt}","attention")

def advance(c):
    j=dict(c.execute("SELECT * FROM journey").fetchone())
    if j["phase"]!="running": return
    step=j["step"]
    if step==0: mark(c,"context","Matched Maya’s existing office: two Model X printers, managed care and standard print profile.")
    elif step==1: mark(c,"solution","Plan created: source two matching devices, deliver Friday, install Monday, then activate supplies and support.")
    elif step==2:
        inv=get(c,"inventory"); inv.update(status="unavailable",internal_available=0); put(c,"inventory",inv)
        mark(c,"inventory","Conflict found · Model X unavailable internally. Searching approved reseller network.","attention")
        event(c,"Orchestrator","Internal stock conflict routed back to sourcing. Northstar reseller selected as the best alternative.")
    elif step==3: call(c,"reseller_call","Reseller","We need two Model X printers delivered before Monday. Can you confirm stock, price and delivery?")
    elif step==4: call(c,"installer_call","Installation Partner","Two devices are being delivered Friday. What installation slots are available?")
    elif step==5: call(c,"maya_call","Maya","I have two installation options: Monday at 10 AM or 2 PM. Which do you prefer?")
    elif step==6:
        quote=get(c,"quote"); quote["status"]="approved_within_threshold"; put(c,"quote",quote)
        mark(c,"commercial","$2,800 total approved within Maya’s delegated $3,000 threshold."); event(c,"Orchestrator","ORDER PLACED · Two Model X printers confirmed for Friday delivery.")
    elif step==7:
        put(c,"supplies",{"status":"scheduled","detail":"Two starter toner sets Friday; usage-based replenishment enabled."}); mark(c,"supplies","Starter toner ships Friday. Usage-based replenishment arranged for both devices.")
    elif step==8:
        put(c,"maintenance",{"status":"active","detail":"Three-year warranty and next-business-day support registered."}); mark(c,"maintenance","Three-year warranty and next-business-day support registered.")
    elif step==9:
        put(c,"monitoring",{"status":"active","detail":"Proactive toner, device health and service alerts activated."}); mark(c,"monitoring","MONITORING ACTIVATED · Toner, device health and service alerts connected.")
    elif step==10:
        mark(c,"communication","Outcome confirmed to Maya, reseller and installation partner."); c.execute("UPDATE journey SET phase='complete'"); event(c,"Orchestrator","COMPLETE · Maya’s second office is ready for delivery and installation.")
    c.execute("UPDATE journey SET step=step+1")

def resolve_call(c,phase,slot=None):
    if phase=="reseller_call":
        put(c,"reseller",{"name":"Northstar Office Solutions","status":"confirmed","response":"2 in stock · $2,500 · Friday delivery"})
        inv=get(c,"inventory"); inv.update(status="reseller_confirmed",reseller_available=2); put(c,"inventory",inv)
        quote=get(c,"quote"); quote["status"]="within_threshold"; put(c,"quote",quote)
        put(c,"resolution",{"trigger":"Internal stock unavailable","action":"Approved reseller confirmed two units within price threshold","status":"resolved"})
        mark(c,"inventory","STOCK CONFIRMED · Northstar: 2 Model X in stock, $2,500, delivery Friday."); mark(c,"commercial","Reseller price checked: package remains $200 below delegated threshold.")
    elif phase=="installer_call":
        slots=[{"id":"10am","label":"Monday · 10:00 AM"},{"id":"2pm","label":"Monday · 2:00 PM"}]; put(c,"slots",slots); put(c,"installation",{"status":"options_found","response":"Monday 10 AM or 2 PM"}); mark(c,"installation","SLOT FOUND · Installation partner offered Monday at 10 AM or 2 PM.")
    elif phase=="maya_call":
        slots=get(c,"slots"); selected=slot or "10am"; match=next((s for s in slots if s["id"]==selected),None)
        if not match: raise HTTPException(422,"Choose one of the installation partner’s slots.")
        put(c,"installation",{"status":"booked","slot":match["label"],"devices":2}); c.execute("UPDATE journey SET selected_slot=?,approved=1",(selected,)); mark(c,"installation",f"APPROVED · Maya chose {match['label']}. Installation booked automatically.")
    c.execute("UPDATE journey SET phase='running',call=NULL"); mark(c,"communication",f"{phase.replace('_call','').title()} response captured and shared with the agent team.")

class Action(BaseModel): action:str=Field(max_length=40); slot:str|None=None

class OpenAIRealtimeRequest(BaseModel):
    sdp: str = Field(min_length=20)
    voice: str = Field(default="marin", max_length=30)

@app.get("/api/openai/status")
def openai_status():
    return {"available": bool(os.environ.get("OPENAI_API_KEY")), "provider": "OpenAI Realtime"}

@app.post("/api/openai/realtime")
def openai_realtime(body: OpenAIRealtimeRequest):
    """Proxy the browser's WebRTC offer so the standard API key stays server-side."""
    api_key=os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "OpenAI voice is not configured. Set OPENAI_API_KEY on the Maya server.")
    voice=body.voice if body.voice in {"marin","cedar","alloy","ash","ballad","coral","echo","sage","shimmer","verse"} else "marin"
    session={"type":"realtime","model":os.environ.get("OPENAI_REALTIME_MODEL","gpt-realtime"),
             "instructions":"You are Maya's friendly customer operations assistant. Speak naturally, briefly, and helpfully. Keep the conversation focused on Maya's printer support journey.",
             "audio":{"output":{"voice":voice}}}
    try:
        with httpx.Client(timeout=25) as client:
            upstream=client.post("https://api.openai.com/v1/realtime/calls",
                headers={"Authorization":f"Bearer {api_key}"},
                files={"sdp":("offer.sdp", body.sdp, "application/sdp"), "session":(None, json.dumps(session), "application/json")})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAI voice connection failed: {exc}") from exc
    if upstream.status_code >= 400:
        raise HTTPException(upstream.status_code, "OpenAI Realtime rejected the call setup.")
    return Response(content=upstream.content, media_type="application/sdp")

@app.post("/api/action")
def action(body:Action):
    with database() as c:
        j=dict(c.execute("SELECT * FROM journey").fetchone()); a=body.action
        if a=="reset": reset(c)
        elif a=="start":
            if j["phase"]=="idle": c.execute("UPDATE journey SET phase='running'"); event(c,"Orchestrator","Goal accepted. Building the second-office plan across people and systems.")
        elif a=="tick": advance(c)
        elif a=="simulate_call":
            if j["phase"] not in ("reseller_call","installer_call","maya_call"): raise HTTPException(409,"No call response is pending.")
            resolve_call(c,j["phase"],body.slot)
        elif a=="choose_slot":
            if j["phase"]!="maya_call": raise HTTPException(409,"Maya’s installation choice is not pending.")
            resolve_call(c,j["phase"],body.slot)
        elif a=="real_call":
            if j["phase"] not in ("reseller_call","installer_call","maya_call"): raise HTTPException(409,"No party is waiting to be called.")
            try: result=TwilioAdapter().call(j["phase"],json.loads(j["call"])["prompt"])
            except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
            event(c,"Customer communication",f"Real Twilio call {result['status']} to {json.loads(j['call'])['party']} at {result['destination']} · {result['call_sid']}")
        elif a=="force_approval":
            if j["phase"]!="maya_call": raise HTTPException(409,"Maya’s choice is not pending.")
            resolve_call(c,"maya_call",body.slot or "10am"); event(c,"Presenter","Maya’s 10 AM response entered by presenter override.")
        elif a=="complete":
            if not j["approved"] or j["phase"] not in ("running","complete"): raise HTTPException(409,"Capture Maya’s installation choice before completing.")
            for _ in range(12): advance(c)
        else: raise HTTPException(422,"Unknown presenter action.")
        return snapshot(c)
