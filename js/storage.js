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

export function mergeCustomRamen(customId, targetId) {
  const d = getData();
  const cKey = String(customId);
  const tKey = String(targetId);
  const rating = d.ratings[cKey];
  if (!rating) return;

  d.rankedList = d.rankedList.filter(e => String(e) !== tKey);

  const idx = d.rankedList.findIndex(e => String(e) === cKey);
  if (idx !== -1) d.rankedList[idx] = targetId;

  d.ratings[tKey] = { ...rating };
  delete d.ratings[cKey];

  delete d.customRamen[cKey];
  delete d.wishlist[cKey];

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

const _MAGIC = [0x52, 0x41, 0x4D, 0x45, 0x4E]; // "RAMEN" (legacy nibble format)
const _HEADER_LEN = 10;

// Robust sync marker for card+nibble format — uses extreme nibble values (0x00/0xFF)
// so each pixel channel is either 0 or 255, surviving heavy JPEG compression.
const _SYNC = [0x00, 0xFF, 0x00, 0xFF];
const _SYNC_HEADER_LEN = 4 + 1 + 4; // sync(4) + version(1) + length(4)

const _CARD_W = 600;
const _CARD_H = 60;
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

  ctx.fillStyle = '#2d1206';
  ctx.fillRect(0, 0, _CARD_W, _CARD_H);

  ctx.textBaseline = 'middle';

  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 16px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('Ramen Ratings Backup', 12, 20);

  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  });
  const timeStr = now.toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit',
  });
  let info = dateStr + ' ' + timeStr;
  if (stats) {
    const s = [];
    if (stats.ratings) s.push(stats.ratings + ' rated');
    if (stats.wishlist) s.push(stats.wishlist + ' wish');
    if (stats.custom) s.push(stats.custom + ' custom');
    if (s.length) info += '  \u00b7  ' + s.join(', ');
  }
  ctx.font = '11px sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.fillText(info, 12, 42);

  ctx.textAlign = 'right';
  ctx.font = '10px sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.fillText('Share as file \u2014 do not screenshot', _CARD_W - 12, 42);

  return canvas;
}

function _buildNibblePayload(compressed) {
  const payload = new Uint8Array(_SYNC_HEADER_LEN + compressed.length);
  payload.set(_SYNC);
  payload[4] = VERSION;
  const dv = new DataView(payload.buffer);
  dv.setUint32(5, compressed.length, false);
  payload.set(compressed, _SYNC_HEADER_LEN);
  return payload;
}

function _nibblePixelRows(payload, width) {
  const totalNibbles = payload.length * 2;
  const totalPixels = Math.ceil(totalNibbles / 3);
  const rows = Math.ceil(totalPixels / width);
  const px = new Uint8ClampedArray(width * rows * 4);

  let nibIdx = 0;
  for (let p = 0; p < width * rows; p++) {
    for (let ch = 0; ch < 3; ch++) {
      if (nibIdx < totalNibbles) {
        const bytePos = nibIdx >> 1;
        px[p * 4 + ch] = ((nibIdx & 1) === 0
          ? (payload[bytePos] >> 4) & 0xF
          : payload[bytePos] & 0xF) * 17;
        nibIdx++;
      }
    }
    px[p * 4 + 3] = 255;
  }
  return { px, rows };
}

// Binary (1-bit/channel) encoding — survives JPEG recompression from messaging apps.
// Distinct 6-byte sync so decoders can tell binary apart from nibble format.
const _BIN_SYNC = [0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00];
const _BIN_HEADER_LEN = 6 + 1 + 4; // sync(6) + version(1) + length(4)
// Guard band: data starts at 8-block-aligned row below card so JPEG artifacts can't bleed in.
const _BIN_DATA_START = 80; // card=60px + 20px black guard (aligned to JPEG 8x8 blocks)

function _buildBinaryPayload(compressed) {
  const payload = new Uint8Array(_BIN_HEADER_LEN + compressed.length);
  payload.set(_BIN_SYNC);
  payload[6] = VERSION;
  const dv = new DataView(payload.buffer);
  dv.setUint32(7, compressed.length, false);
  payload.set(compressed, _BIN_HEADER_LEN);
  return payload;
}

