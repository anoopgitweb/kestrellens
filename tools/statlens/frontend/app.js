'use strict';
document.querySelectorAll('p').forEach(p => { p.textContent = p.textContent.replace('Ten statistical modules', '30+ statistical analyses').replace('Fifteen statistical modules', '30+ statistical analyses'); });
const welcome = document.getElementById('welcome');
function dismissWelcome(){ if(!welcome || welcome.classList.contains('fade')) return; welcome.classList.add('fade'); setTimeout(()=>welcome.remove(),400); }
document.getElementById('welcome-start')?.addEventListener('click',dismissWelcome);
setTimeout(dismissWelcome,4200);
let report = null, jobId = null, busy = false, pptSelected = new Set();
const $ = id => document.getElementById(id);
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = v => v === null ? 'Unavailable' : typeof v === 'number' ? (Math.abs(v) > 0 && Math.abs(v) < .001 ? v.toExponential(3) : v.toLocaleString(undefined,{maximumFractionDigits:4})) : String(v);
function show(view) {
  if (busy && view !== 'working') return;
  if (!report && !['upload','working','learn'].includes(view)) return;
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== view);
  document.querySelectorAll('nav button').forEach(el => el.classList.toggle('active',el.dataset.view === view));
  $('crumb').textContent = view === 'recommend' ? 'RECOMMENDED ANALYSES' : view.toUpperCase();
  window.scrollTo(0,0);
}
document.querySelectorAll('[data-view]').forEach(el => el.addEventListener('click',() => show(el.dataset.view)));
async function api(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'Request failed.');
  return payload;
}
function failure(error) { $('error').textContent = error.message; $('error').hidden = false; }
async function start(url, body) {
  if (busy) return;
  $('error').hidden = true;
  busy = true; show('working'); $('progress').value=0; $('work-message').textContent='Reading your data…';
  try {
    const job = await api(url,{method:'POST',headers:{'X-Local-App':'statlens'},body});
    jobId = job.id;
    for (;;) {
      const state = await api('/api/jobs/'+jobId);
      $('progress').value=state.progress;
      $('work-message').textContent=state.message;
      if (state.status === 'error') throw new Error(state.message);
      if (state.status === 'done') { report=state.result; busy=false; render(); show('profile'); break; }
      await new Promise(resolve => setTimeout(resolve,800));
    }
  } catch(error) { busy=false; show('upload'); failure(error); }
}
function upload(file) {
  if (!file) return;
  if (!/\.(csv|tsv|xlsx)$/i.test(file.name)) return failure(new Error('Choose a CSV, TSV or XLSX file.'));
  if (file.size > 100*1024*1024) return failure(new Error('The file exceeds the 100 MB limit.'));
  start('/api/upload?filename='+encodeURIComponent(file.name),file);
}
$('file').addEventListener('change', e => { upload(e.target.files[0]); e.target.value=''; });
['dragenter','dragover'].forEach(name => $('drop').addEventListener(name,e => {e.preventDefault();$('drop').classList.add('drag');}));
['dragleave','drop'].forEach(name => $('drop').addEventListener(name,e => {e.preventDefault();$('drop').classList.remove('drag');}));
$('drop').addEventListener('drop',e => upload(e.dataTransfer.files[0]));
$('rerun').addEventListener('click',() => {
  const overrides={}; document.querySelectorAll('#columns select').forEach(el => overrides[el.dataset.column]=el.value);
  start('/api/reanalyze/'+jobId,JSON.stringify(overrides));
});
function render() {
  $('file-summary').textContent=report.filename+' · All columns profiled. No rows automatically removed.';
  const quality=report.results.find(r=>r.module==='quality').metrics;
  $('stats').innerHTML=[['Rows',report.rows],['Columns',report.column_count],['Completeness',number(quality['Completeness %'])+'%'],['Duplicate rows',quality['Duplicate rows']]].map(([k,v])=>`<article><b>${escapeHTML(number(v))}</b><span>${k}</span></article>`).join('');
  const types=['numeric','categorical','boolean','date','id','text','constant','empty'];
  $('columns').innerHTML=report.columns.map(c=>`<tr><td><b>${escapeHTML(c.name)}</b></td><td><select aria-label="Type for ${escapeHTML(c.name)}" data-column="${escapeHTML(c.name)}">${types.map(t=>`<option ${t===c.type?'selected':''}>${t}</option>`).join('')}</select></td><td>${number(c.missing)} (${number(c.missing_percent)}%)</td><td>${number(c.invalid)}</td><td>${number(c.unique)}</td><td>${escapeHTML(c.reason)}</td></tr>`).join('');
  $('preview').innerHTML=`<table><thead><tr>${report.columns.map(c=>`<th>${escapeHTML(c.name)}</th>`).join('')}</tr></thead><tbody>${report.preview.map(row=>`<tr>${report.columns.map(c=>`<td>${escapeHTML(row[c.name])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  $('modules').innerHTML=report.recommendations.map(m=>`<article><span class="tag ${m.count?'':'muted'}">${m.count ? m.count+' RESULTS' : 'NOT APPLICABLE'}</span><h2>${escapeHTML(m.label)}</h2><p>${escapeHTML(m.reason)}</p>${m.count?`<button class="secondary" data-module="${m.module}">Explore results →</button>`:''}</article>`).join('');
  $('modules').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{$('filter').value=b.dataset.module;renderFindings();show('dashboard');}));
  $('policy').innerHTML=report.policy.notes.map(n=>`<p>${escapeHTML(n)}</p>`).join('');
  $('filter').innerHTML='<option value="all">All modules</option>'+report.recommendations.map(m=>`<option value="${m.module}">${escapeHTML(m.label)} (${m.count})</option>`).join('');
  $('dashboard-summary').textContent=`${report.results.length} findings · ${report.tests_run} statistical tests with multiple-testing adjustment. Explore effects as well as evidence.`;
  $('csv').href='/api/jobs/'+jobId+'/export?format=csv'; $('json').href='/api/jobs/'+jobId+'/export?format=json';
  renderPptOptions();
  renderLearn();
  $('summary-intro').textContent=`${report.results.length} completed statistical findings across ${report.column_count} profiled columns. Each row below is based on the valid observations available to that analysis.`;
  $('summary-filter').innerHTML='<option value="all">All modules</option>'+report.recommendations.filter(m=>m.count).map(m=>`<option value="${m.module}">${escapeHTML(m.label)} (${m.count})</option>`).join('');
  renderSummary();
  renderFindings();
}
const learnTopics={
 quality:['Data quality profiling','Checks whether values are complete, valid and duplicated.','Example: 98% completeness means 2% of cells need review before analysis.'],
 descriptive:['Descriptive statistics','Summarizes a numeric column with its average, median and spread.','Example: average order value is $120 while the median is $95, suggesting some large orders raise the average.'],
 distribution:['Distribution analysis','Shows how values are shaped and whether a long tail or unusual concentration exists.','Example: a right-skewed revenue distribution means most accounts are smaller while a few accounts are much larger.'],
 correlation:['Correlation','Measures whether two numeric measures move together.','Example: marketing spend and revenue have a positive correlation when higher spend usually appears with higher revenue.'],
 groups:['Group comparison','Compares a numeric measure across categories.','Example: average delivery time differs by region, so operations can investigate the largest gap.'],
 outliers:['Outlier detection','Flags values far outside the middle 50% using Tukey fences.','Example: one transaction is far above the normal order range and should be checked for an input error or exceptional sale.'],
 trend:['Trend analysis','Describes the direction of a measure across dates.','Example: monthly support volume rises steadily through the year.'],
 variance:['Variance / volatility','Measures how consistently values or period-to-period changes behave.','Example: two stores have the same average sales, but the store with lower variation is more predictable.'],
 regression:['Regression / relationships','Fits an exploratory straight-line relationship between two numeric measures.','Example: each additional hour of training is associated with a change in productivity, while the model’s R² shows how much variation it describes.'],
 significance:['Significance testing','Checks whether an observed difference would be unusual under a null hypothesis.','Example: a small p-value suggests the group gap is unlikely to be random under the test assumptions.'],
 effect_size:['Effect sizes & confidence intervals','Describes how large a difference is and how uncertain a slope estimate is.','Example: Cohen’s d of 0.8 is a large standardized group difference, regardless of the original unit.'],
 nonparametric:['Nonparametric tests','Compare ranks when normal-distribution assumptions are not suitable.','Example: Mann–Whitney U compares whether values in one group tend to be higher than another.'],
 seasonality:['Seasonality','Looks for repeated calendar patterns such as month-of-year differences.','Example: demand peaks every December and falls in January across multiple years.'],
 pca:['Principal component analysis','Compresses correlated numeric measures into a few combined dimensions.','Example: revenue, units and orders may combine into one overall “scale” component.'],
 clustering:['Pattern clustering','Groups rows that look similar across selected numeric measures.','Example: customers separate into low-, medium- and high-value patterns for follow-up analysis.']
 ,multiple_regression:['Multiple regression','Estimates one numeric outcome using several numeric predictors together.','Example: estimate revenue from price, region, campaign spend and channel at the same time.']
 ,logistic:['Logistic regression','Estimates the probability of a two-state outcome from a numeric predictor.','Example: estimate the probability that a customer churns as engagement changes.']
 ,forecasting:['Forecasting','Extends a simple time trend into future periods for planning.','Example: project the next three months of demand from observed monthly averages.']
 ,posthoc:['ANOVA post-hoc comparisons','Compares specific pairs after a multi-group difference appears.','Example: identify which regions differ after an overall group test.']
 ,bayesian:['Bayesian proportions','Updates a proportion estimate using observed successes and a transparent prior.','Example: update a conversion-rate estimate after a new campaign.']
 ,survival:['Survival analysis','Estimates the share of observations remaining before an event over time.','Example: estimate how long subscriptions remain active before cancellation.']
 ,power:['Power & sample size','Provides an initial estimate of how much data a future comparison may need.','Example: plan the sample size for an A/B test before collecting data.']
};
const nextTopics=[['Factor analysis','Looks for hidden concepts behind correlated survey questions.','Example: several service questions may reflect one underlying satisfaction factor.'],['Causal inference','Estimates the effect of an intervention while accounting for confounding.','Example: estimate the effect of a discount after adjusting for customer and channel differences.']];
function renderLearn(){
  const used=report?.results||[];
  $('learn-current').innerHTML=Object.entries(learnTopics).map(([module,[title,desc,general]])=>{const matches=used.filter(r=>r.module===module); const example=matches.length?`<b>From your data</b><p>${escapeHTML(matches[0].explanation)}</p>`:`<b>Quick example</b><p>${escapeHTML(general)}</p>`; return `<article><span class="tag">${matches.length?'YOUR DATA':'GENERAL EXAMPLE'}</span><h2>${escapeHTML(title)}</h2><p>${escapeHTML(desc)}</p>${example}</article>`;}).join('');
  $('learn-next').innerHTML=nextTopics.map(([title,desc,example])=>`<article><span class="tag muted">COMING NEXT</span><h2>${escapeHTML(title)}</h2><p>${escapeHTML(desc)}</p><b>Quick example</b><p>${escapeHTML(example)}</p></article>`).join('');
}
function renderPptOptions() {
  pptSelected = new Set(report.results.map(r=>r.id));
  $('ppt-module-filter').innerHTML='<option value="all">All analysis types</option>'+report.recommendations.filter(m=>m.count).map(m=>`<option value="${m.module}">${escapeHTML(m.label)}</option>`).join('');
  drawPptList();
  updatePptCount();
}
function drawPptList(){
  const query=($('ppt-search')?.value||'').toLowerCase(), module=$('ppt-module-filter')?.value||'all';
  const markup=report.results.map((r,i)=>({r,i})).filter(({r})=>(module==='all'||r.module===module)&&(!query||(r.title+' '+r.module+' '+(r.fields||[]).join(' ')).toLowerCase().includes(query))).map(({r,i})=>{const fields=r.fields?.length?r.fields.join(' · '):'Dataset-level'; return `<label data-result-id="${r.id}"><input type="checkbox" class="ppt-result" value="${r.id}" ${pptSelected.has(r.id)?'checked':''}><span>${i+1}. ${escapeHTML(r.title)}</span><small>${escapeHTML(report.recommendations.find(m=>m.module===r.module)?.label||r.module)} · ${r.chart?'chart included':'metrics only'} · Fields: ${escapeHTML(fields)}</small></label>`;}).join('');
  $('ppt-screen-list').innerHTML=markup || '<p class="small" style="padding:15px">No analyses match this filter.</p>';
  $('ppt-list').innerHTML=markup;
  $('ppt-screen-list').querySelectorAll('label[data-result-id]').forEach(row=>row.addEventListener('click',e=>{ if(e.target.tagName!=='INPUT') showPptPreview(report.results.find(r=>r.id===row.dataset.resultId)); else showPptPreview(report.results.find(r=>r.id===row.dataset.resultId)); }));
}
function fieldSummary(r){ return r.fields?.length ? `<div class="field-summary"><b>Fields included</b><span>${r.fields.map(escapeHTML).join(' · ')}</span></div>` : ''; }
function showPptPreview(r){ if(!r)return; $('ppt-preview').innerHTML=`<span class="tag">${escapeHTML(report.recommendations.find(m=>m.module===r.module)?.label||r.module)}</span><h2>${escapeHTML(r.title)}</h2>${fieldSummary(r)}<p>${escapeHTML(r.explanation)}</p>${r.chart?chart(r.chart):'<p class="note">This result has no chart data, so the PPT slide will use its metrics and explanation.</p>'}<h3>Key metrics</h3>${metrics(r)}${r.p_value!==undefined?`<p class="small">p = ${number(r.p_value)}${r.q_value!==undefined?` · adjusted q = ${number(r.q_value)}`:''}</p>`:''}`; }
function updatePptCount() { const n=pptSelected.size; $('ppt-selected-count').textContent=`${n} selected`; $('ppt-screen-count').textContent=`${n} selected`; }
function validPoints(r) {
  const m=r.metrics||{};
  for (const key of ['Valid rows','Paired rows','Rows used','Changes measured','Observed periods']) if (m[key] !== undefined) return m[key];
  const rowKey=Object.keys(m).find(k=>/rows used|paired rows|valid rows/i.test(k));
  return rowKey ? m[rowKey] : '—';
}
function keyStatistics(r) {
  const m=r.metrics||{};
  const preferred=['Mean','Median','Standard deviation','Skewness','Pearson r','Spearman rho','R²','Slope','Flagged %','Cohen’s d','U statistic','Test statistic','Cramér’s V','Seasonal range','PC1 variance %','PC2 variance %'];
  const selected=preferred.filter(k=>m[k]!==undefined).slice(0,4);
  if (!selected.length) return Object.entries(m).filter(([k,v])=>typeof v==='number').slice(0,4).map(([k,v])=>`${k}: ${number(v)}`).join(' · ') || 'See detail';
  return selected.map(k=>`${k}: ${number(m[k])}`).join(' · ');
}
function renderSummary() {
  if (!report) return;
  const selected=$('summary-filter').value;
  const rows=report.results.filter(r=>selected==='all'||r.module===selected);
  $('summary-count').textContent=`${rows.length} result${rows.length===1?'':'s'}`;
  $('summary-rows').innerHTML=rows.map((r,i)=>`<tr><td>${i+1}</td><td><span class="tag">${escapeHTML(report.recommendations.find(m=>m.module===r.module)?.label||r.module)}</span></td><td><b>${escapeHTML(r.title)}</b></td><td>${escapeHTML(r.fields?.join(' · ')||'Dataset-level')}</td><td>${escapeHTML(number(validPoints(r)))}</td><td>${escapeHTML(keyStatistics(r))}</td><td>${r.evidence?`<span class="evidence">${escapeHTML(r.evidence)}<br>q = ${number(r.q_value)}</span>`:r.p_value!==undefined?`p = ${number(r.p_value)}`:'Descriptive'}</td><td>${escapeHTML(r.explanation)}</td></tr>`).join('');
}
function evidence(r) { return r.evidence ? `<span class="evidence">${escapeHTML(r.evidence)} · adjusted q = ${number(r.q_value)}</span>` : ''; }
function renderFindings() {
  const selected=$('filter').value, query=$('search').value.toLowerCase();
  const found=report.results.filter(r=>(selected==='all'||r.module===selected) && (r.title+' '+r.explanation).toLowerCase().includes(query));
  $('findings').innerHTML=found.map(r=>`<article class="finding"><span class="tag">${escapeHTML(report.recommendations.find(m=>m.module===r.module).label)}</span><h2>${escapeHTML(r.title)}</h2><p>${escapeHTML(r.explanation)}</p>${evidence(r)}<button class="secondary" data-result="${r.id}">View statistical detail ↗</button></article>`).join('') || '<p>No matching results. Try another module or search.</p>';
  $('findings').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{const r=report.results.find(r=>r.id===b.dataset.result);$('detail-body').innerHTML=detail(r);$('detail').showModal();}));
}
$('filter').addEventListener('change',renderFindings);$('search').addEventListener('input',renderFindings);
$('summary-filter').addEventListener('change',renderSummary);
$('ppt-open').addEventListener('click',()=>show('ppt-select'));
$('ppt-screen-back').addEventListener('click',()=>show('export'));
$('ppt-all').addEventListener('change',e=>{ document.querySelectorAll('.ppt-result').forEach(c=>c.checked=e.target.checked); updatePptCount(); });
$('ppt-screen-all').addEventListener('change',e=>{ if(e.target.checked) pptSelected=new Set(report.results.map(r=>r.id)); else pptSelected.clear(); drawPptList(); updatePptCount(); });
document.addEventListener('change',e=>{if(e.target.classList?.contains('ppt-result')) { if(e.target.checked) pptSelected.add(e.target.value); else pptSelected.delete(e.target.value); updatePptCount(); }});
$('ppt-search').addEventListener('input',drawPptList); $('ppt-module-filter').addEventListener('change',drawPptList);
$('ppt-screen-generate').addEventListener('click',async()=>{
  const ids=[...pptSelected];
  if(!ids.length){$('ppt-screen-status').textContent='Select at least one analysis.';return;}
  $('ppt-screen-generate').disabled=true;$('ppt-screen-status').textContent='Generating editable charts and slides locally…';
  try { const response=await fetch('/api/jobs/'+jobId+'/ppt',{method:'POST',headers:{'X-Local-App':'statlens','Content-Type':'application/json'},body:JSON.stringify({result_ids:ids})}); if(!response.ok){const e=await response.json();throw new Error(e.error||'Generation failed.');} const blob=await response.blob(); const link=document.createElement('a'); link.href=URL.createObjectURL(blob); link.download='statlens-analysis.pptx'; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); $('ppt-screen-status').textContent='PowerPoint generated and downloaded.'; } catch(e) { $('ppt-screen-status').textContent=e.message; } finally { $('ppt-screen-generate').disabled=false; }
});
$('close-detail').addEventListener('click',()=>$('detail').close());
function metrics(r) { return `<table><tbody>${Object.entries(r.metrics).map(([k,v])=>`<tr><th>${escapeHTML(k)}</th><td>${escapeHTML(number(v))}</td></tr>`).join('')}${r.p_value!==undefined?`<tr><th>Unadjusted p-value</th><td>${number(r.p_value)}</td></tr><tr><th>Adjusted q-value</th><td>${number(r.q_value)}</td></tr>`:''}</tbody></table>`; }
function chart(c) {
  if (!c) return '';
  const W=650,H=250,L=70,R=20,T=20,B=40;
  const points=c.type==='scatter'?c.points:c.values.map((y,x)=>[x,y]);
  if (!points.length) return '';
  let xmin=Math.min(...points.map(p=>p[0])),xmax=Math.max(...points.map(p=>p[0]));
  let ymin=Math.min(0,...points.map(p=>p[1])),ymax=Math.max(0,...points.map(p=>p[1]));
  const x=v=>L+(v-xmin)/(xmax-xmin||1)*(W-L-R), y=v=>H-B-(v-ymin)/(ymax-ymin||1)*(H-T-B);
  let marks='';
  if(c.type==='scatter') marks=points.map(p=>`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="2.8" fill="#208c70" opacity=".5"/>`).join('');
  else if(c.type==='line') marks=`<polyline points="${points.map(p=>x(p[0])+','+y(p[1])).join(' ')}" fill="none" stroke="#208c70" stroke-width="2.4"/>`;
  else { const step=(W-L-R)/points.length; marks=points.map((p,i)=>`<rect x="${L+i*step+2}" y="${Math.min(y(0),y(p[1]))}" width="${Math.max(1,step-4)}" height="${Math.max(1,Math.abs(y(0)-y(p[1])))}" fill="#47a88d"><title>${escapeHTML(c.labels[i])}: ${escapeHTML(number(p[1]))}</title></rect>`).join(''); }
  const first=c.type==='scatter'?number(xmin):c.labels[0],last=c.type==='scatter'?number(xmax):c.labels[c.labels.length-1];
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHTML(c.type)} chart"><line x1="${L}" y1="${y(0)}" x2="${W-R}" y2="${y(0)}" stroke="#bdcdd2"/>${marks}<text x="5" y="${T+5}">${escapeHTML(number(ymax))}</text><text x="5" y="${H-B}">${escapeHTML(number(ymin))}</text><text x="${L}" y="${H-12}">${escapeHTML(first)}</text><text x="${W-R}" y="${H-12}" text-anchor="end">${escapeHTML(last)}</text></svg><p class="chart-caption">${c.type==='scatter'?escapeHTML(c.xLabel)+' (horizontal) · '+escapeHTML(c.yLabel)+' (vertical) · Up to 250 sampled points.':'All observations contribute to these aggregates; expand below for exact labels and values.'}</p>${c.type!=='scatter'?`<details class="chart-data"><summary>Chart values</summary><table>${c.labels.map((l,i)=>`<tr><td>${escapeHTML(l)}</td><td>${number(c.values[i])}</td></tr>`).join('')}</table></details>`:''}`;
}
function detail(r) { return `<span class="tag">STATISTICAL DETAIL</span><h2>${escapeHTML(r.title)}</h2>${fieldSummary(r)}<p>${escapeHTML(r.explanation)}</p>${evidence(r)}${chart(r.chart)}${metrics(r)}<h3>How this was calculated</h3><p>${escapeHTML(r.method)}</p><h3>Before acting on this result</h3><p>${escapeHTML(r.caveat || 'Consider the collection process and business context. A descriptive pattern alone does not establish a cause.')}</p>`; }
$('print').addEventListener('click',()=>{
  $('print-report').innerHTML=`<h1>StatLens analysis report</h1><p>${escapeHTML(report.filename)} · ${number(report.rows)} rows · ${number(report.column_count)} columns</p><h2>Analysis policy</h2>${report.policy.notes.map(n=>`<p>${escapeHTML(n)}</p>`).join('')}<h2>Column profile</h2><table><tr><th>Column</th><th>Type</th><th>Missing</th><th>Invalid</th></tr>${report.columns.map(c=>`<tr><td>${escapeHTML(c.name)}</td><td>${c.type}</td><td>${c.missing}</td><td>${c.invalid}</td></tr>`).join('')}</table>${report.results.map(r=>`<article class="report-item">${detail(r)}</article>`).join('')}`;
  window.print();
});
renderLearn();
