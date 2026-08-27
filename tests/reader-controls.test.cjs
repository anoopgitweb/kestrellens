const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(match[1]);
const source = name => html.split(/\r?\n/).find(line => line.startsWith(`function ${name}(`));
const button = {classList: {toggle() {}}, setAttribute(name, value) {this[name] = value;}};
let scroll;
const canvas = {scrollTop: 300, clientTop: 1, getBoundingClientRect: () => ({top: 100}), scrollTo(value) {scroll = value;}};
const page = {getBoundingClientRect: () => ({top: 450}), offsetTop: 900};
const context = {
  document: {querySelector: () => button},
  window: {speechSynthesis: {}, SpeechSynthesisUtterance() {}},
  state: {jotPageCreatorOpen: false, jotSelectedPageIndex: 0, jotViewMode: 'reading'},
  jotSpeechUtterance: null, jotSpeechPaused: false, jotSpeechContinuous: false,
  selectedJotSpeechPage: () => ({item: page}),
  $: id => id === 'jotCanvas' ? canvas : null,
  jotFlashItems: () => [page, page], renderJotModePageNav() {}, syncJotTimeContext() {},
  stopJotReadAloud() {context.jotSpeechUtterance = null;},
};
vm.createContext(context);
vm.runInContext(['syncJotReaderSpeechButton', 'renderJotReadAloudState', 'selectJotModePage'].map(source).join('\n'), context);
context.renderJotReadAloudState();
assert.equal(button.textContent, '🔊');
context.jotSpeechUtterance = {};
context.renderJotReadAloudState();
assert.equal(button.textContent, '❚❚');
assert.equal(button['aria-label'], 'Pause reading');
context.jotSpeechPaused = true;
context.renderJotReadAloudState();
assert.equal(button.textContent, '▶');
assert.equal(button['aria-label'], 'Resume reading');
context.jotSpeechUtterance = null;
context.jotSpeechContinuous = true;
context.renderJotReadAloudState();
assert.equal(button.textContent, '■');
context.jotSpeechContinuous = false;
context.selectJotModePage(1);
assert.equal(scroll.top, 637, 'Target scroll uses viewport-relative geometry, not offsetParent');
canvas.scrollTop = 0;
page.getBoundingClientRect = () => ({top: 105});
context.selectJotModePage(0);
assert.equal(scroll.top, 0, 'First page never scrolls above zero');
assert.match(html, /\.jot-editor\.page-creator-open #jotViewSelect\{display:none!important\}/);
assert.doesNotMatch(html, /jot-view-diagram|renderJotDiagram|removeJotDiagramDetails|jotDiagramIndex|jot-diagram-detail/);
assert.doesNotMatch(html, /value="diagram"|data-jot-view="diagram"/);
assert.doesNotMatch(html, /value="bullets"|data-jot-view="bullets"|jot-view-bullets/);
assert.match(html, /value="numbered"/);
assert.match(html, /option\.value="immersive"/);
const inserted = [];
let immersivePreviews = 0;
const focusPage = {querySelector: () => null, classList: {remove() {}, add() {}}, prepend(node) {inserted.push(node);}};
Object.assign(context, {
  jotFlashItems: () => [focusPage],
  stopJotFocusTimer() {},
  previousJotFocusSubtopic: () => null, nextJotFocusSubtopic: () => null,
  renderJotImmersivePreview() {immersivePreviews++;},
  setInterval() {throw new Error('Focus must not start a timer');},
});
context.document.createElement = () => ({});
context.state.jotFocusIndex = 0;
context.state.jotViewMode = 'focus';
vm.runInContext(source('renderJotFocus'), context);
context.renderJotFocus();
assert.equal(inserted.length, 1);
assert.equal(inserted[0].className, 'jot-focus-page-number');
assert.doesNotMatch(source('renderJotFocus'), /toggleJotFocusTimer\(\)|active\.prepend\(timer\)/);
context.state.jotViewMode = 'immersive';
context.renderJotFocus();
assert.equal(immersivePreviews, 1, 'Immersive preview remains available');
console.log('Reader controls, scroll alignment, creator dropdown rule and script syntax: passed');
