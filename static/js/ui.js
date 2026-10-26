// ui.js: small helpers shared by every page (formatting, toasts, countdowns, sample banner).
import { t } from './i18n.js';

const IST = 'Asia/Kolkata';

// Show kg with one decimal, rounding from integer grams: 7350 g -> "7.4".
// (g / 1000).toFixed(1) would show 7.3 because of float error.
export function fmtKg(g) {
  if (g === null || g === undefined) return '-';
  return (Math.round(g / 100) / 10).toFixed(1);
}

// "2026-10-30T12:25:00+05:30" -> "12:25" (always shown in IST, whatever the phone's zone is)
export function fmtTimeIST(iso) {
  if (!iso) return '-';
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: IST, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(iso));
}

// "2026-10-30T12:25:00+05:30" -> "30 Oct 2026"
export function fmtDateIST(iso) {
  if (!iso) return '-';
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: IST, day: 'numeric', month: 'short', year: 'numeric',
  }).format(new Date(iso));
}

// Shortcut for document.querySelector.
export function $(selector, root = document) {
  return root.querySelector(selector);
}

// Build an element safely (text is never parsed as HTML).
// el('p', { class: 'muted' }, 'Hello ', el('strong', {}, 'there'))
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (name.startsWith('on') && typeof value === 'function') {
      node.addEventListener(name.slice(2), value);
    } else {
      node.setAttribute(name, value === true ? '' : value);
    }
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function toastArea() {
  let area = document.getElementById('toast-area');
  if (!area) {
    area = el('div', { id: 'toast-area', class: 'toast-area', role: 'status', 'aria-live': 'polite' });
    document.body.append(area);
  }
  return area;
}

// kind: 'info' | 'success' | 'error'
export function toast(message, kind = 'info', ms = 4500) {
  const note = el('div', { class: `toast ${kind}` }, message);
  toastArea().append(note);
  setTimeout(() => note.remove(), ms);
}

// The server's clock, as seen from this phone: serverNow minus the phone time, measured once.
// Countdowns always use this, never the phone clock alone.
export function serverClock(serverNowIso) {
  const offsetMs = Date.parse(serverNowIso) - Date.now();
  return () => Date.now() + offsetMs;
}

function fmtRemaining(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

// Show mm:ss until `deadlineIso` in `node`. Returns a function that stops the countdown.
export function countdown(node, deadlineIso, serverNowIso, onEnd) {
  const now = serverClock(serverNowIso);
  const deadline = Date.parse(deadlineIso);
  node.classList.add('countdown');
  function tick() {
    const left = deadline - now();
    node.textContent = fmtRemaining(left);
    if (left <= 0) {
      clearInterval(timer);
      if (onEnd) onEnd();
    }
  }
  const timer = setInterval(tick, 1000);
  tick();
  return () => clearInterval(timer);
}

// Yellow banner at the top of the page; shown when /api/me says sampleData = true.
export function showSampleBanner() {
  if (document.getElementById('sample-banner')) return;
  const banner = el('div', { id: 'sample-banner', class: 'sample-banner', 'data-i18n': 'sampleData' },
    t('sampleData'));
  document.body.prepend(banner);
}
