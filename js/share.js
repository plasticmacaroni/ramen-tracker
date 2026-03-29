const VERSION = 1;
const STYLE_ENUM = ['Pack', 'Cup', 'Bowl', 'Tray', 'Other'];
const URL_BUDGET = 8000;
const URL_PREFIX_ESTIMATE = 60;

/* ---- Base64url ---- */

function toBase64url(uint8) {
  let bin = '';
  for (let i = 0; i < uint8.length; i++) bin += String.fromCharCode(uint8[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function fromBase64url(str) {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(padded);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

/* ---- Compression via native streams ---- */

async function deflate(data) {
  const cs = new CompressionStream('deflate-raw');
  const writer = cs.writable.getWriter();
  writer.write(data);
  writer.close();
  const reader = cs.readable.getReader();
  const chunks = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  let len = 0;
  for (const c of chunks) len += c.length;
  const result = new Uint8Array(len);
  let off = 0;
  for (const c of chunks) { result.set(c, off); off += c.length; }
  return result;
}

async function inflate(data) {
  const ds = new DecompressionStream('deflate-raw');
  const writer = ds.writable.getWriter();
  writer.write(data);
  writer.close();
  const reader = ds.readable.getReader();
  const chunks = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  let len = 0;
  for (const c of chunks) len += c.length;
  const result = new Uint8Array(len);
  let off = 0;
  for (const c of chunks) { result.set(c, off); off += c.length; }
  return result;
}

/* ---- Share thumbnail compression ---- */

export async function compressShareThumbnail(imageDataUrl) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = 50;
      canvas.height = 50;
      const ctx = canvas.getContext('2d');
      const scale = Math.max(50 / img.width, 50 / img.height);
      const sw = 50 / scale;
      const sh = 50 / scale;
      const sx = (img.width - sw) / 2;
      const sy = (img.height - sh) / 2;
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, 50, 50);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.3);
      const b64 = dataUrl.split(',')[1];
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      resolve(bytes);
    };
    img.onerror = () => resolve(null);
    img.src = imageDataUrl;
  });
}

async function _appendThumbnails(coreBuf, customIds, customRamen) {
  const coreCompressed = await deflate(coreBuf);
  const coreB64Len = toBase64url(coreCompressed).length;
  const remainingB64 = URL_BUDGET - URL_PREFIX_ESTIMATE - coreB64Len;

  if (remainingB64 <= 10) return coreBuf;

  const binaryBudget = Math.floor(remainingB64 * 3 / 4);
  const thumbData = [];
  let thumbTotalBytes = 1;

  for (let i = 0; i < customIds.length; i++) {
    const cr = customRamen[customIds[i]];
    if (!cr || !cr.imageData) continue;
    const bytes = await compressShareThumbnail(cr.imageData);
    if (!bytes || bytes.length === 0 || bytes.length > 0xffff) continue;
    const cost = 1 + 2 + bytes.length;
    if (thumbTotalBytes + cost > binaryBudget) break;
    thumbData.push({ index: i, bytes });
    thumbTotalBytes += cost;
  }

  if (thumbData.length === 0) return coreBuf;

  const thumbSection = new Uint8Array(thumbTotalBytes);
  let tOff = 0;
  thumbSection[tOff++] = thumbData.length;
  for (const t of thumbData) {
    thumbSection[tOff++] = t.index;
    thumbSection[tOff++] = (t.bytes.length >> 8) & 0xff;
    thumbSection[tOff++] = t.bytes.length & 0xff;
    thumbSection.set(t.bytes, tOff);
    tOff += t.bytes.length;
  }

  const out = new Uint8Array(coreBuf.length + thumbSection.length);
  out.set(coreBuf);
  out.set(thumbSection, coreBuf.length);
  return out;
}

/* ---- Binary packing helpers ---- */

function writeString(view, offset, str) {
  const encoded = new TextEncoder().encode(str);
  const len = Math.min(encoded.length, 255);
  view[offset] = len;
  view.set(encoded.subarray(0, len), offset + 1);
  return offset + 1 + len;
}

function readString(view, offset) {
  const len = view[offset];
  const bytes = view.subarray(offset + 1, offset + 1 + len);
  return { value: new TextDecoder().decode(bytes), nextOffset: offset + 1 + len };
}

/* ---- Encode ---- */

