const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const styles = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.KESTREL_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  try {
    const page = await browser.newPage();
    for (const width of [340, 530, 900]) {
      await page.setContent(`<style>${styles}</style><div id="kestrelApp"><div id="jotEditor" class="jot-editor view-mode jot-view-reading" style="display:block;width:${width}px;height:700px"><div id="jotCanvas" class="jot-canvas" style="height:600px"><ol class="jot-card-list"><li data-rich-description="true"><span class="jot-card-heading">Introduction</span><div class="jot-card-content"><p>Before you begin building, four key decisions shape everything that follows. ${'Text must remain readable. '.repeat(15)}</p><p>${'*'.repeat(180)}</p><p><a href="#">https://example.com/${'longpath'.repeat(40)}</a></p><div style="width:1000px"><p>Pasted content</p><img width="1000" height="400" style="width:1000px" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1000' height='400'%3E%3C/svg%3E"></div></div></li></ol></div></div></div>`);
      await page.emulateMedia({reducedMotion:'reduce'});
      for(const mode of ['reading','table','focus','flashcards']) {
      await page.evaluate(mode=>{document.getElementById('jotEditor').className='jot-editor view-mode jot-view-'+mode;document.querySelector('.jot-card-list>li').className=mode==='focus'?'focus-active':mode==='flashcards'?'flash-active flash-revealed':'';},mode);
      await page.evaluate(()=>{const p=document.querySelector('.jot-card-content p');p.style.textAlign='center';});
      assert.equal(await page.locator('.jot-card-content p').first().evaluate(el=>getComputedStyle(el).textAlign),'left',`${mode}: pasted alignment must not center content`);
      const overflow = await page.evaluate(() => {
        const canvas = document.getElementById('jotCanvas');
        return [canvas, ...canvas.querySelectorAll('ol,li,.jot-card-content,p,div,img')].filter(el => el.scrollWidth > el.clientWidth + 1).map(el => `${el.tagName}.${el.className}: ${el.scrollWidth}/${el.clientWidth}`);
      });
      assert.deepEqual(overflow, [], `${mode} pane at ${width}px must wrap text and fit images`);
      }
      await page.evaluate(()=>{const editor=document.getElementById('jotEditor');editor.insertAdjacentHTML('beforeend','<footer class="jot-editor-foot"><div class="jot-footer-summary"><div class="jot-flash-controls"><button>←</button><span>1 of 3</span><button>Reveal</button><button>→</button></div><div class="jot-reader-actions"><button class="jot-rating">✓ Confident</button><button class="jot-rating">Needs practice</button><button>▶</button><select><option>1×</option></select><button>✓</button></div></div></footer>');});
      const footerOverflow=await page.evaluate(()=>[...document.querySelectorAll('.jot-editor-foot,.jot-footer-summary,.jot-reader-actions')].some(el=>el.scrollWidth>el.clientWidth+1));
      assert.equal(footerOverflow,false,'Footer controls must wrap instead of clipping');
    }
    console.log('Reading layout: narrow/wide panes, separators, URLs and oversized images passed');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
