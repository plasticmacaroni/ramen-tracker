const STORAGE_KEY = 'ramen-rater-data';
const VERSION = 1;

function defaultData() {
  return {
    version: VERSION,
    ratings: {},
    rankedList: [],
    stats: { totalFights: 0, fightStreak: 0, biggestUpset: null },
    settings: {
      lastBackupReminder: new Date().toISOString(),
      ratingsAtLastReminder: 0,
      hideRaterScore: false,
    },
    customRamen: {},
    wishlist: {},
  };
}

let data = null;

export function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    data = raw ? JSON.parse(raw) : defaultData();
    if (!data.version) data = { ...defaultData(), ...data };
    if (!data.ratings) data.ratings = {};
    if (!data.rankedList) data.rankedList = [];
    if (!data.stats) data.stats = { totalFights: 0, fightStreak: 0, biggestUpset: null };
    if (!data.settings) data.settings = defaultData().settings;
    if (data.settings.hideRaterScore === undefined) data.settings.hideRaterScore = false;
    if (data.settings.lastBackupReminder === undefined) data.settings.lastBackupReminder = new Date().toISOString();
    if (data.settings.ratingsAtLastReminder === undefined) data.settings.ratingsAtLastReminder = 0;
    if (!data.customRamen) data.customRamen = {};
    if (!data.wishlist) data.wishlist = {};
  } catch {
    data = defaultData();
  }
  return data;
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function getData() {
  if (!data) load();
  return data;
}

export function getRating(id) {
  return getData().ratings[String(id)];
}

export function setRating(id, flavor, noodle) {
  const d = getData();
  const key = String(id);
  const existing = d.ratings[key];
  const today = new Date().toISOString().slice(0, 10);

  if (existing) {
    existing.flavorRating = flavor;
    existing.noodleRating = noodle;
    if (!existing.dates.includes(today)) existing.dates.push(today);
  } else {
    d.ratings[key] = {
      flavorRating: flavor,
      noodleRating: noodle,
      dates: [today],
    };
  }
  delete d.wishlist[key];
  save();
}

export function getRankedList() {
  return getData().rankedList;
}

export function setRankedList(list) {
  getData().rankedList = list;
  save();
}

export function insertIntoRankedList(id, position) {
  const d = getData();
  d.rankedList.splice(position, 0, id);
  save();
}

export function removeRating(id) {
  const d = getData();
  const key = String(id);
  delete d.ratings[key];
  const idx = d.rankedList.indexOf(id);
  if (idx !== -1) d.rankedList.splice(idx, 1);
  save();
}

export function isRated(id) {
  return String(id) in getData().ratings;
}

export function getRatedIds() {
  return new Set(Object.keys(getData().ratings).map(k => {
    const n = Number(k);
    return isNaN(n) ? k : n;
  }));
}

export function getRatedCount() {
  return Object.keys(getData().ratings).length;
}

export function getStats() {
  return getData().stats;
}

export function updateStats(updates) {
  Object.assign(getData().stats, updates);
  save();
}

export function getScore(id) {
  const list = getRankedList();
  const idx = list.indexOf(id);
  if (idx === -1) return null;
  const n = list.length;
  if (n <= 1) return 7.0;

  const rawPct = (n - 1 - idx) / (n - 1);

  // With few ratings, compress the range so grades stay reasonable
  // (no misleading F's when you've only rated 3 ramen).
  // Floor starts at C (7.3) and drops toward 0; ceiling starts at A (9.3) and rises to 10.
  const minScore = Math.max(5.8, 7.3 - (n - 2) * 0.15);
  const maxScore = Math.min(10.0, 9.3 + (n - 2) * 0.07);
  const score = minScore + rawPct * (maxScore - minScore);

  return parseFloat(score.toFixed(1));
}

export function getRank(id) {
  const list = getRankedList();
  const idx = list.indexOf(id);
  return idx === -1 ? null : idx + 1;
}

/* ---- Settings ---- */

export function getHideRaterScore() {
  return getData().settings.hideRaterScore || false;
}

export function setHideRaterScore(val) {
  getData().settings.hideRaterScore = !!val;
  save();
}

export function getCardSize() {
  return getData().settings.cardSize || 'large';
}

export function setCardSize(size) {
  getData().settings.cardSize = size;
  save();
}

/* ---- Custom Ramen CRUD ---- */

export function getCustomRamen() {
  return getData().customRamen;
}

export function getCustomRamenById(id) {
  return getData().customRamen[String(id)] || null;
}

export function getAllCustomRamenList() {
  return Object.values(getData().customRamen);
}

export function addCustomRamen(entry) {
  const d = getData();
  const id = `c-${Date.now()}`;
  const ramen = {
    id,
    variety: entry.variety,
    brand: entry.brand,
    style: entry.style || '',
    country: entry.country || '',
    imageData: entry.imageData || null,
    barcode: entry.barcode || '',
    custom: true,
  };
  d.customRamen[id] = ramen;
  save();
  return ramen;
}

export function deleteCustomRamen(id) {
  const d = getData();
  const key = String(id);
  delete d.customRamen[key];
  delete d.ratings[key];
  const idx = d.rankedList.indexOf(id);
  if (idx !== -1) d.rankedList.splice(idx, 1);
  save();
}

/* ---- Wishlist (Want to Try) ---- */

export function getWishlist() {
  return getData().wishlist;
}

export function addToWishlist(id, customData) {
  const d = getData();
  const key = String(id);
  const entry = { added: new Date().toISOString().slice(0, 10) };
  if (customData) entry.custom = customData;
  d.wishlist[key] = entry;
  save();
}

export function removeFromWishlist(id) {
  const d = getData();
  delete d.wishlist[String(id)];
  save();
}

export function isWishlisted(id) {
  return String(id) in getData().wishlist;
}

export function getWishlistCount() {
  return Object.keys(getData().wishlist).length;
}

export function getWishlistIds() {
  return new Set(Object.keys(getData().wishlist).map(k => {
    const n = Number(k);
    return isNaN(n) ? k : n;
  }));
}

/* ---- Backup Reminder ---- */

export function shouldShowBackupReminder() {
  const d = getData();
  const s = d.settings;
  const ratedCount = Object.keys(d.ratings).length;
  if (ratedCount === 0) return false;

  const lastCount = s.ratingsAtLastReminder || 0;
  const ratingsSince = ratedCount - lastCount;
  // First reminder after 3 ratings, subsequent reminders every 5
  const threshold = lastCount === 0 ? 3 : 5;
  if (ratingsSince >= threshold) return true;

  const lastReminder = new Date(s.lastBackupReminder || 0);
  const daysSince = (Date.now() - lastReminder.getTime()) / (1000 * 60 * 60 * 24);
  return daysSince >= 1;
}

export function dismissBackupReminder() {
  const d = getData();
  d.settings.lastBackupReminder = new Date().toISOString();
  d.settings.ratingsAtLastReminder = Object.keys(d.ratings).length;
  save();
}

export function exportBackup() {
  const d = getData();
  const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const date = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `ramen-rater-backup-${date}.json`;
  a.click();
  URL.revokeObjectURL(url);
  dismissBackupReminder();
}

export function importBackup(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const imported = JSON.parse(reader.result);
        if (!imported.ratings || !imported.rankedList) {
          reject(new Error('Invalid backup file'));
          return;
        }
        data = { ...defaultData(), ...imported };
        save();
        resolve(data);
      } catch {
        reject(new Error('Could not parse backup file'));
      }
    };
    reader.onerror = () => reject(new Error('Could not read file'));
    reader.readAsText(file);
  });
}

export function clearAll() {
  data = defaultData();
  save();
}
