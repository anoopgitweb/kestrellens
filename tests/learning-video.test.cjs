const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.KESTREL_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage();
  await page.setContent('<label><input id="jotNewPageVideoUrl"></label><button id="jotPagePdfBtn"></button><ol><li><a data-storage-path="owner/chapter/video.mp4" data-attachment-name="Lesson.mp4"></a></li></ol>');
  await page.addScriptTag({content:`const $=id=>document.getElementById(id);const state={session:{access_token:'test'},jotPageCreatorAttachment:null};const JOT_IMAGE_BUCKET='jot-down-images';function jotCreatorAttachments(){return state.jotPageCreatorAttachment||[]}async function uploadJotAsset(){return 'private/new.mp4'}function renderJotCreateState(){}function updateJotPageCreatorPreview(){}function showToast(){}async function ensureFreshSession(){}function authHeaders(h){return h}async function loadAuthConfig(){return {supabaseUrl:'https://test.invalid',supabaseAnonKey:'test'}}function jotStoragePathUrl(p){return p}function openJotStoredAttachment(){}function syncSelectedJotPageMarker(){}function selectedJotSpeechPage(){return {item:document.querySelector('li')}}function deleteJotStoragePaths(){}window.fetch=async url=>url.startsWith('/api/')?{ok:true,json:async()=>({status:'complete',transcript:{text:'Hello learning',segments:[{start:1,end:2,text:'Hello learning'}]}})}:{ok:true,blob:async()=>new Blob(['video'])};`});
  await page.addScriptTag({content:'function clearSession(){}'});
  await page.addScriptTag({content:fs.readFileSync('assets/learning-video.js','utf8')});
  await page.locator('#jotUploadedVideosBtn').click();
  await page.locator('.transcript-copy button').waitFor();
  assert.equal(await page.locator('[data-transcribe]').textContent(),'Transcript saved');
  assert.equal(await page.locator('[data-txt]').isEnabled(),true);
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('[data-srt]').click()]);
  assert.equal(download.suggestedFilename(),'Lesson.srt');
  await page.locator('[data-close]').click();
  assert.equal(await page.locator('#jotUploadedVideo').isVisible(),false);
  await page.locator('input[type=file]').setInputFiles({name:'second.mp4',mimeType:'video/mp4',buffer:Buffer.from('video')});
  assert.equal(await page.evaluate(()=>state.jotPageCreatorAttachment[0].name),'second.mp4');
  console.log('Video upload, saved transcript, SRT download, toolbar and dialog checks passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
