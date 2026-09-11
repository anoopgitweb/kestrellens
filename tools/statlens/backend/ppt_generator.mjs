import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const artifactPath = process.env.STATLENS_ARTIFACT_TOOL || 'C:/Users/manju/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const { Presentation, PresentationFile } = await import(pathToFileURL(artifactPath).href);

const inputFile = process.argv[3];
const rawInput = inputFile ? await fs.readFile(inputFile, 'utf8') : await new Promise((resolve, reject) => {
  let data=''; process.stdin.setEncoding('utf8'); process.stdin.on('data', c=>data+=c); process.stdin.on('end',()=>resolve(data)); process.stdin.on('error',reject);
});
const input = JSON.parse(rawInput);
const output = process.argv[2];
if (!output) throw new Error('Output path is required.');
const family = 'Aptos';
const presentation = Presentation.create({slideSize:{width:1280,height:720}});
const colors = {ink:'#172A3A', teal:'#198568', pale:'#EAF3F0', muted:'#637681'};
function text(slide, value, position, style={}) {
  const shape=slide.shapes.add({geometry:'textbox',position,fill:'none',line:{fill:'none',width:0}});
  shape.text=String(value??''); shape.text.style={typeface:family,fontSize:style.fontSize||20,color:style.color||colors.ink,bold:!!style.bold,alignment:style.alignment||'left',autoFit:'shrink'};
  return shape;
}
function metricLine(result) {
  const m=result.metrics||{}; const entries=Object.entries(m).filter(([k,v])=>typeof v==='number' && Number.isFinite(v)).slice(0,5);
  return entries.map(([k,v])=>`${k}: ${Number(v).toLocaleString(undefined,{maximumFractionDigits:4})}`).join('   ·   ');
}
function addChart(slide, chart) {
  if (!chart) return;
  try {
    if (chart.type==='scatter' && chart.points?.length) {
      slide.charts.add('scatter',{position:{left:80,top:300,width:1120,height:330},series:[{name:chart.yLabel||'Value',values:chart.points.map(p=>({x:p[0],y:p[1]})),fill:colors.teal}],hasLegend:false});
    } else if ((chart.type==='bar'||chart.type==='line') && chart.values?.length) {
      const type=chart.type==='line'?'line':'bar';
      const options={position:{left:80,top:300,width:1120,height:330},categories:(chart.labels||[]).map(String),series:[{name:'Value',values:chart.values,fill:colors.teal}],hasLegend:false,dataLabels:{showValue:false}};
      if(type==='bar') options.barOptions={direction:'column',grouping:'clustered'};
      slide.charts.add(type,options);
    }
  } catch (err) {
    text(slide, 'Chart preview unavailable for this result. See the metrics above.', {left:80,top:360,width:1120,height:60},{fontSize:18,color:colors.muted});
  }
}
function addResult(result, index) {
  const slide=presentation.slides.add(); slide.background.fill='#FFFFFF';
  text(slide, input.filename || 'StatLens analysis', {left:60,top:28,width:900,height:28},{fontSize:13,color:colors.teal,bold:true});
  text(slide, result.title, {left:60,top:65,width:1160,height:58},{fontSize:32,bold:true});
  text(slide, result.module.replaceAll('_',' ').toUpperCase(), {left:60,top:132,width:800,height:22},{fontSize:12,color:colors.teal,bold:true});
  if (result.fields?.length) text(slide, `Fields included: ${result.fields.join(' · ')}`, {left:60,top:155,width:1160,height:22},{fontSize:13,color:colors.muted});
  text(slide, result.explanation, {left:60,top:result.fields?.length?195:170,width:1160,height:95},{fontSize:18,color:colors.muted});
  text(slide, metricLine(result) || 'Descriptive result with no single numeric summary.', {left:60,top:result.fields?.length?295:270,width:1160,height:28},{fontSize:15,bold:true,color:colors.ink});
  addChart(slide,result.chart);
  if (result.p_value!==undefined) text(slide, `Evidence: p = ${Number(result.p_value).toPrecision(4)}${result.q_value!==undefined?` · adjusted q = ${Number(result.q_value).toPrecision(4)}`:''}`, {left:60,top:665,width:1160,height:22},{fontSize:12,color:colors.teal});
  text(slide, `StatLens · ${index}`, {left:1100,top:28,width:120,height:22},{fontSize:11,color:colors.muted,alignment:'right'});
  slide.speakerNotes.textFrame.setText(`${result.method}\n\nCaveat: ${result.caveat||'Interpret with the collection process and business context.'}`);
}
const cover=presentation.slides.add(); cover.background.fill=colors.ink;
text(cover,'StatLens',{left:75,top:100,width:600,height:65},{fontSize:50,bold:true,color:'#FFFFFF'});
text(cover,'Automatic statistical analysis',{left:80,top:190,width:900,height:55},{fontSize:30,color:'#8FE2C7'});
text(cover,`${input.selectedCount} selected findings · ${input.filename||'Uploaded dataset'}`,{left:80,top:285,width:1000,height:32},{fontSize:18,color:'#FFFFFF'});
text(cover,'Generated locally from the Results Summary selection',{left:80,top:620,width:900,height:25},{fontSize:14,color:'#B6D2D2'});
for (const [i,result] of input.results.entries()) addResult(result,i+1);
await fs.mkdir(path.dirname(output),{recursive:true});
await (await PresentationFile.exportPptx(presentation)).save(output);
