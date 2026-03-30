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

const _MAGIC = [0x52, 0x41, 0x4D, 0x45, 0x4E]; // "RAMEN" (old nibble format)
const _HEADER_LEN = 10;

const _CARD_W = 600;
const _CARD_H = 400;
const _PNG_SIG = [137, 80, 78, 71, 13, 10, 26, 10];
const _CHUNK_TYPE = [114, 77, 98, 107]; // "rMbk" — ancillary, private, safe-to-copy
const _CHUNK_VER = 1;

const _crcTable = new Uint32Array(256);
for (let n = 0; n < 256; n++) {
  let c = n;
  for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
  _crcTable[n] = c;
}
function _crc32(bytes) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) crc = _crcTable[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function _insertPNGChunk(png, payload) {
  const chunkData = new Uint8Array(1 + payload.length);
  chunkData[0] = _CHUNK_VER;
  chunkData.set(payload, 1);

  const chunk = new Uint8Array(12 + chunkData.length);
  const dv = new DataView(chunk.buffer);
  dv.setUint32(0, chunkData.length, false);
  chunk.set(_CHUNK_TYPE, 4);
  chunk.set(chunkData, 8);
  const crcBuf = new Uint8Array(4 + chunkData.length);
  crcBuf.set(_CHUNK_TYPE, 0);
  crcBuf.set(chunkData, 4);
  dv.setUint32(8 + chunkData.length, _crc32(crcBuf), false);

  const iend = png.length - 12;
  const out = new Uint8Array(png.length + chunk.length);
  out.set(png.subarray(0, iend), 0);
  out.set(chunk, iend);
  out.set(png.subarray(iend), iend + chunk.length);
  return out;
}

function _extractPNGChunk(png) {
  for (let i = 0; i < 8; i++) if (png[i] !== _PNG_SIG[i]) return null;
  let off = 8;
  while (off + 12 <= png.length) {
    const dv = new DataView(png.buffer, png.byteOffset + off);
    const len = dv.getUint32(0, false);
    if (png[off + 4] === 114 && png[off + 5] === 77 &&
        png[off + 6] === 98 && png[off + 7] === 107) {
      return png.slice(off + 8, off + 8 + len);
    }
    off += 12 + len;
  }
  return null;
}

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

function _drawBackupCard(stats) {
  const canvas = new OffscreenCanvas(_CARD_W, _CARD_H);
  const ctx = canvas.getContext('2d', { colorSpace: 'srgb' });

  const grad = ctx.createLinearGradient(0, 0, _CARD_W, _CARD_H);
  grad.addColorStop(0, '#1a0a00');
  grad.addColorStop(0.4, '#4a1a08');
  grad.addColorStop(0.7, '#7c2d12');
  grad.addColorStop(1, '#9a3412');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, _CARD_W, _CARD_H);

  const glow = ctx.createRadialGradient(
    _CARD_W / 2, _CARD_H / 2 - 30, 20,
    _CARD_W / 2, _CARD_H / 2 - 30, 250);
  glow.addColorStop(0, 'rgba(234, 88, 12, 0.25)');
  glow.addColorStop(1, 'rgba(234, 88, 12, 0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, _CARD_W, _CARD_H);

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
  ctx.lineWidth = 2;
  ctx.strokeRect(16, 16, _CARD_W - 32, _CARD_H - 32);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 38px sans-serif';
  ctx.fillText('RAMEN RATINGS', _CARD_W / 2, 130);
  ctx.font = 'bold 28px sans-serif';
  ctx.fillText('BACKUP', _CARD_W / 2, 170);

  ctx.strokeStyle = 'rgba(251, 146, 60, 0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(_CARD_W / 2 - 80, 195);
  ctx.lineTo(_CARD_W / 2 + 80, 195);
  ctx.stroke();

  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
  ctx.font = '18px sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
  ctx.fillText(dateStr, _CARD_W / 2, 225);

  if (stats) {
    const parts = [];
    if (stats.ratings) parts.push(`${stats.ratings} ratings`);
    if (stats.wishlist) parts.push(`${stats.wishlist} wishlisted`);
    if (stats.custom) parts.push(`${stats.custom} custom`);
    if (parts.length) {
      ctx.font = '15px sans-serif';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
      ctx.fillText(parts.join('  \u00b7  '), _CARD_W / 2, 265);
    }
  }

  ctx.font = '13px sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
  ctx.fillText('This image contains your ramen ratings data.', _CARD_W / 2, 320);
  ctx.fillText('Import it in Settings to restore your backup.', _CARD_W / 2, 340);

  ctx.font = '11px sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
  ctx.fillText('Do not edit or screenshot \u2014 use the original PNG file', _CARD_W / 2, _CARD_H - 28);

  return canvas;
}

export async function exportBackupImage() {
  const d = getData();
  const json = JSON.stringify(d);
  const jsonBytes = new TextEncoder().encode(json);
  const compressed = await _deflate(jsonBytes);

  const stats = {
    ratings: Object.keys(d.ratings).length,
    wishlist: Object.keys(d.wishlist).length,
    custom: Object.keys(d.customRamen).length,
  };
  const canvas = _drawBackupCard(stats);
  const cardBlob = await canvas.convertToBlob({ type: 'image/png' });
  const pngBytes = new Uint8Array(await cardBlob.arrayBuffer());
  const finalPng = _insertPNGChunk(pngBytes, compressed);

  const date = new Date().toISOString().slice(0, 10);
  const filename = `ramen-backup-${date}.png`;
  const blob = new Blob([finalPng], { type: 'image/png' });

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

async function _readBackupPixels(file, bitmapOpts) {
  const bitmap = await createImageBitmap(file, bitmapOpts);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d', { colorSpace: 'srgb' });
  ctx.drawImage(bitmap, 0, 0);
  return ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
}

function _decodeBackupPixels(px) {
  const headerBytes = _readNibblesFromPixels(px, _HEADER_LEN);

  for (let i = 0; i < _MAGIC.length; i++) {
    if (headerBytes[i] !== _MAGIC[i]) {
      const headerHex = Array.from(headerBytes).map(b => b.toString(16).padStart(2, '0')).join(' ');
      const headerAscii = Array.from(headerBytes.slice(0, 5)).map(b => String.fromCharCode(b)).join('');
      throw new Error(
        `Not a valid Ramen Rater backup image (header: "${headerAscii}" [${headerHex}])`
      );
    }
  }

  const dv = new DataView(headerBytes.buffer);
  const compLen = dv.getUint32(6, false);
  const totalBytes = _HEADER_LEN + compLen;
  return _readNibblesFromPixels(px, totalBytes).slice(_HEADER_LEN);
}

async function _importBackupImage(file) {
  const fileBytes = new Uint8Array(await file.arrayBuffer());
  const chunkData = _extractPNGChunk(fileBytes);
  if (chunkData && chunkData.length > 1 && chunkData[0] === _CHUNK_VER) {
    const compressed = chunkData.slice(1);
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

  const bitmapStrategies = [
    { colorSpaceConversion: 'none', premultiplyAlpha: 'none' },
    { premultiplyAlpha: 'none' },
  ];
  let lastError;
  for (const opts of bitmapStrategies) {
    try {
      const px = await _readBackupPixels(file, opts);
      const compressed = _decodeBackupPixels(px);
      const jsonBytes = await _inflate(compressed);
      const json = new TextDecoder().decode(jsonBytes);
      const imported = JSON.parse(json);
      if (!imported.ratings || !imported.rankedList) {
        throw new Error('Invalid backup data in image');
      }
      data = { ...defaultData(), ...imported };
      save();
      return data;
    } catch (err) {
      lastError = err;
      if (!err.message?.startsWith('Not a valid Ramen Rater')) throw err;
    }
  }
  throw lastError;
}

export function clearAll() {
  data = defaultData();
  save();
}
