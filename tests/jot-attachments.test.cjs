const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('templates/index.html','utf8');
const elements=new Map();
const context={state:{jotPageCreatorAttachment:null},JOT_ATTACHMENT_TYPES:{pdf:{extension:'pdf',mime:'application/pdf'}},uploadJotAsset:async f=>'private/'+f.name,renderJotCreateState(){},renderJotPageCreatorAttachment(){},updateJotPageCreatorPreview(){},showToast(){},$:id=>{if(!elements.has(id))elements.set(id,{setAttribute(){}});return elements.get(id)}};
vm.createContext(context);
for(const name of ['jotCreatorAttachments','handleJotPageAttachment','jotPdfAttachments','syncJotPdfButton']){const line=html.split('\n').find(l=>l.startsWith('function '+name+'(')||l.startsWith('async function '+name+'('));vm.runInContext(line,context);}
(async()=>{
  await context.handleJotPageAttachment({target:{files:[{name:'one.pdf',size:100},{name:'two.pdf',size:200}],value:'selected'}});
  assert.equal(context.state.jotPageCreatorAttachment.length,2);
  await context.handleJotPageAttachment({target:{files:[{name:'three.pdf',size:300},{name:'oversized.pdf',size:6*1024*1024}],value:'selected'}});
  assert.deepEqual(Array.from(context.state.jotPageCreatorAttachment,a=>a.name),['one.pdf','two.pdf','three.pdf']);
  const item={querySelectorAll:()=>[{dataset:{storagePath:'a',attachmentName:'one.pdf'}},{dataset:{storagePath:'b',attachmentName:'notes.txt'}},{dataset:{storagePath:'c',attachmentName:'two.pdf'}}]};
  assert.deepEqual(Array.from(context.jotPdfAttachments(item),a=>a.path),['a','c']);
  context.syncJotPdfButton(item);assert.equal(elements.get('jotPagePdfCount').textContent,2);assert.equal(elements.get('jotPagePdfBtn').hidden,false);
  context.syncJotPdfButton(null);assert.equal(elements.get('jotPagePdfBtn').hidden,true);
  console.log('Multiple uploads, append order, size validation, and PDF badge checks passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
