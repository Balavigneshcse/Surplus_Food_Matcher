// plan.js: the manager's page. Today's and tomorrow's meals, one card per meal slot:
// - plan a meal from its slot (menu with exactly one reserve dish, usual kg), or edit it while PLANNED
// - watch the live P50/P90 as opt-outs arrive (the page refreshes every 15 s)
// - override the forecast with a reason, issue the cook card, print it
// - keep the door tally (+1, +10, set) once the card is issued
import { api, getMe, logout } from './api.js';
import { $, el, fmtKg, fmtTimeIST, toast } from './ui.js';
import { applyI18n, t, toggleLang } from './i18n.js';

const REFRESH_MS = 15_000;
const DAY_KEY = 'annamsetu.planDay';

const state = {
  setup: null, // GET /api/kitchen/slots: { kitchen, slots, partners }
  dishes: [], // GET /api/kitchen/dishes
  day: loadDay(), // 'today' or 'tomorrow'
  dates: { today: '', tomorrow: '' }, // ISO dates on the server clock (the demo clock can move them)
  serverNow: '',
  views: [], // full meal views for the chosen day
  editing: null, // the slot id whose meal editor is open
  openForms: new Set(), // "override-<mealId>" while an override form is open
};

// ---------------------------------------------------------------- helpers

function loadDay() {
  try {
    return localStorage.getItem(DAY_KEY) === 'tomorrow' ? 'tomorrow' : 'today';
  } catch {
    return 'today';
  }
}

function saveDay(day) {
  try {
    localStorage.setItem(DAY_KEY, day);
  } catch {
    // storage blocked: the page just starts on Today next time
  }
}

function addDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function slotName(slot) {
  return t(slot.toLowerCase());
}

function hhmm(timeText) {
  return (timeText || '').slice(0, 5); // "12:00:00" -> "12:00"
}

// "12.5" or "12,5" kg -> 12500 g; blank -> null
function kgToGrams(text) {
  const value = String(text || '').trim().replace(',', '.');
  if (!value) return null;
  const kg = Number(value);
  return Number.isFinite(kg) && kg >= 0 ? Math.round(kg * 1000) : NaN;
}

function vegMark(isVeg) {
  return el('span', { class: isVeg ? 'veg-mark' : 'veg-mark nonveg', role: 'img', 'aria-label': t(isVeg ? 'veg' : 'nonVeg'), title: t(isVeg ? 'veg' : 'nonVeg') });
}

function busy() {
  return state.editing !== null || state.openForms.size > 0;
}

// ---------------------------------------------------------------- loading

async function refresh() {
  // no ?date = today on the server clock; tomorrow is the day after that
  const today = await api.get('/api/kitchen/meals');
  state.serverNow = today.serverNow;
  state.dates.today = today.date;
  state.dates.tomorrow = addDays(today.date, 1);
  const list = state.day === 'today' ? today : await api.get(`/api/kitchen/meals?date=${state.dates.tomorrow}`);
  state.views = await Promise.all(list.meals.map((m) => api.get(`/api/kitchen/meals/${m.id}`)));
  $('#status').classList.add('hidden');
  render();
}

async function safeRefresh() {
  try {
    await refresh();
  } catch (e) {
    $('#status').textContent = e.message;
    $('#status').classList.remove('hidden');
  }
}

function replaceView(view) {
  state.views = state.views.map((v) => (v.id === view.id ? view : v));
  state.serverNow = view.serverNow;
  render();
}

// ---------------------------------------------------------------- render

function render() {
  applyI18n();
  $('#server-time').textContent = fmtTimeIST(state.serverNow);
  for (const day of ['today', 'tomorrow']) {
    const tab = $(`#tab-${day}`);
    tab.textContent = `${t(day)} ${state.dates[day].slice(8, 10)}/${state.dates[day].slice(5, 7)}`;
    tab.setAttribute('aria-selected', String(state.day === day));
  }
  if (state.setup) $('#kitchen-title').textContent = `${t('plan')}: ${state.setup.kitchen.name}`;

  const box = $('#meals');
  box.replaceChildren();
  for (const slot of state.setup?.slots || []) {
    const view = state.views.find((v) => v.slotId === slot.id);
    if (state.editing === slot.id) {
      box.append(mealEditor(slot, view));
    } else if (view) {
      box.append(mealCard(slot, view));
    } else {
      box.append(emptyCard(slot));
    }
  }
}

