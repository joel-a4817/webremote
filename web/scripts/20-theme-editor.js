(() => {
  'use strict';

  const PRESETS = {
    aurora: { name: 'Aurora Reef', a: '#61e7ce', b: '#9e83ff', c: '#79cad9', bg: 'radial-gradient(circle at 18% 12%,rgba(76,220,185,.30),transparent 35%),radial-gradient(circle at 86% 18%,rgba(144,103,244,.29),transparent 37%),linear-gradient(145deg,#0e1b27,#17293a 52%,#25203d)' },
    forest: { name: 'Forest Bloom', a: '#70e59c', b: '#57bcca', c: '#9bd77d', bg: 'radial-gradient(circle at 16% 10%,rgba(85,211,132,.31),transparent 36%),radial-gradient(circle at 84% 18%,rgba(70,173,183,.27),transparent 39%),linear-gradient(145deg,#10231c,#17332b 52%,#20333c)' },
    ember: { name: 'Ember Coast', a: '#ed9168', b: '#d76f9e', c: '#6bc9c3', bg: 'radial-gradient(circle at 17% 11%,rgba(255,122,76,.28),transparent 36%),radial-gradient(circle at 85% 18%,rgba(205,77,145,.27),transparent 39%),linear-gradient(145deg,#261718,#38202b 52%,#24313b)' },
    violet: { name: 'Violet Nebula', a: '#ae8bed', b: '#6ebce5', c: '#d794bc', bg: 'radial-gradient(circle at 18% 12%,rgba(143,96,236,.31),transparent 36%),radial-gradient(circle at 85% 17%,rgba(67,157,229,.28),transparent 39%),linear-gradient(145deg,#17152b,#252042 52%,#1b3040)' },
    glacier: { name: 'Glacier Reef', a: '#71d8e2', b: '#718fdc', c: '#91cf83', bg: 'radial-gradient(circle at 17% 11%,rgba(64,202,222,.31),transparent 36%),radial-gradient(circle at 84% 18%,rgba(80,117,229,.27),transparent 39%),linear-gradient(145deg,#102029,#152d3c 52%,#1e2941)' }
  };
  const STORAGE_THEME = 'webremote-theme-key';
  const STORAGE_CUSTOM = 'webremote-theme-custom';
  const STORAGE_SAVED = 'webremote-saved-themes';
  const $ = selector => document.querySelector(selector);
  const root = document.documentElement;
  const picker = $('#theme-picker-button');
  const menu = $('#theme-picker-menu');
  const label = $('#startup-theme-name');
  const savedList = $('#saved-theme-list');
  const nameInput = $('#theme-save-name');
  let current = null;
  let currentKey = '';

  function loadSaved() {
    try { return JSON.parse(localStorage.getItem(STORAGE_SAVED) || '{}'); }
    catch { return {}; }
  }
  function storeSaved(themes) { localStorage.setItem(STORAGE_SAVED, JSON.stringify(themes)); }
  function slug(name) {
    const base = String(name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'theme';
    const themes = loadSaved();
    let key = base, n = 2;
    while (Object.hasOwn(themes, key)) key = `${base}-${n++}`;
    return key;
  }
  function randomTheme() {
    const h = Math.floor(Math.random() * 360);
    const h2 = (h + 92 + Math.floor(Math.random() * 66)) % 360;
    const h3 = (h + 205 + Math.floor(Math.random() * 64)) % 360;
    return {
      name: `Custom ${h}°`, a: `hsl(${h} 68% 61%)`, b: `hsl(${h2} 64% 62%)`, c: `hsl(${h3} 62% 63%)`,
      bg: `radial-gradient(circle at 17% 11%,hsl(${h} 75% 58% / .30),transparent 36%),radial-gradient(circle at 84% 18%,hsl(${h2} 72% 58% / .27),transparent 39%),linear-gradient(145deg,hsl(${h} 33% 11%),hsl(${h2} 30% 17%) 52%,hsl(${h3} 28% 18%))`
    };
  }
  function apply(theme, key, persist = true) {
    if (!theme) return;
    current = { ...theme };
    currentKey = key;
    const vars = {
      '--ui-a': theme.a, '--ui-b': theme.b, '--ui-c': theme.c, '--ui-bg': theme.bg,
      '--v10-a': theme.a, '--v10-b': theme.b, '--v10-c': theme.c, '--v10-bg': theme.bg,
      '--v8-a': theme.a, '--v8-b': theme.b, '--v8-c': theme.c, '--v8-bg': theme.bg,
      '--pg-teal': theme.a, '--pg-violet': theme.b, '--pg-amber': theme.c,
      '--b': theme.a, '--v': theme.b, '--g': theme.c
    };
    Object.entries(vars).forEach(([name, value]) => root.style.setProperty(name, value));
    root.style.setProperty('--theme-name', JSON.stringify(theme.name));
    root.dataset.theme = key;
    if (label) label.textContent = `Theme · ${theme.name}`;
    document.querySelectorAll('[data-theme-key]').forEach(button => {
      const selected = button.dataset.themeKey === key;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    if (persist) {
      localStorage.setItem(STORAGE_THEME, key);
      localStorage.setItem(STORAGE_CUSTOM, JSON.stringify(theme));
    }
  }
  function closeMenu() {
    menu.hidden = true;
    menu.classList.remove('is-open');
    picker.classList.remove('is-open');
    picker.setAttribute('aria-expanded', 'false');
  }
  function actionButton(labelText, icon, className, ariaLabel) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.innerHTML = `<span aria-hidden="true">${icon}</span><span class="theme-action-label">${labelText}</span>`;
    button.setAttribute('aria-label', ariaLabel);
    return button;
  }
  function renderSaved() {
    if (!savedList) return;
    savedList.replaceChildren();
    const themes = loadSaved();
    for (const [key, theme] of Object.entries(themes)) {
      const row = document.createElement('div');
      row.className = 'saved-theme-row';
      const choose = document.createElement('button');
      choose.type = 'button';
      choose.className = 'saved-theme-select';
      choose.dataset.themeKey = `saved:${key}`;
      choose.textContent = theme.name;
      choose.addEventListener('click', () => { apply(theme, `saved:${key}`); closeMenu(); });

      const rename = actionButton('Rename', '✎', 'saved-theme-rename', `Rename ${theme.name}`);
      rename.addEventListener('click', event => {
        event.preventDefault(); event.stopPropagation();
        row.classList.add('is-editing');
        const input = row.querySelector('.saved-theme-name-input');
        input.value = theme.name; input.focus(); input.select();
      });
      const remove = actionButton('Delete', '×', 'saved-theme-delete destructive', `Delete ${theme.name}`);
      remove.addEventListener('click', event => {
        event.preventDefault(); event.stopPropagation();
        const next = loadSaved(); delete next[key]; storeSaved(next);
        if (currentKey === `saved:${key}`) apply(PRESETS.aurora, 'aurora');
        renderSaved();
      });
      const editor = document.createElement('div');
      editor.className = 'saved-theme-editor';
      const input = document.createElement('input');
      input.className = 'saved-theme-name-input'; input.type = 'text'; input.maxLength = 40; input.setAttribute('aria-label', `New name for ${theme.name}`);
      const commit = actionButton('Save', '✓', 'saved-theme-commit', 'Save theme name');
      const cancel = actionButton('Cancel', '×', 'saved-theme-cancel', 'Cancel rename');
      const finishRename = () => {
        const name = input.value.trim(); if (!name) { input.focus(); return; }
        const next = loadSaved(); if (!next[key]) return;
        next[key] = { ...next[key], name }; storeSaved(next);
        if (currentKey === `saved:${key}`) apply(next[key], currentKey);
        renderSaved();
      };
      commit.addEventListener('click', finishRename);
      cancel.addEventListener('click', () => row.classList.remove('is-editing'));
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') finishRename();
        if (event.key === 'Escape') row.classList.remove('is-editing');
      });
      editor.append(input, commit, cancel);
      row.append(choose, rename, remove, editor);
      savedList.append(row);
    }
  }
  function incrementRange(range) {
    const min = Number(range.min || 0), max = Number(range.max || 100), value = Number(range.value || min);
    const pct = Math.max(0, Math.min(100, ((value - min) / Math.max(1, max - min)) * 100));
    range.style.setProperty('--range-progress', `${pct}%`);
  }
  function initThemes() {
    if (!picker || !menu || !label) return;
    menu.querySelectorAll('[data-theme]').forEach(button => {
      const key = button.dataset.theme; button.dataset.themeKey = key;
      button.addEventListener('click', () => { apply(PRESETS[key], key); closeMenu(); });
    });
    picker.addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation();
      const open = menu.hidden; menu.hidden = !open;
      menu.classList.toggle('is-open', open); picker.classList.toggle('is-open', open);
      picker.setAttribute('aria-expanded', String(open));
    });
    $('#new-random-theme')?.addEventListener('click', () => apply(randomTheme(), 'random'));
    $('#save-current-theme')?.addEventListener('click', () => {
      if (!current) return;
      const name = (nameInput?.value || '').trim(); if (!name) { nameInput?.focus(); return; }
      const themes = loadSaved(); const key = slug(name); themes[key] = { ...current, name };
      storeSaved(themes); nameInput.value = ''; renderSaved(); apply(themes[key], `saved:${key}`);
    });
    document.addEventListener('click', event => { if (!event.target.closest('.theme-picker')) closeMenu(); });
    renderSaved();
    let key = localStorage.getItem(STORAGE_THEME) || 'aurora';
    let theme = PRESETS[key];
    if (key.startsWith('saved:')) theme = loadSaved()[key.slice(6)];
    if (key === 'random') { try { theme = JSON.parse(localStorage.getItem(STORAGE_CUSTOM) || 'null'); } catch {} }
    if (!theme) { key = 'aurora'; theme = PRESETS.aurora; }
    apply(theme, key, false);
  }
  function initRanges() {
    const ranges = [...document.querySelectorAll('input[type="range"]')];
    ranges.forEach(range => {
      incrementRange(range);
      range.addEventListener('input', () => incrementRange(range));
      range.addEventListener('change', () => incrementRange(range));
    });
    setInterval(() => ranges.forEach(incrementRange), 500);
  }
  initThemes(); initRanges();
})();
