const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "..", "tools", "presenter-5-step-flow.html"), "utf8");
const server = fs.readFileSync(path.join(__dirname, "..", "app.py"), "utf8");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(match => match[1]);
scripts.forEach(source => new Function(source));
assert.match(html, /id="editVideoFile"[^>]+type="file"/);
assert.match(html, /id="editDocumentFile"[^>]+type="file"/);
assert.match(html, /id="editVideo2File"[^>]+type="file"/);
assert.match(html, /id="editDocument3File"[^>]+type="file"/);
assert.match(html, /id="editPpt3File"[^>]+type="file"/);
assert.match(html, /id="editLive3Url"[^>]+type="url"/);
assert.match(html, /Up to 3 videos/);
assert.match(html, /Reference Docs \(PDF\)/);
assert.match(html, /Reference Docs \(PPT\)/);
assert.match(html, /Up to 3 PDFs/);
assert.match(html, /Up to 3 presentations/);
assert.match(html, /Up to 3 links/);
assert.match(html, /\/api\/presenter-media\?launch=/);
assert.match(html, />Clear all content<\/button>/);
assert.match(html, /WARNING: This will permanently delete all capabilities/);
assert.match(html, /welcomeHeading:"Welcome Heading"/);
assert.match(html, /welcomeLocation:"Welcome Location"/);
assert.match(html, /title:`Stage \$\{index\+1\}`/);
assert.match(html, /enablers:\[\],technologies:\[\]/);
assert.match(html, /reference-video/);
assert.match(html, /reference-document/);
assert.match(html, /generated-live-link/);
assert.match(html, /id="linksCard"/);
assert.match(html, /data-links/);
assert.match(html, /preview=1/);
assert.match(server, /def _presenter_pptx_preview/);
assert.match(server, /8 \* 60 \* 60 if tool_key == "presenter-5-step-flow"/);
assert.match(html, /downloadDocumentLink"\)\.hidden=isPpt/);
assert.match(html, /The presentation opens inside the Presenter/);
assert.match(html, /addMenu\("Docs",docs\.length,"docs-summary-btn"/);
assert.match(html, /addMenu\("Videos",videos\.length,"videos-summary-btn"/);
assert.match(html, /addMenu\("Links",links\.length,"links-summary-btn"/);
assert.match(html, /summary\.innerHTML=""/);

function extractFunction(name) {
  const source = scripts.at(-1);
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} should exist`);
  const bodyStart = source.indexOf("{", start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}" && --depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`Could not extract ${name}`);
}

eval(extractFunction("cleanDocumentUrl"));
eval(extractFunction("normalizedExternalUrl"));
eval(extractFunction("documentPreviewUrl"));
eval(extractFunction("videoSource"));

assert.equal(
  cleanDocumentUrl('<iframe src="https://tenant.sharepoint.com/embed.aspx?id=1&amp;web=1"></iframe>'),
  "https://tenant.sharepoint.com/embed.aspx?id=1&web=1"
);
assert.equal(documentPreviewUrl("https://cdn.example.com/guide.pdf", "PDF"), "https://cdn.example.com/guide.pdf");
assert.match(documentPreviewUrl("https://cdn.example.com/deck.pptx", "PPT"), /^https:\/\/view\.officeapps\.live\.com\/op\/embed\.aspx\?src=/);
const sharePointPdf = documentPreviewUrl("https://tenant.sharepoint.com/:b:/r/sites/demo/guide.pdf?download=1", "PDF");
assert.match(sharePointPdf, /web=1/);
assert.doesNotMatch(sharePointPdf, /download=/);
assert.equal(documentPreviewUrl("cdn.example.com/guide.pdf", "PDF"), "https://cdn.example.com/guide.pdf");
assert.deepEqual(videoSource("https://cdn.example.com/demo.mp4"), { url: "https://cdn.example.com/demo.mp4", direct: true });
assert.match(videoSource("https://youtu.be/abc123").embed, /youtube\.com\/embed\/abc123/);
assert.match(videoSource("tenant.sharepoint.com/sites/demo/video").embed, /web=1/);
assert.equal(videoSource("https://tenant.sharepoint.com/sites/demo/video.mp4").direct, undefined);
assert.deepEqual(videoSource("/presenter-media/demo.mp4"), { url: "/presenter-media/demo.mp4", direct: true });
assert.equal(documentPreviewUrl("/presenter-media/guide.pdf", "PDF"), "/presenter-media/guide.pdf");

console.log("Presenter document URL checks passed.");
