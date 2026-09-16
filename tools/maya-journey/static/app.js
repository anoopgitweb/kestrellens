const $=id=>document.getElementById(id);
const chapters=[
  {
    name:"iXHello",label:"SELF SERVICE",accent:"#54e0d4",icon:"◉",
    title:"Five minutes. One printer problem.",
    text:"A few days ago, I was getting ready for an important presentation. It was starting in five minutes—and suddenly, my printer stopped working. I contacted the I X Hello Voice Bot.\n\nI was recognized immediately, my printer was identified, and troubleshooting started right away. When the problem wasn't completely resolved, I was connected to the right support person—and everything we'd already tried went with me. I didn't have to start all over again.",
    line:"With my identity, device and troubleshooting history already carried forward, my journey continued with a support agent.",
    action:"Continue Maya's journey",
    nodes:[["◉","I X HELLO","VOICE BOT"],["✓","CUSTOMER","Recognized"],["▣","DEVICE","Identified"],["⚙","CHECKS","Completed"],["↗","AGENT","Connected"]],
    sync:["I contacted the I X Hello Voice Bot","I contacted the I X Hello Voice Bot","recognized immediately","recognized immediately","printer was identified","printer was identified","troubleshooting started","troubleshooting started","connected to the right support person"],
    dialog:{title:"Try the self-service moment",copy:"Choose what Maya says. iXHello recognizes the intent, identifies the device and preserves the context.",options:["My printer stopped working","My presentation starts in five minutes","Connect me to support"],results:["Maya recognized · Printer matched · Guided troubleshooting started.","Urgency detected · Priority raised · Fast-path support selected.","Right agent found · Identity, device and attempted fixes transferred."]}
  },
  {
    name:"iXHero",label:"AGENT EXPERIENCE",accent:"#6bbbe9",icon:"✦",
    title:"The agent already knew.",
    text:"When the agent joined, I expected the usual questions. Who are you? What's the problem? What have you already tried?\n\nBut none of that happened. The agent already knew because the I X Hello Bot had transferred my customer information and the specifics of my issue to the agent.\n\nThen, almost like magic, the distracting background noise simply disappeared. The agent's accent, which had been a little difficult at first, suddenly sounded clear and effortless. And throughout our conversation, exactly the right information appeared at precisely the right moment.\n\nA few minutes later, my printer was working. The agent did a great job helping me and made the whole experience feel easy. When the conversation ended, I received a detailed email with everything we had discussed, the specifics of the resolution, and clear next steps. I had a complete record without needing to ask for anything else.",
    line:"For me, it was simply one seamless conversation. Want to experience what was happening behind it?",
    action:"Experience iXHero",
    signals:[["◉","I X Hello Bot → Agent","Customer information and issue specifics transferred"],["◌","Clarity activated","Background noise removed"],["≈","Harmony activated","Accent made easier to understand"],["⌁","Knowledge","The right information arrived"],["✓","Issue resolved","Printer working"],["▤","Summarize, Insights, Roleplay, Prompts","Resolution specifics and next steps emailed"]],
    sync:["I X Hello Bot","background noise","accent, which","right information","printer was working","conversation ended"],
    dialog:{title:"See the agent workspace",copy:"Turn on the capabilities that quietly improve Maya's conversation.",options:["Clarity","Harmony","Knowledge","Summarize","Insights","Role Play","Announcements"],results:["Clarity removes distracting background noise.","Harmony makes the conversation easier to understand.","Knowledge finds the next best answer in context.","Summarize completes the interaction notes.","Insights converts the conversation into action.","Role Play gives the agent a safe place to practice.","Announcements keeps the team aligned in the flow of work."]}
  },
  {
    name:"Language Translation",label:"LANGUAGE WITHOUT BARRIERS",accent:"#9b8ae7",icon:"文",
    title:"I preferred to speak in Japanese.",
    text:"Before I left, I had one more question. I preferred to speak in Japanese.\n\nThere was no transfer, no interruption, and no waiting. I simply started speaking in Japanese. It felt completely seamless—I understood everything clearly, and the conversation continued naturally.\n\nI spoke in the language I was most comfortable with and got exactly the information I wanted.",
    line:"I didn't adapt to the technology. The technology adapted to me—and the conversation simply continued.",
    action:"Choose a language",
    dialog:{title:"Choose Maya's language",copy:"Maya speaks naturally while the agent continues in English. Meaning moves between them in real time.",options:["日本語 · Japanese","हिन्दी · Hindi","Español · Spanish","Français · French","Deutsch · German"],results:["こんにちは。プリンターについてもう一つ質問があります。 ↔ Hello. I have one more question about my printer.","नमस्ते। मेरे प्रिंटर के बारे में एक और सवाल है। ↔ Hello. I have one more question about my printer.","Hola. Tengo otra pregunta sobre mi impresora. ↔ Hello. I have one more question about my printer.","Bonjour. J'ai une autre question sur mon imprimante. ↔ Hello. I have one more question about my printer.","Hallo. Ich habe noch eine Frage zu meinem Drucker. ↔ Hello. I have one more question about my printer."]}
  },
  {
    name:"Agentic AI",label:"FROM RESPONSE TO OUTCOME",accent:"#efbd67",icon:"✳",
    title:"What if I didn't have to keep asking?",
    text:"Recently, I applied for my first home loan. There were documents, checks, policies and different people involved. Normally, I'd have to keep checking what was happening and what I needed to do next.\n\nThis time, I simply gave AI my goal. It checked my information. It checked my documents. When something was missing, it emailed me. When I didn't respond, it followed up. When I still didn't respond, it called me.\n\nIt coordinated the property valuation and legal verification, then kept working until everything required for my application was ready for the authorized person to review.",
    line:"I didn't manage the process. I simply told AI what I wanted to achieve. Want to see an AI actually work toward a goal?",
    action:"Give AI the goal",
    goal:"Get my home-loan application ready for approval.",
    tasks:["Information checked","Documents checked","Missing item emailed","Follow-up sent","Maya called","Valuation coordinated","Legal verification complete","Ready for authorized review"],
    sync:["gave AI my goal","checked my information","checked my documents","something was missing","didn't respond","it called me","property valuation","legal verification","ready for the authorized person"],
    dialog:{title:"AI is working toward Maya's goal",copy:"The AI can coordinate the work, follow up and react to delays. The lending decision remains with the authorized person.",options:["Start goal run","Show missing document","Follow up with Maya","Call Maya","Prepare for review"],results:["Goal accepted · Plan created · Six connected workstreams started.","Income statement missing · Secure upload request sent to Maya.","No response received · Context-aware reminder sent automatically.","Calling Maya · Reason explained · Secure upload link reissued.","All required checks complete · Application packaged for authorized review."]}
  },
  {
    name:"Replication",label:"FROM ONE TO THOUSANDS",accent:"#73d3a1",icon:"∞",
    title:"Why should an experience like mine happen only once?",
    text:"So that's my experience. From the moment I asked for help to the moment everything was resolved, the journey felt simple, personal, and effortless.\n\nAnd if it worked so well for me, perhaps it could create the same positive experience for another customer.\n\nI came away feeling heard, understood, and well cared for. It was a smooth, connected experience from beginning to end—and one I would be happy to have again.",
    line:"My journey felt simple, personal, and connected from beginning to end.",
    action:"Explore the experiences",
    replicas:[["01","iXHello"],["02","iXHero"],["03","Language Translation Tools"],["04","Agentic AI"]],
    dialog:{title:"A repeatable path to scale",copy:"Take a proven customer outcome and make it reusable across accounts, processes and markets.",options:["Discover","Prove","Replicate","Scale"],results:["Find the moments where customer effort and operational friction meet.","Validate the experience with real users, controls and measurable outcomes.","Package the workflow, integrations, guardrails and learning.","Deploy the proven pattern across teams, accounts and markets."]}
  }
];
let active=0,voiceEnabled=true,musicEnabled=true,musicVolume=.85,autoAdvance=false,autoAdvanceTimer=null,speechRun=0,introActive=true,introSpeechStarted=false;
let musicContext=null,musicMaster=null,musicTimer=null,musicStep=0;

