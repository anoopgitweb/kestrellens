'use strict';
const $ = id => document.getElementById(id);
let config, deck, selected=0, timer, revision=0, savedLocally=true, runSlides=[], runIndex=0, zoomScale=1;
const key='slide-studio-v1';
const status=(message,error=false)=>{$('status').textContent=message;$('status').classList.toggle('error',error)};
function makeSlide(t){return {type:t.id,title:t.title,subtitle:t.subtitle,content:t.content,...(t.eyebrow!==undefined?{eyebrow:t.eyebrow}:{})}}
function titleLabelFor(s){return s.eyebrow??(s.subtitle==='Notebook presentation'?'NOTEBOOK PRESENTATION':s.content==='Chapter'?'CHAPTER':'PRESENTATION')}
function migrateSlide(s){
  if(s.chartType==='correlation'){
    const rows=s.content.split(/\r?\n/).filter(Boolean).map(line=>line.split('|').map(v=>v.trim()));
    if(rows.some(r=>Number.isNaN(Number(r[0]))))s.content=rows.map((r,i)=>`${i+1} | ${r[r.length-1]??''}`).join('\n');
  }
  if(s.chartType==='matrix'){
    const rows=s.content.split(/\r?\n/).filter(Boolean).map(line=>line.split('|').map(v=>v.trim()));
    if(rows.some(r=>Number.isNaN(Number(r[0]))))s.content=rows.map((r,i)=>[i+1,...r.slice(1)].join(' | ')).join('\n');
  }
  return s;
}
async function api(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok){let e;try{e=(await r.json()).error}catch{e='Request failed. Check your content.'}throw Error(e||'Request failed.')}return r}
function persist(){try{localStorage.setItem(key,JSON.stringify(deck));savedLocally=true}catch{savedLocally=false;status('Local autosave unavailable. Use Save project to keep your work.',true)}}
function list(){ $('slides').replaceChildren();deck.slides.forEach((s,i)=>{const row=document.createElement('div');row.className='slide-item'+(i===selected?' active':'');const b=document.createElement('button');b.className='slide-select';const small=document.createElement('small');small.textContent=`${String(i+1).padStart(2,'0')}  ${config.templates.find(t=>t.id===s.type).name}`;b.append(small,document.createTextNode(s.title||'Untitled'));b.onclick=()=>{selected=i;render()};const order=document.createElement('div');order.className='order';[-1,1].forEach((d)=>{const a=document.createElement('button');a.textContent=d===-1?'↑':'↓';a.setAttribute('aria-label',`Move slide ${i+1} ${d===-1?'up':'down'}`);a.disabled=i+d<0||i+d>=deck.slides.length;a.onclick=()=>{[deck.slides[i],deck.slides[i+d]]=[deck.slides[i+d],deck.slides[i]];selected=i+d;changed()};order.append(a)});row.append(b,order);$('slides').append(row)});$('count').textContent=deck.slides.length;$('position').textContent=`Slide ${selected+1} of ${deck.slides.length}`;$('delete').disabled=deck.slides.length===1;$('add').disabled=$('duplicate').disabled=deck.slides.length>=60;}
function render(){const s=deck.slides[selected];['title','subtitle','content','type'].forEach(k=>$(k).value=s[k]);$('theme').value=deck.theme;$('projectName').value=deck.name||'My presentation';const t=config.templates.find(t=>t.id===s.type);$('current').textContent=t.name;extras(s,t);renderRows(s,t);list();preview();}
function rowLimit(s,t){return ['correlation','matrix','descriptive','histogram','boxplot'].includes(s.chartType)?100:t.layout==='chart'?12:['table','summary'].includes(t.layout)?8:6}
function rowFields(s,t){
  if(t.layout!=='chart')return t.fields;
  if(['descriptive','histogram'].includes(s.chartType))return ['Value'];
  if(s.chartType==='boxplot')return ['Group','Value'];
  const width=Math.max(2,...s.content.split('\n').filter(Boolean).map(r=>r.split('|').length));
  if(s.chartType==='pareto')return ['Category','Value'];
  if(s.chartType==='correlation')return ['X','Y'];
  const names=(s.seriesNames||'').split('|').map(v=>v.trim());
  if(s.chartType==='matrix')return Array.from({length:Math.min(4,width)},(_,i)=>names[i]||'Variable '+(i+1));
  return [s.chartType==='scatter'?'X':'Category',...Array.from({length:width-1},(_,i)=>names[i]||'Value '+(i+1))];
}
function renderRows(s,t){
  const structured=!!t.fields.length;$('structuredEditor').hidden=!structured;$('freeContent').hidden=structured;
  if(!structured){$('format').textContent=t.layout==='notebook'?'Add the page details. Imported video references remain attached to this slide.':'Add a short closing line or presenter details.';return}
  const rows=s.content.split(/\r?\n/).filter(line=>line.length).map(line=>line.split('|').map(v=>v.trim()));
  const fields=rowFields(s,t);$('contentRows').replaceChildren();
  (rows.length?rows:[fields.map(()=> '')]).forEach(row=>addRow(row,fields));
  $('addRow').disabled=$('contentRows').children.length>=rowLimit(s,t);
  renderSeries(s,t,fields);
}
function addRow(values,fields){
  const row=document.createElement('div');row.className='data-row';
  const fieldsWrap=document.createElement('div');fieldsWrap.className='data-row-fields';fieldsWrap.style.setProperty('--field-count',Math.min(2,fields.length));
  fields.forEach((field,i)=>{const label=document.createElement('label');label.textContent=field;const input=document.createElement('input');
    input.value=values[i]??'';input.maxLength=180;
    input.setAttribute('aria-label','Row '+($('contentRows').children.length+1)+' '+field);
    input.oninput=()=>{if(input.value.includes('|')){input.setCustomValidity('Use a field without the | character.');input.reportValidity();return}input.setCustomValidity('');syncRows();persist();preview()};
    label.append(input);fieldsWrap.append(label)});
  const remove=document.createElement('button');remove.className='remove-row';remove.type='button';remove.textContent='×';remove.title='Remove row';
  remove.onclick=()=>{row.remove();syncRows();persist();renderRows(deck.slides[selected],config.templates.find(t=>t.id===deck.slides[selected].type));preview()};
  row.append(fieldsWrap,remove);$('contentRows').append(row);
}
function syncRows(){
  const rows=[...$('contentRows').querySelectorAll('.data-row')].map(row=>[...row.querySelectorAll('input')].map(i=>i.value.trim()).join(' | '));
  deck.slides[selected].content=rows.join('\n');$('content').value=deck.slides[selected].content;list();
}
function renderSeries(s,t,fields){
  const panel=$('seriesEditor');panel.replaceChildren();panel.hidden=t.layout!=='chart'||['pareto','correlation','descriptive','histogram','boxplot'].includes(s.chartType);
  if(panel.hidden)return;
  const matrix=s.chartType==='matrix',count=matrix?fields.length:fields.length-1;
  const names=(s.seriesNames||'').split('|').map(v=>v.trim());
  for(let i=0;i<count;i++){const label=document.createElement('label');label.textContent=(matrix?'Variable ':'Series ')+(i+1)+' name';const input=document.createElement('input');input.maxLength=24;input.value=names[i]||((matrix?'Variable ':'Series ')+(i+1));input.onchange=()=>{s.seriesNames=[...panel.querySelectorAll('input')].map(v=>v.value.trim()).join(' | ');changed()};label.append(input);panel.append(label)}
  if(!['pie','donut','combo'].includes(s.chartType)){
    const add=document.createElement('button');add.textContent=matrix?'＋ Add variable':'＋ Add series';add.disabled=count>=4;
    add.onclick=()=>{s.content=(s.content||fields.map(()=> '').join(' | ')).split('\n').map(r=>r+' | 0').join('\n');s.seriesNames=[...panel.querySelectorAll('input')].map(v=>v.value.trim()).concat((matrix?'Variable ':'Series ')+(count+1)).join(' | ');changed()};panel.append(add);
    if(count>(matrix?2:1)){const remove=document.createElement('button');remove.textContent='Remove last '+(matrix?'variable':'series');remove.onclick=()=>{if(!confirm('Remove the last value column and its data?'))return;s.content=s.content.split('\n').map(r=>r.split('|').slice(0,-1).join(' | ')).join('\n');s.seriesNames=[...panel.querySelectorAll('input')].slice(0,-1).map(v=>v.value.trim()).join(' | ');changed()};panel.append(remove)}
  }
}
function changed(){persist();render()}
function preparedNow(){return new Date().toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}
async function preview(){const rev=++revision;clearTimeout(timer);status('Updating preview…');timer=setTimeout(async()=>{try{const previewTitleOrdinal=deck.slides.slice(0,selected+1).filter(slide=>slide.type==='title').length-1;const response=await api('/api/preview',{...deck,slides:[deck.slides[selected]],previewSlideNumber:selected+1,previewTotalSlides:deck.slides.length,previewTitleOrdinal:Math.max(0,previewTitleOrdinal)});const result=await response.json();if(rev!==revision)return; // SVG is generated and escaped by the local server.
$('preview').innerHTML=result.slides[0];const texts=$('preview').querySelectorAll('text');if(texts.length)texts[texts.length-1].textContent=String(selected+1).padStart(2,'0');status(savedLocally?'Preview ready · Autosaved on this device':'Preview ready · Autosave full. Use Save project to keep images.',!savedLocally)}catch(e){if(rev===revision){$('preview').replaceChildren();status(e.message,true)}}},160)}
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}
function renderRunSlide(){
  if(!runSlides.length)return;
  const stage=$('runStage'),slide=deck.slides[runIndex],type=slide.transition&&slide.transition!=='inherit'?slide.transition:(deck.transition?.type||'none');
  stage.className='run-stage';stage.style.setProperty('--transition-duration',({slow:'1s',medium:'.6s',fast:'.35s'})[deck.transition?.speed||'medium']);
  stage.innerHTML=runSlides[runIndex];void stage.offsetWidth;if(!['none','cut'].includes(type))stage.classList.add('effect-'+type);
  $('runPosition').textContent=`${runIndex+1} / ${runSlides.length}`;
  $('runPrevious').disabled=runIndex===0;$('runNext').disabled=runIndex===runSlides.length-1;
}
function stepRunSlide(amount){runIndex=Math.max(0,Math.min(runSlides.length-1,runIndex+amount));renderRunSlide()}
function closeRunDeck(){
  if(document.fullscreenElement===$('runDeck'))document.exitFullscreen();
  if($('runDeck').open)$('runDeck').close();
  runSlides=[];$('runStage').replaceChildren();
}
function setImageZoom(scale){
  zoomScale=Math.max(.5,Math.min(4,scale));
  $('zoomImage').style.transform=`scale(${zoomScale})`;$('zoomLevel').textContent=Math.round(zoomScale*100)+'%';
}
function openImageZoom(image){
  const href=image.href?.baseVal||image.getAttribute('href');if(!href)return;
  $('zoomImage').src=href;setImageZoom(1);$('imageZoom').showModal();
}
function closeImageZoom(){if($('imageZoom').open)$('imageZoom').close();$('zoomImage').removeAttribute('src');setImageZoom(1)}
async function init(){try{config=await(await fetch('/api/config')).json();config.templates.forEach(t=>{$('type').add(new Option(t.name,t.id));const b=document.createElement('button');b.textContent=t.name;const small=document.createElement('small');small.textContent=t.fields.length?'Structured content':'Opening / closing';b.append(small);b.onclick=()=>{if(deck.slides.length>=60)return;deck.slides.splice(selected+1,0,makeSlide(t));selected++;$('picker').close();changed()};$('templateGrid').append(b)});Object.entries(config.themes).forEach(([id,t])=>$('theme').add(new Option(t.name,id)));deck={name:'Quarterly business review',theme:'ocean',slides:config.templates.map(makeSlide),preparedAt:preparedNow()};let saved;try{saved=localStorage.getItem(key)}catch{}if(saved){try{const candidate=JSON.parse(saved);if(!candidate||!Array.isArray(candidate.slides)||!candidate.slides.length||!config.themes[candidate.theme]||candidate.slides.some(s=>!config.templates.some(t=>t.id===s.type)||['title','subtitle','content'].some(k=>typeof s[k]!=='string')))throw Error('Invalid project structure');candidate.slides=candidate.slides.map(migrateSlide);deck=candidate}catch{status('Saved project could not load. A sample deck is open.',true)}}deck.preparedAt??=preparedNow();render();}catch(e){status('Unable to start the editor. Check that the local server is running. '+e.message,true)}}
const pptZoomLabel=document.createElement('label');pptZoomLabel.className='check-label';pptZoomLabel.innerHTML='<input id="pptImageZoom" type="checkbox" checked> Add click-to-enlarge images to PowerPoint';$('imageOptions').before(pptZoomLabel);
const titleImageSection=document.createElement('div');titleImageSection.className='title-image-controls';
titleImageSection.innerHTML='<h3>Title page images</h3><label>Add up to 5 images<input id="titleImagesFile" type="file" multiple accept="image/png,image/jpeg,image/webp"></label><p class="hint">Images are distributed across cover and chapter title pages. Each title page keeps the same image in previews and exports.</p><div id="titleImageList" class="title-image-list"></div>';
$('logoOptions').after(titleImageSection);
const titleLabelWrap=document.createElement('label');titleLabelWrap.id='titleLabelWrap';titleLabelWrap.textContent='Title label';const titleLabelInput=document.createElement('input');titleLabelInput.id='eyebrow';titleLabelInput.maxLength=60;titleLabelInput.placeholder='PRESENTATION';titleLabelWrap.append(titleLabelInput);$('title').closest('label').before(titleLabelWrap);
['title','subtitle','content'].forEach(k=>$(k).oninput=()=>{deck.slides[selected][k]=$(k).value;persist();list();preview()});
$('projectName').oninput=()=>{deck.name=$('projectName').value;persist()};
$('theme').onchange=()=>{deck.theme=$('theme').value;changed()};
$('type').onchange=()=>{const old=deck.slides[selected], t=config.templates.find(t=>t.id===$('type').value);if(!confirm('Change slide type and replace its content with the new template?')){$('type').value=old.type;return}deck.slides[selected]={...makeSlide(t),image:old.image,imagePosition:old.imagePosition,imageSize:old.imageSize};changed()};
$('add').onclick=()=>$('picker').showModal();$('closePicker').onclick=()=>$('picker').close();
$('duplicate').onclick=()=>{if(deck.slides.length>=60)return;deck.slides.splice(selected+1,0,structuredClone(deck.slides[selected]));selected++;changed()};
$('delete').onclick=()=>{if(deck.slides.length===1||!confirm('Delete this slide?'))return;deck.slides.splice(selected,1);selected=Math.min(selected,deck.slides.length-1);changed()};
$('save').onclick=()=>download(new Blob([JSON.stringify(deck,null,2)],{type:'application/json'}),(deck.name||'presentation')+'.json');
$('open').onclick=()=>$('file').click();$('file').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>40*1024*1024)throw Error('Project exceeds 40 MB.');const candidate=JSON.parse(await file.text());await api('/api/preview',candidate);deck=candidate;selected=0;changed()}catch(err){status('Could not open project: '+err.message,true)}e.target.value=''};
$('importNotebook').onclick=()=>$('notebookFile').click();
$('notebookFile').onchange=async e=>{
  const file=e.target.files[0];e.target.value='';if(!file)return;
  if(!confirm('Import this Notebook workbook and replace the current Slide Studio project?'))return;
  $('importNotebook').disabled=true;status('Importing Notebook and creating slides…');
  try{
    if(file.size>25*1024*1024)throw Error('Notebook workbook exceeds 25 MB.');
    const body=new FormData();body.append('file',file);
    const response=await fetch('/api/import-notebook',{method:'POST',body});
    const result=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(result.error||'The Notebook workbook could not be imported.');
    deck=result;deck.preparedAt=preparedNow();selected=0;changed();status(`${deck.slides.length} slides created from ${file.name}.`);
  }catch(err){status('Could not import Notebook: '+err.message,true)}finally{$('importNotebook').disabled=false}
};
$('runPpt').onclick=async()=>{
  $('runPpt').disabled=true;status('Preparing presentation preview…');
  try{
    deck.preparedAt=preparedNow();persist();
    const response=await api('/api/preview',deck),result=await response.json();
    runSlides=result.slides;runIndex=Math.min(selected,runSlides.length-1);$('runTitle').textContent=deck.name||'Presentation';
    renderRunSlide();$('runDeck').showModal();status('Presentation preview ready.');
  }catch(err){status('Could not run presentation: '+err.message,true)}finally{$('runPpt').disabled=false}
};
$('runPrevious').onclick=()=>stepRunSlide(-1);$('runNext').onclick=()=>stepRunSlide(1);
$('runStage').onclick=e=>{if(e.target.closest('image')){openImageZoom(e.target.closest('image'));return}if(!e.target.closest('a'))stepRunSlide(1)};
$('preview').onclick=e=>{const image=e.target.closest('image');if(image)openImageZoom(image)};
$('runClose').onclick=closeRunDeck;
$('runFullscreen').onclick=async()=>{try{if(!document.fullscreenElement)await $('runDeck').requestFullscreen();else await document.exitFullscreen()}catch{status('Fullscreen is unavailable in this browser.',true)}};
$('runDeck').addEventListener('close',()=>{if(runSlides.length)closeRunDeck()});
$('zoomOut').onclick=()=>setImageZoom(zoomScale-.25);$('zoomIn').onclick=()=>setImageZoom(zoomScale+.25);$('zoomReset').onclick=()=>setImageZoom(1);$('zoomClose').onclick=closeImageZoom;
$('zoomViewport').addEventListener('wheel',event=>{event.preventDefault();setImageZoom(zoomScale+(event.deltaY<0?.15:-.15))},{passive:false});
$('imageZoom').addEventListener('click',event=>{if(event.target===$('imageZoom'))closeImageZoom()});
$('imageZoom').addEventListener('close',()=>{$('zoomImage').removeAttribute('src');setImageZoom(1)});
document.addEventListener('keydown',event=>{
  if($('imageZoom').open){
    if(event.key==='+'||event.key==='='){event.preventDefault();setImageZoom(zoomScale+.25)}
    else if(event.key==='-'){event.preventDefault();setImageZoom(zoomScale-.25)}
    else if(event.key==='0'){event.preventDefault();setImageZoom(1)}
    else if(event.key==='Escape'){event.preventDefault();closeImageZoom()}
    return;
  }
  if(!$('runDeck').open)return;
  if(event.key==='ArrowLeft'){event.preventDefault();stepRunSlide(-1)}
  else if(event.key==='ArrowRight'||event.key===' '||event.key==='PageDown'){event.preventDefault();stepRunSlide(1)}
  else if(event.key==='PageUp'){event.preventDefault();stepRunSlide(-1)}
  else if(event.key==='Home'){event.preventDefault();runIndex=0;renderRunSlide()}
  else if(event.key==='End'){event.preventDefault();runIndex=runSlides.length-1;renderRunSlide()}
});
$('generate').onclick=async()=>{$('generate').disabled=true;status('Generating PowerPoint…');try{deck.preparedAt=preparedNow();persist();const r=await api('/api/generate',deck);download(await r.blob(),(deck.name||'presentation')+'.pptx');status('PowerPoint downloaded. All slide objects are editable.')}catch(e){status(e.message,true)}finally{$('generate').disabled=false}};
function extras(s,t){
  $('titleLabelWrap').hidden=s.type!=='title';$('eyebrow').value=titleLabelFor(s);
  $('chartControls').hidden=t.layout!=='chart';
  $('chartType').value=s.chartType||'column';$('seriesNames').value=s.seriesNames||'';
  if(t.layout==='chart')$('format').textContent=({
    pareto:'Enter nonnegative category values. Duplicate categories are combined, sorted largest first, with cumulative % and an 80% reference.',
    correlation:'Enter 3–100 matched X and Y observations. Pearson r, R² and a least-squares line update automatically.',
    matrix:'Enter 3–100 matched observations for 2–4 variables. Each row describes the same observation across all variables.',
    descriptive:'Enter 1–100 values. Summary includes count, mean, median, sample standard deviation and percentiles.',
    histogram:'Enter 1–100 values. Choose automatic bins or set the number of equal-width intervals.',
    boxplot:'Enter a group name and value on each row. Up to 100 observations across 4 groups. Use the same group name to combine observations.'
  })[s.chartType]||'Fill each row and add series as needed. Up to 12 rows. Scatter uses numeric X values.';
  $('loadExample').hidden=t.layout!=='chart'||!Object.hasOwn(statsChoices,s.chartType);
  $('histogramControls').hidden=t.layout!=='chart'||s.chartType!=='histogram';
  $('histogramBins').value=s.histogramBins??'auto';
  if(t.layout!=='chart'&&t.fields.length)$('format').textContent=`Fill in each row below. Add rows as needed, up to ${['table','summary'].includes(t.layout)?8:6}.`;
  $('imageOptions').hidden=!s.image;
  if(s.image)$('imageThumb').src=s.image;else $('imageThumb').removeAttribute('src');
  $('imagePosition').value=s.imagePosition||'right';$('imageSize').value=s.imageSize||'medium';
  const fixedImageLayout=['image-focus','image-caption'].includes(t.layout);$('imagePosition').closest('label').hidden=fixedImageLayout;$('imageSize').closest('label').hidden=fixedImageLayout;
  $('pptImageZoom').checked=deck.pptImageZoom!==false;
  $('logoOptions').hidden=!deck.logo;if(deck.logo)$('logoThumb').src=deck.logo;else $('logoThumb').removeAttribute('src');
  $('logoPosition').value=deck.logoPosition||'top-right';$('logoSize').value=deck.logoSize||'medium';$('hideLogoOnTitle').checked=deck.hideLogoOnTitle!==false;
  renderTitleImages();
  $('defaultTransition').value=deck.transition?.type||'none';$('transitionSpeed').value=deck.transition?.speed||'medium';$('slideTransition').value=s.transition||'inherit';
}
$('eyebrow').oninput=()=>{deck.slides[selected].eyebrow=$('eyebrow').value;persist();preview()};
function renderTitleImages(){
  const list=$('titleImageList'),items=Array.isArray(deck.titleImages)?deck.titleImages:[];list.replaceChildren();
  items.forEach((uri,index)=>{const item=document.createElement('div');item.className='title-image-item';const image=document.createElement('img');image.src=uri;image.alt=`Title page image ${index+1}`;const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.title='Remove title page image';remove.setAttribute('aria-label',`Remove title page image ${index+1}`);remove.onclick=()=>{deck.titleImages.splice(index,1);changed()};item.append(image,remove);list.append(item)});
  const remaining=5-items.length;$('titleImagesFile').disabled=remaining===0;$('titleImagesFile').closest('label').firstChild.textContent=remaining?`Add images (${items.length} / 5)`:'Maximum reached (5 / 5)';
}
['chartType','imagePosition','imageSize'].forEach(k=>$(k).onchange=()=>{deck.slides[selected][k]=$(k).value;changed()});
$('chartType').onchange=()=>{
  const s=deck.slides[selected],kind=$('chartType').value,previous=s.chartType||'column';
  let rows=s.content.split('\n').filter(Boolean).map(r=>r.split('|').map(v=>v.trim()));
  const single=['descriptive','histogram'].includes(kind),wasSingle=['descriptive','histogram'].includes(previous);
  if(single){
    if(!wasSingle&&rows.some(r=>r.length>1)&&!confirm('Use the last value column for this analysis? Other columns will be removed from this slide.')){$('chartType').value=previous;return}
    s.content=rows.map(r=>r[r.length-1]).join('\n');s.seriesNames='';s.chartType=kind;changed();return;
  }
  if(wasSingle)rows=rows.map((r,i)=>[kind==='boxplot'?'Group 1':String(i+1),r[0]]);
  if(kind==='correlation' && rows.some(r=>Number.isNaN(Number(r[0])))){
    // Category labels from a standard trend chart become ordered numeric observations.
    rows=rows.map((r,i)=>[String(i+1),r[r.length-1]??'']);
  }
  if(kind==='matrix' && rows.some(r=>Number.isNaN(Number(r[0])))){
    rows=rows.map((r,i)=>[String(i+1),...r.slice(1)]);
  }
  const width=Math.max(2,...rows.map(r=>r.length));
  const cap=['pareto','correlation','pie','donut','boxplot'].includes(kind)?2:kind==='matrix'?4:kind==='combo'?3:5;
  if(width>cap&&!confirm('This chart supports fewer columns. Remove the extra value columns?')){$('chartType').value=previous;return}
  const target=kind==='combo'?3:Math.min(width,cap);
  s.content=rows.map(row=>Array.from({length:target},(_,i)=>row[i]??'0').join(' | ')).join('\n');
  const count=kind==='matrix'?target:target-1,names=(s.seriesNames||'').split('|').map(v=>v.trim());
  s.seriesNames=Array.from({length:count},(_,i)=>names[i]||(kind==='matrix'?'Variable ':'Series ')+(i+1)).join(' | ');
  s.chartType=kind;changed();
};
$('seriesNames').oninput=()=>{deck.slides[selected].seriesNames=$('seriesNames').value;persist();preview()};
$('addRow').onclick=()=>{const s=deck.slides[selected],t=config.templates.find(t=>t.id===s.type);if($('contentRows').children.length>=rowLimit(s,t))return;addRow([],rowFields(s,t));syncRows();persist();$('addRow').disabled=$('contentRows').children.length>=rowLimit(s,t);$('contentRows').lastElementChild.querySelector('input').focus()};
$('removeImage').onclick=()=>{delete deck.slides[selected].image;changed()};
$('imageFile').onchange=async e=>{
  const file=e.target.files[0], target=deck.slides[selected];if(!file)return;
  try{
    if(file.size>5*1024*1024)throw Error('Image exceeds 5 MB.');
    if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('Choose a PNG, JPEG or WebP image.');
    const uri=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read image.'));reader.readAsDataURL(file)});
    await api('/api/preview',{theme:deck.theme,slides:[{...target,image:uri}]});
    target.image=uri;changed();
  }catch(err){status(err.message,true)}finally{e.target.value=''}
};
$('pptImageZoom').onchange=()=>{deck.pptImageZoom=$('pptImageZoom').checked;changed()};
$('logoFile').onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  try{
    if(file.size>5*1024*1024)throw Error('Logo exceeds 5 MB.');
    if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('Choose a PNG, JPEG or WebP logo.');
    const uri=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read logo.'));reader.readAsDataURL(file)});
    await api('/api/preview',{...deck,logo:uri,slides:[deck.slides[selected]]});
    deck.logo=uri;deck.logoPosition??='top-right';deck.logoSize??='medium';deck.hideLogoOnTitle??=true;changed();
  }catch(err){status(err.message,true)}finally{e.target.value=''}
};
$('removeLogo').onclick=()=>{delete deck.logo;changed()};
$('titleImagesFile').onchange=async e=>{
  const files=[...e.target.files];e.target.value='';if(!files.length)return;
  try{
    const existing=Array.isArray(deck.titleImages)?deck.titleImages:[];
    if(existing.length+files.length>5)throw Error(`Choose no more than 5 title page images. You can add ${5-existing.length} more.`);
    const added=[];
    for(const file of files){
      if(file.size>5*1024*1024)throw Error(`${file.name} exceeds 5 MB.`);
      if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error(`${file.name} is not a PNG, JPEG or WebP image.`);
      added.push(await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error(`Could not read ${file.name}.`));reader.readAsDataURL(file)}));
    }
    const titleImages=[...existing,...added];await api('/api/preview',{...deck,titleImages});deck.titleImages=titleImages;changed();status(`${added.length} title page image${added.length===1?'':'s'} added.`);
  }catch(err){status(err.message,true)}
};
$('logoPosition').onchange=()=>{deck.logoPosition=$('logoPosition').value;changed()};
$('logoSize').onchange=()=>{deck.logoSize=$('logoSize').value;changed()};
$('hideLogoOnTitle').onchange=()=>{deck.hideLogoOnTitle=$('hideLogoOnTitle').checked;changed()};
$('defaultTransition').onchange=()=>{deck.transition={type:$('defaultTransition').value,speed:$('transitionSpeed').value};changed()};
$('transitionSpeed').onchange=()=>{deck.transition={type:$('defaultTransition').value,speed:$('transitionSpeed').value};changed()};
$('slideTransition').onchange=()=>{deck.slides[selected].transition=$('slideTransition').value;changed()};
const statsChoices={pareto:'Pareto',correlation:'Correlation + regression',matrix:'Correlation matrix',descriptive:'Descriptive statistics',histogram:'Histogram',boxplot:'Box plot'};
Object.entries(statsChoices).forEach(([id,name])=>$('chartType').add(new Option(name,id)));
const seriesEditor=document.createElement('div');seriesEditor.id='seriesEditor';$('seriesNames').closest('label').hidden=true;$('chartControls').append(seriesEditor);
const example=document.createElement('button');example.id='loadExample';example.type='button';example.textContent='Load example data';$('chartControls').append(example);
const histLabel=document.createElement('label');histLabel.id='histogramControls';histLabel.textContent='Histogram bins';
const histSelect=document.createElement('select');histSelect.id='histogramBins';histSelect.add(new Option('Automatic','auto'));
for(let i=2;i<=12;i++)histSelect.add(new Option(String(i),String(i)));
histSelect.onchange=()=>{deck.slides[selected].histogramBins=histSelect.value==='auto'?'auto':Number(histSelect.value);changed()};
histLabel.append(histSelect);$('chartControls').append(histLabel);
example.onclick=()=>{
  if(!confirm('Replace this slide’s data with a statistical example?'))return;
  const s=deck.slides[selected];
  const examples={
    pareto:{content:'Delivery | 45\nQuality | 25\nBilling | 15\nSupport | 10\nOther | 5',seriesNames:'Count',title:'Issue priorities',subtitle:'Illustrative data'},
    correlation:{content:'1 | 2\n2 | 4\n3 | 5\n4 | 4\n5 | 5\n6 | 7',seriesNames:'Y',title:'Relationship between X and Y',subtitle:'Illustrative matched observations'},
    matrix:{content:'1 | 8 | 10\n2 | 6 | 20\n3 | 7 | 30\n4 | 3 | 40\n5 | 2 | 50\n6 | 1 | 60',seriesNames:'Volume | Wait time | Revenue',title:'Correlation matrix',subtitle:'Illustrative matched observations'},
    descriptive:{content:'12\n14\n15\n15\n16\n17\n18\n20\n22\n45',seriesNames:'',title:'Resolution time summary',subtitle:'Illustrative values in minutes'},
    histogram:{content:'12\n14\n15\n15\n16\n17\n18\n20\n22\n45',seriesNames:'',histogramBins:'auto',title:'Resolution time distribution',subtitle:'Illustrative values in minutes'},
    boxplot:{content:'Team A | 12\nTeam A | 14\nTeam A | 15\nTeam A | 16\nTeam A | 18\nTeam A | 45\nTeam B | 8\nTeam B | 10\nTeam B | 11\nTeam B | 13\nTeam B | 15\nTeam B | 17',seriesNames:'',title:'Resolution times by team',subtitle:'Illustrative values in minutes'}
  };
  Object.assign(s,examples[s.chartType]);changed();
};
init();
