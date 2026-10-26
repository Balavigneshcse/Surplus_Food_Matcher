// setup.js: kitchen setup with two tabs.
// - Meal slots: times, opt-out cutoff, attendance ratio, buffer %, share at T-90, standing partner,
//   pickup offset, rescue on/off (PUT /api/kitchen/slots/{id})
// - Dishes: English + Tamil name, veg, cooked and raw g per diner, cost (POST / PUT /api/kitchen/dishes)
import { api, getMe, logout } from './api.js';
import { $, el, toast } from './ui.js';
import { applyI18n, t, toggleLang } from './i18n.js';

const TAB_KEY = 'annamsetu.setupTab';

const state = {
  tab: loadTab(),
  setup: null, // { kitchen, slots, partners }
  dishes: [],
  editingDish: null, // a dish id, 'new', or null
};

function loadTab() {
  try {
    return localStorage.getItem(TAB_KEY) === 'dishes' ? 'dishes' : 'slots';
  } catch {
    return 'slots';
  }
}

function saveTab(tab) {
  try {
    localStorage.setItem(TAB_KEY, tab);
  } catch {
    // storage blocked: start on the first tab next time
  }
}

// One labelled input. `attrs` go on the <input>.
function field(id, labelKey, attrs) {
  return el('div', { class: 'field' }, el('label', { for: id }, t(labelKey)), el('input', { id, ...attrs }));
}

function numberOrNull(text) {
  const value = String(text).trim().replace(',', '.');
  return value === '' ? null : Number(value);
}

// ---------------------------------------------------------------- render

function render() {
  applyI18n();
  if (!state.setup) return; // a tab or language tap before the data has loaded
  const { kitchen } = state.setup;
  $('#kitchen-title').textContent = `${t('setup')}: ${kitchen.name}`;
  $('#kitchen-info').textContent = `${kitchen.code} · ${t('registeredDiners')}: ${kitchen.registeredDiners} · `
    + `${t('sideDishBasis')}: ${t(`basis_${kitchen.sideDishBasis}`)} (${t('setByAdmin')})`;
  for (const tab of ['slots', 'dishes']) {
    $(`#tab-${tab}`).setAttribute('aria-selected', String(state.tab === tab));
    $(`#panel-${tab}`).classList.toggle('hidden', state.tab !== tab);
  }
  $('#panel-slots').replaceChildren(...state.setup.slots.map(slotForm));
  renderDishes();
}

// ---------------------------------------------------------------- meal slots

function slotForm(slot) {
  const id = (name) => `s${slot.id}-${name}`;
  const partner = el('select', { id: id('partner') },
    el('option', { value: '' }, t('none')),
    ...state.setup.partners.map((p) => el('option', { value: p.id, selected: p.id === slot.standingNgoId }, p.name)));
  const rescue = el('input', { id: id('rescue'), type: 'checkbox', checked: slot.rescueEnabled });
  const error = el('p', { class: 'error-text', role: 'alert' });
  const form = el('form', { class: 'card', novalidate: true },
    el('h2', {}, t(slot.slot.toLowerCase())),
    el('div', { class: 'grid2' },
      field(id('start'), 'serviceStart', { type: 'time', required: true, value: slot.serviceStart.slice(0, 5) }),
      field(id('end'), 'serviceEnd', { type: 'time', required: true, value: slot.serviceEnd.slice(0, 5) }),
      field(id('cutoff'), 'cutoffMin', { type: 'number', inputmode: 'numeric', min: '0', max: '1440', value: slot.optoutCutoffMin }),
      field(id('ratio'), 'attendanceRatio', { type: 'text', inputmode: 'decimal', value: slot.attendanceRatio }),
      field(id('buffer'), 'bufferPct', { type: 'text', inputmode: 'decimal', value: slot.bufferPct }),
      field(id('share'), 'shareT90', { type: 'text', inputmode: 'decimal', value: slot.shareArrivedByT90 }),
      field(id('pickup'), 'pickupOffset', { type: 'number', inputmode: 'numeric', min: '0', value: slot.pickupOffsetMin }),
      el('div', { class: 'field' }, el('label', { for: id('partner') }, t('standingPartner')), partner)),
    el('label', { class: 'check' }, rescue, t('rescueEnabled')),
    error,
    el('button', { type: 'submit', class: 'primary block' }, t('save')));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';
    const body = {
      serviceStart: $(`#${id('start')}`).value,
      serviceEnd: $(`#${id('end')}`).value,
      optoutCutoffMin: Number($(`#${id('cutoff')}`).value),
      attendanceRatio: numberOrNull($(`#${id('ratio')}`).value),
      bufferPct: numberOrNull($(`#${id('buffer')}`).value),
      shareArrivedByT90: numberOrNull($(`#${id('share')}`).value),
      standingNgoId: partner.value ? Number(partner.value) : null,
      pickupOffsetMin: Number($(`#${id('pickup')}`).value),
      rescueEnabled: rescue.checked,
    };
    try {
      const saved = await api.put(`/api/kitchen/slots/${slot.id}`, body, { quiet: true });
      state.setup.slots = state.setup.slots.map((s) => (s.id === saved.id ? saved : s));
      toast(t('saved'), 'success');
      render();
    } catch (e) {
      error.textContent = `${e.message} (${e.code})`;
    }
  });
  return form;
}