function slotHeading(slot) {
  return `${slotName(slot.slot)} ${hhmm(slot.serviceStart)}-${hhmm(slot.serviceEnd)}`;
}

function emptyCard(slot) {
  return el('article', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', {}, slotHeading(slot)), el('span', { class: 'muted' }, t('notPlanned'))),
    el('button', { type: 'button', class: 'primary block', onclick: () => openEditor(slot.id) }, t('planMeal')));
}

function mealCard(slot, view) {
  const f = view.forecast;
  const planned = view.status === 'PLANNED';
  const card = el('article', { class: 'card', 'aria-label': slotHeading(slot) });

  card.append(el('div', { class: 'card-head' },
    el('h2', {}, `${slotName(view.slot)} ${fmtTimeIST(view.serviceStartAt)}-${fmtTimeIST(view.serviceEndAt)}`),
    el('span', { class: `badge ${view.status.toLowerCase()}` }, t(`status_${view.status}`))));

  card.append(el('div', { class: 'stats' },
    el('div', { class: 'stat' }, el('span', { class: 'value' }, f.p50), el('span', { class: 'label' }, t('p50'))),
    el('div', { class: 'stat' }, el('span', { class: 'value' }, f.p90), el('span', { class: 'label' }, t('p90')))));

  const method = el('p', { class: 'small' }, el('strong', {}, t(`method_${f.method}`)));
  if (f.method === 'MANUAL') method.append(` (${t('reason')}: ${f.overrideReason}; rule ${f.ruleP50}/${f.ruleP90})`);
  method.append(' · ', f.frozen ? `${t('frozenAt')} ${fmtTimeIST(view.issuedAt)}` : t('liveUpdates'));
  card.append(method);

  const extra = view.extraOptOuts ? ` (+${view.extraOptOuts})` : '';
  card.append(el('div', { class: 'facts' },
    el('span', {}, `${t('registeredDiners')}: `, el('strong', {}, view.registeredCount)),
    el('span', {}, `${t('optedOut')}: `, el('strong', {}, `${view.optOutRows}${extra}`)),
    el('span', {}, `${t('eligible')}: `, el('strong', {}, view.eligible)),
    el('span', {}, `${t('optoutCutoff')}: `, el('strong', {}, fmtTimeIST(view.cutoffAt)))));

  card.append(cookCardList(view));

  const actions = el('div', { class: 'actions-row' });
  if (planned) {
    actions.append(
      el('button', { type: 'button', onclick: () => openEditor(slot.id) }, t('editMeal')),
      el('button', { type: 'button', onclick: () => toggleOverride(view.id) }, t('override')),
      el('button', { type: 'button', class: 'primary', onclick: () => issue(view) }, t('issueCookCard')));
  }
  actions.append(el('a', { class: 'btn', href: `/kitchen/cookcard.html?meal=${view.id}` }, t('printCookCard')));
  card.append(actions);

  if (planned && state.openForms.has(`override-${view.id}`)) card.append(overrideForm(view));
  if (view.status === 'ISSUED' || view.status === 'IN_SERVICE') card.append(tallyBlock(view));
  return card;
}

// The cook card in short: one block per dish (a table would not fit 360 px).
function cookCardList(view) {
  const amount = (key, grams) => el('span', {}, `${t(key)}: `, el('strong', {}, `${fmtKg(grams)} ${t('kg')}`));
  return el('ul', { class: 'dish-list', 'aria-label': t('cookCard') }, ...view.cookCard.map((line) => el('li', {},
    el('div', {}, vegMark(line.isVeg), ' ', el('strong', {}, line.name),
      line.isReserve ? el('span', { class: 'badge issued' }, t('reserveDish')) : null),
    el('div', { class: 'facts' },
      amount('servingLine', line.lineG),
      line.isReserve ? amount('reserveVessel', line.reserveG) : null,
      !line.isReserve && line.topUpG > 0 ? amount('topUp', line.topUpG) : null,
      line.rawG !== null ? amount('rawKg', line.rawG) : null,
      line.usualG !== null ? amount('usual', line.usualG) : null))));
}

// ---------------------------------------------------------------- meal editor (create / edit)

function openEditor(slotId) {
  state.editing = slotId;
  render();
}

