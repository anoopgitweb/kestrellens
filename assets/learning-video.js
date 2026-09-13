/* Uploaded notebook videos and private saved transcripts. */
(() => {
  const isVideo=a=>Boolean(a&&/\.(mp4|webm|mov)$/i.test(a.name||a.path||''));
  const style=document.createElement('style');
  style.textContent=`#jotUploadedVideo{margin:auto;border:1px solid #2ca69b;border-radius:16px;background:#032c35;color:#e5f8f6;width:min(1100px,94vw);max-height:92dvh;padding:20px;box-sizing:border-box;overflow:auto}#jotUploadedVideo::backdrop{background:#00171dde}#jotUploadedVideo header,#jotUploadedVideo .video-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}#jotUploadedVideo h2{font-size:18px;flex:1;margin:0;overflow-wrap:anywhere}#jotUploadedVideo button,#jotUploadedVideo select{background:#08464c;color:#effffd;border:1px solid #268d88;border-radius:8px;padding:8px 12px}#jotUploadedVideo button:disabled{opacity:.45}#jotUploadedVideo video{display:block;width:100%;max-height:48dvh;background:#00191e}#jotUploadedVideo .transcript-copy{white-space:pre-wrap;line-height:1.7;max-height:30vh;overflow:auto;padding:14px;background:#05212b}#jotUploadedVideo .transcript-copy button{display:block;text-align:left;width:100%;margin-bottom:8px}#jotUploadedVideosBtn[hidden]{display:none!important}`;
  document.head.append(style);
  const dialog=document.createElement('dialog');dialog.id='jotUploadedVideo';
  dialog.innerHTML='<header><h2>Video and transcript</h2><button type="button" data-close aria-label="Close video">Close</button></header><select aria-label="Select uploaded video"></select><video controls preload="metadata"></video><p role="status" data-status></p><div class="video-actions"><button data-transcribe>Transcribe video</button><button data-txt disabled>Download TXT</button><button data-srt disabled>Download SRT</button><button data-pdf disabled>Print / Save PDF</button></div><small>Transcribing sends this video\'s audio to OpenAI. The transcript is saved privately with the video. Please check names and technical terms for accuracy.</small><div class="transcript-copy"></div>';
  document.body.append(dialog);
  const media=dialog.querySelector('video'),select=dialog.querySelector('select'),status=dialog.querySelector('[data-status]'),copy=dialog.querySelector('.transcript-copy'),transcribe=dialog.querySelector('[data-transcribe]');
  let videos=[],current=null,transcript=null,objectUrl='',version=0,pollTimer;
  const close=()=>{version++;clearTimeout(pollTimer);media.pause();media.removeAttribute('src');media.load();if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl='';dialog.close();};
  dialog.querySelector('[data-close]').onclick=close;dialog.oncancel=e=>{e.preventDefault();close();};
  function collect(item){return Array.from(item?.querySelectorAll('a[data-storage-path][data-attachment-name]')||[]).map(a=>({path:a.dataset.storagePath,name:a.dataset.attachmentName,type:a.dataset.attachmentType})).filter(isVideo);}
  async function api(action,jobId,path){await ensureFreshSession();const response=await fetch('/api/discover-learn/transcript',{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify({action,job_id:jobId,path})});const result=await response.json();if(!response.ok)throw Error(result.error||'Transcription unavailable');return result;}
  function renderTranscript(value){transcript=value;copy.replaceChildren();for(const key of ['txt','srt','pdf'])dialog.querySelector('[data-'+key+']').disabled=!value;transcribe.disabled=Boolean(value);transcribe.textContent=value?'Transcript saved':'Transcribe video';if(!value)return;status.textContent='Transcript saved in your private storage.';if(value.segments?.length){for(const segment of value.segments){const button=document.createElement('button');button.type='button';button.textContent=stamp(segment.start)+'  '+segment.text;button.onclick=()=>{media.currentTime=segment.start;media.play().catch(()=>{});};copy.append(button);}}else copy.textContent=value.text;}
  async function track(action='read',jobId,request=version,path=current.path){
    try{const result=await api(action,jobId,path);if(request!==version)return;
      status.textContent=result.message||'Ready to transcribe.';
      if(result.status==='complete'){renderTranscript(result.transcript);return;}
      transcribe.disabled=result.status==='processing';
      if(result.status==='processing')pollTimer=setTimeout(()=>track('status',result.job_id,request,path),2500);
      else if(result.status==='failed'){status.textContent=result.message;transcribe.disabled=false;}
    }catch(error){if(request===version){status.textContent=error.message;transcribe.disabled=false;}}
  }
  async function load(index){const request=++version;clearTimeout(pollTimer);current=videos[index];renderTranscript(null);media.pause();media.removeAttribute('src');media.load();if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl='';status.textContent='Loading video...';dialog.querySelector('h2').textContent=current.name;const path=current.path;
    track('read',null,request,path);
    try{await ensureFreshSession();const cfg=await loadAuthConfig(),response=await fetch(`${cfg.supabaseUrl}/storage/v1/object/${JOT_IMAGE_BUCKET}/${jotStoragePathUrl(path)}`,{headers:{apikey:cfg.supabaseAnonKey,Authorization:`Bearer ${state.session.access_token}`}});if(!response.ok)throw Error('Video could not be loaded.');const blob=await response.blob();if(request!==version)return;objectUrl=URL.createObjectURL(blob);media.src=objectUrl;}
    catch(error){if(request===version)status.textContent=error.message;}
  }
  function open(list,index=0){videos=list;if(!videos.length)return;select.replaceChildren();videos.forEach((v,i)=>{const o=document.createElement('option');o.value=i;o.textContent=v.name;select.append(o);});select.value=index;select.hidden=videos.length<2;(document.fullscreenElement||document.body).append(dialog);if(!dialog.open)dialog.showModal();load(index);}
  select.onchange=()=>load(Number(select.value));transcribe.onclick=()=>{transcribe.disabled=true;status.textContent='Starting transcription...';track('start');};
  function stamp(seconds,srt=false){const ms=Math.max(0,Math.round(Number(seconds||0)*1000));return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(n=>String(n).padStart(2,'0')).join(':')+(srt?','+String(ms%1000).padStart(3,'0'):'');}
  function download(format){if(!transcript)return;const text=format==='srt'?(transcript.segments||[]).map((s,i)=>`${i+1}\n${stamp(s.start,true)} --> ${stamp(s.end,true)}\n${s.text}\n`).join('\n'):transcript.text;const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=current.name.replace(/\.[^.]+$/,'')+'.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  dialog.querySelector('[data-txt]').onclick=()=>download('txt');dialog.querySelector('[data-srt]').onclick=()=>download('srt');
  dialog.querySelector('[data-pdf]').onclick=()=>{const popup=window.open('','_blank');if(!popup){status.textContent='Allow the print window to save as PDF.';return;}const doc=popup.document;doc.title=current.name+' transcript';const css=doc.createElement('style');css.textContent='body{font:12pt/1.6 Arial,sans-serif;margin:24mm}pre{white-space:pre-wrap;font:inherit}h1{font-size:20pt}@page{margin:18mm}';doc.head.append(css);const title=doc.createElement('h1'),body=doc.createElement('pre');title.textContent=current.name;body.textContent=transcript.text;doc.body.append(title,body);popup.focus();popup.print();};
  const originalOpen=openJotStoredAttachment;
  openJotStoredAttachment=function(event,attachment,button){if(isVideo(attachment)){event?.preventDefault();event?.stopPropagation();const list=collect(event?.currentTarget?.closest('li'));open(list.length?list:[attachment],Math.max(0,list.findIndex(a=>a.path===attachment.path)));return;}return originalOpen(event,attachment,button);};
  const toolbar=document.createElement('button');toolbar.id='jotUploadedVideosBtn';toolbar.type='button';toolbar.hidden=true;toolbar.textContent='Video';toolbar.title='Open uploaded videos and transcripts';toolbar.onclick=()=>open(collect(selectedJotSpeechPage()?.item));$('jotPagePdfBtn').after(toolbar);
  const originalSync=syncSelectedJotPageMarker;
  syncSelectedJotPageMarker=function(){originalSync();const list=collect(selectedJotSpeechPage()?.item);toolbar.hidden=!list.length;toolbar.textContent='Video ('+list.length+')';};
  const originalDelete=deleteJotStoragePaths;
  deleteJotStoragePaths=function(paths=[]){return originalDelete([...paths,...paths.filter(path=>isVideo({path})).map(path=>path+'.transcript.json')]);};
  const originalClearSession=clearSession;
  clearSession=function(){close();current=null;videos=[];renderTranscript(null);return originalClearSession();};
  syncSelectedJotPageMarker();
})();
