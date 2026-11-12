'use strict';
// Minimal DOM harness for the actual settings script, no browser dependency.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');

class Element {
  constructor(id = '') {
    this.id = id;
    this.disabled = false;
    this.hidden = false;
    this.value = '';
    this.checked = false;
    this.textContent = '';
    this.children = [];
    this.dataset = {};
    this.handlers = {};
    this.classSet = new Set();
    this.classList = {
      add: x => this.classSet.add(x),
      contains: x => this.classSet.has(x),
      toggle: (x, on) => {
        if (on === undefined) on = !this.classSet.has(x);
        if (on) this.classSet.add(x);
        else this.classSet.delete(x);
      },
    };
  }
  setAttribute(k, v) { this[k] = v; }
  addEventListener(ev, fn) { this.handlers[ev] = fn; }
  click() { if (this.handlers.click) this.handlers.click(); }
  replaceChildren(...els) { this.children = [...els]; }
  appendChild(el) { this.children.push(el); }
  checkValidity() { return true; }
  focus() {}
  select() {}
}

const map = new Map();
function get(id) {
  if (!map.has(id)) map.set(id, new Element(id));
  return map.get(id);
}
const multipliers = [2, 3, 4].map(n => {
  const item = new Element();
  item.dataset.multiplier = String(n);
  return item;
});
const messages = [];
const window = {
  webkit: {messageHandlers: {zeitopSettings: {
    postMessage: text => messages.push(JSON.parse(text)),
  }}},
};
const document = {
  getElementById: get,
  createElement: () => new Element(),
  querySelectorAll: selector => selector === '[data-multiplier]' ? multipliers : [],
};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../ui/fg-settings.js'), 'utf8'), {
  window, document, setTimeout: () => 1, clearTimeout: () => {},
});

assert.equal(messages.pop().action, 'fg_load');
const state = {
  path: '/tmp/original/conf.toml', exists: true, revision: 'some-revision',
  global: {dll:'',allow_fp16:true,log_level:'info',log_file:''},
  profiles: [
    {name:'4x Profile',source_index:0,multiplier:4,flow_scale:0.85,
      active_in:['vkcube'],performance_mode:true,pacing_mode:'vsync'},
    {name:'2x Profile',source_index:1,multiplier:2,flow_scale:1.0,
      active_in:'Game.exe',performance_mode:false,pacing_mode:'vsync'},
  ],
};
function highlighted() {
  return get('profile-list').children.findIndex(x => x.className?.split(' ').includes('selected'));
}
window.zeitopFgResponse({type:'state',state,selectedProfile:'2x Profile',status:{}});
assert.equal(highlighted(), 1, 'saved profile should restore highlight');
assert.equal(get('save').disabled, true, 'initial load cannot be dirty');
assert.equal(get('profile-name').value,'2x Profile');

get('profile-list').children[0].click();
assert.equal(highlighted(), 0);
assert.equal(get('save').disabled,false,'changing profile should enable Save');
get('save').click();
assert.equal(messages.at(-1).action, 'fg_save');
assert.equal(messages.at(-1).selected_profile,'4x Profile');
assert.equal(messages.at(-1).revision,state.revision);
window.zeitopFgResponse({type:'saved',state,selectedProfile:'4x Profile',changed:true});
assert.equal(get('save').disabled,true);
assert.equal(highlighted(),0);

// New settings window and Reload must select the persisted preference.
window.zeitopFgResponse({type:'state',state,selectedProfile:'4x Profile',status:{}});
assert.equal(highlighted(),0);
assert.equal(get('save').disabled,true);
get('profile-list').children[1].click();
assert.equal(get('save').disabled,false);
get('reload').click();
assert.equal(messages.at(-1).action,'fg_load');
window.zeitopFgResponse({type:'state',state,selectedProfile:'4x Profile',status:{}});
assert.equal(highlighted(),0,'reload must discard unsaved selection');

// First-time users can save even the default first row.
window.zeitopFgResponse({type:'state',state,selectedProfile:null,status:{}});
assert.equal(highlighted(),0);
assert.equal(get('save').disabled,true);
get('profile-list').children[0].click();
assert.equal(get('save').disabled,false,'clicking first row should permit explicit selection');
get('save').click();
assert.equal(messages.at(-1).selected_profile,'4x Profile');
console.log('DOM profile selection/save/reopen/reload behavior verified');
