// optout.js: the student page (optout.html?k=MESS1). No login: hostel ID, the meals still open for opt-out
// as big buttons, a confirm step, and Undo until the cutoff. The hostel ID is sent in the JSON body,
// never in the URL.
import { api } from './api.js';
import { $, el, fmtTimeIST, showSampleBanner, toast } from './ui.js';
import { applyI18n, t, toggleLang } from './i18n.js';

const kitchenCode = (new URLSearchParams(location.search).get('k') || '').trim().toUpperCase();
const MEMORY_KEY = 'annamsetu.optout'; // this phone only: the last hostel ID and what it opted out of
const REFRESH_MS = 60_000;

let openMeals = [];
let serverToday = ''; // the server's IST date, so "today" never depends on the phone clock
let pending = null; // the meal waiting for the confirm tap
let memory = loadMemory();

// ---------------------------------------------------------------- small helpers

function loadMemory() {
  try {
    const saved = JSON.parse(localStorage.getItem(MEMORY_KEY));
    return { hostelId: saved?.hostelId || '', done: saved?.done || {} };
  } catch {
    return { hostelId: '', done: {} };
  }
}

function saveMemory() {
  try {
    localStorage.setItem(MEMORY_KEY, JSON.stringify(memory));
  } catch {
    // private window or blocked storage: the page still works, it just forgets on reload
  }
}

function hostelId() {
  return $('#hostel-id').value.trim().toUpperCase();
}

function mealKey(id, meal) {
  return `${kitchenCode}|${id}|${meal.date}|${meal.slot}`;
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function dayLabel(isoDate) {
  if (isoDate === serverToday) return t('today');
  if (isoDate === addDays(serverToday, 1)) return t('tomorrow');
  return isoDate;
}

function mealName(meal) {
  return `${dayLabel(meal.date)} · ${t(meal.slot.toLowerCase())}`;
}

function body(meal) {
  return { kitchenCode, date: meal.date, slot: meal.slot, hostelId: hostelId() };
}

// ---------------------------------------------------------------- render

function render() {
  const list = $('#meals');
  list.replaceChildren();
  if (openMeals.length === 0) {
    list.append(el('p', { class: 'muted' }, t('noOpenMeals')));
    return;
  }
  const id = hostelId();
  for (const meal of openMeals) {
    const done = Boolean(id && memory.done[mealKey(id, meal)]);
    const status = done ? `✓ ${t('youOptedOut')}` : `${t('closesAt')} ${fmtTimeIST(meal.cutoffAt)}`;
    const button = el('button', {
      type: 'button', class: done ? 'choice done' : 'choice', 'aria-pressed': done ? 'true' : 'false',
      onclick: () => (done ? null : choose(meal)),
    },
    el('span', {}, mealName(meal), el('br'), el('span', { class: 'when' }, fmtTimeIST(meal.serviceStartAt))),
    el('span', { class: 'when' }, status));
    const row = el('div', { class: 'stack' }, button);
    if (done) {
      row.append(el('button', { type: 'button', class: 'block', onclick: () => undo(meal) }, t('undo')));
    }
    list.append(row);
  }
}

// ---------------------------------------------------------------- actions

function choose(meal) {
  if (!hostelId()) {
    toast(t('enterHostelId'), 'error');
    $('#hostel-id').focus();
    return;
  }
  pending = meal;
  $('#confirm-meal').textContent = `${mealName(meal)} (${fmtTimeIST(meal.serviceStartAt)}) · ${t('hostelId')}: ${hostelId()}`;
  $('#confirm').classList.remove('hidden');
  $('#confirm').scrollIntoView({ block: 'center', behavior: 'smooth' });
  $('#confirm-yes').focus({ preventScroll: true });
}

function closeConfirm() {
  pending = null;
  $('#confirm').classList.add('hidden');
}

async function confirmOptOut() {
  const meal = pending;
  if (!meal) return;
  const button = $('#confirm-yes');
  button.disabled = true;
  try {
    await api.post('/api/public/opt-outs', body(meal));
    memory.hostelId = hostelId();
    memory.done[mealKey(hostelId(), meal)] = true;
    saveMemory();
    toast(`${t('youOptedOut')}: ${mealName(meal)}`, 'success');
    closeConfirm();
    render();
  } catch (e) {
    closeConfirm(); // api.js already showed the reason (e.g. OPTOUT_CLOSED, INVALID_HOSTEL_ID)
    if (e.code === 'OPTOUT_CLOSED') await loadMeals();
  } finally {
    button.disabled = false;
  }
}

async function undo(meal) {
  try {
    await api.post('/api/public/opt-outs/cancel', body(meal));
    delete memory.done[mealKey(hostelId(), meal)];
    saveMemory();
    toast(t('undone'), 'success');
    render();
  } catch (e) {
    if (e.code === 'OPTOUT_CLOSED') await loadMeals();
  }
}

async function loadMeals() {
  try {
    const data = await api.get(`/api/public/kitchens/${encodeURIComponent(kitchenCode)}/open-meals`, { quiet: true });
    if (data.sampleData) showSampleBanner();
    $('#kitchen-name').textContent = data.kitchenName;
    serverToday = data.serverNow.slice(0, 10); // the ISO string carries +05:30, so this is the IST date
    openMeals = data.meals;
    for (const key of Object.keys(memory.done)) { // forget past meals
      const date = key.split('|')[2];
      if (date < serverToday) delete memory.done[key];
    }
    $('#load-error').textContent = '';
    render();
  } catch (e) {
    $('#load-error').textContent = e.message;
    $('#meals').replaceChildren();
  }
}

// ---------------------------------------------------------------- start

applyI18n();
$('#lang-toggle').addEventListener('click', () => {
  toggleLang();
  render();
});
$('#confirm-yes').addEventListener('click', confirmOptOut);
$('#confirm-no').addEventListener('click', closeConfirm);
$('#hostel-id').value = memory.hostelId;
$('#hostel-id').addEventListener('input', render);

if (!kitchenCode) {
  $('#load-error').textContent = t('badLink');
  $('#meals').replaceChildren();
} else {
  await loadMeals();
  setInterval(() => {
    if (!document.hidden && !pending) loadMeals();
  }, REFRESH_MS);
}
