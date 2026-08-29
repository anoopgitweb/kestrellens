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

console.log('Member welcome: personalized routes, assigned learning progress, access gating and motion fallback passed');
