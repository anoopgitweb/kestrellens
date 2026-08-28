const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');const {chromium}=require('playwright');
const html=fs.readFileSync(path.join(__dirname,'../templates/index.html'),'utf8');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.KESTREL_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const page=await browser.newPage({viewport:{width:1400,height:950}});
 await page.route('**/*',route=>route.abort());
 await page.setContent(html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),{waitUntil:'domcontentloaded'});
 const editor=await page.locator('#jotEditor').evaluate(el=>el.outerHTML);
 const styles=[...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m=>m[1]).join('\n');
 await page.setContent('<style>'+styles+'</style><main id="kestrelApp" style="display:block"><div class="jot-workspace">'+editor+'</div></main>');
 await page.evaluate(()=>document.getElementById('jotPageCreator').classList.remove('hidden'));
 for(const mode of ['cards','reading','numbered','focus','immersive','flashcards','table']){
   await page.locator('#jotEditor').evaluate((el,mode)=>el.className='jot-editor view-mode page-creator-open jot-view-'+mode,mode);
   for(const selector of ['.jot-editor-foot','.jot-mode-page-pane','#jotPageDetail','#jotCanvas','#jotViewSelect','#jotCopyPageBtn','#jotFocusControls','#jotFlashControls']){
     if(await page.locator(selector).count())assert.equal(await page.locator(selector).first().isVisible(),false,mode+': '+selector+' leaked into creator');
   }
   assert.equal(await page.locator('#jotNewPageDescription').isVisible(),true);
 }
 await page.addScriptTag({content:`const $=id=>document.getElementById(id);const state={jotPageCreatorOpen:true};function activeJotSubtopic(){return {id:'chapter'}}function jotImmersiveStructuredText(el){return el.textContent}async function ensureFreshSession(){}function authHeaders(h){return h}\n`+html.slice(html.indexOf('let jotPlainAiRequest'),html.indexOf('let jotInlineDraftPaths'))});
 const result=await page.evaluate(async()=>{
   const source=$('jotNewPageDescription'),target=$('jotNewPagePlainLanguage');source.textContent='Original description';$('jotNewPageHeading').value='Title';target.value='Old explanation';
   let calls=0,payload;window.confirm=()=>false;window.fetch=async(url,options)=>{calls++;payload=JSON.parse(options.body);return {ok:true,json:async()=>({explanation:'Simple explanation'})}};
   await generateJotPlainExplanation();if(calls)throw Error('API called without confirmation');
   window.confirm=()=>true;await generateJotPlainExplanation();if(target.value!=='Simple explanation'||!state.jotPageCreatorDirty)throw Error('Draft not filled');
   if(payload.description!=='Original description'||!payload.consent||Object.keys(payload).some(k=>/image|notes|key/i.test(k)))throw Error('Incorrect API payload');
   window.fetch=async()=>({ok:false,json:async()=>({error:'Service unavailable'})});await generateJotPlainExplanation();if(target.value!=='Simple explanation')throw Error('Failure overwrote content');
   window.fetch=async()=>{target.value='Typed while waiting';return {ok:true,json:async()=>({explanation:'Stale result'})}};await generateJotPlainExplanation();if(target.value!=='Typed while waiting')throw Error('Stale result replaced edits');
   if($('jotSimplifyBtn').disabled)throw Error('Button stuck busy');return calls;
 });
 assert.equal(result,1);
 console.log('Creator isolation across all modes; API confirmation, draft insertion, failure and stale-response protection passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
