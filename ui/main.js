(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const power = $('toggle');
  const fgPower = $('fg-toggle');
  const canvas = $('graph');
  const ctx = canvas.getContext('2d');
  const state = {enabled:false,connected:false,samples:[],real:null,average:null,target:33.333333};
  let timeout = null;
  function post(action) {
    const handler = window.webkit?.messageHandlers?.zeitop;
    if (handler) handler.postMessage(JSON.stringify({action}));
    else zeitopNotice('Run Zeitop as a desktop app');
  }
  power.addEventListener('click', () => post('toggle'));
  fgPower.addEventListener('click', () => post('toggle_fg'));
  $('copy').addEventListener('click', () => post('copy'));
  $('settings').addEventListener('click', () => post('settings'));
  $('close').addEventListener('click', () => post('close'));

  // The WebView is an app UI, not a selectable web page.
  // Capture early so WebKit does not open a context menu or select text.
  document.addEventListener('contextmenu', (event) => {
    event.preventDefault();
    event.stopPropagation();
  }, true);
  document.addEventListener('selectstart', (event) => event.preventDefault(), true);
  document.addEventListener('dragstart', (event) => event.preventDefault(), true);
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key?.toLowerCase() === 'a') {
      event.preventDefault();
      window.getSelection()?.removeAllRanges();
    }
  }, true);

  window.zeitopNotice = (message) => {
    const toast = $('toast');
    toast.textContent = message;
    toast.classList.add('show');
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => toast.classList.remove('show'), 1600);
  };
  const metric = (n) => Number.isFinite(n) ? n.toFixed(2) : '--.--';
  function draw() {
    const w = canvas.width, h = canvas.height, target = state.target;
    ctx.clearRect(0,0,w,h);
    const valid = state.samples.filter((n) => Number.isFinite(n) && n > 0);
    const max = Math.max(target * 1.5, ...valid);
    const min = Math.max(0, Math.min(target * 0.5, ...(valid.length ? valid : [target])));
    const y = (value) => h - 7 - (value-min) / Math.max(0.1,max-min) * (h-13);
    const baseY = y(target);
    ctx.strokeStyle='#27353b';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(0,h-8);ctx.lineTo(w,h-8);ctx.stroke();
    ctx.setLineDash([3,5]);ctx.strokeStyle='#3a654f';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(0,baseY);ctx.lineTo(w,baseY);ctx.stroke();ctx.setLineDash([]);
    if (valid.length < 2) {
      ctx.beginPath();ctx.moveTo(0,baseY);ctx.lineTo(w,baseY);
      ctx.lineWidth=1.7;ctx.strokeStyle='#37cf85';ctx.stroke();
      return;
    }
    const length = valid.length;
    const x = (i) => i * w / (Math.max(1,length-1));
    for(let i=1;i<length;i++){
      const sample = valid[i];
      const color=sample<=34.5?'#42e39a':sample<=40?'#f4c95c':'#ff6b76';
      ctx.beginPath();ctx.moveTo(x(i-1),y(valid[i-1]));ctx.lineTo(x(i),y(sample));
      ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineCap='round';ctx.lineJoin='round';ctx.stroke();
    }
    ctx.beginPath();ctx.arc(x(length-1),y(valid[length-1]),2.8,0,Math.PI*2);
    ctx.fillStyle=valid[length-1]<=34.5?'#42e39a':valid[length-1]<=40?'#f4c95c':'#ff6b76';ctx.fill();
  }
  window.zeitopUpdate=(next)=>{
    Object.assign(state,next);
    power.classList.toggle('active',!!state.enabled);
    power.setAttribute('aria-label',state.enabled?'Disable limiter':'Enable limiter');
    power.title=state.enabled?'Disable limiter':'Enable limiter';
    fgPower.classList.toggle('active', !!state.fgEnabled);
    fgPower.classList.toggle('unavailable', !state.fgAvailable);
    fgPower.setAttribute('aria-pressed', String(!!state.fgEnabled));
    fgPower.setAttribute('aria-label', state.fgEnabled?'Disable lsfg-vk':'Enable lsfg-vk');
    fgPower.title = state.fgAvailable ?
      (state.fgEnabled?'Disable FG (next game launch)':'Enable FG (next game launch)') :
      'lsfg-vk unavailable';
    const real=$('real'), avg=$('average');
    real.textContent=metric(state.real);
    avg.textContent=metric(state.average);
    real.style.color=Number.isFinite(state.real)?(state.real<=34.5?'#55e7a5':state.real<=40?'#efc568':'#fa7980'):'#ecedef';
    $('connected').textContent=state.connected?'GAME CONNECTED':'WAITING FOR GAME';
    $('live-dot').classList.toggle('online',!!state.connected);
    draw();
  };
  draw();
})();
