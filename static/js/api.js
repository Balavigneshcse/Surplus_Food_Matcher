// api.js: every page talks to /api through these helpers. It does five things:
// 1. sends credentials: 'same-origin' (the session cookie)
// 2. reads the XSRF-TOKEN cookie and sends it as X-CSRF-Token on every POST, PUT and DELETE
// 3. calls GET /api/auth/csrf when a page loads, and again after login or logout (both issue a new token)
// 4. sends the user to login.html on a 401
// 5. shows problem+json errors (detail, code) as a toast, and the SAMPLE DATA banner when the server says so
import { showSampleBanner, toast } from './ui.js';

const CSRF_COOKIE = 'XSRF-TOKEN';
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export class ApiError extends Error {
  constructor(problem) {
    super(problem.detail || 'Request failed');
    this.status = problem.status;
    this.code = problem.code;
    this.problem = problem;
  }
}

function readCookie(name) {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

export async function loadCsrf() {
  const res = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
  if (!res.ok) throw new ApiError(await readProblem(res));
  const body = await res.json();
  return body.csrfToken;
}

// Duty 3: fetch a token as soon as any page loads.
let csrfReady = loadCsrf().catch(() => '');

async function readProblem(res) {
  try {
    const body = await res.json();
    return { status: res.status, code: body.code || `HTTP_${res.status}`, detail: body.detail || res.statusText, ...body };
  } catch {
    return { status: res.status, code: `HTTP_${res.status}`, detail: res.statusText || 'Request failed' };
  }
}

export function goToLogin() {
  if (!location.pathname.endsWith('/login.html')) {
    location.href = '/login.html';
  }
}

// options: json (body object), form (object sent as form fields), quiet (no toast), stay (no redirect on 401)
async function request(method, path, { json, form, quiet = false, stay = false } = {}) {
  const headers = { Accept: 'application/json, application/problem+json' };
  let body;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    body = new URLSearchParams(form);
  }
  if (UNSAFE.has(method)) {
    await csrfReady;
    let token = readCookie(CSRF_COOKIE);
    if (!token) token = await loadCsrf();
    headers['X-CSRF-Token'] = token;
  }

  const res = await fetch(path, { method, headers, body, credentials: 'same-origin' });

  if (res.status === 401 && !stay) {
    goToLogin();
    throw new ApiError(await readProblem(res));
  }
  if (!res.ok) {
    const problem = await readProblem(res);
    if (!quiet) toast(`${problem.detail} (${problem.code})`, 'error');
    throw new ApiError(problem);
  }
  if (res.status === 204) return null;
  const type = res.headers.get('content-type') || '';
  return type.includes('json') ? res.json() : res.text();
}

export const api = {
  get: (path, options) => request('GET', path, options),
  post: (path, json, options) => request('POST', path, { ...options, json }),
  put: (path, json, options) => request('PUT', path, { ...options, json }),
  del: (path, options) => request('DELETE', path, options),
};

export async function login(username, password) {
  csrfReady = loadCsrf();
  await csrfReady;
  const result = await request('POST', '/api/auth/login', { form: { username, password }, quiet: true, stay: true });
  csrfReady = loadCsrf(); // login issued a new token
  await csrfReady;
  return result;
}

export async function logout() {
  try {
    await request('POST', '/api/auth/logout', { stay: true });
  } finally {
    csrfReady = loadCsrf().catch(() => ''); // logout issued a new session
    await csrfReady;
    location.href = '/login.html';
  }
}

// Who is logged in. Shows the SAMPLE DATA banner in demo mode. Redirects to login on 401
// unless { stay: true } is passed.
export async function getMe({ stay = false } = {}) {
  const me = await request('GET', '/api/me', { stay, quiet: stay });
  if (me.sampleData) showSampleBanner();
  return me;
}
