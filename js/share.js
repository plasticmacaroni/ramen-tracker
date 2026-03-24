const VERSION = 1;
const STYLE_ENUM = ['Pack', 'Cup', 'Bowl', 'Tray', 'Other'];

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

  for (const id of rankedList) {
    const rating = ratings[String(id)];
    if (!rating) continue;
    const flavor = rating.flavorRating || 1;
    const noodle = rating.noodleRating || 1;

    if (typeof id === 'string' && id.startsWith('c-')) {
      const cr = customRamen[id];
      if (!cr) continue;
      customEntries.push({ variety: cr.variety, brand: cr.brand, style: cr.style || '', country: cr.country || '', flavor, noodle });
    } else {
      dbEntries.push({ id: Number(id), flavor, noodle });
    }
  }

  // Calculate buffer size
  let size = 1; // version
  const nameBytes = new TextEncoder().encode(name);
  size += 1 + nameBytes.length; // name length-prefixed
  size += 2; // db count
  size += dbEntries.length * 3;
  size += 1; // custom count
  for (const c of customEntries) {
    const vBytes = new TextEncoder().encode(c.variety);
    const bBytes = new TextEncoder().encode(c.brand);
    const cBytes = new TextEncoder().encode(c.country);
    size += 1 + vBytes.length + 1 + bBytes.length + 1 + 1 + cBytes.length + 1;
  }

  const buf = new Uint8Array(size);
  let off = 0;

  buf[off++] = VERSION;

  off = writeString(buf, off, name);

  // DB entries (big-endian ID + packed flavor/noodle)
  buf[off++] = (dbEntries.length >> 8) & 0xff;
  buf[off++] = dbEntries.length & 0xff;

  for (const e of dbEntries) {
    buf[off++] = (e.id >> 8) & 0xff;
    buf[off++] = e.id & 0xff;
    buf[off++] = ((e.flavor - 1) << 4) | (e.noodle - 1);
  }

  // Custom entries
  buf[off++] = customEntries.length & 0xff;

  for (const c of customEntries) {
    off = writeString(buf, off, c.variety);
    off = writeString(buf, off, c.brand);
    buf[off++] = Math.max(0, STYLE_ENUM.indexOf(c.style || 'Other'));
    off = writeString(buf, off, c.country);
    buf[off++] = ((c.flavor - 1) << 4) | (c.noodle - 1);
  }

  const compressed = await deflate(buf);
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

  const entries = [];

  for (let i = 0; i < dbCount; i++) {
    const id = (buf[off] << 8) | buf[off + 1];
    off += 2;
    const packed = buf[off++];
    const flavor = ((packed >> 4) & 0xf) + 1;
    const noodle = (packed & 0xf) + 1;
    entries.push({ id, flavor, noodle, custom: false });
  }

  const customCount = buf[off++] || 0;

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

    entries.push({
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

  return { name, entries };
}
