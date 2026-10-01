#!/usr/bin/env node
// Run the JS actually served by a local page against a stub DOM, print the shell
// command it generates, and save that command so it can be executed verbatim.
//
//   node page_command_harness.js page.html tick.json out.sh
//
// page.html : output of `curl -s -u "$USER:$PASS" http://127.0.0.1:<port>/`
// tick.json : JSON array of absolute paths to mark as ticked (values as served in
//             data-p; percent-encoded entries are decoded for you)
// out.sh    : where the generated command is written (one shell command, possibly
//             spanning lines with trailing backslashes)
//
// Page contract: a <script> defining upd(), checkbox inputs class="pk" carrying
// data-p (absolute path) and data-s (size), a #cmdwrap container and a #cmd textarea.
// Rename the ids below for a page that uses different ones.
const fs = require('fs');
const [htmlPath, tickJson, outPath] = process.argv.slice(2);
if (!htmlPath || !tickJson || !outPath) {
  console.error('usage: node page_command_harness.js page.html tick.json out.sh');
  process.exit(2);
}
const html = fs.readFileSync(htmlPath, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) throw new Error('no <script> block in the page');
const js = m[1];
const tick = JSON.parse(fs.readFileSync(tickJson, 'utf8')).map(decodeURIComponent);

// data-p is HTML-escaped in the served markup; undo exactly those entities.
const unesc = s => s.replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
  .replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&amp;/g, '&');
const attrs = [...html.matchAll(/data-p="([^"]*)"/g)].map(x => unesc(x[1]));
const sizes = [...html.matchAll(/data-p="[^"]*"\s+data-s="(\d+)"/g)].map(x => x[1]);
if (!attrs.length) throw new Error('no data-p attributes: wrong page, or the feature flag is off');
if (attrs.length !== sizes.length) throw new Error('markup mismatch: data-p/data-s counts differ');

const inputs = attrs.map((p, i) => ({checked: tick.includes(p), dataset: {p, s: sizes[i]}}));
// one fake row per input, pick cell first, so the pick column reads as present
const rows = inputs.map((inp, i) => ({
  dataset: {n: 'r' + i},
  style: {},                              // filter code writes r.style.display
  cells: [{dataset: {}}, {dataset: {v: 'r' + i}}, {dataset: {v: '1'}}, {dataset: {v: '2'}}],
}));
const el = {cmd: {value: '', focus() {}, select() {}}, cmdwrap: {hidden: true},
            nsel: {textContent: ''}, szsel: {textContent: ''}, all: {checked: false}};

global.document = {
  querySelector: s => (s === 'th.pick' ? {} : {rows, dataset: {}, appendChild() {}}),
  querySelectorAll: s => (s === 'input.pk:checked' ? inputs.filter(i => i.checked)
                        : s === 'input.pk' ? inputs : rows),
  getElementById: id => el[id],
  execCommand: () => true,
};
// node >= 18 defines `navigator` as a getter-only global: a plain assignment silently
// no-ops and the code under test takes its execCommand fallback branch instead.
Object.defineProperty(global, 'navigator', {
  configurable: true, writable: true,
  value: {clipboard: {writeText(t) { global.__copied = t; }}},
});

eval(js);                                 // run the page's own script
upd();
console.log('ticked:', el.nsel.textContent, '|', el.szsel.textContent,
            '| box hidden:', el.cmdwrap.hidden);
if (el.cmdwrap.hidden) {
  throw new Error('nothing ticked - check that tick.json paths match the data-p values');
}
fs.writeFileSync(outPath, el.cmd.value + '\n');
console.log('--- generated command ---\n' + el.cmd.value);
console.log('\nnext: run it against a scratch sandbox and diff the file list; run it on\n' +
            '      the real tree only if that is what you mean to do.');
