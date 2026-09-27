const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../tools/notebook-presenter.html'),'utf8');
const fields=Object.fromEntries(['f-videourl','f-localurl','local-video-name','f-videofile'].map(id=>[id,{value:'',dataset:{}}]));
const revoked=[],alerts=[],rows=[],slides=[];
let next=0;
const context=vm.createContext({document:{getElementById:id=>fields[id]},csvRows:rows,slides,URL:{createObjectURL:()=>`blob:local-${++next}`,revokeObjectURL:url=>revoked.push(url)},alert:message=>alerts.push(message)});
vm.runInContext(html.slice(html.indexOf('const localVideoFiles='),html.indexOf('function openEditForm(')),context);
fields['f-videourl'].value='https://example.com/online.mp4';
context.selectLocalVideo({files:[{name:'lesson.mp4',size:1000}]});
assert.equal(fields['f-localurl'].dataset.videoUrl,'blob:local-1');
assert.equal(fields['f-localurl'].value,'lesson.mp4');
assert.equal(fields['local-video-name'].textContent,'Selected local video: lesson.mp4');
rows.push({_localVideoUrl:'blob:local-1'});
context.selectLocalVideo({files:[{name:'second.MP4',size:2000}]});
assert.deepEqual(revoked,[]); // Saved row remains playable while editing a replacement.
context.clearLocalVideo();
assert.equal(fields['f-videourl'].value,'https://example.com/online.mp4');
assert.deepEqual(revoked,['blob:local-2']);
assert.equal(fields['f-localurl'].value,'');
assert.equal(fields['local-video-name'].textContent,'');
context.selectLocalVideo({files:[{name:'bad.txt',size:100}]});
context.selectLocalVideo({files:[{name:'empty.mp4',size:0}]});
assert.equal(alerts.length,2);assert.equal(next,2);
rows.length=0;context.releaseUnusedLocalVideos();assert.deepEqual(revoked,['blob:local-2','blob:local-1']);
assert.match(html,/if\(!url.startsWith\('blob:'\)\) videoSide.appendChild/);
console.log('Local MP4 selection, validation, replacement, clearing, and object URL cleanup passed.');

