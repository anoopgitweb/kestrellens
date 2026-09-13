const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('http://kestrel.test/**',async route=>{const request=route.request();if(request.method()==='GET')return route.fulfill({contentType:'text/html',body:fs.readFileSync('C:/KestrelIQ/tools/mp4-transcriber.html','utf8')});if(request.url().includes('/upload'))return route.fulfill({status:202,json:{job_id:'job',status:'processing'}});const data=request.postDataJSON();return route.fulfill({json:data.action==='dependencies'?{ffmpeg:true,faster_whisper:true}:{job_id:'job',status:'complete',message:'Transcript ready',percent:100,segments:[{text:'Hello MP4'}]}});});
 await page.goto('http://kestrel.test/tools/mp4-transcriber?launch=test');assert.equal(await page.locator('#start').isEnabled(),false);
 await page.locator('#file').setInputFiles({name:'meeting.mp4',mimeType:'video/mp4',buffer:Buffer.from('0000ftypisom')});assert.equal(await page.locator('#start').isEnabled(),true);
 await page.locator('#start').click();await page.getByText('Hello MP4',{exact:true}).waitFor();assert.equal(await page.locator('.download').count(),3);assert.deepEqual(errors,[]);
 console.log('MP4 selection, upload, transcript preview and TXT/SRT/VTT links passed.');
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1});
