const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../tools/notebook-presenter.html'),'utf8');
const context=vm.createContext({});
vm.runInContext(html.slice(html.indexOf('function switchPageMedia('),html.indexOf('function openImagePreview(')),context);
let paused=0,cloned=0;
function panel(name,video=false){return {dataset:{mediaPanel:name},hidden:name!=='image',children:[],childElementCount:0,classList:{contains:value=>video&&value==='page-media-video'},appendChild(node){this.children.push(node);this.childElementCount=this.children.length;},querySelectorAll(){return video&&this.children.length?[{pause(){paused++;}}]:[];},replaceChildren(){this.children=[];this.childElementCount=0;}};}
const panels=[panel('image'),panel('video',true),panel('local-video',true)];
const templates=Object.fromEntries(['video','local-video'].map(name=>[name,{content:{cloneNode(){cloned++;return {name};}}}]));
const buttons=['image','video','local-video'].map((name,index)=>({dataset:{media:name},pressed:String(index===0),getAttribute(){return this.pressed;},setAttribute(key,value){this.pressed=value;},closest(){return media;}}));
const media={querySelector(selector){const match=selector.match(/data-media-template="([^"]+)/);return match?templates[match[1]]:null;},querySelectorAll(selector){return selector==='[data-media-panel]'?panels:buttons;}};
context.switchPageMedia(buttons[2]);
assert.equal(panels[0].hidden,true);assert.equal(panels[2].hidden,false);assert.equal(cloned,1);assert.equal(buttons[2].pressed,'true');
context.switchPageMedia(buttons[2]);assert.equal(cloned,1);
context.switchPageMedia(buttons[1]);assert.equal(panels[1].hidden,false);assert.equal(panels[2].childElementCount,0);assert.equal(paused,1);assert.equal(cloned,2);
context.switchPageMedia(buttons[0]);assert.equal(panels[0].hidden,false);assert.equal(panels[1].childElementCount,0);assert.equal(paused,2);
console.log('Image, online video, and local video switching with playback cleanup passed.');