function esc(value){return String(value).replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]))}
function mayaVoice(){
  const voices=speechSynthesis.getVoices();
  return voices.find(voice=>/en-IN/i.test(voice.lang)&&/female|heera|veena|neerja/i.test(voice.name))||voices.find(voice=>/en-IN/i.test(voice.lang))||voices.find(voice=>/female|samantha|zira|aria/i.test(voice.name))||null;
}
function syncMusicButtons(){
  [["musicButton","♫ Music on","♫ Music off"],["introMusicButton","♫ Music on","♫ Music off"]].forEach(([id,on,off])=>{const button=$(id);button.setAttribute("aria-pressed",String(musicEnabled));button.classList.toggle("active",musicEnabled);button.textContent=musicEnabled?on:off});
  ["musicVolume","introMusicVolume"].forEach(id=>{$(id).value=Math.round(musicVolume*100);$(id).disabled=!musicEnabled});
}
function setMusicVolume(value){
  musicVolume=Math.max(0,Math.min(1,Number(value)/100));syncMusicButtons();
  if(musicContext&&musicMaster&&musicTimer){const now=musicContext.currentTime;musicMaster.gain.cancelScheduledValues(now);musicMaster.gain.setValueAtTime(Math.max(.0001,musicMaster.gain.value),now);musicMaster.gain.linearRampToValueAtTime(Math.max(.0001,musicVolume*1.2),now+.18)}
}
function musicNote(frequency,duration=.38,volume=.026,type="sine"){
  if(!musicContext||!musicMaster)return;
  const now=musicContext.currentTime,oscillator=musicContext.createOscillator(),gain=musicContext.createGain();
  oscillator.type=type;oscillator.frequency.setValueAtTime(frequency,now);gain.gain.setValueAtTime(.0001,now);gain.gain.exponentialRampToValueAtTime(volume,now+.045);gain.gain.exponentialRampToValueAtTime(.0001,now+duration);
  oscillator.connect(gain).connect(musicMaster);oscillator.start(now);oscillator.stop(now+duration+.03);
}
function musicBeat(){
  const melody=[261.63,329.63,392,493.88,440,392,329.63,293.66];
  musicNote(melody[musicStep%melody.length],.34,.023,"sine");
  if(musicStep%2===0)musicNote(melody[(musicStep+2)%melody.length]/2,.55,.012,"triangle");
  musicStep++;
}
function startMusic(){
  if(!musicEnabled||musicTimer)return;
  const AudioContextClass=window.AudioContext||window.webkitAudioContext;if(!AudioContextClass)return;
  if(!musicContext){musicContext=new AudioContextClass();musicMaster=musicContext.createGain();musicMaster.gain.value=.0001;musicMaster.connect(musicContext.destination)}
  musicContext.resume();const now=musicContext.currentTime;musicMaster.gain.cancelScheduledValues(now);musicMaster.gain.setValueAtTime(Math.max(.0001,musicMaster.gain.value),now);musicMaster.gain.linearRampToValueAtTime(Math.max(.0001,musicVolume*1.2),now+.7);
  musicBeat();musicTimer=setInterval(musicBeat,430);
}
function stopMusic(){
  if(musicTimer){clearInterval(musicTimer);musicTimer=null}
  if(musicContext&&musicMaster){const now=musicContext.currentTime;musicMaster.gain.cancelScheduledValues(now);musicMaster.gain.setValueAtTime(Math.max(.0001,musicMaster.gain.value),now);musicMaster.gain.linearRampToValueAtTime(.0001,now+.65)}
}
function toggleMusic(){musicEnabled=!musicEnabled;syncMusicButtons();if(!musicEnabled)stopMusic();else if(speechSynthesis?.speaking)startMusic()}
function postMayaState(){window.parent?.postMessage({type:"maya-state",voiceEnabled,musicEnabled,musicVolume,autoAdvance},"*")}
function enterJourney(){
  if(!introActive)return;
  introActive=false;speechRun++;speechSynthesis?.cancel();
  const intro=$("mayaIntro");
  intro.classList.add("leaving");
  setTimeout(()=>{intro.hidden=true;intro.classList.remove("leaving");$("experienceShell").hidden=false;showChapter(0)},580);
}
function speakIntro(continueToJourney=false){
  if(!introActive||introSpeechStarted||!voiceEnabled||!("speechSynthesis" in window)){if(continueToJourney)enterJourney();return}
  introSpeechStarted=true;speechSynthesis.cancel();
  const utterance=new SpeechSynthesisUtterance("Hello, I'm Maya. I'm going to take you through one connected customer journey, and show you the technology working quietly behind every moment. It all began with a printer problem, just minutes before an important presentation. Let me show you what happened.");
  utterance.voice=mayaVoice();utterance.rate=1.08;utterance.pitch=1.02;
  utterance.onend=()=>{stopMusic();if(continueToJourney)enterJourney()};
  utterance.onerror=()=>{stopMusic();introSpeechStarted=false;if(continueToJourney)enterJourney()};
  startMusic();speechSynthesis.speak(utterance);
}
function renderRail(){
  $("chapterRail").innerHTML=chapters.map((chapter,index)=>`<button class="chapter-tab ${index===active?"active":""}" style="--accent:${chapter.accent}" data-index="${index}"><span>${String(index+1).padStart(2,"0")}</span><b>${esc(chapter.name)}</b></button>`).join("");
  document.querySelectorAll(".chapter-tab").forEach(button=>button.onclick=()=>showChapter(+button.dataset.index));
}
function visualFor(chapter){
  if(chapter.nodes)return `<div class="flow-row">${chapter.nodes.map((node,index)=>`<div class="flow-node"><b>${node[0]}</b><span>${node[1]}<br>${node[2]}</span></div>${index<chapter.nodes.length-1?'<i class="flow-arrow">→</i>':""}`).join("")}</div>`;
  if(chapter.signals)return `<div class="signal-list">${chapter.signals.map((item,index)=>`<div class="signal" style="--fill:${34+index*14}%"><span class="signal-icon">${item[0]}</span><div><b>${item[1]}</b><small>${item[2]}</small></div></div>`).join("")}</div>`;
  if(chapter.name==="Language Translation")return '<div class="translation-bridge"><div class="speaker"><b>Maya</b><span>日本語 · Japanese</span></div><div class="bridge-core">→<small>SPEAKS<br>NATURALLY</small></div><div class="wisdom-box"><b>iXWisdom</b><span>Real-time language intelligence</span></div><div class="bridge-core">→<small>MEANING<br>PRESERVED</small></div><div class="speaker"><b>Agent</b><span>English</span></div></div>';
  if(chapter.goal)return `<div class="goal-card"><small>MAYA'S GOAL</small><b>“${chapter.goal}”</b></div><div class="task-grid">${chapter.tasks.map(task=>`<div class="task">${task}</div>`).join("")}</div>`;
  return `<div class="replication">${chapter.replicas.map(item=>`<div class="replica"><b>${item[0]}</b><span>${item[1]}</span></div>`).join("")}</div>`;
}
function revealFeatures(syncToSpeech=false){
  const canvas=$("visualCanvas"),items=[...canvas.querySelectorAll(".flow-node,.flow-arrow,.signal,.speaker,.bridge-core,.wisdom-box,.goal-card,.task,.replica")];
  canvas.classList.remove("revealing");
  items.forEach((item,index)=>{item.classList.add("reveal-item");item.classList.remove("revealed");item.style.setProperty("--reveal-delay",syncToSpeech?"0s":`${.35+index*1.35}s`)});
  if(!syncToSpeech)requestAnimationFrame(()=>requestAnimationFrame(()=>canvas.classList.add("revealing")));
}
function speak(){
  if(introActive||!voiceEnabled||!("speechSynthesis" in window))return;
  const run=++speechRun,chapterIndex=active;
  speechSynthesis.cancel();
  const chapter=chapters[active],spokenText=`${chapter.text} ${chapter.line}`;revealFeatures(!!chapter.sync);
  const utterance=new SpeechSynthesisUtterance(spokenText);
  utterance.voice=mayaVoice();
  if(chapter.sync){const offsets=chapter.sync.map(phrase=>spokenText.indexOf(phrase));utterance.onboundary=event=>{document.querySelectorAll("#visualCanvas .reveal-item").forEach((item,index)=>{if(offsets[index]>=0&&event.charIndex>=offsets[index])item.classList.add("revealed")})}}
  utterance.rate=1.12;utterance.pitch=1.02;utterance.onend=()=>{if(run===speechRun)stopMusic();document.querySelectorAll(".reveal-item").forEach(item=>{item.style.opacity="1";item.style.transform="none"});if(run===speechRun&&chapterIndex===active&&autoAdvance){clearTimeout(autoAdvanceTimer);autoAdvanceTimer=setTimeout(()=>transitionToNextScene(),1100)}};utterance.onerror=()=>{if(run===speechRun)stopMusic()};startMusic();speechSynthesis.speak(utterance);
}
function showChapter(index,{speakNow=true}={}){
  clearTimeout(autoAdvanceTimer);speechRun++;
  active=Math.max(0,Math.min(chapters.length-1,index));const chapter=chapters[active];
  document.body.dataset.chapter=String(active+1);
  document.documentElement.style.setProperty("--accent",chapter.accent);
  $("chapterNumber").textContent=String(active+1).padStart(2,"0");$("chapterName").textContent=chapter.name;
  $("storyKicker").innerHTML=`${String(active+1).padStart(2,"0")} · ${chapter.label}${active===3?' <span class="prototype-badge">PROTOTYPE</span>':""}`;
  $("storyTitle").textContent=chapter.title;$("storyText").textContent=chapter.text;$("mayaLine").textContent=`“${chapter.line}”`;
  $("primaryAction").firstChild.textContent=chapter.action+" ";$("visualCanvas").innerHTML=visualFor(chapter);revealFeatures(!!chapter.sync);
  $("previousButton").disabled=active===0;$("nextButton").textContent=active===chapters.length-1?"Finish journey →":"Next chapter →";
  $("progressLabel").textContent=`${active+1} of ${chapters.length}`;$("progressBar").style.width=`${(active+1)/chapters.length*100}%`;
  renderRail();if(speakNow)speak();
}
function transitionToNextScene(){
  const stage=document.querySelector(".story-stage");
  stage.classList.remove("scene-entering");stage.classList.add("scene-leaving");
  setTimeout(()=>{stage.classList.remove("scene-leaving");if(active===chapters.length-1){renderFinale();return}showChapter(active+1);stage.classList.add("scene-entering");setTimeout(()=>stage.classList.remove("scene-entering"),620)},460);
}
function openExperience(index=active){
  speechRun++;speechSynthesis?.cancel();stopMusic();
  const chapter=chapters[index],dialog=chapter.dialog;
  document.documentElement.style.setProperty("--accent",chapter.accent);
  $("dialogContent").innerHTML=`<div class="dialog-body"><span>${String(index+1).padStart(2,"0")} · ${chapter.name}</span><h2>${dialog.title}</h2><p>${dialog.copy}</p><div class="try-panel"><h3>Choose an action</h3><div class="try-options">${dialog.options.map((option,i)=>`<button data-result="${i}">${option}</button>`).join("")}</div><div class="try-result">Select an option to begin.</div></div></div>`;
  $("dialogContent").querySelectorAll("[data-result]").forEach(button=>button.onclick=()=>{
    $("dialogContent").querySelectorAll("[data-result]").forEach(item=>item.classList.remove("active"));button.classList.add("active");
    $("dialogContent").querySelector(".try-result").textContent=dialog.results[+button.dataset.result];
  });
  $("experienceDialog").showModal();
}
function speakFinale(){
  if($("finale").hidden||!voiceEnabled||!("speechSynthesis" in window))return;
  const finaleText="Now you know my journey, and you have seen how each experience helped make it simple, personal, and connected. But you do not have to experience it only through my story. Here at the Tech Experience Center, you can try these capabilities for yourself, in real time. Start at Kiosk One and speak with the I X Hello Voice Bot. At Kiosk Two, experience a clearer, more helpful conversation. At Kiosk Three, communicate naturally in the language you prefer. At Kiosk Four, give AI a goal and watch it coordinate the work. And at Kiosk Five, see how a successful experience can reach another customer. Please explore the kiosks, try the technology, and imagine what an effortless experience could feel like for your customers. I hope you enjoy it as much as I did.";
  const kioskOffsets=["Kiosk One","Kiosk Two","Kiosk Three","Kiosk Four","Kiosk Five"].map(phrase=>finaleText.indexOf(phrase));
  const highlightKiosk=index=>document.querySelectorAll(".experience-tile").forEach((card,cardIndex)=>card.classList.toggle("speaking",cardIndex===index));
  const utterance=new SpeechSynthesisUtterance(finaleText);
  utterance.voice=mayaVoice();utterance.rate=1.08;utterance.pitch=1.02;utterance.onboundary=event=>{let current=-1;kioskOffsets.forEach((offset,index)=>{if(event.charIndex>=offset)current=index});if(current>=0)highlightKiosk(current)};utterance.onend=()=>{stopMusic();highlightKiosk(-1)};utterance.onerror=()=>{stopMusic();highlightKiosk(-1)};startMusic();speechSynthesis.speak(utterance);
}
function renderFinale(){
  clearTimeout(autoAdvanceTimer);speechRun++;speechSynthesis?.cancel();stopMusic();$("finale").hidden=false;
  const kioskActivities=[
    "Talk to the I X Hello Voice Bot and try the printer-support self-service journey.",
    "Experience noise removal, accent clarity and real-time knowledge during a live conversation.",
    "Choose a language and experience seamless real-time communication through iXWisdom.",
    "Give AI a goal and watch it coordinate the steps needed to prepare a home-loan application.",
    "Explore how one proven experience can be replicated across processes, accounts and markets."
  ];
  const orbitNames=["iXHello","iXHero","Language Translation Tools","Agent AI","Tech Replication Tools"];
  $("experienceTiles").innerHTML=chapters.map((chapter,index)=>`<button class="experience-tile" style="--accent:${chapter.accent};--orbit-index:${index}" data-index="${index}" aria-label="Open Kiosk ${index+1}: ${orbitNames[index]}"><em>0${index+1}</em><span>${chapter.icon}</span><b>${orbitNames[index]}</b><small>Try this experience →</small></button>`).join("");
  document.querySelectorAll(".experience-tile").forEach(tile=>tile.onclick=()=>openExperience(+tile.dataset.index));
  setTimeout(speakFinale,500);
}
function beginJourney(){
  if(!introActive||introSpeechStarted)return;
  const button=$("beginJourney");button.disabled=true;button.setAttribute("aria-busy","true");button.innerHTML="Maya is speaking <span>●</span>";
  speakIntro(true);
}
$("primaryAction").onclick=()=>active===0?showChapter(1):active===chapters.length-1?renderFinale():openExperience();
$("beginJourney").onclick=beginJourney;
$("musicButton").onclick=toggleMusic;
$("introMusicButton").onclick=toggleMusic;
$("musicVolume").oninput=event=>setMusicVolume(event.target.value);
$("introMusicVolume").oninput=event=>setMusicVolume(event.target.value);
$("closeDialog").onclick=()=>$("experienceDialog").close();
$("experienceDialog").onclick=event=>{if(event.target===$("experienceDialog"))$("experienceDialog").close()};
$("previousButton").onclick=()=>showChapter(active-1);
$("nextButton").onclick=()=>active===chapters.length-1?renderFinale():showChapter(active+1);
$("restartButton").onclick=()=>{speechRun++;clearTimeout(autoAdvanceTimer);speechSynthesis?.cancel();stopMusic();$("finale").hidden=true;$("experienceShell").hidden=true;$("mayaIntro").hidden=false;introActive=true;introSpeechStarted=false;const button=$("beginJourney");button.disabled=false;button.removeAttribute("aria-busy");button.innerHTML="Begin Maya’s Journey <span>→</span>"};
$("backToStory").onclick=()=>{speechRun++;speechSynthesis?.cancel();stopMusic();$("finale").hidden=true;showChapter(4,{speakNow:false})};
$("replayVoice").onclick=speak;
$("voiceButton").onclick=()=>{voiceEnabled=!voiceEnabled;$("voiceButton").setAttribute("aria-pressed",voiceEnabled);$("voiceButton").textContent=voiceEnabled?"◉ Maya voice on":"○ Maya voice off";if(voiceEnabled)speak();else{speechRun++;clearTimeout(autoAdvanceTimer);speechSynthesis?.cancel();stopMusic()}};
$("autoAdvanceButton").onclick=()=>{autoAdvance=!autoAdvance;$("autoAdvanceButton").classList.toggle("active",autoAdvance);$("autoAdvanceButton").setAttribute("aria-pressed",autoAdvance);$("autoAdvanceButton").textContent=autoAdvance?"● Auto advance on":"▷ Auto advance";if(!autoAdvance)clearTimeout(autoAdvanceTimer);else if(!voiceEnabled){voiceEnabled=true;$("voiceButton").setAttribute("aria-pressed","true");$("voiceButton").textContent="◉ Maya voice on";speak()}};
$("fullscreenButton").onclick=()=>document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();
document.addEventListener("fullscreenchange",()=>{const full=!!document.fullscreenElement;$("fullscreenButton").textContent=full?"⛶ Exit full screen":"⛶ Full screen";$("fullscreenButton").setAttribute("aria-label",full?"Exit full screen":"Enter full screen")});
document.addEventListener("keydown",event=>{if($("experienceDialog").open)return;if(event.key==="ArrowRight")$("nextButton").click();if(event.key==="ArrowLeft")$("previousButton").click();if(event.key==="Escape"&&!$("finale").hidden)$("backToStory").click()});
window.addEventListener("message",event=>{
  if(event.data?.type==="maya-audio-start"){if(voiceEnabled&&!introActive)speak();return}
  if(event.data?.type!=="maya-control")return;
  const {action,value}=event.data;
  if(action==="toggle-voice")$("voiceButton").click();
  if(action==="toggle-music")$("musicButton").click();
  if(action==="set-volume")setMusicVolume(value);
  if(action==="toggle-auto")$("autoAdvanceButton").click();
  if(action==="restart")$("restartButton").click();
  postMayaState();
});
speechSynthesis?.getVoices();syncMusicButtons();showChapter(0,{speakNow:false});
