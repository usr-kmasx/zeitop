"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const path = require("path");
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "ui", "main.js"), "utf8");
const css = fs.readFileSync(path.join(root, "ui", "style.css"), "utf8");
const callbacks = {};
const makeElement = () => ({
  textContent: "", style: {}, title: "",
  classList: { add() {}, remove() {}, toggle() {} },
  addEventListener(type, callback) { this["on_" + type] = callback; },
  setAttribute() {}, getContext() { return { clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, setLineDash() {} }; }
});
const elements = new Map();
const document = {
  getElementById(id) {
    if(!elements.has(id)) elements.set(id,makeElement());
    return elements.get(id);
  },
  addEventListener(name,callback) { callbacks[name] = callback; }
};
const window = { getSelection() { return { removeAllRanges() {} }; } };
vm.runInNewContext(source,{document,window,console, setTimeout(){return 1;}, clearTimeout(){}});
assert.ok(callbacks.contextmenu, "contextmenu must be blocked");
assert.ok(callbacks.keydown, "Ctrl+A must be blocked");
function evt(attrs = {}) {
  return Object.assign({
    defaultPrevented:false,
    preventDefault(){this.defaultPrevented=true;},
    stopPropagation(){},
  }, attrs);
}
const context = evt({button:2});
callbacks.contextmenu(context);
assert.ok(context.defaultPrevented, "right click contextmenu must be canceled");
const select = evt({key:"a",ctrlKey:true});
callbacks.keydown(select);
assert.ok(select.defaultPrevented, "Ctrl+A must be canceled");
const ordinary = evt({key:"a",ctrlKey:false});
callbacks.keydown(ordinary);
assert.equal(ordinary.defaultPrevented,false,"ordinary keys should be unaffected");
assert.match(css, /user-select\s*:\s*none/, "CSS must disable text selection");
assert.match(css, /cursor\s*:\s*grab/, "ZeiTop must advertise draggability");
console.log("UI guards OK");
