// Build step for the Margin Notes review tool.
//
// The Claude Artifact publish pipeline stalls on any single upload roughly
// above ~300-500KB. margin_notes.html is one file with a single
// `const DOC = [...]` array holding all manuscript blocks -- if that array
// grows large (e.g. once this paper's real figures are embedded as base64
// images, per its own \todo in main.tex), it can't be published directly
// (confirmed empirically in a sibling project: 5MB/1MB/500KB publishes all
// fail with "upload stalled", 200-300KB publishes work). As of this file's
// last generation, margin_notes.html here is ~146KB with no embedded images,
// so this script is not currently needed -- it's included so it's ready the
// moment content growth requires it, without re-deriving this logic.
//
// This script never needs to be run by hand for normal editing. Edit
// margin_notes.html directly (it's a complete, ordinary single-file HTML
// page you can open in a browser) -- then run this script to regenerate
// dist/, and publish dist/index.html (+ dist/chunks/*.js as `files`) to the
// live artifact. dist/ is generated output: never hand-edit it, it will be
// overwritten the next time this runs.
//
// Usage: node build_chunks.js

const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, 'margin_notes.html');
const distDir = path.join(__dirname, 'dist');
const chunkDir = path.join(distDir, 'chunks');

const html = fs.readFileSync(srcPath, 'utf8');

const docStartMarker = 'const DOC = [';
const docStartIdx = html.indexOf(docStartMarker);
if (docStartIdx === -1) throw new Error('const DOC = [ not found');
const arrayOpenIdx = docStartIdx + docStartMarker.length - 1;

function findMatchingBracket(s, openIdx) {
  let depth = 0, i = openIdx, inString = null;
  for (; i < s.length; i++) {
    const c = s[i];
    if (inString) { if (c === '\\') { i++; continue; } if (c === inString) inString = null; continue; }
    if (c === '"' || c === "'" || c === '`') { inString = c; continue; }
    if (c === '[' || c === '{' || c === '(') depth++;
    else if (c === ']' || c === '}' || c === ')') { depth--; if (depth === 0) return i; }
  }
  throw new Error('no matching bracket found');
}

const arrayCloseIdx = findMatchingBracket(html, arrayOpenIdx);
const inner = html.slice(arrayOpenIdx + 1, arrayCloseIdx);

function splitTopLevelElements(s) {
  const elements = [];
  let depth = 0, inString = null, start = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inString) { if (c === '\\') { i++; continue; } if (c === inString) inString = null; continue; }
    if (c === '"' || c === "'" || c === '`') { inString = c; continue; }
    if (c === '{' || c === '[' || c === '(') { if (depth === 0 && start === null) start = i; depth++; }
    else if (c === '}' || c === ']' || c === ')') { depth--; if (depth === 0 && start !== null) { elements.push(s.slice(start, i + 1)); start = null; } }
  }
  return elements;
}

const elements = splitTopLevelElements(inner);
console.log('found', elements.length, 'top-level DOC elements');

const LARGE_THRESHOLD = 200000;    // elements bigger than this get raw-text-split
const SMALL_GROUP_TARGET = 180000; // target size for grouped small-element chunks
const PART_SIZE = 220000;          // size of each raw-text part for large elements
// All thresholds stay comfortably under the empirically-confirmed
// ~300KB-safe / 500KB-fails publish boundary.

if (!fs.existsSync(distDir)) fs.mkdirSync(distDir, { recursive: true });
if (!fs.existsSync(chunkDir)) fs.mkdirSync(chunkDir, { recursive: true });
for (const f of fs.readdirSync(chunkDir)) fs.unlinkSync(path.join(chunkDir, f));

let chunkFiles = []; // list of filenames in load order
let smallBuf = [];
let smallBufSize = 0;
let chunkIdx = 0;

function flushSmallBuf() {
  if (!smallBuf.length) return;
  const body = 'window.__DOC_CHUNKS = window.__DOC_CHUNKS || [];\nwindow.__DOC_CHUNKS.push([\n' + smallBuf.join(',\n') + '\n]);\n';
  const fname = 'chunk' + (chunkIdx++) + '.js';
  fs.writeFileSync(path.join(chunkDir, fname), body, 'utf8');
  chunkFiles.push({ file: fname, kind: 'small', size: body.length, count: smallBuf.length });
  smallBuf = [];
  smallBufSize = 0;
}

