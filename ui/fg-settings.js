(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let configuration = null;
  let selected = 0;
  let dirty = false;
  let busy = false;
  let noticeTimer = null;

  function post(action, extra = {}) {
    const handler = window.webkit?.messageHandlers?.zeitopSettings;
    if (handler) handler.postMessage(JSON.stringify({ action, ...extra }));
    else notify('Launch the settings window from the Zeitop desktop app.', true);
  }
  function notify(message, error = false) {
    const note = $('notification');
    note.textContent = message;
    note.classList.toggle('error', error);
    note.classList.add('visible');
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => note.classList.remove('visible'), 4200);
  }
  function updateActions() {
    const hasProfile = !!current();
    const validMultiplier = !hasProfile || $('custom-multiplier').checkValidity();
    $('save').disabled = busy || !dirty || !configuration ||
      configuration.profiles.length === 0 || !validMultiplier;
    $('copy-profile').disabled = busy || dirty || !configuration?.exists ||
      !hasProfile || current().source_index == null;
  }
  function changed() {
    dirty = true;
    updateActions();
    $('footer-status').textContent = 'Unsaved changes. Save to edit the original lsfg-vk conf.toml.';
  }
  const activeLabels = (value) => Array.isArray(value) ? value.join(', ') : (value || '');
  const current = () => configuration?.profiles[selected] || null;
  function renderProfiles() {
    const list = $('profile-list');
    list.replaceChildren();
    if (!configuration) return;
    configuration.profiles.forEach((profile, index) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'profile-option' + (index === selected ? ' selected' : '');
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(index === selected));
      item.textContent = profile.name || 'Unnamed profile';
      item.addEventListener('click', () => {
        selected = index;
        $('profile-command-panel').hidden = true;
        render();
        if (!dirty) {
          $('footer-status').textContent =
            'Selected "' + profile.name + '" for editing. Copy for Steam to use it at the next game launch.';
        }
      });
      list.appendChild(item);
    });
    $('duplicate-profile').disabled = !current();
    $('remove-profile').disabled = !current();
  }
  function renderProfile() {
    const profile = current();
    $('profile-fields').hidden = !profile;
    $('empty-profile').hidden = !!profile;
    if (!profile) return;
    $('profile-name').value = profile.name || '';
    $('custom-multiplier').value = String(profile.multiplier ?? 2);
    $('active-in').value = activeLabels(profile.active_in);
    $('pacing-mode').value = profile.pacing_mode || 'vsync';
    $('flow-scale').value = String(profile.flow_scale ?? 1);
    $('flow-value').textContent = Number(profile.flow_scale ?? 1).toFixed(2);
    $('performance-mode').checked = !!profile.performance_mode;
    $('override-present-mode').checked = profile.override_present_mode !== false;
    $('preserve-image-count').checked = !!profile.preserve_swapchain_image_count;
    document.querySelectorAll('[data-multiplier]').forEach((button) => {
      const selectedValue = Number(button.dataset.multiplier) === Number(profile.multiplier || 2);
      button.classList.toggle('active', selectedValue);
      button.setAttribute('aria-pressed', String(selectedValue));
    });
  }
  function render() {
    if (!configuration) return;
    selected = Math.min(Math.max(0, selected), Math.max(0, configuration.profiles.length - 1));
    $('config-path').value = configuration.path || '';
    $('config-status').textContent = configuration.exists ? 'Detected' : 'Not found — will create on save';
    $('config-status').classList.toggle('missing', !configuration.exists);
    $('dll').value = configuration.global.dll || '';
    $('allow-fp16').checked = configuration.global.allow_fp16 !== false;
    $('log-level').value = configuration.global.log_level || 'info';
    $('log-file').value = configuration.global.log_file || '';
    renderProfiles();
    renderProfile();
    updateActions();
  }
  function newName(base) {
    const names = new Set(configuration.profiles.map((p) => p.name));
    if (!names.has(base)) return base;
    for (let n = 2; n < 999; n++) {
      const candidate = base + ' ' + n;
      if (!names.has(candidate)) return candidate;
    }
    return base + ' (New)';
  }
  function addProfile(from = null) {
    if (!configuration) return;
    if (configuration.profiles.length >= 100) {
      notify('Maximum of 100 profiles.', true);
      return;
    }
    const base = from || {
      source_index: null, name: 'New Profile', active_in: [],
      multiplier: 2, flow_scale: 1.0, performance_mode: false,
      pacing_mode: 'vsync', override_present_mode: true,
      preserve_swapchain_image_count: false,
    };
    const entry = JSON.parse(JSON.stringify(base));
    entry.source_index = null;
    entry.name = newName(from ? from.name + ' Copy' : 'New Profile');
    configuration.profiles.push(entry);
    selected = configuration.profiles.length - 1;
    changed();
    render();
    $('profile-name').focus();
    $('profile-name').select();
  }
  function setField(id, field, mapper = (x) => x, event = 'input') {
    $(id).addEventListener(event, () => {
      const profile = current();
      if (!profile) return;
      profile[field] = mapper($(id));
      changed();
      if (field === 'name') renderProfiles();
      if (field === 'flow_scale') $('flow-value').textContent = Number(profile.flow_scale).toFixed(2);
    });
  }
  $('add-profile').addEventListener('click', () => addProfile());
  $('duplicate-profile').addEventListener('click', () => {
    if (current()) addProfile(current());
  });
  $('remove-profile').addEventListener('click', () => {
    if (!current()) return;
    configuration.profiles.splice(selected, 1);
    selected = Math.min(selected, configuration.profiles.length - 1);
    changed();
    render();
  });
  setField('profile-name', 'name', (input) => input.value);
  setField('active-in', 'active_in', (input) => {
    const names = input.value.split(',').map((x) => x.trim()).filter(Boolean);
    return names.length === 1 ? names[0] : names;
  });
  setField('pacing-mode', 'pacing_mode', (input) => input.value, 'change');
  setField('flow-scale', 'flow_scale', (input) => Number(input.value));
  setField('performance-mode', 'performance_mode', (input) => input.checked, 'change');
  setField('override-present-mode', 'override_present_mode', (input) => input.checked, 'change');
  setField('preserve-image-count', 'preserve_swapchain_image_count', (input) => input.checked, 'change');
  document.querySelectorAll('[data-multiplier]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!current()) return;
      current().multiplier = Number(button.dataset.multiplier);
      changed();
      renderProfile();
    });
  });
  $('custom-multiplier').addEventListener('input', () => {
    const profile = current();
    if (!profile) return;
    const input = $('custom-multiplier');
    const value = Number(input.value);
    if (!input.checkValidity() || !Number.isInteger(value) || value < 1 || value > 1024) {
      $('save').disabled = true;
      return;
    }
    profile.multiplier = value;
    changed();
    document.querySelectorAll('[data-multiplier]').forEach((button) => {
      const active = Number(button.dataset.multiplier) === value;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  });
  $('dll').addEventListener('input', () => {
    if (!configuration) return;
    configuration.global.dll = $('dll').value.trim();
    changed();
  });
  $('allow-fp16').addEventListener('change', () => {
    if (!configuration) return;
    configuration.global.allow_fp16 = $('allow-fp16').checked;
    changed();
  });
  $('log-level').addEventListener('change', () => {
    if (!configuration) return;
    configuration.global.log_level = $('log-level').value;
    changed();
  });
  $('log-file').addEventListener('input', () => {
    if (!configuration) return;
    configuration.global.log_file = $('log-file').value.trim();
    changed();
  });
  $('browse-config').addEventListener('click', () => post('fg_choose_config'));
  $('browse-dll').addEventListener('click', () => post('fg_choose_dll'));
  $('reload').addEventListener('click', () => post('fg_load'));
  $('copy-profile').addEventListener('click', () => {
    const profile = current();
    if (!profile || dirty || busy || !configuration?.exists ||
        profile.source_index == null) {
      notify('Save your changes before using this profile.', true);
      return;
    }
    post('fg_copy_profile', { name: profile.name, revision: configuration.revision });
  });
  $('dismiss-command').addEventListener('click', () => {
    $('profile-command-panel').hidden = true;
  });
  $('fg-close').addEventListener('click', () => post('fg_close'));
  $('save').addEventListener('click', () => {
    if (!configuration || busy || !configuration.profiles.length) return;
    busy = true;
    $('save').disabled = true;
    $('footer-status').textContent = 'Validating changes with lsfg-vk-cli...';
    post('fg_save', { settings: configuration, revision: configuration.revision });
  });

  window.zeitopFgResponse = (message) => {
    switch (message.type) {
      case 'state': {
        configuration = message.state;
        selected = 0;
        busy = false;
        dirty = false;
        $('profile-command-panel').hidden = true;
        render();
        const status = message.status;
        $('footer-status').textContent = status?.cli_available ?
          'lsfg-vk-cli detected. Edits are saved to the original config, not a Zeitop copy.' :
          'lsfg-vk-cli was not found; local TOML validation is available.';
        break;
      }
      case 'saved':
        configuration = message.state;
        busy = false;
        dirty = false;
        render();
        $('footer-status').textContent = message.changed ?
          'Configuration saved. Some changes may require restarting the game.' :
          'No changes to save.';
        notify(message.changed ? 'LSFG-VK configuration validated and saved.' : 'Already up to date.');
        break;
      case 'profile_copied':
        $('profile-command-text').value = message.command || '';
        $('profile-command-panel').hidden = false;
        $('footer-status').textContent =
          'Copied for "' + message.name + '". Paste in Steam Launch Options and restart the game (FG only).';
        notify('Profile launch command copied. Paste it into Steam and restart the game.');
        break;
      case 'picked_dll':
        if (!configuration) return;
        configuration.global.dll = message.path;
        $('dll').value = message.path;
        changed();
        break;
      case 'error':
        busy = false;
        updateActions();
        $('footer-status').textContent = 'Error: ' + (message.message || 'Unknown error');
        notify(message.message || 'Configuration operation failed.', true);
        break;
      default:
        break;
    }
  };
  post('fg_load');
})();
