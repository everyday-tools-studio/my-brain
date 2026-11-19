'use strict';
const $ = (id) => document.getElementById(id);
const bridge = window.Android;
const views = {
  inbox: ['Boîte de réception', 'inbox'],
  note: ['Notes', 'note'],
  task: ['Tâches', 'task'],
  event: ['Agenda', 'event'],
  review: ['À confirmer', 'review'],
};
const kinds = { note: 'Note', task: 'Tâche', event: 'Rendez-vous', review: 'À confirmer' };
const drawings = {
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0a8 8 0 0 1 16 0',
  inbox: 'M3 14l3-9h12l3 9v5H3z M3 14h5l2 3h4l2-3h5',
  note: 'M5 3h14v13l-5 5H5z M14 21v-5h5 M8 8h8 M8 12h6',
  task: 'M7 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7 M7 11l3 3 9-10',
  event: 'M3 6h18v15H3z M3 10h18 M7 3v6 M17 3v6 M7 14h3 M14 14h3',
  review: 'M12 3a9 9 0 1 0 .01 0 M12 7v6l4 2',
  pin: 'M8 3h8l-1 5 4 4v2H5v-2l4-4z M12 14v7',
  mic: 'M9 6a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0z M5 11v1a7 7 0 0 0 14 0v-1 M12 19v3 M9 22h6',
  plus: 'M12 5v14 M5 12h14',
  left: 'M15 5l-7 7 7 7',
  right: 'M9 5l7 7-7 7',
  close: 'M5 5l14 14 M19 5L5 19',
  send: 'M3 4l19 8-19 8 4-8z M7 12h14',
  done: 'M4 12l5 5L20 6',
  undo: 'M3 5v6h6 M3 11a8 8 0 1 1 2 8',
  settings: 'M3 6h18 M3 18h18 M8 3v6 M16 15v6',
  sync: 'M4 11a8 8 0 0 1 14-5l2 3 M20 3v6h-6 M20 13a8 8 0 0 1-14 5l-2-3 M4 21v-6h6',
};
function node(tag, cls, content) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (content !== undefined) el.textContent = content;
  return el;
}
function icon(name) {
  const ns = 'http://www.w3.org/2000/svg',
    svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', drawings[name] || '');
  svg.append(path);
  return svg;
}
document.querySelectorAll('[data-icon]').forEach((el) => el.append(icon(el.dataset.icon)));
const state = {
  items: [],
  view: 'inbox',
  month: new Date(),
  day: null,
  loaded: false,
  editing: null,
  provider: null,
  serial: 0,
};
let pendingAudio = '',
  recorder = null,
  recordingTimer,
  statusTimer;