function closeEditor() {
  state.editing = null;
  render();
}

function mealEditor(slot, view) {
  const onMenu = new Map((view?.cookCard || []).map((line) => [line.dishId, line]));
  const dishes = state.dishes.filter((d) => d.active || onMenu.has(d.id));
  const groupName = `reserve-${slot.id}`;
  const error = el('p', { class: 'error-text', role: 'alert' });

  const registered = el('input', { id: 'f-registered', type: 'number', inputmode: 'numeric', min: '0', required: true,
    value: view ? view.registeredCount : state.setup.kitchen.registeredDiners });
  const extra = el('input', { id: 'f-extra', type: 'number', inputmode: 'numeric', min: '0',
    value: view ? view.extraOptOuts : 0 });

  const rows = dishes.map((dish) => {
    const line = onMenu.get(dish.id);
    const check = el('input', { type: 'checkbox', checked: Boolean(line), 'data-dish': dish.id });
    const radio = el('input', { type: 'radio', name: groupName, value: dish.id, checked: Boolean(line?.isReserve),
      disabled: !dish.isVeg });
    const usual = el('input', { type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-label': `${t('usualKg')}: ${dish.name}`,
      value: line?.usualG != null ? fmtKg(line.usualG) : '' });
    radio.addEventListener('change', () => { check.checked = true; }); // the reserve dish is on the menu
    check.addEventListener('change', () => { if (!check.checked) radio.checked = false; });
    return {
      dish, check, radio, usual,
      node: el('div', { class: 'pick-row' },
        el('div', {}, vegMark(dish.isVeg), ' ', el('strong', {}, dish.name), dish.nameTa ? ` · ${dish.nameTa}` : '',
          el('span', { class: 'muted small' }, ` · ${dish.cookedGPerDiner} g`)),
        el('div', { class: 'opts' },
          el('label', { class: 'check' }, check, t('onMenu')),
          el('label', { class: 'check' }, radio, t('reserveDish')),
          el('label', { class: 'usual small' }, t('usualKg'), usual))),
    };
  });

  const form = el('form', { class: 'card editing', novalidate: true });
  form.append(
    el('div', { class: 'card-head' }, el('h2', {}, `${view ? t('editMeal') : t('planMeal')}: ${slotHeading(slot)}`)),
    el('div', { class: 'grid2' },
      el('div', { class: 'field' }, el('label', { for: 'f-registered' }, t('registeredDiners')), registered),
      el('div', { class: 'field' }, el('label', { for: 'f-extra' }, t('extraOptOuts')), extra)),
    el('h3', {}, t('menu')),
    el('p', { class: 'muted small' }, t('pickReserve')),
    ...rows.map((r) => r.node),
    error,
    el('div', { class: 'actions-row' },
      el('button', { type: 'submit', class: 'primary' }, t('save')),
      el('button', { type: 'button', onclick: closeEditor }, t('cancel'))));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';
    const chosen = rows.filter((r) => r.check.checked);
    const reserves = chosen.filter((r) => r.radio.checked);
    if (reserves.length !== 1 || !reserves[0].dish.isVeg) {
      error.textContent = t('pickReserve');
      return;
    }
    const menu = chosen.map((r) => ({ dishId: r.dish.id, isReserve: r.radio.checked, usualG: kgToGrams(r.usual.value) }));
    if (menu.some((m) => Number.isNaN(m.usualG))) {
      error.textContent = `${t('usualKg')}?`;
      return;
    }
    const counts = { registeredCount: Number(registered.value), extraOptOuts: Number(extra.value || 0) };
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      if (view) {
        await api.put(`/api/kitchen/meals/${view.id}`, { ...counts, dishes: menu, version: view.version });
      } else {
        await api.post('/api/kitchen/meals', { slotId: slot.id, date: state.dates[state.day], ...counts, dishes: menu });
      }
      toast(t('saved'), 'success');
      state.editing = null;
      await refresh();
    } catch (e) {
      error.textContent = e.message;
    } finally {
      button.disabled = false;
    }
  });
  setTimeout(() => registered.focus(), 0);
  return form;
}

// ---------------------------------------------------------------- override, issue, tally

function toggleOverride(mealId) {
  const key = `override-${mealId}`;
  if (state.openForms.has(key)) state.openForms.delete(key);
  else state.openForms.add(key);
  render();
}

