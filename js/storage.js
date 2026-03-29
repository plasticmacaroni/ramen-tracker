const STORAGE_KEY = 'ramen-rater-data';
const VERSION = 1;

function defaultData() {
  return {
    version: VERSION,
    ratings: {},
    rankedList: [],
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
    delete data.stats;
    if (!data.settings) data.settings = defaultData().settings;
    if (data.settings.hideRaterScore === undefined) data.settings.hideRaterScore = false;
    if (data.settings.lastBackupReminder === undefined) data.settings.lastBackupReminder = new Date().toISOString();
    if (data.settings.ratingsAtLastReminder === undefined) data.settings.ratingsAtLastReminder = 0;
    if (!data.customRamen) data.customRamen = {};
    if (!data.wishlist) data.wishlist = {};
    // Reconcile: remove rankedList entries with no corresponding rating
    data.rankedList = data.rankedList.filter(id => String(id) in data.ratings);
  } catch {
    data = defaultData();
  }
  return data;
}

export function save() {
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
  d.rankedList = d.rankedList.filter(e => String(e) !== key);
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

export function scoreFromPosition(idx, total) {
  if (total <= 1) return 9.7;
  const rawPct = (total - 1 - idx) / (total - 1);
  const minScore = Math.max(5.5, 8.7 - (total - 2) * 0.25);
  const maxScore = Math.min(10.0, 9.7 + (total - 2) * 0.03);
  return parseFloat((minScore + rawPct * (maxScore - minScore)).toFixed(1));
}

export function getScore(id) {
  const list = getRankedList();
  const idx = list.indexOf(id);
  if (idx === -1) return null;
  return scoreFromPosition(idx, list.length);
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

export function findCustomRamenByContent(variety, brand) {
  const customs = getData().customRamen;
  for (const id of Object.keys(customs)) {
    const cr = customs[id];
    if (cr.variety === variety && cr.brand === brand) return cr;
  }
  return null;
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
  d.rankedList = d.rankedList.filter(e => String(e) !== key);
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
  const isImage = file.type.startsWith('image/') ||
    /\.(png|webp|bmp)$/i.test(file.name);

  if (isImage) return _importBackupImage(file);

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

/* ---- Image Backup (PNG pixel encoding) ---- */

const _MAGIC = [0x52, 0x41, 0x4D, 0x45, 0x4E]; // "RAMEN"
const _IMG_VERSION = 2;
const _HEADER_LEN = 10; // 5 magic + 1 version + 4 length
const _IMG_WIDTH = 256;

async function _deflate(bytes) {
  const cs = new CompressionStream('deflate-raw');
  const writer = cs.writable.getWriter();
  writer.write(bytes);
  writer.close();
  const chunks = [];
  const reader = cs.readable.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  let len = 0;
  for (const c of chunks) len += c.length;
  const out = new Uint8Array(len);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out;
}

async function _inflate(bytes) {
  const ds = new DecompressionStream('deflate-raw');
  const writer = ds.writable.getWriter();
  writer.write(bytes);
  writer.close();
  const chunks = [];
  const reader = ds.readable.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  let len = 0;
  for (const c of chunks) len += c.length;
  const out = new Uint8Array(len);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out;
}

function _buildPayload(compressed) {
  const total = _HEADER_LEN + compressed.length;
  const payload = new Uint8Array(total);
  payload.set(_MAGIC, 0);
  payload[5] = _IMG_VERSION;
  const dv = new DataView(payload.buffer);
  dv.setUint32(6, compressed.length, false);
  payload.set(compressed, _HEADER_LEN);
  return payload;
}

function _pixelsFromPayload(payload) {
  const totalNibbles = payload.length * 2;
  const pixelCount = Math.ceil(totalNibbles / 3);
  const h = Math.ceil(pixelCount / _IMG_WIDTH);
  const canvas = new OffscreenCanvas(_IMG_WIDTH, h);
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(_IMG_WIDTH, h);
  const d = img.data;

  let nibIdx = 0;
  for (let px = 0; px < _IMG_WIDTH * h; px++) {
    for (let ch = 0; ch < 3; ch++) {
      if (nibIdx < totalNibbles) {
        const bytePos = nibIdx >> 1;
        const nibble = (nibIdx & 1) === 0
          ? (payload[bytePos] >> 4) & 0xF
          : payload[bytePos] & 0xF;
        d[px * 4 + ch] = nibble * 17;
        nibIdx++;
      }
    }
    d[px * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

export async function exportBackupImage() {
  const json = JSON.stringify(getData());
  const jsonBytes = new TextEncoder().encode(json);
  const compressed = await _deflate(jsonBytes);
  const payload = _buildPayload(compressed);
  const canvas = _pixelsFromPayload(payload);

  const blob = await canvas.convertToBlob({ type: 'image/png' });
  const date = new Date().toISOString().slice(0, 10);
  const filename = `ramen-backup-${date}.png`;

  const file = new File([blob], filename, { type: 'image/png' });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file] });
    } catch (err) {
      if (err.name !== 'AbortError') throw err;
    }
  } else {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
  dismissBackupReminder();
}

function _readNibblesFromPixels(px, numBytes) {
  const out = new Uint8Array(numBytes);
  let nibIdx = 0;
  const totalNibbles = numBytes * 2;
  const totalPixels = px.length / 4;
  for (let p = 0; p < totalPixels && nibIdx < totalNibbles; p++) {
    for (let ch = 0; ch < 3 && nibIdx < totalNibbles; ch++) {
      const val = px[p * 4 + ch];
      const nibble = Math.round(val / 17);
      const bytePos = nibIdx >> 1;
      if ((nibIdx & 1) === 0) {
        out[bytePos] = (nibble & 0xF) << 4;
      } else {
        out[bytePos] |= nibble & 0xF;
      }
      nibIdx++;
    }
  }
  return out;
}

async function _importBackupImage(file) {
  const bitmap = await createImageBitmap(file, {
    colorSpaceConversion: 'none',
    premultiplyAlpha: 'none',
  });

  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, 0, 0);
  const imgData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
  const px = imgData.data;

  console.log('[backup-image] Image loaded:', bitmap.width, 'x', bitmap.height,
    '| first 20 RGBA:', Array.from(px.slice(0, 20)));

  const headerBytes = _readNibblesFromPixels(px, _HEADER_LEN);

  const headerHex = Array.from(headerBytes).map(b => b.toString(16).padStart(2, '0')).join(' ');
  const headerAscii = Array.from(headerBytes.slice(0, 5)).map(b => String.fromCharCode(b)).join('');
  console.log('[backup-image] Header:', headerHex, '| ASCII:', JSON.stringify(headerAscii));

  for (let i = 0; i < _MAGIC.length; i++) {
    if (headerBytes[i] !== _MAGIC[i]) {
      throw new Error(
        `Not a valid Ramen Rater backup image (header: "${headerAscii}" [${headerHex}])`
      );
    }
  }

  const dv = new DataView(headerBytes.buffer);
  const compLen = dv.getUint32(6, false);
  const totalBytes = _HEADER_LEN + compLen;
  console.log('[backup-image] Compressed length:', compLen, '| total payload:', totalBytes);

  const payload = _readNibblesFromPixels(px, totalBytes);

  const compressed = payload.slice(_HEADER_LEN);
  const jsonBytes = await _inflate(compressed);
  const json = new TextDecoder().decode(jsonBytes);
  const imported = JSON.parse(json);

  if (!imported.ratings || !imported.rankedList) {
    throw new Error('Invalid backup data in image');
  }
  data = { ...defaultData(), ...imported };
  save();
  return data;
}

export function clearAll() {
  data = defaultData();
  save();
}
