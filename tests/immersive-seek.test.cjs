const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../templates/index.html'),'utf8');
const start=html.split(/\r?\n/).find(line=>line.startsWith('function startJotReadAloud('));
const seek=html.slice(html.indexOf('function seekJotImmersiveSentence('),html.indexOf('function mountJotImmersiveImages('));
const text='First. Second. Third.';
let spoken,highlight,requested;
const context={state:{jotViewMode:'immersive'},jotSpeechPageIndex:2,jotSpeechSourceText:text,jotSpeechCurrentCharIndex:8,
 selectedJotSpeechPage:()=>({index:2,item:{classList:{add(){}}}}),jotSpeechPageText:()=>text,
 jotSentenceRanges:()=>[{start:0,end:7},{start:7,end:15},{start:15,end:21}],
 startJotReadAloud:(...args)=>requested=args};
vm.createContext(context);vm.runInContext(seek,context);
vm.runInContext('seekJotImmersiveSentence(-1)',context);assert.deepEqual(requested,[false,0]);
vm.runInContext('seekJotImmersiveSentence(1)',context);assert.deepEqual(requested,[false,15]);
context.jotSpeechCurrentCharIndex=20;vm.runInContext('seekJotImmersiveSentence(1)',context);assert.deepEqual(requested,[false,15]);
Object.assign(context,{$:()=>({value:'1'}),stopJotReadAloud(){},renderJotSpeechTranscript(){},renderJotImmersiveCopy(){},highlightJotSpeechSentence:n=>highlight=n,
 SpeechSynthesisUtterance:function(value){this.text=value},window:{speechSynthesis:{getVoices:()=>[],speak:u=>spoken=u}},jotImmersiveVoiceUri:()=>'',renderJotReadAloudState(){},setTimeout:fn=>fn()});
vm.runInContext(start,context);vm.runInContext('startJotReadAloud(false,7)',context);
assert.equal(spoken.text,text.slice(7));assert.equal(highlight,7);
spoken.onboundary({charIndex:8});assert.equal(highlight,15);assert.equal(context.jotSpeechPageIndex,2);
assert.equal(context.jotSpeechContinuous,false,'Seeking must not auto-advance pages');
for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)){if(match[1].trim())new vm.Script(match[1]);}
console.log('Immersive seeking: sentence offsets, boundaries, same-page playback and script syntax passed');
