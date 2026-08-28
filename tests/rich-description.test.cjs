const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const html = fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
const lines = html.split(/\r?\n/);
function fn(name){return lines.find(l=>l.startsWith('function '+name+'(')||l.startsWith('async function '+name+'('));}
(async()=>{
  const browser=await chromium.launch({headless:true, executablePath:process.env.KESTREL_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try {
    const page=await browser.newPage({viewport:{width:1000,height:850}});
    await page.setContent('<div id="jotNewPageDescription" contenteditable="true"></div><div id="jotCanvas"></div><div id="jotPlainLanguageCopy">Plain explanation</div><textarea id="jotNotesDraft">Saved notes</textarea><button id="jotPopupRead-plain"></button><button id="jotPopupRead-notes"></button><button id="jotPopupStop-plain"></button><button id="jotPopupStop-notes"></button>');
    const helpers='function bindJotImageZoom(){}function cancelJotPlainGeneration(){}\n'+html.slice(html.indexOf('let jotInlineDraftPaths'),html.indexOf('function jotCopyText()'));
    await page.addScriptTag({content:`const $=id=>document.getElementById(id);const state={};let hydrated=0;function hydrateJotStorageImages(){hydrated++}function bindJotCardTooltips(){}function showToast(){}function updateJotPageCreatorPreview(){}function renderJotCreateState(){}async function compressJotImage(file){return file}async function uploadJotImage(){return 'private/diagram.webp'}function deleteJotStoragePaths(){}function stopJotReadAloud(){stopJotPopupSpeech()}\n${helpers}\n${fn('jotCardParts')}\n${fn('prepareJotCardItems')}\n${fn('restoreJotCardItems')}\n${fn('cleanJotHtml')}`});
    const result=await page.evaluate(async()=>{
      const clean=sanitizeJotDescription('<p onclick="evil()">Before <b>bold</b></p><img data-storage-path="private/image" src="https://example.invalid/x" onerror="evil()"><p>After</p><script>evil()</script><a href="javascript:evil()">Bad</a>');
      if(/onclick|onerror|<script|javascript:|src=/.test(clean))throw Error('Unsafe markup retained');
      if(sanitizeJotDescription('<img data-storage-path="forged">',false).includes('<img'))throw Error('Pasted private path accepted');
      const canvas=$('jotCanvas');canvas.innerHTML='<ol class="jot-card-list"><li data-rich-description="true" data-page-id="stable"><span class="jot-card-heading">Title</span><div class="jot-card-content">'+clean+'<ul><li>Inner bullet</li></ul></div></li></ol>';
      const before=canvas.innerHTML;prepareJotCardItems(canvas);restoreJotCardItems([canvas.firstElementChild]);prepareJotCardItems(canvas);
      const content=canvas.querySelector('.jot-card-content');
      if(content.children[0].tagName!=='P'||content.children[1].tagName!=='IMG'||content.children[2].textContent!=='After')throw Error('Image moved');
      if(!content.querySelector('b')||canvas.querySelector('li').dataset.pageId!=='stable')throw Error('Formatting or ID lost');
      if(jotCardParts(canvas.querySelector('li')).heading!=='Title')throw Error('Rich heading broken');
      setJotDescription(canvas.querySelector('li'));
      if(!$('jotNewPageDescription').querySelector('img'))throw Error('Editing lost image');
      const host=$('jotNewPageDescription');host.innerHTML='<p>Before</p><p>After</p>';
      const range=document.createRange();range.setStartAfter(host.firstChild);range.collapse(true);window.getSelection().removeAllRanges();window.getSelection().addRange(range);
      await pasteJotDescription({preventDefault(){},stopPropagation(){},clipboardData:{items:[{type:'image/png',getAsFile:()=>new Blob(['image'],{type:'image/png'})}]}});
      if(host.children[1].tagName!=='IMG'||host.children[2].textContent!=='After')throw Error('Paste did not use cursor position');
      if(state.jotImageUploading)throw Error('Upload state stuck');
      const persisted=cleanJotHtml(host.innerHTML);if(!persisted.includes('data-storage-path="private/diagram.webp"'))throw Error('Private image path missing');
      let spoken=[],cancelled=0,paused=0,resumed=0;
      Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak:u=>spoken.push(u),cancel:()=>cancelled++,pause:()=>paused++,resume:()=>resumed++}});
      window.SpeechSynthesisUtterance=function(text){this.text=text};
      toggleJotPopupSpeech('plain');toggleJotPopupSpeech('plain');toggleJotPopupSpeech('plain');
      if(paused!==1||resumed!==1)throw Error('Pause/resume failed');
      const old=spoken[0];toggleJotPopupSpeech('notes');old.onend();
      if(spoken.length!==2||spoken[1].text!=='Saved notes')throw Error('Speech sessions overlapped');
      spoken[1].onend();if($('jotPopupRead-notes').textContent!=='▶ Read aloud')throw Error('Completion state stale');
      toggleJotPopupSpeech('notes');stopJotPopupSpeech();if(!$('jotPopupStop-notes').disabled)throw Error('Stop state stale');
      return {clean, persisted, cancelled};
    });
    assert.ok(result.cancelled>=2);
    await page.addScriptTag({content:`
      let savedContent='', removedPaths=[];
      function activeJotSubtopic(){return {id:'chapter',title:'Chapter'}}
      function activeJotNote(){return {title:'Chapter'}}
      function parseYouTubeUrl(){return null}
      function jotStoragePathsFromContent(content){const t=document.createElement('template');t.innerHTML=content;return [...t.content.querySelectorAll('[data-storage-path]')].map(n=>n.dataset.storagePath)}
      function jotPageSource(){const template=document.createElement('template');template.innerHTML='<ol class="jot-card-list"><li data-page-id="stable" data-review="rating">Old - Description</li></ol>';return {template}}
      async function jotRequest(url,payload){savedContent=payload.content}
      function renderJotPages(){}
      deleteJotStoragePaths=paths=>removedPaths.push(...paths);
      ${fn('submitJotPageCreator')}
    `});
    await page.evaluate(async()=>{
      const heading=document.createElement('input');heading.id='jotNewPageHeading';heading.value='Rich page';document.body.append(heading);
      state.jotPageCreatorMode='edit';state.jotPageCreatorIndex=0;state.jotPageCreatorOriginalPaths=['private/diagram.webp','removed.webp'];state.jotPageCreatorOpen=true;
      await submitJotPageCreator({preventDefault(){}});
      if(state.jotPageCreatorOpen)throw Error('Save did not finish');
      const t=document.createElement('template');t.innerHTML=savedContent;const item=t.content.querySelector('li'),content=item.querySelector('.jot-card-content');
      if(item.dataset.pageId!=='stable'||item.dataset.review!=='rating')throw Error('Save lost rating/ID');
      if(content.children[1].tagName!=='IMG'||content.children[2].textContent!=='After')throw Error('Save moved inline image');
      if(removedPaths.includes('private/diagram.webp')||!removedPaths.includes('removed.webp'))throw Error('Incorrect storage cleanup');
    });
    if(process.env.KESTREL_TEST_SCREENSHOT){
      const styles=[...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m=>m[1]).join('\n');
      const field=lines.find(l=>l.includes('id="jotDescriptionLabel"'));
      await page.setContent('<style>'+styles+'</style><main style="padding:30px;max-width:900px;margin:auto;background:#00232b"><h2 style="color:white">Edit learning page</h2>'+field+'<div class="jot-video-dialog-head" style="margin-top:30px"><b>Saved notes</b><div><button type="button" id="jotPopupRead-notes">▶ Read aloud</button><button>■</button><button>×</button></div></div></main>');
      await page.locator('#jotNewPageDescription').fill('');
      await page.evaluate(()=>document.getElementById('jotNewPageDescription').innerHTML='<p>Requests flow through the API. Refer to the diagram below:</p><img alt="Example diagram" src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22100%22%3E%3Crect width=%22600%22 height=%22100%22 fill=%22%23d8eeee%22/%3E%3Ctext x=%2230%22 y=%2260%22 font-size=%2224%22 fill=%22%2300333b%22%3EYour app → API → Model → Response%3C/text%3E%3C/svg%3E"><p><b>The response</b> returns to your application.</p>');
      await page.screenshot({path:process.env.KESTREL_TEST_SCREENSHOT});
    }
    console.log('Rich description: safe paste, inline image order, edit/restore preservation and popup speech lifecycle passed');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