function _binaryPixelRows(payload, width) {
  const totalBits = payload.length * 8;
  const BLOCK = 2;
  const bitsPerBlockRow = Math.floor(width / BLOCK);
  const blockRows = Math.ceil(totalBits / bitsPerBlockRow);
  const rows = blockRows * BLOCK;
  const px = new Uint8ClampedArray(width * rows * 4);

  let bitIdx = 0;
  for (let by = 0; by < blockRows; by++) {
    for (let bx = 0; bx < bitsPerBlockRow && bitIdx < totalBits; bx++) {
      const bytePos = bitIdx >> 3;
      const bitPos = 7 - (bitIdx & 7);
      const val = ((payload[bytePos] >> bitPos) & 1) * 255;
      for (let dy = 0; dy < BLOCK; dy++) {
        for (let dx = 0; dx < BLOCK; dx++) {
          const pi = ((by * BLOCK + dy) * width + bx * BLOCK + dx) * 4;
          px[pi] = val;
          px[pi + 1] = val;
          px[pi + 2] = val;
          px[pi + 3] = 255;
        }
      }
      bitIdx++;
    }
  }
  return { px, rows };
}

export async function exportBackupImage() {
  const d = getData();

  // Full data for lossless PNG chunk (includes full-quality custom ramen images)
  const fullJson = JSON.stringify(d);
  const fullCompressed = await _deflate(new TextEncoder().encode(fullJson));

  // Pixel data: strip imageData so the pixel layer stays compact for JPEG resilience
  const pixelData = JSON.parse(fullJson);
  if (pixelData.customRamen) {
    for (const id of Object.keys(pixelData.customRamen)) {
      pixelData.customRamen[id].imageData = null;
    }
  }
  const pixelJson = JSON.stringify(pixelData);
  const pixelCompressed = await _deflate(new TextEncoder().encode(pixelJson));

  const stats = {
    ratings: Object.keys(d.ratings).length,
    wishlist: Object.keys(d.wishlist).length,
    custom: Object.keys(d.customRamen).length,
  };

  const binPayload = _buildBinaryPayload(pixelCompressed);
  const { px: binPx, rows: binRows } = _binaryPixelRows(binPayload, _CARD_W);

  const totalH = _BIN_DATA_START + binRows;
  const canvas = new OffscreenCanvas(_CARD_W, totalH);
  const ctx = canvas.getContext('2d', { colorSpace: 'srgb' });

  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, _CARD_W, totalH);

  const cardCanvas = _drawBackupCard(stats);
  ctx.drawImage(cardCanvas, 0, 0);

  const binImg = new ImageData(binPx, _CARD_W, binRows);
  ctx.putImageData(binImg, 0, _BIN_DATA_START);

  const cardBlob = await canvas.convertToBlob({ type: 'image/png' });
  const pngBytes = new Uint8Array(await cardBlob.arrayBuffer());
  const finalPng = _insertPNGChunk(pngBytes, fullCompressed);

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

