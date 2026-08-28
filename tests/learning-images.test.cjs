const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const html=fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
const lines=html.split(/\r?\n/);
const fn=name=>lines.find(l=>l.startsWith('function '+name+'('));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.KESTREL_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:950}});
  const styles=[...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m=>m[1]).join('\n');
  const picture='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300"><rect width="600" height="300" fill="#bbdfd7"/><text x="40" y="150" font-size="38">Example diagram</text></svg>');
  await page.setContent('<style>'+styles+'</style><div id="jotEditor" class="jot-editor view-mode jot-view-immersive jot-view-focus" style="height:900px;display:block;padding:20px"><div id="jotCanvas" style="height:800px"><ol class="jot-card-list"><li class="focus-active"><span class="jot-card-heading">Example</span><div class="jot-card-content"><p>Before first image.</p><img alt="First diagram" src="'+picture+'"><p>Between diagrams.</p><img alt="Second diagram" src="'+picture+'"><p>After second image.</p></div></li></ol></div></div>');
  await page.addScriptTag({content:`const $=id=>document.getElementById(id);const state={jotViewMode:'immersive'};const jotImmersiveDetectedHeadings=new Map();const jotSpeechSentences=[];let jotSpeechUtterance=null;function hydrateJotStorageImages(){}function selectedJotSpeechPage(){return {index:0}}function jotCardParts(){return {content:''}}\n${fn('jotImmersiveStructuredText')}\n${fn('jotImmersiveExtractHeadings')}\n${fn('jotSpeechPageText')}\n`+html.slice(html.indexOf('function bindJotImageZoom('),html.indexOf('let jotInlineDraftPaths'))});
  const result=await page.evaluate(()=>{
    const item=document.querySelector('li.focus-active'),cues=jotImmersiveImageCues(item),full=jotSpeechPageText(item);
    if(!full.includes('image.\n\nBetween'))throw Error('Image boundary lost word separation');
    const copy=document.createElement('div');copy.className='jot-immersive-copy';const title=document.createElement('h2');title.textContent='Images stay beside the explanation';const scenes=document.createElement('div');scenes.innerHTML='<section class="jot-immersive-scene"><h3>Overview</h3><p>Before first image.</p><p>Between diagrams.</p><p>After second image.</p></section>';copy.append(title,scenes);item.append(copy);mountJotImmersiveImages(item,copy,scenes);
    const panel=item.querySelector('aside');syncJotImmersiveImage(cues[0].at-1);if(panel.querySelector('img'))throw Error('First image appeared too soon');
    syncJotImmersiveImage(cues[0].at);if(panel.querySelector('img')?.alt!=='First diagram')throw Error('First cue missed');
    syncJotImmersiveImage(cues[1].at-1);if(panel.querySelector('img')?.alt!=='First diagram')throw Error('First image did not persist');
    syncJotImmersiveImage(cues[1].at);if(panel.querySelector('img')?.alt!=='Second diagram')throw Error('Second cue missed');
    bindJotImageZoom(item);return cues.map(c=>c.at);
  });
  assert.ok(result[1]>result[0]);
  await page.evaluate(()=>{
    const record=(id,date,entries)=>{const item=document.createElement('li');item.dataset.glossary=JSON.stringify(entries);return {id,updated_at:date,content:'<ol>'+item.outerHTML+'</ol>'};};
    state.jotNotes=[record('a','2026-08-01',{classifier:'Earlier definition',xml:'Markup language'}),record('b','2026-08-02',{classifier:'Latest definition',workflow:'Sequence of steps'})];
    const glossary=jotCustomGlossary();if(glossary.xml!=='Markup language'||glossary.workflow!=='Sequence of steps'||glossary.classifier!=='Latest definition')throw Error('Cross-page glossary merge failed');
    state.jotNotes=[];if(Object.keys(jotCustomGlossary()).length)throw Error('Glossary leaked after account data was cleared');
  });
  await page.evaluate(()=>{
    window.startJotReadAloud=(continuous,offset)=>window.seekResult={continuous,offset};
    window.openJotWordActions=(word,offset)=>window.wordResult={word,offset};
    jotSpeechSentences.push({start:0,end:8},{start:9,end:30});
    const scenes=document.createElement('div');scenes.innerHTML='<section class="jot-immersive-scene"><h3>Section</h3><p><span class="jot-immersive-sentence" data-sentence-index="1">Read here <span class="jot-key-term">API</span></span></p></section>';
    document.body.append(scenes);bindJotImmersiveSeeking(scenes);
    scenes.querySelector('h3').click();if(window.seekResult?.offset!==9)throw Error('Heading should seek to section start');
    window.seekResult=null;scenes.querySelector('.jot-immersive-sentence').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));if(window.wordResult?.offset!==9)throw Error('Keyboard word menu failed');
    window.seekResult=null;scenes.querySelector('.jot-key-term').click();if(window.seekResult||window.wordResult?.word!=='API')throw Error('Glossary click should show word actions');
    scenes.remove();
  });
  const actions=lines.find(line=>line.startsWith('<div class="jot-reader-actions"'));
  await page.locator('#jotEditor').evaluate((el,markup)=>el.insertAdjacentHTML('beforeend','<span class="jot-focus-page-number">PAGE 01</span>'+markup),actions);
  for(const selector of ['.jot-focus-page-number','#jotConfidentBtn','#jotPracticeBtn','#jotPagePlainLanguageBtn','.jot-reader-actions button[onclick="saveJotPage(true)"]']){
    assert.equal(await page.locator(selector).evaluate(el=>getComputedStyle(el).display),'none','Immersive-only controls should be hidden');
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.jot-immersive-media-layout').evaluate(el=>getComputedStyle(el).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{const root=document.createElement('div');root.id='kestrelApp';document.body.append(root);root.append(document.getElementById('jotEditor'));});
  await page.locator('.jot-immersive-media-layout > :first-child').evaluate(el=>el.classList.add('jot-immersive-scenes'));
  await page.evaluate(()=>document.getElementById('jotEditor').requestFullscreen());
  await page.addScriptTag({content:html.slice(html.indexOf('function jotPlaybackIcon('),html.indexOf('function setupJotPlaybackIcons('))});
  await page.evaluate(()=>{
    for(const [direction,kind] of [[-1,'rewind'],[1,'forward']]){
      const button=document.querySelector(`button[onclick="seekJotImmersiveSentence(${direction})"]`);button.innerHTML=jotPlaybackIcon(kind);
      const b=button.getBoundingClientRect(),s=button.querySelector('svg').getBoundingClientRect();
      if(Math.abs(b.x+b.width/2-s.x-s.width/2)>1||Math.abs(b.y+b.height/2-s.y-s.height/2)>1)throw Error('Playback icon is not centered');
    }
  });
  await page.addScriptTag({content:'function jotImmersiveVoiceUri(){return "";}\n'+fn('populateJotImmersiveVoices')+'\n'+lines.find(line=>line.startsWith('const JOT_IMMERSIVE_TERMS='))});
  await page.evaluate(()=>{
    const popup=document.createElement('div');popup.id='jotNotesPlayer';document.body.append(popup);prepareJotFullscreenPopups();if(popup.parentElement!==document.fullscreenElement)throw Error('Notes must be inside fullscreen');popup.remove();
    openJotImmersiveOptions();const drawer=document.getElementById('jotImmersiveOptions');if(!drawer.open||!drawer.textContent.includes('Glossary'))throw Error('Glossary drawer action missing');if(/Confident|Needs practice|Save manually/.test(drawer.textContent))throw Error('Removed drawer actions are still present');if(!drawer.querySelector('#jotImmersiveVoice'))throw Error('Voice selector missing');drawer.close();
    openJotGlossary();const glossary=document.getElementById('jotGlossaryDialog'),search=glossary.querySelector('input');search.value='context window';search.dispatchEvent(new Event('input'));if(glossary.querySelectorAll('dt').length!==1)throw Error('Glossary search failed');search.value='no-match-123';search.dispatchEvent(new Event('input'));if(glossary.querySelectorAll('dt').length)throw Error('Empty search failed');glossary.close();
  });
  assert.equal(await page.locator('.jot-immersive-scene p').first().evaluate(el=>getComputedStyle(el).color),'rgb(217, 238, 238)','Teal panels must use light readable text');
  assert.equal(await page.locator('.jot-immersive-image-panel').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(0, 43, 52)');
  assert.ok(!fn('renderJotImmersiveCopy').includes('copy.append(createJotImmersiveReferenceHead'),'Top progress strip must not be rendered');
  await page.locator('.jot-immersive-image-stage img').click();
  assert.equal(await page.locator('#jotImageZoom').evaluate(d=>d.open),true);
  const bounds=await page.locator('#jotImageZoom img').boundingBox();assert.ok(Math.abs(bounds.x+bounds.width/2-750)<10,'Zoom should be centered');
  assert.ok(bounds.width<=600&&bounds.height<=300,'Images must not upscale beyond their natural resolution');
  assert.ok(!html.includes('function runJotImmersiveAction('),'Immersive action handler should be removed');
  assert.ok(!html.includes('function showJotImmersiveReflection('),'Reflection overlay should be removed');
  assert.ok(!html.includes('function showJotImmersiveSummary('),'Completion overlay should be removed');
  await page.keyboard.press('Escape');assert.equal(await page.locator('#jotImageZoom').evaluate(d=>d.open),false);
  const position=await page.locator('.jot-immersive-image-panel').boundingBox();const scene=await page.locator('.jot-immersive-media-layout > :first-child').boundingBox();assert.ok(position.x>scene.x+scene.width,'Image panel should be on the right');
  assert.ok(Math.abs(position.width-scene.width)<2,'Panels must have equal widths');
  assert.ok(Math.abs(position.height-scene.height)<2,'Panels must have equal heights');
  assert.ok(position.height>950*.48,'Panels should expand beyond the old 48vh limit');
  assert.ok(position.y+position.height<850,'Panels should leave room for the footer');
  assert.ok(html.includes('onclick="seekJotImmersiveSentence(-1)"'));
  assert.ok(html.includes('onclick="seekJotImmersiveSentence(1)"'));
  assert.ok(!fn('renderJotImmersiveCopy').includes('jot-immersive-progress-cards'));
  await page.locator('.jot-immersive-image-controls button').first().click();assert.equal(await page.locator('.jot-immersive-image-stage img').getAttribute('alt'),'First diagram');
  if(process.env.KESTREL_TEST_SCREENSHOT)await page.screenshot({path:process.env.KESTREL_TEST_SCREENSHOT});
  await page.setViewportSize({width:700,height:900});
  const columns=await page.locator('.jot-immersive-media-layout').evaluate(el=>getComputedStyle(el).gridTemplateColumns);assert.equal(columns.trim().split(' ').length,1,'Narrow layouts should stack');
  console.log('Learning images: cue timing, persistence, manual browsing, zoom, centering and responsive layout passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
