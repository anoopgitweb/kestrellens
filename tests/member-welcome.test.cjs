const fs = require('node:fs');
const assert = require('node:assert/strict');

const html = fs.readFileSync('templates/index.html', 'utf8');
const scripts = [...html.matchAll(new RegExp('<script[^>]*>([\\s\\S]*?)</script>', 'gi'))];
scripts.forEach(match => new Function(match[1]));

assert.match(html, /id="memberWelcome"/);
assert.match(html, />Build my edge</);
assert.match(html, />Signal Radar</);
assert.match(html, /function memberNotebookProgress\(/);
assert.match(html, /function renderMemberWelcome\(/);
assert.match(html, /state\.session&&!canUseOwnerDashboard\(\)/);
assert.match(html, /await loadJotDown\(false\)/);
assert.match(html, /prefers-reduced-motion:reduce/);
assert.match(html, /\.member-progress\{display:block;position:relative;width:100%;height:6px/);
assert.match(html, /\.member-progress i\{display:block;position:absolute;inset:0 auto 0 0;max-width:100%/);

console.log('Member welcome: personalized routes, assigned learning progress, access gating and motion fallback passed');
