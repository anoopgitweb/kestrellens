const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname,'../templates/index.html'),'utf8');
let selection = {isCollapsed:true}, page = null, copied = '', notice = '';
const region = {contains: node => node === 'inside'};
const context = {window:{getSelection:()=>selection}, $:()=>region,
  selectedJotSpeechPage:()=>page, showToast:title=>notice=title,
  navigator:{clipboard:{writeText:async text=>{copied=text;}}}};
vm.createContext(context);
vm.runInContext(html.slice(html.indexOf('function jotCopyText()'),html.indexOf('function nextJotReview(')),context);
(async()=>{
  assert.equal(context.jotCopyText(),'');
  selection={isCollapsed:false,anchorNode:'inside',focusNode:'inside',toString:()=> 'Highlighted text'};
  await context.copyJotPageText();
  assert.equal(copied,'Highlighted text');
  selection={isCollapsed:true};
  const content={textContent:'Explanation',querySelectorAll:()=>[]};
  page={item:{querySelector:selector=>selector==='.jot-card-heading'?{textContent:'Heading'}:{cloneNode:()=>content}}};
  assert.equal(context.jotCopyText(),'Heading\n\nExplanation');
  context.navigator.clipboard.writeText=async()=>{throw Error('Denied');};
  await context.copyJotPageText();
  assert.equal(notice,'Could not copy');
  assert.match(html,/id="jotCopyPageBtn"/);
  console.log('Page copy: selection, page fallback, empty state and clipboard failure passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
