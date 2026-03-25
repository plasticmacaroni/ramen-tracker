import * as storage from './storage.js';

let allRamen = [];
let countries = [];
let styles = [];
let brands = [];
let barcodeMap = {};

export async function loadRamenData() {
  try {
    const [ramenRes, popRes, barcodeRes, urlsRes] = await Promise.all([
      fetch('data/ramen.json'),
      fetch('data/popularity.json'),
      fetch('data/barcodes.json'),
      fetch('data/urls.json'),
    ]);
    allRamen = ramenRes.ok ? await ramenRes.json() : [];
    const popMap = popRes.ok ? await popRes.json() : {};
    const urlMap = urlsRes.ok ? await urlsRes.json() : {};
    for (const r of allRamen) {
      const pop = popMap[r.id];
      if (pop) r.popularity = pop;
      const directUrl = urlMap[r.id];
      if (directUrl) r.url = directUrl;
    }
    const barcodeList = barcodeRes.ok ? await barcodeRes.json() : [];
    barcodeMap = {};
    for (const entry of barcodeList) {
      const id = entry.id;
      const codes = entry.barcodes || [];
      if (codes.length) {
        for (const raw of codes) {
          const code = String(raw).trim();
          if (!code) continue;
          barcodeMap[code] = id;
          const ean13 = _toEan13(code);
          if (ean13 && ean13 !== code) barcodeMap[ean13] = id;
        }
      } else {
        for (const [key, val] of Object.entries(entry)) {
          if (key === 'id' || key === 'barcodes') continue;
          const code = String(val).trim();
          barcodeMap[code] = id;
          const ean13 = _toEan13(code);
          if (ean13 && ean13 !== code) barcodeMap[ean13] = id;
        }
      }
    }
  } catch {
    allRamen = [];
  }

  for (const cr of storage.getAllCustomRamenList()) {
    if (cr.barcode) {
      const bc = String(cr.barcode).trim();
      if (bc) {
        barcodeMap[bc] = cr.id;
        const ean13 = _toEan13(bc);
        if (ean13 && ean13 !== bc) barcodeMap[ean13] = cr.id;
      }
    }
  }

  const combined = [...allRamen, ...storage.getAllCustomRamenList()];

  countries = [...new Set(combined.map(r => r.country).filter(Boolean))].sort();
  styles = [...new Set(combined.map(r => r.style).filter(Boolean))].sort();

  const brandSet = new Set();
  for (const r of combined) {
    if (!r.brand) continue;
    if (r.brand.includes('/')) {
      for (const part of r.brand.split('/')) {
        const trimmed = part.trim();
        if (trimmed) brandSet.add(trimmed);
      }
    } else {
      brandSet.add(r.brand);
    }
  }
  brands = [...brandSet].sort();

  return allRamen;
}

export function getAllRamen() { return allRamen; }
export function getCountries() { return countries; }
export function getStyles() { return styles; }
export function getBrands() { return brands; }

export function brandMatches(ramenBrand, filterBrand) {
  if (!filterBrand) return true;
  if (ramenBrand === filterBrand) return true;
  if (ramenBrand && ramenBrand.includes('/')) {
    return ramenBrand.split('/').some(p => p.trim() === filterBrand);
  }
  return false;
}

export function getRamenById(id) {
  if (typeof id === 'string' && id.startsWith('c-')) {
    return storage.getCustomRamenById(id);
  }
  return allRamen.find(r => r.id === id);
}

function _toEan13(code) {
  if (/^\d{12}$/.test(code)) return '0' + code;
  if (/^\d{13}$/.test(code)) return code;
  return null;
}

export function registerBarcode(code, id) {
  const bc = String(code).trim();
  if (!bc) return;
  barcodeMap[bc] = id;
  const ean13 = _toEan13(bc);
  if (ean13 && ean13 !== bc) barcodeMap[ean13] = id;
}

export function lookupBarcode(code) {
  const raw = String(code).trim();
  let ramenId = barcodeMap[raw];
  if (ramenId == null) {
    const ean13 = _toEan13(raw);
    if (ean13) ramenId = barcodeMap[ean13];
  }
  if (ramenId != null) return getRamenById(ramenId);
  return null;
}

export function searchRamen(query, list = allRamen) {
  if (!query || query.length < 2) return [];
  const trimmed = query.trim();
  if (/^\d{8,14}$/.test(trimmed)) {
    const match = lookupBarcode(trimmed);
    if (match) return [match];
  }
  const numId = /^\d+$/.test(trimmed) ? Number(trimmed) : null;
  if (numId !== null) {
    const exact = list.filter(r => r.id === numId);
    if (exact.length) return exact;
  }
  const q = query.toLowerCase();
  const terms = q.split(/\s+/);
  return list.filter(r => {
    const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
    return terms.every(t => haystack.includes(t));
  }).slice(0, 50);
}

export function searchAll(query) {
  if (!query || query.length < 2) return [];
  const dbResults = searchRamen(query);
  const customList = storage.getAllCustomRamenList();
  const customResults = searchRamen(query, customList);
  return [...customResults, ...dbResults].slice(0, 50);
}

/** Least-popular order: items with a popularity score first (lowest first), unrated last (same as badge: no score when !pop). */
export function comparePopularAsc(a, b) {
  const rated = (r) => Number(r.popularity) > 0;
  const ra = rated(a);
  const rb = rated(b);
  if (ra !== rb) return ra ? -1 : 1;
  if (!ra) return 0;
  return a.popularity - b.popularity;
}

export function filterAndSort(options = {}) {
  const {
    search = '',
    brand = '',
    country = '',
    style = '',
    sort = 'stars-desc',
    hideRated = false,
    ratedIds = new Set(),
  } = options;

  let list = [...allRamen, ...storage.getAllCustomRamenList()];

  if (search && search.length >= 2) {
    const trimmed = search.trim();
    if (/^\d{8,14}$/.test(trimmed)) {
      const match = lookupBarcode(trimmed);
      if (match) { list = [match]; }
      else { list = []; }
    } else if (/^\d+$/.test(trimmed)) {
      const numId = Number(trimmed);
      list = list.filter(r => r.id === numId);
    } else {
      const terms = search.toLowerCase().split(/\s+/);
      list = list.filter(r => {
        const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
        return terms.every(t => haystack.includes(t));
      });
    }
  }

  if (brand) list = list.filter(r => brandMatches(r.brand, brand));
  if (country) list = list.filter(r => r.country === country);
  if (style) list = list.filter(r => r.style === style);
  if (hideRated) list = list.filter(r => !ratedIds.has(r.id));

  switch (sort) {
    case 'stars-desc':
      list.sort((a, b) => (b.stars || 0) - (a.stars || 0));
      break;
    case 'stars-asc':
      list.sort((a, b) => (a.stars || 0) - (b.stars || 0));
      break;
    case 'brand':
      list.sort((a, b) => (a.brand || '').localeCompare(b.brand || ''));
      break;
    case 'country':
      list.sort((a, b) => (a.country || '').localeCompare(b.country || ''));
      break;
    case 'newest':
      list.sort((a, b) => (typeof b.id === 'number' ? b.id : 0) - (typeof a.id === 'number' ? a.id : 0));
      break;
    case 'popular-desc':
      list.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
      break;
    case 'popular-asc':
      list.sort(comparePopularAsc);
      break;
  }

  return list;
}
