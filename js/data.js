import * as storage from './storage.js';

let allRamen = [];
let countries = [];
let styles = [];
let brands = [];

export async function loadRamenData() {
  try {
    const res = await fetch('data/ramen.json');
    if (!res.ok) {
      allRamen = [];
    } else {
      allRamen = await res.json();
    }
  } catch {
    allRamen = [];
  }

  countries = [...new Set(allRamen.map(r => r.country).filter(Boolean))].sort();
  styles = [...new Set(allRamen.map(r => r.style).filter(Boolean))].sort();
  brands = [...new Set(allRamen.map(r => r.brand).filter(Boolean))].sort();

  return allRamen;
}

export function getAllRamen() { return allRamen; }
export function getCountries() { return countries; }
export function getStyles() { return styles; }
export function getBrands() { return brands; }

export function getRamenById(id) {
  if (typeof id === 'string' && id.startsWith('c-')) {
    return storage.getCustomRamenById(id);
  }
  return allRamen.find(r => r.id === id);
}

export function searchRamen(query, list = allRamen) {
  if (!query || query.length < 2) return [];
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

  let list = [...allRamen];

  if (search && search.length >= 2) {
    const terms = search.toLowerCase().split(/\s+/);
    list = list.filter(r => {
      const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
      return terms.every(t => haystack.includes(t));
    });
  }

  if (brand) list = list.filter(r => r.brand === brand);
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
      list.sort((a, b) => b.id - a.id);
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