function overrideForm(view) {
  const p50 = el('input', { id: `o-p50-${view.id}`, type: 'number', inputmode: 'numeric', min: '0', value: view.forecast.p50 });
  const p90 = el('input', { id: `o-p90-${view.id}`, type: 'number', inputmode: 'numeric', min: '0', value: view.forecast.p90 });
  const reason = el('input', { id: `o-reason-${view.id}`, maxlength: '200', autocomplete: 'off',
    value: view.forecast.overrideReason || '' });
  const error = el('p', { class: 'error-text', role: 'alert' });
  const form = el('form', { class: 'sub-form', novalidate: true },
    el('h3', {}, t('override')),
    el('div', { class: 'grid2' },
      el('div', { class: 'field' }, el('label', { for: `o-p50-${view.id}` }, t('p50')), p50),
      el('div', { class: 'field' }, el('label', { for: `o-p90-${view.id}` }, t('p90')), p90)),
    el('div', { class: 'field' }, el('label', { for: `o-reason-${view.id}` }, t('reason')), reason),
    error,
    el('div', { class: 'actions-row' },
      el('button', { type: 'submit', class: 'primary' }, t('save')),
      el('button', { type: 'button', onclick: () => toggleOverride(view.id) }, t('cancel'))));
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const body = { p50: Number(p50.value), p90: Number(p90.value), reason: reason.value.trim(), version: view.version };
    if (!body.reason) { error.textContent = t('needReason'); return; }
    if (body.p90 < body.p50) { error.textContent = t('p90BelowP50'); return; }
    try {
      const updated = await api.post(`/api/kitchen/meals/${view.id}/override`, body);
      state.openForms.delete(`override-${view.id}`);
      toast(t('saved'), 'success');
      replaceView(updated);
    } catch (e) {
      error.textContent = e.message;
    }
  });
  return form;
}

async function issue(view) {
  if (!window.confirm(t('issueConfirm'))) return;
  try {
    const updated = await api.post(`/api/kitchen/meals/${view.id}/issue-cook-card`);
    toast(t('issued'), 'success');
    replaceView(updated);
  } catch {
    await safeRefresh(); // api.js showed the reason (e.g. already issued at the cutoff)
  }
}

function tallyBlock(view) {
  const input = el('input', { id: `tally-${view.id}`, type: 'number', inputmode: 'numeric', min: '0',
    'aria-label': t('doorTally') });
  async function send(body) {
    try {
      replaceView(await api.post(`/api/kitchen/meals/${view.id}/live-count`, body));
    } catch {
      // api.js showed the reason
    }
  }
  return el('div', { class: 'sub-form' },
    el('div', { class: 'card-head' },
      el('h3', {}, t('doorTally')),
      el('span', { class: 'stat' }, el('span', { class: 'value' }, view.liveCount))),
    el('div', { class: 'actions-row' },
      el('button', { type: 'button', class: 'primary', onclick: () => send({ delta: 1 }) }, '+1'),
      el('button', { type: 'button', class: 'primary', onclick: () => send({ delta: 10 }) }, '+10')),
    el('div', { class: 'actions-row' },
      input,
      el('button', { type: 'button', onclick: () => {
        const count = Number(input.value);
        if (input.value !== '' && Number.isInteger(count) && count >= 0) send({ count });
      } }, t('set'))));
}

// ---------------------------------------------------------------- start

applyI18n();
$('#lang-toggle').addEventListener('click', () => { toggleLang(); render(); });
$('#logout').addEventListener('click', logout);
for (const day of ['today', 'tomorrow']) {
  $(`#tab-${day}`).addEventListener('click', async () => {
    state.day = day;
    state.editing = null;
    state.openForms.clear();
    saveDay(day);
    await safeRefresh();
  });
}

try {
  const me = await getMe(); // a 401 goes to login.html
  if (me.role !== 'KITCHEN') {
    location.replace('/index.html');
  } else {
    [state.setup, state.dishes] = await Promise.all([api.get('/api/kitchen/slots'), api.get('/api/kitchen/dishes')]);
    await refresh();
    setInterval(() => {
      if (!document.hidden && !busy()) safeRefresh();
    }, REFRESH_MS);
  }
} catch (e) {
  if (e.status !== 401) {
    $('#status').textContent = e.message;
    $('#status').classList.remove('hidden');
  }
}