export async function encode(name, rankedList, ratings, customRamen) {
  const dbEntries = [];
  const customEntries = [];
  const customIds = [];
  const order = [];

  for (const id of rankedList) {
    const rating = ratings[String(id)];
    if (!rating) continue;
    const flavor = rating.flavorRating || 1;
    const noodle = rating.noodleRating || 1;

    if (typeof id === 'string' && id.startsWith('c-')) {
      const cr = customRamen[id];
      if (!cr) continue;
      order.push(0x80 | customEntries.length);
      customEntries.push({ variety: cr.variety, brand: cr.brand, style: cr.style || '', country: cr.country || '', flavor, noodle });
      customIds.push(id);
    } else {
      order.push(dbEntries.length);
      dbEntries.push({ id: Number(id), flavor, noodle });
    }
  }

  let size = 1; // version
  const nameBytes = new TextEncoder().encode(name);
  size += 1 + nameBytes.length;
  size += 2; // db count
  size += dbEntries.length * 3;
  size += 1; // custom count
  for (const c of customEntries) {
    const vBytes = new TextEncoder().encode(c.variety);
    const bBytes = new TextEncoder().encode(c.brand);
    const cBytes = new TextEncoder().encode(c.country);
    size += 1 + vBytes.length + 1 + bBytes.length + 1 + 1 + cBytes.length + 1;
  }
  const canOrder = dbEntries.length <= 127 && customEntries.length <= 127;
  if (canOrder) size += order.length;

  const coreBuf = new Uint8Array(size);
  let off = 0;

  coreBuf[off++] = VERSION;

  off = writeString(coreBuf, off, name);

  coreBuf[off++] = (dbEntries.length >> 8) & 0xff;
  coreBuf[off++] = dbEntries.length & 0xff;

  for (const e of dbEntries) {
    coreBuf[off++] = (e.id >> 8) & 0xff;
    coreBuf[off++] = e.id & 0xff;
    coreBuf[off++] = ((e.flavor - 1) << 4) | (e.noodle - 1);
  }

  coreBuf[off++] = customEntries.length & 0xff;

  for (const c of customEntries) {
    off = writeString(coreBuf, off, c.variety);
    off = writeString(coreBuf, off, c.brand);
    coreBuf[off++] = Math.max(0, STYLE_ENUM.indexOf(c.style || 'Other'));
    off = writeString(coreBuf, off, c.country);
    coreBuf[off++] = ((c.flavor - 1) << 4) | (c.noodle - 1);
  }

  if (canOrder) {
    for (const o of order) coreBuf[off++] = o;
  }

  const finalBuf = customIds.length > 0
    ? await _appendThumbnails(coreBuf, customIds, customRamen)
    : coreBuf;

  const compressed = await deflate(finalBuf);
  return toBase64url(compressed);
}

/* ---- Decode ---- */

export async function decode(base64str) {
  const compressed = fromBase64url(base64str);
  const buf = await inflate(compressed);
  let off = 0;

  const version = buf[off++];
  if (version !== VERSION) throw new Error('Unsupported share version');

  const nameResult = readString(buf, off);
  off = nameResult.nextOffset;
  const name = nameResult.value;

  const dbCount = (buf[off] << 8) | buf[off + 1];
  off += 2;

  const dbEntries = [];

  for (let i = 0; i < dbCount; i++) {
    const id = (buf[off] << 8) | buf[off + 1];
    off += 2;
    const packed = buf[off++];
    const flavor = ((packed >> 4) & 0xf) + 1;
    const noodle = (packed & 0xf) + 1;
    dbEntries.push({ id, flavor, noodle, custom: false });
  }

  const customCount = buf[off++] || 0;
  const customEntries = [];

  for (let i = 0; i < customCount; i++) {
    const variety = readString(buf, off);
    off = variety.nextOffset;
    const brand = readString(buf, off);
    off = brand.nextOffset;
    const styleIdx = buf[off++];
    const country = readString(buf, off);
    off = country.nextOffset;
    const packed = buf[off++];
    const flavor = ((packed >> 4) & 0xf) + 1;
    const noodle = (packed & 0xf) + 1;

    customEntries.push({
      id: `shared-custom-${i}`,
      variety: variety.value,
      brand: brand.value,
      style: STYLE_ENUM[styleIdx] || 'Other',
      country: country.value,
      flavor,
      noodle,
      custom: true,
    });
  }

  const totalEntries = dbCount + customCount;

  if (off < buf.length) {
    const ordered = [];
    const orderEnd = Math.min(off + totalEntries, buf.length);
    while (off < orderEnd) {
      const b = buf[off++];
      if (b & 0x80) {
        const idx = b & 0x7f;
        if (idx < customEntries.length) ordered.push(customEntries[idx]);
      } else {
        if (b < dbEntries.length) ordered.push(dbEntries[b]);
      }
    }

    if (off < buf.length) {
      const thumbCount = buf[off++] || 0;
      for (let t = 0; t < thumbCount && off + 3 <= buf.length; t++) {
        const idx = buf[off++];
        const imgLen = (buf[off] << 8) | buf[off + 1];
        off += 2;
        if (off + imgLen > buf.length) break;
        const imgBytes = buf.subarray(off, off + imgLen);
        off += imgLen;
        let bin = '';
        for (let i = 0; i < imgBytes.length; i++) bin += String.fromCharCode(imgBytes[i]);
        const dataUrl = 'data:image/jpeg;base64,' + btoa(bin);
        if (idx < customEntries.length) {
          customEntries[idx].imageData = dataUrl;
        }
      }
    }

    if (ordered.length > 0) return { name, entries: ordered };
  }

  return { name, entries: [...dbEntries, ...customEntries] };
}