function alertUser(message, error = false) {
  const dialog =
    document.querySelector('dialog[open]:last-of-type') ||
    Array.from(document.querySelectorAll('dialog[open]')).pop();
  if (dialog && error) {
    let box = dialog.querySelector('.dialog-error');
    if (!box) {
      box = node('p', 'dialog-error');
      box.setAttribute('role', 'alert');
      dialog.append(box);
    }
    box.textContent = message;
    return;
  }
  $('status').textContent = message;
  $('status').hidden = false;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(
    () => {
      $('status').hidden = true;
    },
    error ? 12000 : 4200
  );
}
async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const response = await fetch('/api/' + path, { cache: 'no-store', ...options });
  const result = await response.json();
  if (!response.ok || result.error) {
    const message =
      response.status === 409
        ? 'Cet élément a changé. Fermez puis rouvrez sa fiche pour retrouver la dernière version.'
        : result.error || 'Le service local ne répond pas.';
    throw new Error(message);
  }
  return result;
}
function unpack(raw) {
  const value = JSON.parse(raw);
  if (value.error) throw new Error(value.error);
  return value;
}
async function reload() {
  const serial = ++state.serial;
  try {
    const data = bridge ? unpack(bridge.listItems()) : await api('items?audio=summary');
    if (serial !== state.serial) return;
    state.items = data.items.filter((i) => !i.deleted);
    if (!bridge) state.items.reverse();
    state.loaded = true;
    if (bridge) $('sync-status').textContent = bridge.getStatus();
    render();
  } catch (error) {
    alertUser(error.message, true);
  }
}
async function save(item) {
  const result = bridge ? unpack(bridge.saveItem(JSON.stringify(item))) : await api('items', item);
  await reload();
  return result.item;
}
function blank(kind = 'note') {
  return {
    id: crypto.randomUUID(),
    rev: 0,
    kind,
    title: '',
    body: '',
    when: '',
    done: false,
    pinned: false,
    source: '',
    audio: '',
    deleted: false,
  };
}
function localInput(iso) {
  const d = new Date(iso);
  if (!iso || !Number.isFinite(+d)) return '';
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function dateDisplay(iso) {
  const d = new Date(iso);
  return iso && Number.isFinite(+d)
    ? d.toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
    : '';
}
const normalize = (s) =>
  (s || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('fr');
function setView(key) {
  state.view = views[key] ? key : 'inbox';
  state.day = null;
  $('query').value = '';
  render();
}
function navigate(key) {
  if (location.hash !== '#' + key) location.hash = key;
  else setView(key);
}
function render() {
  const { items, view } = state;
  const query = normalize($('query').value.trim());
  $('heading').textContent = query ? 'Recherche' : views[view][0];
  $('today').textContent = new Date().toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  const nav = $('navigation');
  nav.replaceChildren();
  for (const [key, [label, symbol]] of Object.entries(views)) {
    const btn = node('button', key === view && !query ? 'active' : '');
    btn.append(icon(symbol), node('span', '', label));
    if (key === view && !query) btn.setAttribute('aria-current', 'page');
    if (key === 'review') {
      const n = items.filter((i) => i.kind === 'review').length;
      if (n) btn.append(node('span', 'counter', n));
    }
    btn.onclick = () => navigate(key);
    nav.append(btn);
  }
  $('composer').hidden = query || view !== 'inbox';
  $('calendar').hidden = query || view !== 'event';
  if (!$('calendar').hidden) renderMonth();
  $('list-title').textContent = query
    ? 'Résultats'
    : {
        inbox: 'Derniers éléments',
        event: state.day ? 'Rendez-vous du jour' : 'Rendez-vous du mois',
        note: 'Toutes les notes',
        task: 'Toutes les tâches',
        review: 'Éléments à vérifier',
      }[view];
  $('create').hidden = query || !['event', 'task', 'note'].includes(view);
  const matches = items.filter((i) => {
    if (query)
      return [i.title, i.body, i.source, dateDisplay(i.when)].some((s) => normalize(s).includes(query));
    if (view === 'event') {
      const day = localInput(i.when).slice(0, 10);
      return i.kind === view && day.startsWith(state.day || monthPrefix());
    }
    return view === 'inbox' || i.kind === view;
  });
  if (view === 'event' && !query) matches.sort((a, b) => new Date(a.when) - new Date(b.when));
  if (view === 'task' && !query) matches.sort((a, b) => Number(a.done) - Number(b.done));
  const list = $('items');
  list.replaceChildren();
  for (const item of matches) list.append(row(item));
  if (!matches.length)
    list.append(
      node(
        'p',
        'empty',
        state.loaded
          ? query
            ? 'Aucun résultat pour cette recherche.'
            : {
                inbox: 'Vos premières captures apparaîtront ici.',
                note: 'Aucune note pour le moment.',
                task: 'Aucune tâche pour le moment.',
                event: 'Aucun rendez-vous sur cette période.',
                review: 'Tout est à jour.',
              }[view]
          : 'Chargement…'
      )
    );
  const focus = items.find((i) => i.kind === 'task' && i.pinned && !i.done);
  const panel = $('focus');
  panel.replaceChildren();
  const focusCard = panel.parentElement;
  if (matchMedia('(max-width:660px)').matches && focus && !query && view === 'inbox') {
    $('composer').after(focusCard);
    focusCard.classList.add('mobile-focus');
  } else {
    document.querySelector('aside').prepend(focusCard);
    focusCard.classList.remove('mobile-focus');
  }
  if (focus) {
    const b = node('button', '', focus.title);
    b.onclick = () => openEditor(focus);
    panel.append(b);
    if (focus.body && focus.body !== focus.title) panel.append(node('p', 'next-step', focus.body));
  } else panel.append(node('p', '', 'Épinglez une tâche pour retrouver votre prochain geste ici.'));
  const next = items
    .filter((i) => i.kind === 'event' && new Date(i.when) >= new Date())
    .sort((a, b) => new Date(a.when) - new Date(b.when))[0];
  const upcoming = $('upcoming');
  upcoming.replaceChildren();
  if (next) {
    const b = node('button', '', next.title);
    b.onclick = () => openEditor(next);
    upcoming.append(b, node('p', 'muted', dateDisplay(next.when)));
  } else upcoming.append(node('p', 'muted', 'Aucun rendez-vous à venir.'));
}
function row(item) {
  const container = node('div', 'item' + (item.done ? ' done' : ''));
  const btn = node('button', 'item-open');
  const badge = node('span', 'kind-icon ' + item.kind);
  badge.append(icon(item.kind));
  let meta = kinds[item.kind] || 'Élément';
  if (item.pinned) meta += ' · Épinglée';
  if (item.when) meta += ' · ' + dateDisplay(item.when);
  else if (item.audio || item.hasAudio) meta += ' · Mémo vocal';
  else if (item.source) meta += ' · ' + item.source.split('\n')[0].slice(0, 80);
  const summary = node('span', 'summary');
  summary.append(node('strong', '', item.title), node('small', '', meta));
  btn.append(badge, summary);
  btn.onclick = () => openEditor(item);
  container.append(btn);
  if (item.kind === 'task') {
    const t = node('button', 'icon-button toggle');
    t.append(icon(item.done ? 'undo' : 'done'));
    t.title = t.ariaLabel = item.done ? 'Rouvrir la tâche' : 'Marquer comme terminée';
    t.onclick = async () => {
      t.disabled = true;
      try {
        const full = await fullItem(item);
        await save({ ...full, done: !item.done, pinned: false });
      } catch (e) {
        alertUser(e.message, true);
        await reload();
      } finally {
        t.disabled = false;
      }
    };
    container.append(t);
  }
  return container;
}
function monthPrefix() {
  return state.month.getFullYear() + '-' + String(state.month.getMonth() + 1).padStart(2, '0');
}
function renderMonth() {
  const year = state.month.getFullYear(),
    month = state.month.getMonth(),
    grid = $('month-grid');
  grid.replaceChildren();
  $('month').textContent = state.month.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  for (const day of ['L', 'M', 'M', 'J', 'V', 'S', 'D']) grid.append(node('small', '', day));
  const start = new Date(year, month, 1);
  for (let n = 0; n < (start.getDay() + 6) % 7; n++) grid.append(node('span'));
  const dates = new Set(
    state.items.filter((i) => i.kind === 'event').map((i) => localInput(i.when).slice(0, 10))
  );
  for (let n = 1; n <= new Date(year, month + 1, 0).getDate(); n++) {
    const day = monthPrefix() + '-' + String(n).padStart(2, '0');
    const b = node('button', '', n);
    if (day === localInput(new Date()).slice(0, 10)) b.classList.add('today');
    if (day === state.day) b.classList.add('selected');
    if (dates.has(day)) b.classList.add('has-events');
    b.ariaLabel =
      new Date(year, month, n).toLocaleDateString('fr-FR', { dateStyle: 'full' }) +
      (dates.has(day) ? ', avec rendez-vous' : '');
    b.onclick = () => {
      state.day = state.day === day ? null : day;
      render();
    };
    grid.append(b);
  }
  $('reset-day').hidden = !state.day;
}
for (const [id, step] of [
  ['prev', -1],
  ['next', 1],
])
  $(id).onclick = () => {
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() + step, 1);
    state.day = null;
    render();
  };
$('reset-day').onclick = () => {
  state.day = null;
  render();
};
function showDialog(el) {
  el.querySelector('.dialog-error')?.remove();
  el.showModal();
}
document
  .querySelectorAll('[data-close]')
  .forEach((btn) => (btn.onclick = () => btn.closest('dialog').close()));
function onKind() {
  const k = $('kind').value;
  $('time-label').hidden = !['event', 'task'].includes(k);
  $('when').required = k === 'event';
  $('pin-field').hidden = k !== 'task' || Boolean(state.editing?.done);
  $('body-label').textContent =
    k === 'task'
      ? 'Prochain geste ou détails'
      : state.editing?.audio
        ? 'Transcription et notes'
        : 'Contenu';
}
function player(url) {
  const a = node('audio');
  a.controls = true;
  a.preload = 'none';
  a.src = url;
  return a;
}
async function fullItem(item) {
  if (!item.hasAudio || item.audio) return item;
  const result = bridge
    ? unpack(bridge.getItem(item.id))
    : await api('item?id=' + encodeURIComponent(item.id));
  if (result.item.rev !== item.rev) throw new Error('Cet élément a changé. Actualisez la liste.');
  return result.item;
}
let openingEditor = 0;
async function openEditor(item) {
  const sequence = ++openingEditor;
  try {
    item = await fullItem(item);
  } catch (e) {
    alertUser(e.message, true);
    await reload();
    return;
  }
  if (sequence !== openingEditor) return;
  state.editing = { ...item };
  $('kind').value = item.kind;
  $('title').value = item.title;
  $('body').value = item.body || '';
  $('pinned').checked = Boolean(item.pinned);
  $('when').value = localInput(item.when);
  // A review can be confirmed by filling the missing date directly.
  if (item.kind === 'review') $('kind').value = 'event';
  $('edit-heading').textContent =
    !item.rev && !state.items.some((i) => i.id === item.id)
      ? 'Nouvel élément'
      : item.kind === 'review'
        ? 'Confirmer le rendez-vous'
        : 'Modifier l’élément';
  $('commit').textContent = item.kind === 'review' ? 'Confirmer' : 'Enregistrer';
  $('remove').hidden = !state.items.some((i) => i.id === item.id);
  $('analysis-result').hidden = true;
  $('analysis-result').textContent = '';
  const src = $('source');
  src.replaceChildren();
  if (item.source) {
    const d = node('details', 'source');
    const s = node('summary', '', 'Message d’origine');
    d.append(s, node('p', '', item.source));
    src.append(d);
  }
  const media = $('media');
  media.replaceChildren();
  if (item.audio && item.audio.startsWith('data:audio/')) {
    media.append(player(item.audio));
    if (!bridge) {
      const t = node('button', 'soft', 'Transcrire sur ce PC');
      t.type = 'button';
      t.onclick = async () => {
        const currentId = item.id;
        t.disabled = true;
        t.textContent = 'Transcription en cours…';
        try {
          const r = await api('transcribe', { id: currentId });
          if ($('editor').open && state.editing?.id === currentId) {
            $('body').value = [$('body').value.trim(), r.text].filter(Boolean).join('\n\n');
            alertUser('Transcription prête. Enregistrez la fiche.');
          }
        } catch (e) {
          alertUser(e.message, true);
        } finally {
          t.disabled = false;
          t.textContent = 'Transcrire sur ce PC';
        }
      };
      media.append(t);
    }
  }
  const links = $('links');
  links.replaceChildren();
  if (!bridge) {
    for (const url of new Set(
      [item.title, item.body].join('\n').match(/https?:\/\/[^\s<>"']+/g) || []
    )) {
      const a = node('a', '', url);
      a.href = url;
      a.target = '_blank';
      a.rel = 'noreferrer noopener';
      links.append(a);
    }
  } else if (typeof bridge.openLink === 'function') {
    for (const url of new Set(
      [item.title, item.body].join('\n').match(/https?:\/\/[^\s<>"']+/g) || []
    )) {
      const b = node('button', 'text-button', url);
      b.type = 'button';
      b.onclick = () => bridge.openLink(url);
      links.append(b);
    }
  }
  $('analyze').hidden = !state.provider?.available || $('remove').hidden;
  if (state.provider?.available) {
    $('analyze-label').textContent = state.provider.local
      ? 'Analyser en local…'
      : 'Analyser avec un modèle externe…';
  }
  onKind();
  showDialog($('editor'));
}
$('kind').onchange = onKind;
$('create').onclick = () => {
  const item = blank(state.view);
  if (state.view === 'event' && state.day) item.when = new Date(state.day + 'T09:00').toISOString();
  openEditor(item);
};
$('edit-form').onsubmit = async (ev) => {
  ev.preventDefault();
  const item = state.editing;
  if (!item) return;
  const kind = $('kind').value,
    title = $('title').value.trim();
  if (!title) {
    $('title').focus();
    return;
  }
  const dt = ['event', 'task'].includes(kind) ? $('when').value : '';
  const updated = {
    ...item,
    kind,
    title,
    body: $('body').value,
    when: dt ? new Date(dt).toISOString() : '',
    pinned: kind === 'task' && !item.done && $('pinned').checked,
    done: kind === 'task' && item.done,
  };
  $('commit').disabled = true;
  try {
    await save(updated);
    $('editor').close();
    alertUser('Élément enregistré.');
  } catch (e) {
    alertUser(e.message, true);
    await reload();
  } finally {
    $('commit').disabled = false;
  }
};
$('remove').onclick = () => {
  $('delete-title').textContent = state.editing.title;
  showDialog($('confirm-delete'));
};
$('delete-yes').onclick = async () => {
  const item = state.editing;
  $('delete-yes').disabled = true;
  try {
    if (bridge) {
      unpack(bridge.deleteItem(item.id, item.rev));
      await reload();
    } else await save({ ...item, deleted: true, pinned: false });
    $('confirm-delete').close();
    $('editor').close();
    alertUser('Élément supprimé.');
  } catch (e) {
    alertUser(e.message, true);
    await reload();
  } finally {
    $('delete-yes').disabled = false;
  }
};
$('analyze').onclick = () => {
  const item = state.editing;
  const isLocal = Boolean(state.provider.local);
  $('consent-title').textContent = isLocal
    ? 'Analyser ce message en local ?'
    : 'Autoriser cet envoi externe ?';
  $('destination').textContent = isLocal
    ? 'Ce texte sera analysé localement sur ce PC avec ' + state.provider.name + '.'
    : 'Ce texte sera transmis à ' + state.provider.name + ' pour cette analyse.';
  $('send').textContent = isLocal ? 'Analyser localement' : 'Envoyer ce message';
  $('payload').textContent = item.source || item.body || item.title;
  showDialog($('consent'));
};
$('send').onclick = async () => {
  const item = state.editing;
  $('send').disabled = true;
  try {
    const r = await api('analyze', {
      id: item.id,
      rev: item.rev,
      provider: state.provider.name,
      consent: true,
    });
    $('consent').close();
    $('analysis-result').hidden = false;
    $('analysis-result').textContent = r.result;
  } catch (e) {
    alertUser(e.message, true);
  } finally {
    $('send').disabled = false;
  }
};
let captureId = null;
async function capture() {
  const raw = $('capture').value.trim();
  if (!raw && !pendingAudio) {
    $('capture').focus();
    return;
  }
  const draft = blank();
  captureId ??= draft.id;
  draft.id = captureId;
  const first = raw.split('\n')[0];
  draft.title = first ? (first.length > 95 ? first.slice(0, 92) + '…' : first) : 'Mémo vocal';
  draft.body = raw;
  draft.audio = pendingAudio;
  $('capture-save').disabled = true;
  try {
    await save(draft);
    $('capture').value = '';
    pendingAudio = '';
    captureId = null;
    resetPreview();
    alertUser('Capture enregistrée.');
    $('capture').focus();
  } catch (e) {
    alertUser(e.message, true);
  } finally {
    $('capture-save').disabled = false;
  }
}
$('capture-save').onclick = capture;
$('capture').onkeydown = (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !$('capture-save').disabled) {
    e.preventDefault();
    capture();
  }
};
function resetPreview() {
  const div = $('audio-preview');
  div.replaceChildren();
  div.hidden = !pendingAudio;
  if (pendingAudio) {
    const remove = node('button', 'text-button', 'Retirer le mémo');
    remove.onclick = () => {
      pendingAudio = '';
      resetPreview();
    };
    div.append(player(pendingAudio), remove);
  }
}
async function record() {
  if (bridge) {
    bridge.record();
    return;
  }
  if (recorder?.state === 'recording') {
    recorder.stop();
    return;
  }
  if (pendingAudio) {
    alertUser('Enregistrez ou retirez le mémo actuel avant de recommencer.');
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    alertUser('Le micro nécessite un navigateur compatible ouvert sur localhost ou HTTPS.', true);
    return;
  }
  $('record').disabled = true;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    const parts = [];
    let bytes = 0;
    recorder.ondataavailable = (ev) => {
      if (ev.data.size) {
        parts.push(ev.data);
        bytes += ev.data.size;
      }
      if (bytes > 16 * 1024 * 1024 && recorder.state === 'recording') {
        recorder.stop();
      }
    };
    recorder.onstop = () => {
      clearInterval(recordingTimer);
      stream.getTracks().forEach((track) => track.stop());
      $('record-text').textContent = 'Mémo vocal';
      $('record').classList.remove('recording');
      const reader = new FileReader();
      reader.onload = () => {
        pendingAudio = reader.result;
        resetPreview();
        $('capture-save').disabled = false;
        alertUser('Mémo prêt à enregistrer.');
      };
      reader.onerror = () => {
        alertUser('Lecture du mémo impossible.', true);
        $('capture-save').disabled = false;
      };
      reader.readAsDataURL(new Blob(parts, { type: recorder.mimeType || 'audio/webm' }));
      recorder = null;
    };
    recorder.start(1000);
    $('capture-save').disabled = true;
    $('record').classList.add('recording');
    const start = Date.now();
    const tick = () => {
      const seconds = Math.floor((Date.now() - start) / 1000);
      $('record-text').textContent =
        'Arrêter · ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
    };
    tick();
    recordingTimer = setInterval(tick, 500);
  } catch (e) {
    stream?.getTracks().forEach((t) => t.stop());
    alertUser('Enregistrement impossible. Vérifiez l’accès au microphone.', true);
  } finally {
    $('record').disabled = false;
  }
}
$('record').onclick = record;
$('query').oninput = render;
document.addEventListener('keydown', (e) => {
  if (
    e.key === '/' &&
    !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) &&
    !document.querySelector('dialog[open]')
  ) {
    e.preventDefault();
    $('query').focus();
  }
});
function setupDesktopPairing() {
  const dialog = $('pairing');
  const generate = $('pair-generate');
  const code = $('pair-code');
  const qr = $('pair-qr');
  let generation = 0;
  $('settings').title = 'Associer le téléphone';
  $('settings').ariaLabel = 'Réglages du PC et association du téléphone';
  $('settings').onclick = () => showDialog(dialog);
  generate.onclick = async () => {
    const request = ++generation;
    generate.disabled = true;
    dialog.querySelector('.dialog-error')?.remove();
    try {
      const result = await api('pair', {});
      if (!dialog.open || request !== generation) return;
      const { url, token, fingerprint } = result;
      if (!url || !token || !fingerprint) throw new Error('Code d’association incomplet.');
      code.value = JSON.stringify({ url, token, fingerprint });
      $('pair-instructions').hidden = false;
      generate.hidden = true;
      if (typeof result.qr === 'string' && result.qr.startsWith('data:image/png;base64,')) {
        qr.src = result.qr;
        qr.hidden = false;
        $('pair-help').textContent =
          'Sur le téléphone, scannez le QR comme du texte et copiez le résultat. Dans Mon cerveau, ouvrez Réglages → Associer le PC et collez le code.';
      } else {
        $('pair-help').textContent =
          'Transférez le code texte directement sur le téléphone. Dans Mon cerveau, ouvrez Réglages → Associer le PC et collez le code.';
        $('pair-details').open = true;
      }
    } catch (error) {
      if (dialog.open && request === generation) alertUser(error.message, true);
    } finally {
      if (request === generation) generate.disabled = false;
    }
  };
  $('pair-copy').onclick = async () => {
    try {
      await navigator.clipboard.writeText(code.value);
      $('pair-copy').textContent = 'Code copié';
    } catch {
      code.focus();
      code.select();
      alertUser('Le code est sélectionné. Utilisez le raccourci de copie de votre appareil.', true);
    }
  };
  dialog.addEventListener('close', () => {
    generation++;
    code.value = '';
    qr.removeAttribute('src');
    qr.hidden = true;
    $('pair-instructions').hidden = true;
    $('pair-details').open = false;
    $('pair-copy').textContent = 'Copier le code';
    generate.disabled = false;
    generate.hidden = false;
  });
}
window.addEventListener('hashchange', () => setView(location.hash.slice(1)));
if (bridge) {
  $('settings').hidden = false;
  $('sync').hidden = false;
  $('settings').onclick = () => bridge.settings();
  $('sync').onclick = () => {
    bridge.refresh();
    $('sync-status').textContent = bridge.getStatus();
  };
  window.addEventListener('itemschange', reload);
  window.monCerveauRefresh = reload;
} else {
  setupDesktopPairing();
  api('provider')
    .then((p) => {
      state.provider = p;
    })
    .catch(() => {});
  setInterval(() => {
    if (!document.hidden && !document.querySelector('dialog[open]')) reload();
  }, 30000);
}
matchMedia('(max-width:660px)').addEventListener('change', render);
window.addEventListener('focus', reload);
setView(location.hash.slice(1));
reload();
