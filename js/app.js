import * as data from './data.js';
import * as storage from './storage.js';
import * as share from './share.js';
import * as ui from './ui.js';

let tabs, views;
let currentTab = 'rate';
let suppressHashUpdate = false;

function refreshTabsAndViews() {
  tabs = document.querySelectorAll('#tab-nav .tab-btn:not(.hidden)');
  views = document.querySelectorAll('#app-main .view:not(.hidden)');
}

/* ---- URL Hash State ---- */

const FILTER_ELEMENTS = {
  rate: { q: 'rate-search' },
  collection: {
    q: 'collection-search', sort: 'collection-sort',
    brand: 'collection-brand', country: 'collection-country', style: 'collection-style',
  },
  wishlist: {
    q: 'wishlist-search',
    brand: 'wishlist-brand', country: 'wishlist-country', style: 'wishlist-style',
  },
  discover: {
    q: 'discover-search', sort: 'discover-sort',
    brand: 'discover-brand', country: 'discover-country', style: 'discover-style',
    hideRated: 'discover-hide-rated',
  },
};

function readHash() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) return {};
  const params = {};
  for (const part of raw.split('&')) {
    const [k, ...rest] = part.split('=');
    params[decodeURIComponent(k)] = decodeURIComponent(rest.join('='));
  }
  return params;
}

function writeHash() {
  if (suppressHashUpdate) return;
  const params = { tab: currentTab };

  const elMap = FILTER_ELEMENTS[currentTab];
  if (elMap) {
    for (const [key, id] of Object.entries(elMap)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const val = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
      if (val) params[key] = val;
    }
  }

  if (currentTab === 'discover') {
    const p = ui.getDiscoverPageCount();
    if (p > 1) params.p = String(p);
  }

  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  }
  const newHash = parts.join('&');
  if (location.hash.replace(/^#/, '') !== newHash) {
    history.replaceState(null, '', '#' + newHash);
  }
}

function getValidTabs() {
  const base = ['rate', 'collection', 'wishlist', 'discover'];
  if (ui.getSharedData()) base.push('shared');
  return base;
}

function restoreFromHash() {
  const params = readHash();
  const validTabs = getValidTabs();
  const tab = params.tab && validTabs.includes(params.tab) ? params.tab : 'rate';

  const elMap = FILTER_ELEMENTS[tab];
  if (elMap) {
    suppressHashUpdate = true;
    for (const [key, id] of Object.entries(elMap)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const val = params[key] || '';
      if (el.type === 'checkbox') {
        el.checked = val === '1';
      } else {
        el.value = val;
      }
    }
    suppressHashUpdate = false;
  }

  const restorePages = tab === 'discover' ? (parseInt(params.p) || 0) : 0;
  switchTab(tab, true, restorePages);

  if (tab === 'rate' && params.q) {
    document.getElementById('rate-search').dispatchEvent(new Event('input'));
  }

}

function observeFilterChanges() {
  for (const [, elMap] of Object.entries(FILTER_ELEMENTS)) {
    for (const [, id] of Object.entries(elMap)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const evt = el.type === 'checkbox' ? 'change'
        : el.tagName === 'SELECT' ? 'change' : 'input';
      el.addEventListener(evt, () => writeHash());
    }
  }
}

/* ---- Tab Switching ---- */

function switchTab(tab, skipHash, restorePages) {
  currentTab = tab;
  refreshTabsAndViews();

  tabs.forEach(t => {
    const isActive = t.dataset.tab === tab;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
    t.setAttribute('tabindex', isActive ? '0' : '-1');
  });

  // Include hidden shared view section in toggle logic
  document.querySelectorAll('#app-main .view').forEach(v => {
    const isActive = v.id === `view-${tab}`;
    v.classList.toggle('active', isActive);
    v.setAttribute('aria-hidden', isActive ? 'false' : 'true');
  });

  refreshView(tab, restorePages);
  if (!skipHash) writeHash();
}

function refreshView(tab, restorePages) {
  switch (tab) {
    case 'collection':
      ui.renderCollection();
      break;
    case 'wishlist':
      ui.renderWishlist();
      break;
    case 'discover':
      ui.renderDiscover(restorePages);
      break;
    case 'shared':
      ui.renderSharedCollection();
      break;
  }
}

