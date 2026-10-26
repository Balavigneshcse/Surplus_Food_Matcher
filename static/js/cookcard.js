// cookcard.js: the printable cook card (kitchen/cookcard.html?meal=ID). Large type, English and Tamil
// together: for each dish the raw kg to cook, the serving-line kg, the top-up line for side dishes and the
// RESERVE VESSEL kg for the reserve dish. A card that is not issued yet is marked DRAFT.
import { api, getMe, logout } from './api.js';
import { $, el, fmtDateIST, fmtKg, fmtTimeIST } from './ui.js';
import { applyI18n, label } from './i18n.js';

const mealId = new URLSearchParams(location.search).get('meal');

// "English / தமிழ்" for one label key
function both(key) {
  return el('span', {}, label(key, 'en'), ' / ', el('span', { lang: 'ta' }, label(key, 'ta')));
}

function kg(grams) {
  return `${fmtKg(grams)} kg`;
}

function amountRow(key, grams, extra = null) {
  return el('div', { class: 'amount' }, el('span', {}, both(key), extra), el('strong', {}, kg(grams)));
}

function vegMark(isVeg) {
  const text = `${label(isVeg ? 'veg' : 'nonVeg', 'en')} / ${label(isVeg ? 'veg' : 'nonVeg', 'ta')}`;
  return el('span', { class: 'small' }, el('span', { class: isVeg ? 'veg-mark' : 'veg-mark nonveg', 'aria-hidden': 'true' }), ` ${text}`);
}

function dishBlock(line) {
  const block = el('section', { class: 'cook-dish' },
    el('h2', {}, line.name, line.nameTa ? el('span', { class: 'ta', lang: 'ta' }, line.nameTa) : null),
    vegMark(line.isVeg));
  if (line.rawG !== null) block.append(amountRow('cookRaw', line.rawG));
  block.append(amountRow('servingLine', line.lineG, el('span', { class: 'ta' }, `${label('cookedKg', 'en')} / ${label('cookedKg', 'ta')}`)));
  if (line.isReserve) {
    block.append(el('div', { class: 'reserve-box' },
      amountRow('reserveVessel', line.reserveG),
      el('p', { class: 'small' }, both('reserveNote'))));
  } else if (line.topUpG > 0) {
    block.append(amountRow('topUp', line.topUpG));
  }
  if (line.usualG !== null) {
    block.append(el('p', { class: 'small muted' },
      both('usual'), `: ${kg(line.usualG)} → `, both('planned'), `: ${kg(line.plannedG)}`));
  }
  return block;
}

function render(view) {
  const f = view.forecast;
  const card = $('#card');
  card.replaceChildren(
    el('h1', {}, both('cookCard')),
    el('p', {}, el('strong', {}, view.kitchenName), ` · ${fmtDateIST(view.serviceStartAt)} · `, both(view.slot.toLowerCase()),
      ` · ${fmtTimeIST(view.serviceStartAt)}-${fmtTimeIST(view.serviceEndAt)}`),
    f.frozen
      ? el('p', {}, both('issued'), ` ${fmtTimeIST(view.issuedAt)}`)
      : el('p', { class: 'draft' }, both('draftCard')),
    el('div', { class: 'stats' },
      el('div', { class: 'stat' }, el('span', { class: 'value' }, f.p50), el('span', { class: 'label' }, both('p50'))),
      el('div', { class: 'stat' }, el('span', { class: 'value' }, f.p90), el('span', { class: 'label' }, both('p90')))),
    el('p', { class: 'small' }, both(`method_${f.method}`), f.method === 'MANUAL' ? ` (${f.overrideReason})` : '',
      ` · ${label('registeredDiners', 'en')} ${view.registeredCount} · ${label('optedOut', 'en')} ${view.optedOut}`),
    ...view.cookCard.map(dishBlock),
    el('p', { class: 'small muted' }, `${label('serverClock', 'en')} ${fmtDateIST(view.serverNow)} ${fmtTimeIST(view.serverNow)} · #${view.id}`));
  card.classList.remove('hidden');
  $('#status').classList.add('hidden');
  document.title = `Cook card ${view.slot} ${view.date}`;
}

applyI18n();
$('#print').addEventListener('click', () => window.print());
$('#logout').addEventListener('click', logout);

try {
  const me = await getMe(); // shows the SAMPLE DATA banner in demo mode (it is printed too)
  if (me.role !== 'KITCHEN') {
    location.replace('/index.html');
  } else if (!mealId) {
    $('#status').textContent = 'Open this page from the meal plan (cookcard.html?meal=...)';
  } else {
    render(await api.get(`/api/kitchen/meals/${encodeURIComponent(mealId)}`));
  }
} catch (e) {
  if (e.status !== 401) $('#status').textContent = e.message;
}