async function _readBackupPixels(file, bitmapOpts, startRow = 0) {
  const bitmap = await createImageBitmap(file, bitmapOpts);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext('2d', { colorSpace: 'srgb' });
  ctx.drawImage(bitmap, 0, 0);
  const h = bitmap.height - startRow;
  if (h <= 0) return null;
  const data = ctx.getImageData(0, startRow, bitmap.width, h).data;
  data._width = bitmap.width;
  return data;
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

function _decodeSyncPixels(px) {
  const headerBytes = _readNibblesFromPixels(px, _SYNC_HEADER_LEN);

  for (let i = 0; i < _SYNC.length; i++) {
    if (Math.abs(headerBytes[i] - _SYNC[i]) > 0x11) {
      throw new Error('Not a valid Ramen Rater backup image (sync mismatch)');
    }
  }

  const dv = new DataView(headerBytes.buffer);
  const compLen = dv.getUint32(5, false);
  if (compLen === 0 || compLen > px.length) {
    throw new Error('Not a valid Ramen Rater backup image (bad length)');
  }
  const totalBytes = _SYNC_HEADER_LEN + compLen;
  return _readNibblesFromPixels(px, totalBytes).slice(_SYNC_HEADER_LEN);
}

function _readBitsFromPixels(px, numBytes, width) {
  const out = new Uint8Array(numBytes);
  const BLOCK = 2;
  const bitsPerBlockRow = Math.floor(width / BLOCK);
  const imgRows = px.length / 4 / width;
  const blockRows = Math.floor(imgRows / BLOCK);
  let bitIdx = 0;
  const totalBits = numBytes * 8;

  for (let by = 0; by < blockRows && bitIdx < totalBits; by++) {
    for (let bx = 0; bx < bitsPerBlockRow && bitIdx < totalBits; bx++) {
      let sum = 0;
      for (let dy = 0; dy < BLOCK; dy++) {
        for (let dx = 0; dx < BLOCK; dx++) {
          const pi = ((by * BLOCK + dy) * width + bx * BLOCK + dx) * 4;
          sum += px[pi] + px[pi + 1] + px[pi + 2];
        }
      }
      const avg = sum / (BLOCK * BLOCK * 3);
      const bit = avg >= 128 ? 1 : 0;
      const bytePos = bitIdx >> 3;
      const bitPos = 7 - (bitIdx & 7);
      out[bytePos] |= bit << bitPos;
      bitIdx++;
    }
  }
  return out;
}

function _decodeBinaryPixels(px) {
  const width = px._width || _CARD_W;
  const headerBytes = _readBitsFromPixels(px, _BIN_HEADER_LEN, width);

  for (let i = 0; i < _BIN_SYNC.length; i++) {
    if (headerBytes[i] !== _BIN_SYNC[i]) {
      throw new Error('Not a valid Ramen Rater backup image (binary sync mismatch)');
    }
  }

  const dv = new DataView(headerBytes.buffer);
  const compLen = dv.getUint32(7, false);
  if (compLen === 0 || compLen > px.length) {
    throw new Error('Not a valid Ramen Rater backup image (bad binary length)');
  }
  const totalBytes = _BIN_HEADER_LEN + compLen;
  return _readBitsFromPixels(px, totalBytes, width).slice(_BIN_HEADER_LEN);
}

async function _tryNibbleDecode(file, bitmapStrategies, startRow, decoderFn) {
  let lastError;
  for (const opts of bitmapStrategies) {
    try {
      const px = await _readBackupPixels(file, opts, startRow);
      if (!px) continue;
      const compressed = decoderFn(px);
      const jsonBytes = await _inflate(compressed);
      const json = new TextDecoder().decode(jsonBytes);
      const imported = JSON.parse(json);
      if (!imported.ratings || !imported.rankedList) {
        throw new Error('Invalid backup data in image');
      }
      return imported;
    } catch (err) {
      lastError = err;
      if (!err.message?.startsWith('Not a valid Ramen Rater')) throw err;
    }
  }
  return lastError;
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

  // Try binary (1-bit/channel) data below guard band — survives JPEG recompression
  const binResult = await _tryNibbleDecode(file, bitmapStrategies, _BIN_DATA_START, _decodeBinaryPixels);
  if (binResult && !(binResult instanceof Error)) {
    data = { ...defaultData(), ...binResult };
    save();
    return data;
  }

  // Try nibble data below the branded card (older format with sync header)
  const cardResult = await _tryNibbleDecode(file, bitmapStrategies, _CARD_H, _decodeSyncPixels);
  if (cardResult && !(cardResult instanceof Error)) {
    data = { ...defaultData(), ...cardResult };
    save();
    return data;
  }

  // Fall back to full-image nibble decode (legacy RAMEN header format)
  const legacyResult = await _tryNibbleDecode(file, bitmapStrategies, 0, _decodeBackupPixels);
  if (legacyResult && !(legacyResult instanceof Error)) {
    data = { ...defaultData(), ...legacyResult };
    save();
    return data;
  }

  throw legacyResult || cardResult || binResult || new Error('Could not decode backup image');
}

export function clearAll() {
  data = defaultData();
  save();
}