for (const el of elements) {
  const idMatch = el.match(/id:\s*['"`]([^'"`]+)['"`]/);
  const id = idMatch ? idMatch[1] : 'unknown';

  if (el.length > LARGE_THRESHOLD) {
    flushSmallBuf();
    // Split this element's raw text into PART_SIZE-byte parts. All parts of
    // one element share the SAME window.__RAW_<id> variable name -- do not
    // key this per-part, or reconstruction silently truncates to one part.
    const varName = '__RAW_' + id.replace(/[^A-Za-z0-9_]/g, '_');
    const partFiles = [];
    for (let off = 0; off < el.length; off += PART_SIZE) {
      const part = el.slice(off, off + PART_SIZE);
      const body = 'window.' + varName + ' = window.' + varName + ' || [];\nwindow.' + varName + '.push(' + JSON.stringify(part) + ');\n';
      const fname = 'chunk' + (chunkIdx++) + '.js';
      fs.writeFileSync(path.join(chunkDir, fname), body, 'utf8');
      partFiles.push({ file: fname, varName, size: body.length });
    }
    // Final reconstruct+push chunk for this element (tiny).
    const reconstructBody =
      'window.__DOC_CHUNKS = window.__DOC_CHUNKS || [];\n' +
      'window.__DOC_CHUNKS.push([ new Function("return (" + window.' + varName + '.join("") + ")")() ]);\n';
    const fname = 'chunk' + (chunkIdx++) + '.js';
    fs.writeFileSync(path.join(chunkDir, fname), reconstructBody, 'utf8');
    chunkFiles.push({ file: fname, kind: 'large-reconstruct', id, parts: partFiles.length, totalSize: el.length });
    partFiles.forEach(p => chunkFiles.splice(chunkFiles.length - 1, 0, { file: p.file, kind: 'large-part', id, size: p.size }));
  } else {
    smallBuf.push(el);
    smallBufSize += el.length + 2;
    if (smallBufSize >= SMALL_GROUP_TARGET) flushSmallBuf();
  }
}
flushSmallBuf();

console.log('\nwrote', chunkFiles.length, 'chunk files:');
chunkFiles.forEach(c => console.log(' ', c.file, c.kind, c.id || '', c.size || c.totalSize, 'bytes', c.count ? '(' + c.count + ' blocks)' : '', c.parts ? '(' + c.parts + ' parts)' : ''));

const maxSize = Math.max(...chunkFiles.map(c => fs.statSync(path.join(chunkDir, c.file)).size));
console.log('\nmax single chunk file size:', maxSize, 'bytes (must stay well under ~300KB)');

// Build the deploy shell HTML. `before` ends mid-way through the page's
// original single inline <script> block (right before "const DOC = ["), and
// `after` resumes mid-way through that SAME block (right after the old
// array's closing "]"). The chunk-loader <script src> tags are separate
// script elements, so the currently-open script must be closed, the loader
// tags inserted as siblings, then a fresh inline <script> reopened for the
// remainder of `after` (which still ends with the original file's own
// closing </script> tag, unchanged). Splicing the loader tags in WITHOUT
// this close/reopen makes the parser treat them as literal text inside the
// still-open script -- this bit us once already.
const before = html.slice(0, docStartIdx);
const after = html.slice(arrayCloseIdx + 1);

let loaderScripts = '';
for (const c of chunkFiles) {
  loaderScripts += `<script src="chunks/${c.file}"></script>\n`;
}
loaderScripts += '<script>const DOC = [].concat(...window.__DOC_CHUNKS);</script>\n';

const newHtml = before + '</script>\n' + loaderScripts.trimEnd() + '\n<script>' + after;
const outPath = path.join(distDir, 'index.html');
fs.writeFileSync(outPath, newHtml, 'utf8');
console.log('\nwrote shell:', outPath, (fs.statSync(outPath).size / 1024).toFixed(1), 'KB');
console.log('total chunk files:', chunkFiles.length);
console.log('\nTo publish: Artifact action:publish file_path=dist/index.html url=<the live artifact URL>,');
console.log('then one or more follow-up publish calls adding dist/chunks/*.js via `files`');
console.log('(batch a few per call, staying under ~250KB combined per call).');
