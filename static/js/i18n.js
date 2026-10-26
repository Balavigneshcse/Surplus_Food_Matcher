// i18n.js: English and Tamil labels for staff screens.
// Mark text with data-i18n="key" (or data-i18n-placeholder="key") and call applyI18n().

const LABELS = {
  en: {
    appName: 'AnnamSetu',
    tagline: 'Cook right, keep the reserve safe, share the surplus.',
    login: 'Log in',
    logout: 'Log out',
    username: 'Username',
    password: 'Password',
    language: 'தமிழ்',
    loading: 'Loading…',
    welcome: 'Welcome',
    role: 'Role',
    kitchen: 'Kitchen',
    ngo: 'NGO',
    serverTime: 'Server time (IST)',
    comingSoon: 'Your home page arrives in the next build phase.',
    badCredentials: 'Wrong username or password',
    sampleData: 'SAMPLE DATA: all names and numbers are fictional',
    save: 'Save',
    cancel: 'Cancel',
    confirm: 'Confirm',
    today: 'Today',
    tomorrow: 'Tomorrow',
    breakfast: 'Breakfast',
    lunch: 'Lunch',
    dinner: 'Dinner',
    kg: 'kg',
    cookCard: 'Cook card',
    servingLine: 'Serving line',
    rawKg: 'Raw (uncooked)',
    cookedKg: 'Cooked',
    topUp: 'Top-up ready (20-min quick cook)',
    reserveVessel: 'RESERVE VESSEL',
    temperature: 'Temperature (°C)',
    weight: 'Weight (kg)',
    probeReading: 'Probe reading',
    handover: 'Handover',
    doorTally: 'Door tally',
  },
  ta: {
    appName: 'AnnamSetu',
    tagline: 'சரியாகச் சமை, இருப்பைப் பாதுகாப்பாக வை, மீதியைப் பகிர்.',
    login: 'உள்நுழை',
    logout: 'வெளியேறு',
    username: 'பயனர் பெயர்',
    password: 'கடவுச்சொல்',
    language: 'English',
    loading: 'ஏற்றுகிறது…',
    welcome: 'வரவேற்கிறோம்',
    role: 'பங்கு',
    kitchen: 'சமையலறை',
    ngo: 'தொண்டு நிறுவனம்',
    serverTime: 'சர்வர் நேரம் (IST)',
    comingSoon: 'உங்கள் முகப்புப் பக்கம் அடுத்த கட்டத்தில் வரும்.',
    badCredentials: 'பயனர் பெயர் அல்லது கடவுச்சொல் தவறு',
    sampleData: 'மாதிரி தரவு: அனைத்துப் பெயர்களும் எண்களும் கற்பனையானவை',
    save: 'சேமி',
    cancel: 'ரத்து செய்',
    confirm: 'உறுதிசெய்',
    today: 'இன்று',
    tomorrow: 'நாளை',
    breakfast: 'காலை உணவு',
    lunch: 'மதிய உணவு',
    dinner: 'இரவு உணவு',
    kg: 'கி.கி',
    cookCard: 'சமையல் அட்டை',
    servingLine: 'பரிமாறும் வரிசை',
    rawKg: 'சமைக்காதது',
    cookedKg: 'சமைத்தது',
    topUp: 'கூடுதல் தயார் (20 நிமிட விரைவுச் சமையல்)',
    reserveVessel: 'இருப்புப் பாத்திரம்',
    temperature: 'வெப்பநிலை (°C)',
    weight: 'எடை (கி.கி)',
    probeReading: 'வெப்பமானி அளவீடு',
    handover: 'ஒப்படை',
    doorTally: 'வாசல் எண்ணிக்கை',
  },
};

const STORAGE_KEY = 'annamsetu.lang';

export function getLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'ta' ? 'ta' : 'en';
  } catch {
    return 'en';
  }
}

export function setLang(lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // private window or blocked storage: the choice just isn't remembered
  }
  document.documentElement.lang = lang;
  applyI18n();
}

export function toggleLang() {
  setLang(getLang() === 'en' ? 'ta' : 'en');
}

// The label for `key` in the current language (falls back to English, then to the key).
export function t(key) {
  const lang = getLang();
  return LABELS[lang][key] ?? LABELS.en[key] ?? key;
}

export function applyI18n(root = document) {
  document.documentElement.lang = getLang();
  for (const node of root.querySelectorAll('[data-i18n]')) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of root.querySelectorAll('[data-i18n-placeholder]')) {
    node.setAttribute('placeholder', t(node.dataset.i18nPlaceholder));
  }
}
