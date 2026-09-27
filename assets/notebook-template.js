(function(global){
  'use strict';
  const columns=Object.freeze(['Notebook','Chapter','Page Heading','Page Details','Video URL','Local Video URL','Diagram','Page Order']);
  const filename='KestrelIQ_Notebook_Template.xlsx';
  let loading;
  function ensureExcel(){
    if(global.XLSX) return Promise.resolve();
    if(!loading) loading=new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      script.src='https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js';
      const fail=()=>{script.remove();loading=null;reject(new Error('Excel support could not load. Check your connection and try again.'));};
      script.onload=()=>global.XLSX?resolve():fail();
      script.onerror=fail;
      document.head.appendChild(script);
    });
    return loading;
  }
  async function write(rows=[],name=filename){
    await ensureExcel();
    const sheet=global.XLSX.utils.aoa_to_sheet([Array.from(columns),...rows]);
    sheet['!cols']=[24,24,36,80,44,44,44,14].map(wch=>({wch}));
    sheet['!autofilter']={ref:sheet['!ref']};
    const book=global.XLSX.utils.book_new();
    global.XLSX.utils.book_append_sheet(book,sheet,'Notebook');
    global.XLSX.writeFile(book,name);
  }
  global.NotebookTemplate=Object.freeze({columns,filename,ensureExcel,write,download:()=>write()});
})(window);