// ---------------------------------------------------------------- dishes

function renderDishes() {
  const panel = $('#panel-dishes');
  panel.replaceChildren();
  if (state.editingDish === 'new') {
    panel.append(dishForm(null));
  } else {
    panel.append(el('button', { type: 'button', class: 'primary block', onclick: () => editDish('new') }, t('addDish')));
  }
  for (const dish of state.dishes) {
    panel.append(state.editingDish === dish.id ? dishForm(dish) : dishCard(dish));
  }
}

function dishCard(dish) {
  const facts = [
    `${t('cookedG')}: ${dish.cookedGPerDiner}`,
    dish.rawGPerDiner ? `${t('rawGShort')}: ${dish.rawGPerDiner}` : null,
    dish.costPerKgInr !== null ? `₹/kg ${dish.costPerKgInr}` : null,
  ].filter(Boolean);
  return el('article', { class: 'card' },
    el('div', { class: 'card-head' },
      el('h2', {}, dish.name, dish.nameTa ? el('span', { class: 'muted', lang: 'ta' }, ` · ${dish.nameTa}`) : null),
      el('span', { class: 'small' },
        el('span', { class: dish.isVeg ? 'veg-mark' : 'veg-mark nonveg', 'aria-hidden': 'true' }),
        ` ${t(dish.isVeg ? 'veg' : 'nonVeg')} · ${t(dish.active ? 'inUse' : 'notInUse')}`)),
    el('p', { class: 'muted small' }, facts.join(' · ')),
    el('button', { type: 'button', onclick: () => editDish(dish.id) }, t('edit')));
}

function editDish(id) {
  state.editingDish = id;
  renderDishes();
}

function dishForm(dish) {
  const id = (name) => `d${dish ? dish.id : 'new'}-${name}`;
  const veg = el('input', { id: id('veg'), type: 'checkbox', checked: dish ? dish.isVeg : true });
  const active = el('input', { id: id('active'), type: 'checkbox', checked: dish ? dish.active : true });
  const error = el('p', { class: 'error-text', role: 'alert' });
  const form = el('form', { class: 'card editing', novalidate: true },
    el('h2', {}, dish ? `${t('edit')}: ${dish.name}` : t('addDish')),
    el('div', { class: 'grid2' },
      field(id('name'), 'dishName', { maxlength: '100', required: true, value: dish?.name ?? '' }),
      field(id('name-ta'), 'dishNameTa', { maxlength: '100', lang: 'ta', value: dish?.nameTa ?? '' }),
      field(id('cooked'), 'cookedG', { type: 'number', inputmode: 'numeric', min: '1', required: true, value: dish?.cookedGPerDiner ?? '' }),
      field(id('raw'), 'rawG', { type: 'number', inputmode: 'numeric', min: '1', value: dish?.rawGPerDiner ?? '' }),
      field(id('cost'), 'costPerKg', { type: 'text', inputmode: 'decimal', value: dish?.costPerKgInr ?? '' })),
    el('div', { class: 'row' },
      el('label', { class: 'check' }, veg, t('veg')),
      el('label', { class: 'check' }, active, t('inUse'))),
    error,
    el('div', { class: 'actions-row' },
      el('button', { type: 'submit', class: 'primary' }, t('save')),
      el('button', { type: 'button', onclick: () => editDish(null) }, t('cancel'))));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';
    const body = {
      name: $(`#${id('name')}`).value.trim(),
      nameTa: $(`#${id('name-ta')}`).value.trim() || null,
      isVeg: veg.checked,
      cookedGPerDiner: numberOrNull($(`#${id('cooked')}`).value),
      rawGPerDiner: numberOrNull($(`#${id('raw')}`).value),
      costPerKgInr: numberOrNull($(`#${id('cost')}`).value),
      active: active.checked,
    };
    try {
      const saved = dish
        ? await api.put(`/api/kitchen/dishes/${dish.id}`, body, { quiet: true })
        : await api.post('/api/kitchen/dishes', body, { quiet: true });
      state.dishes = await api.get('/api/kitchen/dishes');
      state.editingDish = null;
      toast(`${t('saved')}: ${saved.name}`, 'success');
      renderDishes();
    } catch (e) {
      error.textContent = `${e.message} (${e.code})`;
    }
  });
  setTimeout(() => $(`#${id('name')}`)?.focus(), 0);
  return form;
}

// ---------------------------------------------------------------- start

applyI18n();
$('#lang-toggle').addEventListener('click', () => { toggleLang(); render(); });
$('#logout').addEventListener('click', logout);
for (const tab of ['slots', 'dishes']) {
  $(`#tab-${tab}`).addEventListener('click', () => {
    state.tab = tab;
    saveTab(tab);
    render();
  });
}

try {
  const me = await getMe(); // a 401 goes to login.html
  if (me.role !== 'KITCHEN') {
    location.replace('/index.html');
  } else {
    [state.setup, state.dishes] = await Promise.all([api.get('/api/kitchen/slots'), api.get('/api/kitchen/dishes')]);
    $('#status').classList.add('hidden');
    render();
  }
} catch (e) {
  if (e.status !== 401) $('#status').textContent = e.message;
}
