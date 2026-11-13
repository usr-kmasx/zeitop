"use strict";
// Standalone WebKit-compatible DOM harness (no npm dependencies).
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const assert = require("assert");
const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "ui/index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "ui/style.css"), "utf8");
const source = fs.readFileSync(path.join(root, "ui/main.js"), "utf8");
assert.match(html, /class="target-label">FPS<\/span>/);
assert.match(html, /id="source-fps"/);
assert.match(html, /id="output-fps"/);
assert.match(html, /id="fps-output" hidden/);
assert.doesNotMatch(html, /class="target-label">TARGET<\/span>/);
assert.match(html, /33\.33 MS · TARGET/, "retain graph's frame-time target");
assert.match(css, /\.fps-output\[hidden\]\{display:none\}/);
const elements = new Map();
function makeElement() {
  const element = {
    textContent: "", title: "", style: {}, hidden: false,
    classList: {toggle() {}, add() {}, remove() {}},
    addEventListener() {},
    setAttribute() {},
    getContext() {
      return {
        clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {},
        stroke() {}, setLineDash() {}, arc() {}, fill() {},
      };
    },
  };
  return element;
}
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, makeElement());
    return elements.get(id);
  },
  addEventListener() {},
};
const window = {getSelection() {return {removeAllRanges() {}};}};
vm.runInNewContext(source, {
  document, window, console, setTimeout() {return 1;}, clearTimeout() {},
});
const get = (name) => document.getElementById(name);
window.zeitopUpdate({connected:true, fgEnabled:false, fgAvailable:true, sourceFps:29.79, outputFps:59.59});
assert.equal(get("source-fps").textContent, "30");
assert.equal(get("output-fps").textContent, "60");
assert.equal(get("fps-output").hidden, true, "output must be hidden when FG OFF");
window.zeitopUpdate({fgEnabled:true});
assert.equal(get("fps-output").hidden, false);
assert.equal(get("source-fps").textContent, "30");
assert.equal(get("output-fps").textContent, "60");
window.zeitopUpdate({outputFps:null});
assert.equal(get("output-fps").textContent, "--", "must not fabricate generated FPS");
window.zeitopUpdate({fgEnabled:false, connected:false, sourceFps:null});
assert.equal(get("fps-output").hidden, true);
assert.equal(get("source-fps").textContent, "--");
console.log("FPS DOM controls OK");
