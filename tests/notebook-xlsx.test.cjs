const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../tools/notebook-presenter.html'), 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)) new Function(match[1]);
const start = html.indexOf('const NOTEBOOK_COLUMNS=');
const end = html.indexOf('function toggleFmtGuide()', start);
let input, output;
const XLSX = {
  read: () => ({SheetNames:['Notebook'], Sheets:{Notebook:input}}),
  utils: {
    sheet_to_json: sheet => sheet,
    aoa_to_sheet: rows => ({rows, '!ref':'A1:G3'}),
    book_new: () => ({}),
    book_append_sheet: (book,sheet,name) => {book[name]=sheet;}
  },
  writeFile: (book,filename) => {output={book,filename};}
};
const context = vm.createContext({XLSX, window:{XLSX}, csvRows:[], notebookTitle:'Test notebook', alert:message=>{throw Error(message);}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/notebook-template.js'),'utf8'),context);
vm.runInContext(html.slice(start,end),context);
const columns=['Notebook','Chapter','Page Heading','Page Details','Video URL','Local Video URL','Diagram','Page Order'];
(async()=>{
  await context.downloadTemplate();
  assert.equal(output.filename,'KestrelIQ_Notebook_Template.xlsx');
  assert.deepEqual(Array.from(output.book.Notebook.rows[0]),columns);
  assert.equal(output.book.Notebook.rows.length,1);
  input=[columns,['Demo','Chapter 1','Heading','First line\nSecond line','https://example.com/video','lesson.mp4','https://example.com/diagram.png',2],['','','','','','','']];
  const rows=context.parseNotebookXLSX(new Uint8Array());
  assert.equal(rows.length,1);
  assert.equal(rows[0]['Page Details'],'First line\nSecond line');
  assert.equal(rows[0]['Page Order'],'2');
  assert.equal(rows[0]['Local Video URL'],'lesson.mp4');
  context.csvRows=rows;
  await context.adminExportXLSX();
  assert.equal(output.book.Notebook.rows[1][5],'lesson.mp4');
  assert.equal(output.book.Notebook.rows[1][6],'https://example.com/diagram.png');
  assert.equal(output.book.Notebook.rows[1][7],2);
  context.csvRows[0]['Image URL']='';
  await context.adminExportXLSX();
  assert.equal(output.book.Notebook.rows[1][6],''); // A cleared diagram stays cleared.
  input=[columns.filter(name=>name!=='Local Video URL'),['Demo','Chapter','Legacy','Details','','',1]];
  assert.equal(context.parseNotebookXLSX(null)[0]['Page Heading'],'Legacy');
  input=[columns.slice(0,7)];
  assert.throws(()=>context.parseNotebookXLSX(null),/Missing columns: Page Order/);
  input=[[...columns,'Chapter']];
  assert.throws(()=>context.parseNotebookXLSX(null),/unique/);
  input=[];
  assert.throws(()=>context.parseNotebookXLSX(null),/empty/);
  assert.match(html,/if\(!row\['Image URL'\]\) row\['Image URL'\]=row\['Diagram'\]/);
  assert.match(html,/if\(isExcel\) r.readAsArrayBuffer\(file\); else r.readAsText\(file\)/);
  console.log('Notebook XLSX template, mapping, export, and validation checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

