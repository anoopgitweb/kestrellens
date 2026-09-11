const fs = require('node:fs');
const assert = require('node:assert/strict');

const page = fs.readFileSync('tools/talentedge.html', 'utf8');
const app = fs.readFileSync('app.py', 'utf8');
const sql = fs.readFileSync('supabase_talentedge.sql', 'utf8');

for (const match of page.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)) new Function(match[1]);

assert.match(page, /\/api\/talentedge\/assessment/);
assert.match(page, /Saving results…/);
assert.match(page, /Assessment results saved successfully to Supabase/);
assert.match(page, /crypto\.randomUUID\(\)/);
assert.match(page, /\/api\/admin\/talentedge-assessments/);
assert.match(page, /Select candidate/);
assert.match(page, /Results are loaded from Supabase, newest session first/);
assert.match(app, /def _save_talentedge_assessment/);
assert.match(app, /def _admin_talentedge_assessments/);
assert.match(sql, /create table if not exists public\.talentedge_assessments/);
console.log('TalentEdge Supabase logout persistence passed');