ui.setRefreshCallback(() => refreshView(currentTab));
ui.onDiscoverPageChange(() => writeHash());

function setupTabListeners() {
  refreshTabsAndViews();
  document.querySelectorAll('#tab-nav .tab-btn').forEach(t => {
    t.addEventListener('click', () => {
      if (t.classList.contains('hidden')) return;
      switchTab(t.dataset.tab);
    });
    t.addEventListener('keydown', e => {
      const order = getValidTabs();
      const idx = order.indexOf(t.dataset.tab);
      if (idx < 0) return;
      let next = -1;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % order.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + order.length) % order.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = order.length - 1;
      if (next >= 0) {
        e.preventDefault();
        const btn = document.getElementById(`tab-${order[next]}`);
        if (btn && !btn.classList.contains('hidden')) { btn.focus(); switchTab(order[next]); }
      }
    });
  });
}

window.addEventListener('hashchange', async () => {
  const hasShare = await handleShareParam();
  if (hasShare) {
    switchTab('shared', true);
  } else {
    restoreFromHash();
  }
});

/* ---- Share Detection ---- */

const SHARE_SESSION_KEY = 'ramen_shared';

async function handleShareParam() {
  const params = readHash();
  const payload = params.share || null;

  if (payload) {
    try {
      const decoded = await share.decode(payload);
      sessionStorage.setItem(SHARE_SESSION_KEY, payload);
      ui.showSharedView(decoded);
      refreshTabsAndViews();
      writeHash();
      return true;
    } catch (err) {
      console.error('Failed to decode shared rankings:', err);
      return false;
    }
  }

  const cached = sessionStorage.getItem(SHARE_SESSION_KEY);
  if (cached) {
    try {
      const decoded = await share.decode(cached);
      ui.showSharedView(decoded);
      refreshTabsAndViews();
      return true;
    } catch { sessionStorage.removeItem(SHARE_SESSION_KEY); }
  }

  return false;
}

ui.setShareDismissCallback(() => {
  sessionStorage.removeItem(SHARE_SESSION_KEY);
  refreshTabsAndViews();
  switchTab('rate');
});

/* ---- Init ---- */

async function init() {
  storage.load();
  await data.loadRamenData();

  ui.initRateView();
  ui.initRatingModal();
  ui.initCustomRamenModal();
  ui.initCollectionView();
  ui.initWishlistView();
  ui.initDiscoverView();
  ui.initSettingsModal();
  ui.initShareModal();
  ui.initSharedView();
  ui.initBanner();
  ui.initGoToButtons();
  ui.initBarcodeScanner();

  setupTabListeners();
  observeFilterChanges();

  const hasShare = await handleShareParam();
  if (hasShare) {
    switchTab('shared', true);
  } else {
    restoreFromHash();
  }

  syncSearchClearButtons();

  ui.checkBackupBanner();
  ui.resumePendingInsertion();
  migrateCustomImages();
}

function syncSearchClearButtons() {
  document.querySelectorAll('.search-box').forEach(box => {
    const input = box.querySelector('input[type="text"]');
    const btn = box.querySelector('.search-clear');
    if (input && btn) btn.classList.toggle('hidden', !input.value.trim());
  });
}

async function migrateCustomImages() {
  const customs = storage.getCustomRamen();
  let changed = false;
  for (const id of Object.keys(customs)) {
    const ramen = customs[id];
    if (!ramen.imageData) continue;
    if (ramen.imageData.startsWith('data:image/webp')) continue;
    try {
      const compressed = await ui.compressExistingImage(ramen.imageData);
      if (compressed !== ramen.imageData) {
        ramen.imageData = compressed;
        changed = true;
      }
    } catch { /* skip broken images */ }
  }
  if (changed) storage.save();
}

init();

window.addEventListener('pageshow', () => {
  syncSearchClearButtons();
  requestAnimationFrame(syncSearchClearButtons);
});

const scrollTopBtn = document.getElementById('scroll-top');
let scrollTopTick = false;
window.addEventListener('scroll', () => {
  if (scrollTopTick) return;
  scrollTopTick = true;
  requestAnimationFrame(() => {
    scrollTopBtn.classList.toggle('hidden', window.scrollY < 400);
    scrollTopTick = false;
  });
}, { passive: true });
scrollTopBtn.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});
