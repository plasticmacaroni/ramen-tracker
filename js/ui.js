import * as data from './data.js';
import * as storage from './storage.js';
import * as ranking from './ranking.js';
import * as share from './share.js';

const FLAVOR_LABELS = ['', 'Gross...', 'Mid', 'Average', 'Tasty!', 'Shlurp!'];
const NOODLE_LABELS = ['', 'Bad...', 'Mid', 'Average', 'Great!', 'Quality!'];
const ITEMS_PER_PAGE = 40;

/* ---- Accessibility: focus trap for modals ---- */
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
let _prevFocus = null;

function trapFocus(modalEl) {
  _prevFocus = document.activeElement;
  const firstFocusable = modalEl.querySelector(FOCUSABLE);
  if (firstFocusable) firstFocusable.focus();

  modalEl._trapHandler = e => {
    if (e.key !== 'Tab') return;
    const focusable = [...modalEl.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  modalEl.addEventListener('keydown', modalEl._trapHandler);
}

function releaseFocus(modalEl) {
  if (modalEl._trapHandler) {
    modalEl.removeEventListener('keydown', modalEl._trapHandler);
    delete modalEl._trapHandler;
  }
  if (_prevFocus && _prevFocus.focus) _prevFocus.focus();
  _prevFocus = null;
}

function setupModalA11y(modalEl, closeFn) {
  modalEl.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); closeFn(); }
  });
}

function announce(msg) {
  const el = document.getElementById('a11y-announce');
  if (el) { el.textContent = ''; requestAnimationFrame(() => { el.textContent = msg; }); }
}

let discoverPage = 0;
let discoverFiltered = [];
let discoverObserver = null;

/* ---- Letter Grade System ---- */

function starsToGrade(stars) {
  if (stars == null || stars === '' || isNaN(stars)) return null;
  const pct = (stars / 5) * 100;
  return pctToGrade(pct);
}

function scoreToGrade(score) {
  if (score == null) return null;
  const pct = (score / 10) * 100;
  return pctToGrade(pct);
}

function pctToGrade(pct) {
  if (pct >= 97) return 'A+';
  if (pct >= 93) return 'A';
  if (pct >= 90) return 'A-';
  if (pct >= 87) return 'B+';
  if (pct >= 83) return 'B';
  if (pct >= 80) return 'B-';
  if (pct >= 77) return 'C+';
  if (pct >= 73) return 'C';
  if (pct >= 70) return 'C-';
  if (pct >= 67) return 'D+';
  if (pct >= 63) return 'D';
  if (pct >= 60) return 'D-';
  return 'F';
}

function gradeClass(grade) {
  if (!grade) return '';
  const letter = grade.charAt(0);
  return `grade-${letter.toLowerCase()}`;
}

/* ---- Popularity Badge ---- */

const POP_TIERS = { a: -45, b: -22, c: 0, d: 22, f: 45 };
const POP_LABELS = { a: 'Very popular', b: 'Popular', c: 'Moderate', d: 'Niche', f: 'Obscure' };

function popularityTier(pop) {
  if (!pop) return null;
  const log = Math.log10(pop);
  const normalized = Math.max(0, Math.min(1, (log - 2) / 4));
  if (normalized >= 0.8) return 'a';
  if (normalized >= 0.6) return 'b';
  if (normalized >= 0.4) return 'c';
  if (normalized >= 0.2) return 'd';
  return 'f';
}

function popularityBadge(ramen) {
  const tier = popularityTier(ramen.popularity);
  if (!tier) return '';
  const angle = POP_TIERS[tier];
  return `<span class="card-pop-badge grade-${tier}" title="${POP_LABELS[tier]}">`
    + `<svg width="16" height="14" viewBox="0 0 16 14" style="transform:rotate(${angle}deg)">`
    + `<polyline points="1,12 5,5 8,8 10.5,4.7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`
    + `<polygon points="14,1 10,3 13.2,5.4" fill="currentColor"/>`
    + `</svg></span>`;
}

/* ---- Flag Emoji Lookup ---- */

const COUNTRY_FLAGS = {
  'Japan': '\u{1F1EF}\u{1F1F5}', 'South Korea': '\u{1F1F0}\u{1F1F7}',
  'China': '\u{1F1E8}\u{1F1F3}', 'Taiwan': '\u{1F1F9}\u{1F1FC}',
  'Thailand': '\u{1F1F9}\u{1F1ED}', 'Indonesia': '\u{1F1EE}\u{1F1E9}',
  'Malaysia': '\u{1F1F2}\u{1F1FE}', 'Singapore': '\u{1F1F8}\u{1F1EC}',
  'Vietnam': '\u{1F1FB}\u{1F1F3}', 'Philippines': '\u{1F1F5}\u{1F1ED}',
  'India': '\u{1F1EE}\u{1F1F3}', 'United States': '\u{1F1FA}\u{1F1F8}',
  'Canada': '\u{1F1E8}\u{1F1E6}', 'Mexico': '\u{1F1F2}\u{1F1FD}',
  'Germany': '\u{1F1E9}\u{1F1EA}', 'United Kingdom': '\u{1F1EC}\u{1F1E7}',
  'Australia': '\u{1F1E6}\u{1F1FA}', 'Nigeria': '\u{1F1F3}\u{1F1EC}',
  'Brazil': '\u{1F1E7}\u{1F1F7}', 'Hong Kong': '\u{1F1ED}\u{1F1F0}',
  'Myanmar': '\u{1F1F2}\u{1F1F2}', 'Nepal': '\u{1F1F3}\u{1F1F5}',
  'Pakistan': '\u{1F1F5}\u{1F1F0}', 'Bangladesh': '\u{1F1E7}\u{1F1E9}',
  'Cambodia': '\u{1F1F0}\u{1F1ED}', 'Fiji': '\u{1F1EB}\u{1F1EF}',
  'Netherlands': '\u{1F1F3}\u{1F1F1}', 'Sweden': '\u{1F1F8}\u{1F1EA}',
  'Italy': '\u{1F1EE}\u{1F1F9}', 'France': '\u{1F1EB}\u{1F1F7}',
  'Poland': '\u{1F1F5}\u{1F1F1}', 'Hungary': '\u{1F1ED}\u{1F1FA}',
  'Colombia': '\u{1F1E8}\u{1F1F4}', 'Peru': '\u{1F1F5}\u{1F1EA}',
  'Chile': '\u{1F1E8}\u{1F1F1}', 'Estonia': '\u{1F1EA}\u{1F1EA}',
  'Finland': '\u{1F1EB}\u{1F1EE}', 'Ghana': '\u{1F1EC}\u{1F1ED}',
  'Sarawak': '\u{1F1F2}\u{1F1FE}', 'USA': '\u{1F1FA}\u{1F1F8}',
};

function flag(country) {
  return COUNTRY_FLAGS[country] || '\u{1F30F}';
}

/* ---- Card Renderers ---- */

const BRAND_LOGO_EXTS = ['png', 'svg', 'webp', 'jpg', 'avif', 'jpeg', 'gif', 'bmp', 'ico', 'jfif', 'tiff', 'tif'];

function brandLogoPath(brand, ext = 'png') {
  return `images/brand/${brand.toLowerCase()}.${ext}`;
}

const _logoBgCache = {};

function _analyzeLogoBg(img) {
  const key = img.src;
  if (key in _logoBgCache) return _logoBgCache[key];

  try {
    const canvas = document.createElement('canvas');
    const size = 64;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, size, size);
    const { data } = ctx.getImageData(0, 0, size, size);

    let hasTransparent = false;
    let rSum = 0, gSum = 0, bSum = 0, count = 0;

    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 128) {
        hasTransparent = true;
      } else {
        rSum += data[i];
        gSum += data[i + 1];
        bSum += data[i + 2];
        count++;
      }
    }

    if (!hasTransparent || count === 0) {
      _logoBgCache[key] = null;
      return null;
    }

    const r = Math.round(rSum / count);
    const g = Math.round(gSum / count);
    const b = Math.round(bSum / count);

    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

    let bgR, bgG, bgB, bgA;
    if (luminance < 0.4) {
      bgR = 240; bgG = 240; bgB = 240; bgA = 0.92;
    } else {
      bgR = Math.min(255, r + Math.round((255 - r) * 0.75));
      bgG = Math.min(255, g + Math.round((255 - g) * 0.75));
      bgB = Math.min(255, b + Math.round((255 - b) * 0.75));
      bgA = 0.15;
    }

    const result = `rgba(${bgR},${bgG},${bgB},${bgA})`;
    _logoBgCache[key] = result;
    return result;
  } catch {
    _logoBgCache[key] = null;
    return null;
  }
}

function _applyLogoBg(img) {
  const wrap = img.closest('.brand-logo-wrap');
  if (!wrap) return;
  const bg = _analyzeLogoBg(img);
  if (bg) wrap.style.background = bg;
}
window.__applyLogoBg = _applyLogoBg;

window.__brandLogoFallback = function (img) {
  const idx = (parseInt(img.dataset.extIdx) || 0) + 1;
  const brand = img.dataset.brand;
  if (idx < BRAND_LOGO_EXTS.length) {
    img.dataset.extIdx = idx;
    img.src = brandLogoPath(brand, BRAND_LOGO_EXTS[idx]);
  } else {
    img.parentElement.style.display = 'none';
    img.parentElement.nextElementSibling.style.display = '';
  }
};

function brandHtml(brand) {
  if (!brand) return '';
  const src = brandLogoPath(brand);
  const escaped = brand.replace(/"/g, '&quot;');
  return `<span class="brand-logo-wrap"><img src="${src}" alt="${escaped}" class="brand-logo" data-brand="${escaped}" data-ext-idx="0" crossorigin="anonymous" onload="window.__applyLogoBg(this)" onerror="window.__brandLogoFallback(this)"></span><span class="brand-text" style="display:none">${brand}</span>`;
}

function ramenImage(ramen) {
  if (ramen.custom && ramen.imageData) {
    return `<img src="${ramen.imageData}" alt="${ramen.variety}" loading="lazy">`;
  }
  return `<img src="images/ramen/${ramen.id}.webp" alt="${ramen.variety}" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'placeholder-icon',role:'img',ariaLabel:'No photo available',textContent:'🍜'}))">`;
}

export function renderRamenCard(ramen, options = {}) {
  const { showUserScore = false, showStars = true, clickable = true, hideRaterGrade = false, showWishlistBadge = false } = options;
  const rating = storage.getRating(ramen.id);
  const isRated = !!rating;
  const score = storage.getScore(ramen.id);
  const rank = storage.getRank(ramen.id);

  const el = document.createElement('div');
  el.className = 'ramen-card';
  el.setAttribute('role', 'listitem');
  if (isRated) el.classList.add('card-user-rated');
  if (clickable) {
    el.dataset.ramenId = ramen.id;
    el.setAttribute('tabindex', '0');
    el.setAttribute('role', 'button');
  }

  // Build accessible label
  const a11yParts = [ramen.variety, ramen.brand];
  if (ramen.country) a11yParts.push(ramen.country);
  if (ramen.style) a11yParts.push(ramen.style);

  let scoreHtml = '';
  if (showUserScore && rank !== null) {
    const grade = scoreToGrade(score);
    scoreHtml = `<div class="card-score ${gradeClass(grade)}" title="Your grade: ${grade}, ranked number ${rank}"><span>${grade}</span><span class="score-rank">#${rank}</span></div>`;
    a11yParts.push(`Your grade: ${grade}, rank ${rank}`);
  }

  let tiersHtml = '';
  if (rating) {
    tiersHtml = `
      <span class="badge badge-tier" data-tier="${rating.flavorRating}" title="Flavor: ${FLAVOR_LABELS[rating.flavorRating]}"><span class="badge-label">Flavor:</span> ${FLAVOR_LABELS[rating.flavorRating]}</span>
      <span class="badge badge-tier" data-tier="${rating.noodleRating}" title="Noodles/Ingredients: ${NOODLE_LABELS[rating.noodleRating]}"><span class="badge-label">Noodles:</span> ${NOODLE_LABELS[rating.noodleRating]}</span>
    `;
    a11yParts.push(`Flavor: ${FLAVOR_LABELS[rating.flavorRating]}, Noodles/Ingredients: ${NOODLE_LABELS[rating.noodleRating]}`);
  }

  const shouldHideGrade = hideRaterGrade && storage.getHideRaterScore();
  const starGrade = starsToGrade(ramen.stars);
  const gradeOverlay = showStars && starGrade && !ramen.custom && !shouldHideGrade
    ? `<span class="card-rater-grade ${gradeClass(starGrade)}" title="Ramen Rater grade: ${starGrade} (${ramen.stars} stars)">${starGrade}</span>`
    : '';
  if (showStars && starGrade && !ramen.custom && !shouldHideGrade) {
    a11yParts.push(`Ramen Rater grade: ${starGrade}`);
  }
  const popTier = popularityTier(ramen.popularity);
  if (popTier) {
    a11yParts.push(`Popularity: ${POP_LABELS[popTier]}`);
  }

  const customBadge = ramen.custom
    ? '<span class="badge badge-custom" title="Custom entry you added">Custom</span>'
    : '';
  if (ramen.custom) a11yParts.push('Custom entry');

  const ratedBadge = isRated && !showUserScore && !ramen.custom
    ? '<span class="badge badge-rated" title="You have rated this ramen">RATED</span>'
    : '';
  if (isRated && !showUserScore) a11yParts.push('Rated');

  const wishlisted = !isRated && (showWishlistBadge || showStars) && storage.isWishlisted(ramen.id);
  const wishlistBadge = wishlisted
    ? '<span class="badge badge-wishlist" title="On your Want to Try list">&#x2661; Want to Try</span>'
    : '';
  if (wishlisted) a11yParts.push('Want to Try');

  el.setAttribute('aria-label', a11yParts.join(', '));
  el.setAttribute('title', a11yParts.join(' · '));

  el.innerHTML = `
    <div class="card-image">${ramenImage(ramen)}${gradeOverlay}${popularityBadge(ramen)}</div>
    <div class="card-body">
      <div class="card-variety">${ramen.variety}</div>
      <div class="card-brand">${brandHtml(ramen.brand)}</div>
      <div class="card-meta">
        ${customBadge}
        ${ramen.style ? `<span class="badge badge-style" title="Style: ${ramen.style}">${ramen.style}</span>` : ''}
        ${tiersHtml}
        ${ratedBadge}
        ${wishlistBadge}
      </div>
      <div class="card-country">${flag(ramen.country)} ${ramen.country || 'Unknown'}</div>
    </div>
    ${scoreHtml}
  `;

  return el;
}

function renderCompareCard(ramen, targetEl) {
  const rating = storage.getRating(ramen.id);
  let tiersHtml = '';
  if (rating) {
    tiersHtml = `
      <span class="badge badge-tier" data-tier="${rating.flavorRating}"><span class="badge-label">Flavor:</span> ${FLAVOR_LABELS[rating.flavorRating]}</span>
      <span class="badge badge-tier" data-tier="${rating.noodleRating}"><span class="badge-label">Noodles:</span> ${NOODLE_LABELS[rating.noodleRating]}</span>
    `;
  }

  targetEl.innerHTML = `
    <div class="card-img">${ramenImage(ramen)}</div>
    <div class="card-name">${ramen.variety}</div>
    <div class="card-brand-small">${ramen.brand}</div>
    <div class="card-meta" style="justify-content:center">${tiersHtml}</div>
  `;
  targetEl.dataset.ramenId = ramen.id;
  targetEl.setAttribute('aria-label', `Choose ${ramen.variety} by ${ramen.brand}`);
  targetEl.setAttribute('title', `${ramen.variety} — ${ramen.brand}`);
}

/* ---- Rate View ---- */

export function initRateView() {
  const searchInput = document.getElementById('rate-search');
  const clearBtn = document.getElementById('rate-search-clear');
  const results = document.getElementById('rate-results');
  const welcome = document.getElementById('rate-welcome');

  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    clearBtn.classList.toggle('hidden', !q);

    if (q.length < 2) {
      results.innerHTML = '';
      welcome.classList.remove('hidden');
      return;
    }

    welcome.classList.add('hidden');
    const found = data.searchAll(q);
    results.innerHTML = '';

    if (found.length === 0) {
      results.innerHTML = '<div class="empty-state"><p>No ramen found</p></div>';
      announce('No ramen found');
      return;
    }

    found.forEach(r => {
      const card = renderRamenCard(r, { showStars: true, showUserScore: false, hideRaterGrade: true });
      card.addEventListener('click', () => openRatingModal(r));
      card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRatingModal(r); } });
      results.appendChild(card);
    });
    announce(`${found.length} ramen found`);
  });

  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchInput.focus();
    searchInput.dispatchEvent(new Event('input'));
  });

  document.getElementById('rate-add-custom').addEventListener('click', (e) => {
    e.preventDefault();
    const q = searchInput.value.trim();
    openCustomRamenModal(q);
  });
}

/* ---- Rating Modal ---- */

let currentRatingRamen = null;
let selectedFlavor = 0;
let selectedNoodle = 0;

export function openRatingModal(ramen) {
  currentRatingRamen = ramen;
  selectedFlavor = 0;
  selectedNoodle = 0;

  const modal = document.getElementById('modal-rate');
  document.getElementById('rating-ramen-name').textContent = ramen.variety;
  document.getElementById('rating-ramen-meta').textContent = `${ramen.brand} · ${flag(ramen.country)} ${ramen.country || ''}`;
  const headerImg = document.getElementById('rating-header-image');
  headerImg.innerHTML = ramenImage(ramen);
  headerImg.style.cursor = 'zoom-in';

  const detailsEl = document.getElementById('rating-details');
  const creditEl = document.getElementById('rating-ramen-credit');
  const deleteBtn = document.getElementById('rating-delete-custom');

  const detailParts = [];
  if (ramen.style) detailParts.push(`<span class="detail-chip">${ramen.style}</span>`);
  if (!ramen.custom && ramen.stars != null) {
    const sg = starsToGrade(ramen.stars);
    detailParts.push(`<span class="detail-chip detail-grade ${gradeClass(sg)}">Rater: ${sg} (${ramen.stars}★)</span>`);
  }
  const existingRating = storage.getRating(ramen.id);
  if (existingRating) {
    const userRank = storage.getRank(ramen.id);
    const userScore = storage.getScore(ramen.id);
    const ug = scoreToGrade(userScore);
    detailParts.push(`<span class="detail-chip detail-user-grade ${gradeClass(ug)}">You: ${ug} #${userRank}</span>`);
    detailParts.push(`<span class="detail-chip" data-tier="${existingRating.flavorRating}">\u{1F35C} Flavor: ${FLAVOR_LABELS[existingRating.flavorRating]}</span>`);
    detailParts.push(`<span class="detail-chip" data-tier="${existingRating.noodleRating}">\u{1F962} Noodles/Ingredients: ${NOODLE_LABELS[existingRating.noodleRating]}</span>`);
  }
  detailsEl.innerHTML = detailParts.join('');

  if (ramen.custom) {
    creditEl.innerHTML = '<span class="badge badge-custom">Custom Entry</span>';
    deleteBtn.classList.remove('hidden');
  } else {
    const url = ramen.url || `https://www.theramenrater.com/?s=%23${ramen.id}%3A`;
    creditEl.innerHTML = `<a href="${url}" target="_blank" rel="noopener" class="rater-link">View on The Ramen Rater ↗</a>`;
    deleteBtn.classList.add('hidden');
  }

  const wishBtn = document.getElementById('rating-wishlist');
  if (existingRating) {
    wishBtn.classList.add('hidden');
  } else {
    wishBtn.classList.remove('hidden');
    const wishlisted = storage.isWishlisted(ramen.id);
    wishBtn.classList.toggle('active', wishlisted);
    wishBtn.innerHTML = wishlisted ? '&#x2665; On Your List' : '&#x2661; Want to Try';
  }

  document.getElementById('rating-step-rate').classList.remove('hidden');
  document.getElementById('rating-step-compare').classList.add('hidden');
  document.getElementById('rating-step-done').classList.add('hidden');

  document.querySelectorAll('.tier-btn').forEach(b => {
    b.classList.remove('selected');
    b.setAttribute('aria-checked', 'false');
  });
  document.getElementById('rating-next').disabled = true;

  const existing = storage.getRating(ramen.id);
  const removeBtn = document.getElementById('rating-remove');
  if (existing) {
    selectTier('tier-flavor', existing.flavorRating);
    selectTier('tier-noodle', existing.noodleRating);
    selectedFlavor = existing.flavorRating;
    selectedNoodle = existing.noodleRating;
    document.getElementById('rating-next').disabled = false;
    removeBtn.classList.remove('hidden');
  } else {
    removeBtn.classList.add('hidden');
  }

  modal.classList.remove('hidden');
  trapFocus(modal);
}

function selectTier(containerId, tier) {
  const container = document.getElementById(containerId);
  container.querySelectorAll('.tier-btn').forEach(b => {
    const match = parseInt(b.dataset.tier) === tier;
    b.classList.toggle('selected', match);
    b.setAttribute('aria-checked', match ? 'true' : 'false');
  });
}

function _populateTierButtons(containerId, labels, category) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  for (let i = 1; i < labels.length; i++) {
    const btn = document.createElement('button');
    btn.className = 'tier-btn';
    btn.dataset.tier = i;
    btn.setAttribute('role', 'radio');
    btn.setAttribute('aria-checked', 'false');
    btn.setAttribute('title', `${category}: ${labels[i]} (${i} of ${labels.length - 1})`);
    btn.textContent = labels[i];
    container.appendChild(btn);
  }
}

export function initRatingModal() {
  _populateTierButtons('tier-flavor', FLAVOR_LABELS, 'Flavor');
  _populateTierButtons('tier-noodle', NOODLE_LABELS, 'Noodles/Ingredients');

  const modal = document.getElementById('modal-rate');
  const nextBtn = document.getElementById('rating-next');
  const doneBtn = document.getElementById('rating-done');
  const lightbox = document.getElementById('image-lightbox');
  const lightboxImg = document.getElementById('lightbox-img');

  document.getElementById('rating-header-image').addEventListener('click', () => {
    const img = document.querySelector('#rating-header-image img');
    if (!img) return;
    lightboxImg.src = img.src;
    lightbox.classList.remove('hidden');
  });
  function closeLightbox() { lightbox.classList.add('hidden'); lightboxImg.src = ''; }
  lightbox.addEventListener('click', closeLightbox);
  lightbox.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

  modal.querySelector('.modal-close').addEventListener('click', closeRatingModal);
  modal.querySelector('.modal-backdrop').addEventListener('click', closeRatingModal);
  setupModalA11y(modal, closeRatingModal);

  document.getElementById('tier-flavor').addEventListener('click', e => {
    const btn = e.target.closest('.tier-btn');
    if (!btn) return;
    selectedFlavor = parseInt(btn.dataset.tier);
    selectTier('tier-flavor', selectedFlavor);
    nextBtn.disabled = !(selectedFlavor && selectedNoodle);
  });

  document.getElementById('tier-noodle').addEventListener('click', e => {
    const btn = e.target.closest('.tier-btn');
    if (!btn) return;
    selectedNoodle = parseInt(btn.dataset.tier);
    selectTier('tier-noodle', selectedNoodle);
    nextBtn.disabled = !(selectedFlavor && selectedNoodle);
  });

  nextBtn.addEventListener('click', () => {
    if (!currentRatingRamen || !selectedFlavor || !selectedNoodle) return;
    storage.setRating(currentRatingRamen.id, selectedFlavor, selectedNoodle);

    const alreadyRanked = storage.getRankedList().includes(currentRatingRamen.id);
    if (alreadyRanked) {
      showDoneStep();
      return;
    }

    const result = ranking.startInsertion(currentRatingRamen.id);
    if (result.done) {
      showDoneStep();
    } else {
      showCompareStep(result);
    }
  });

  const compareNew = document.getElementById('compare-new');
  const compareExisting = document.getElementById('compare-existing');
  compareNew.addEventListener('click', () => handleCompareChoice(true));
  compareExisting.addEventListener('click', () => handleCompareChoice(false));
  compareNew.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCompareChoice(true); } });
  compareExisting.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleCompareChoice(false); } });

  doneBtn.addEventListener('click', closeRatingModal);

  document.getElementById('rating-remove').addEventListener('click', () => {
    if (!currentRatingRamen) return;
    if (!confirm(`Remove your rating for "${currentRatingRamen.variety}"?`)) return;
    ranking.cancelInsertion();
    storage.removeRating(currentRatingRamen.id);
    closeRatingModal();
  });

  document.getElementById('rating-delete-custom').addEventListener('click', () => {
    if (!currentRatingRamen || !currentRatingRamen.custom) return;
    if (!confirm(`Delete "${currentRatingRamen.variety}"? This removes the ramen and its rating permanently.`)) return;
    ranking.cancelInsertion();
    storage.deleteCustomRamen(currentRatingRamen.id);
    closeRatingModal();
  });

  document.getElementById('rating-wishlist').addEventListener('click', () => {
    if (!currentRatingRamen) return;
    const id = currentRatingRamen.id;
    const btn = document.getElementById('rating-wishlist');
    if (storage.isWishlisted(id)) {
      storage.removeFromWishlist(id);
      btn.classList.remove('active');
      btn.innerHTML = '&#x2661; Want to Try';
    } else {
      storage.addToWishlist(id);
      btn.classList.add('active');
      btn.innerHTML = '&#x2665; On Your List';
    }
  });
}

function handleCompareChoice(preferNew) {
  const newCard = document.getElementById('compare-new');
  const existCard = document.getElementById('compare-existing');

  newCard.classList.toggle('winner', preferNew);
  newCard.classList.toggle('loser', !preferNew);
  existCard.classList.toggle('winner', !preferNew);
  existCard.classList.toggle('loser', preferNew);

  setTimeout(() => {
    newCard.classList.remove('winner', 'loser');
    existCard.classList.remove('winner', 'loser');

    const result = ranking.processChoice(preferNew);
    if (result.done) {
      showDoneStep();
    } else {
      showCompareStep(result);
    }
  }, 400);
}

function showCompareStep(result) {
  document.getElementById('rating-step-rate').classList.add('hidden');
  document.getElementById('rating-step-compare').classList.remove('hidden');
  document.getElementById('rating-step-done').classList.add('hidden');

  document.getElementById('compare-counter').textContent = `Comparison ${result.step} of ~${result.totalSteps}`;

  const dots = document.getElementById('compare-dots');
  dots.innerHTML = '';
  for (let i = 0; i < result.totalSteps; i++) {
    const dot = document.createElement('span');
    dot.className = 'compare-dot';
    if (i < result.step - 1) dot.classList.add('done');
    if (i === result.step - 1) dot.classList.add('current');
    dots.appendChild(dot);
  }

  const newRamen = data.getRamenById(result.newId);
  const compareRamen = data.getRamenById(result.compareId);

  if (newRamen) renderCompareCard(newRamen, document.getElementById('compare-new'));
  if (compareRamen) renderCompareCard(compareRamen, document.getElementById('compare-existing'));
}

function showDoneStep() {
  document.getElementById('rating-step-rate').classList.add('hidden');
  document.getElementById('rating-step-compare').classList.add('hidden');
  document.getElementById('rating-step-done').classList.remove('hidden');

  const rank = storage.getRank(currentRatingRamen.id);
  const score = storage.getScore(currentRatingRamen.id);
  const grade = scoreToGrade(score);
  const total = storage.getRankedList().length;

  document.getElementById('done-rank').textContent = `#${rank} of ${total}`;
  document.getElementById('done-rank').className = `done-rank ${gradeClass(grade)}`;
  document.getElementById('done-score').textContent = `Grade: ${grade} (${score}/10)`;
}

function closeRatingModal() {
  const modal = document.getElementById('modal-rate');
  modal.classList.add('hidden');
  releaseFocus(modal);
  currentRatingRamen = null;
  refreshCurrentView();
}

export function resumePendingInsertion() {
  const pendingId = ranking.getPendingInsertion();
  if (!pendingId) return;
  const ramen = data.getRamenById(pendingId);
  if (!ramen) { ranking.cancelInsertion(); return; }

  currentRatingRamen = ramen;
  const modal = document.getElementById('modal-rate');
  document.getElementById('rating-ramen-name').textContent = ramen.variety;
  document.getElementById('rating-ramen-meta').textContent = `${ramen.brand} · ${flag(ramen.country)} ${ramen.country || ''}`;
  document.getElementById('rating-header-image').innerHTML = ramenImage(ramen);

  const result = ranking.nextComparison();
  if (!result) { ranking.cancelInsertion(); return; }
  if (result.done) {
    showDoneStep();
  } else {
    showCompareStep(result);
  }
  modal.classList.remove('hidden');
}

/* ---- Custom Ramen Modal ---- */

export function initCustomRamenModal() {
  const modal = document.getElementById('modal-custom-ramen');
  const closeCustom = () => { modal.classList.add('hidden'); releaseFocus(modal); };
  modal.querySelector('.modal-close').addEventListener('click', closeCustom);
  modal.querySelector('.modal-backdrop').addEventListener('click', closeCustom);
  setupModalA11y(modal, closeCustom);

  const imageInput = document.getElementById('custom-image');
  const preview = document.getElementById('custom-image-preview');

  imageInput.addEventListener('change', () => {
    const file = imageInput.files[0];
    if (!file) {
      preview.innerHTML = '';
      return;
    }
    compressImage(file).then(dataUrl => {
      preview.innerHTML = `<img src="${dataUrl}" alt="Preview">`;
      preview.dataset.imageData = dataUrl;
    });
  });

  document.getElementById('custom-ramen-save').addEventListener('click', () => {
    const variety = document.getElementById('custom-variety').value.trim();
    const brand = document.getElementById('custom-brand').value.trim();
    const style = document.getElementById('custom-style').value;
    const country = document.getElementById('custom-country').value.trim();

    if (!variety || !brand) {
      alert('Please enter a variety name and brand.');
      return;
    }

    const imageData = preview.dataset.imageData || null;

    const ramen = storage.addCustomRamen({ variety, brand, style, country, imageData });
    modal.classList.add('hidden');
    resetCustomForm();
    openRatingModal(ramen);
  });
}

function openCustomRamenModal(prefill = '') {
  const modal = document.getElementById('modal-custom-ramen');
  resetCustomForm();
  if (prefill) {
    document.getElementById('custom-variety').value = prefill;
  }

  const countrySelect = document.getElementById('custom-country');
  if (countrySelect.options.length <= 1) {
    data.getCountries().forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      opt.textContent = c;
      countrySelect.appendChild(opt);
    });
  }

  modal.classList.remove('hidden');
  trapFocus(modal);
}

function resetCustomForm() {
  document.getElementById('custom-variety').value = '';
  document.getElementById('custom-brand').value = '';
  document.getElementById('custom-style').value = 'Pack';
  document.getElementById('custom-country').value = '';
  document.getElementById('custom-image').value = '';
  const preview = document.getElementById('custom-image-preview');
  preview.innerHTML = '';
  preview.dataset.imageData = '';
}

function compressImage(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const maxW = 300;
        let w = img.width;
        let h = img.height;
        if (w > maxW) {
          h = Math.round(h * (maxW / w));
          w = maxW;
        }
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.6));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

/* ---- Collection View ---- */

let collectionMode = 'rankings';

function updateWishlistCount() {
  const count = storage.getWishlistCount();
  const badge = document.getElementById('wishlist-count');
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}

export function initCollectionView() {
  const sortSelect = document.getElementById('collection-sort');
  const brandSelect = document.getElementById('collection-brand');
  const countrySelect = document.getElementById('collection-country');
  const styleSelect = document.getElementById('collection-style');
  const searchInput = document.getElementById('collection-search');
  const clearBtn = document.getElementById('collection-search-clear');

  data.getBrands().forEach(b => {
    const opt = document.createElement('option');
    opt.value = b;
    opt.textContent = b;
    brandSelect.appendChild(opt);
  });

  data.getCountries().forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = `${flag(c)} ${c}`;
    countrySelect.appendChild(opt);
  });

  data.getStyles().forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    styleSelect.appendChild(opt);
  });

  const clearFiltersBtn = document.getElementById('collection-clear-filters');

  const refresh = () => {
    if (collectionMode === 'wishlist') renderWishlist();
    else renderCollection();
    const active = (collectionMode === 'rankings' && sortSelect.value !== 'rank')
      || brandSelect.value || countrySelect.value
      || styleSelect.value || searchInput.value.trim();
    clearFiltersBtn.classList.toggle('hidden', !active);
  };

  sortSelect.addEventListener('change', refresh);
  brandSelect.addEventListener('change', refresh);
  countrySelect.addEventListener('change', refresh);
  styleSelect.addEventListener('change', refresh);

  searchInput.addEventListener('input', () => {
    clearBtn.classList.toggle('hidden', !searchInput.value.trim());
    refresh();
  });

  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchInput.focus();
    searchInput.dispatchEvent(new Event('input'));
  });

  clearFiltersBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    sortSelect.value = 'rank';
    brandSelect.value = '';
    countrySelect.value = '';
    styleSelect.value = '';
    [sortSelect, brandSelect, countrySelect, styleSelect].forEach(el =>
      el.dispatchEvent(new Event('change')));
    refresh();
  });

  const toggleRankings = document.getElementById('toggle-rankings');
  const toggleWishlist = document.getElementById('toggle-wishlist');

  function setCollectionMode(mode) {
    collectionMode = mode;
    toggleRankings.classList.toggle('active', mode === 'rankings');
    toggleWishlist.classList.toggle('active', mode === 'wishlist');
    toggleRankings.setAttribute('aria-selected', mode === 'rankings' ? 'true' : 'false');
    toggleWishlist.setAttribute('aria-selected', mode === 'wishlist' ? 'true' : 'false');
    sortSelect.classList.toggle('hidden', mode === 'wishlist');
    if (mode === 'rankings') {
      document.getElementById('wishlist-list').classList.add('hidden');
      document.getElementById('wishlist-empty').classList.add('hidden');
      renderCollection();
    } else {
      document.getElementById('collection-list').classList.add('hidden');
      document.getElementById('collection-empty').classList.add('hidden');
      renderWishlist();
    }
    const active = brandSelect.value || countrySelect.value
      || styleSelect.value || searchInput.value.trim()
      || (mode === 'rankings' && sortSelect.value !== 'rank');
    clearFiltersBtn.classList.toggle('hidden', !active);
  }

  toggleRankings.addEventListener('click', () => setCollectionMode('rankings'));
  toggleWishlist.addEventListener('click', () => setCollectionMode('wishlist'));
  updateWishlistCount();
}

export function renderCollection() {
  updateWishlistCount();
  if (collectionMode === 'wishlist') { renderWishlist(); return; }
  document.getElementById('wishlist-list').classList.add('hidden');
  document.getElementById('wishlist-empty').classList.add('hidden');
  const list = document.getElementById('collection-list');
  list.classList.remove('hidden');
  const empty = document.getElementById('collection-empty');
  const sort = document.getElementById('collection-sort').value;
  const brandFilter = document.getElementById('collection-brand').value;
  const countryFilter = document.getElementById('collection-country').value;
  const styleFilter = document.getElementById('collection-style').value;
  const searchQuery = document.getElementById('collection-search').value.trim().toLowerCase();
  const ranked = storage.getRankedList();

  if (ranked.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');

  let items = ranked.map(id => {
    const ramen = data.getRamenById(id);
    const rating = storage.getRating(id);
    return ramen ? { ...ramen, rating, rank: storage.getRank(id), score: storage.getScore(id) } : null;
  }).filter(Boolean);

  if (brandFilter) items = items.filter(r => data.brandMatches(r.brand, brandFilter));
  if (countryFilter) items = items.filter(r => r.country === countryFilter);
  if (styleFilter) items = items.filter(r => r.style === styleFilter);
  if (searchQuery.length >= 2) {
    const numId = /^\d+$/.test(searchQuery) ? Number(searchQuery) : null;
    if (numId !== null) {
      items = items.filter(r => r.id === numId);
    } else {
      const terms = searchQuery.split(/\s+/);
      items = items.filter(r => {
        const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
        return terms.every(t => haystack.includes(t));
      });
    }
  }

  switch (sort) {
    case 'rank':
      break;
    case 'newest':
      items.sort((a, b) => {
        const da = a.rating?.dates?.at(-1) || '';
        const db = b.rating?.dates?.at(-1) || '';
        return db.localeCompare(da);
      });
      break;
    case 'oldest':
      items.sort((a, b) => {
        const da = a.rating?.dates?.[0] || '';
        const db = b.rating?.dates?.[0] || '';
        return da.localeCompare(db);
      });
      break;
    case 'flavor':
      items.sort((a, b) => (b.rating?.flavorRating || 0) - (a.rating?.flavorRating || 0));
      break;
    case 'noodle':
      items.sort((a, b) => (b.rating?.noodleRating || 0) - (a.rating?.noodleRating || 0));
      break;
    case 'popular-desc':
      items.sort((a, b) => (b.popularity || 0) - (a.popularity || 0));
      break;
    case 'popular-asc':
      items.sort(data.comparePopularAsc);
      break;
  }

  list.innerHTML = '';
  items.forEach(item => {
    const card = renderRamenCard(item, { showUserScore: true, showStars: false });
    card.addEventListener('click', () => openRatingModal(item));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRatingModal(item); } });
    list.appendChild(card);
  });
  announce(`${items.length} ramen in your collection`);
}

function renderWishlist() {
  document.getElementById('collection-list').classList.add('hidden');
  document.getElementById('collection-empty').classList.add('hidden');
  const list = document.getElementById('wishlist-list');
  const empty = document.getElementById('wishlist-empty');
  list.classList.remove('hidden');

  const brandFilter = document.getElementById('collection-brand').value;
  const countryFilter = document.getElementById('collection-country').value;
  const styleFilter = document.getElementById('collection-style').value;
  const searchQuery = document.getElementById('collection-search').value.trim().toLowerCase();
  const wishlist = storage.getWishlist();
  const keys = Object.keys(wishlist);

  if (keys.length === 0) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    updateWishlistCount();
    return;
  }
  empty.classList.add('hidden');

  let items = keys.map(key => {
    const entry = wishlist[key];
    const numId = isNaN(Number(key)) ? key : Number(key);
    let ramen = data.getRamenById(numId);
    if (!ramen && entry.custom) {
      ramen = { id: numId, ...entry.custom, custom: true };
    }
    if (!ramen) return null;
    return { ...ramen, _wishlistAdded: entry.added };
  }).filter(Boolean);

  if (brandFilter) items = items.filter(r => data.brandMatches(r.brand, brandFilter));
  if (countryFilter) items = items.filter(r => r.country === countryFilter);
  if (styleFilter) items = items.filter(r => r.style === styleFilter);
  if (searchQuery.length >= 2) {
    const numId = /^\d+$/.test(searchQuery) ? Number(searchQuery) : null;
    if (numId !== null) {
      items = items.filter(r => r.id === numId);
    } else {
      const terms = searchQuery.split(/\s+/);
      items = items.filter(r => {
        const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
        return terms.every(t => haystack.includes(t));
      });
    }
  }

  items.sort((a, b) => (b._wishlistAdded || '').localeCompare(a._wishlistAdded || ''));

  list.innerHTML = '';
  items.forEach(item => {
    const wrap = document.createElement('div');
    wrap.className = 'wishlist-card-wrap';
    const card = renderRamenCard(item, { showStars: true, showUserScore: false });
    card.addEventListener('click', () => openRatingModal(item));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRatingModal(item); } });
    const removeBtn = document.createElement('button');
    removeBtn.className = 'wishlist-remove';
    removeBtn.setAttribute('aria-label', `Remove ${item.variety} from Want to Try`);
    removeBtn.innerHTML = '&times;';
    removeBtn.addEventListener('click', e => {
      e.stopPropagation();
      storage.removeFromWishlist(item.id);
      renderWishlist();
      updateWishlistCount();
    });
    wrap.appendChild(card);
    wrap.appendChild(removeBtn);
    list.appendChild(wrap);
  });
  updateWishlistCount();
  announce(`${items.length} ramen in your want-to-try list`);
}

/* ---- Discover View ---- */

export function initDiscoverView() {
  const searchInput = document.getElementById('discover-search');
  const clearBtn = document.getElementById('discover-search-clear');
  const sortSelect = document.getElementById('discover-sort');
  const brandSelect = document.getElementById('discover-brand');
  const countrySelect = document.getElementById('discover-country');
  const styleSelect = document.getElementById('discover-style');
  const hideRatedCb = document.getElementById('discover-hide-rated');

  data.getBrands().forEach(b => {
    const opt = document.createElement('option');
    opt.value = b;
    opt.textContent = b;
    brandSelect.appendChild(opt);
  });

  data.getCountries().forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = `${flag(c)} ${c}`;
    countrySelect.appendChild(opt);
  });

  data.getStyles().forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    styleSelect.appendChild(opt);
  });

  const clearFiltersBtn = document.getElementById('discover-clear-filters');

  const refresh = () => {
    discoverPage = 0;
    renderDiscover();
    const active = sortSelect.value !== 'stars-desc' || brandSelect.value || countrySelect.value
      || styleSelect.value || searchInput.value.trim() || hideRatedCb.checked;
    clearFiltersBtn.classList.toggle('hidden', !active);
  };

  searchInput.addEventListener('input', () => {
    clearBtn.classList.toggle('hidden', !searchInput.value.trim());
    refresh();
  });
  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchInput.focus();
    searchInput.dispatchEvent(new Event('input'));
  });

  sortSelect.addEventListener('change', refresh);
  brandSelect.addEventListener('change', refresh);
  countrySelect.addEventListener('change', refresh);
  styleSelect.addEventListener('change', refresh);
  hideRatedCb.addEventListener('change', refresh);

  clearFiltersBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    sortSelect.value = 'stars-desc';
    brandSelect.value = '';
    countrySelect.value = '';
    styleSelect.value = '';
    hideRatedCb.checked = false;
    [sortSelect, brandSelect, countrySelect, styleSelect, hideRatedCb].forEach(el =>
      el.dispatchEvent(new Event('change')));
    refresh();
  });

  setupInfiniteScroll();
}

export function getDiscoverPageCount() { return discoverPage; }

let _onDiscoverPageChange = null;
export function onDiscoverPageChange(fn) { _onDiscoverPageChange = fn; }

export function renderDiscover(restorePages) {
  const list = document.getElementById('discover-list');
  const loading = document.getElementById('discover-loading');

  discoverFiltered = data.filterAndSort({
    search: document.getElementById('discover-search').value.trim(),
    brand: document.getElementById('discover-brand').value,
    country: document.getElementById('discover-country').value,
    style: document.getElementById('discover-style').value,
    sort: document.getElementById('discover-sort').value,
    hideRated: document.getElementById('discover-hide-rated').checked,
    ratedIds: storage.getRatedIds(),
  });

  list.innerHTML = '';
  discoverPage = 0;

  const pagesToLoad = restorePages > 1 ? restorePages : 1;
  for (let i = 0; i < pagesToLoad && discoverPage * ITEMS_PER_PAGE < discoverFiltered.length; i++) {
    appendDiscoverPage();
  }

  if (restorePages > 1) {
    try {
      const raw = sessionStorage.getItem('discover_anchor');
      sessionStorage.removeItem('discover_anchor');
      if (raw) {
        const { index, offset } = JSON.parse(raw);
        const card = list.children[index];
        if (card) {
          requestAnimationFrame(() => window.scrollTo(0, card.offsetTop - offset));
        }
      }
    } catch { }
  }

  loading.classList.toggle('hidden', discoverFiltered.length > 0);
  if (discoverFiltered.length === 0) {
    loading.textContent = 'No ramen found';
    loading.classList.remove('hidden');
    announce('No ramen found');
  } else {
    announce(`${discoverFiltered.length} ramen found`);
  }
}

function appendDiscoverPage() {
  const list = document.getElementById('discover-list');
  const start = discoverPage * ITEMS_PER_PAGE;
  const slice = discoverFiltered.slice(start, start + ITEMS_PER_PAGE);

  slice.forEach(r => {
    const card = renderRamenCard(r, { showStars: true, showUserScore: true });
    card.addEventListener('click', () => openRatingModal(r));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRatingModal(r); } });
    list.appendChild(card);
  });

  discoverPage++;
}

function setupInfiniteScroll() {
  const sentinel = document.createElement('div');
  sentinel.id = 'discover-sentinel';
  sentinel.style.height = '1px';
  document.getElementById('discover-list').after(sentinel);

  window.addEventListener('beforeunload', () => {
    try {
      const cards = document.querySelectorAll('#discover-list .ramen-card');
      for (let i = 0; i < cards.length; i++) {
        const rect = cards[i].getBoundingClientRect();
        if (rect.bottom > 0) {
          sessionStorage.setItem('discover_anchor', JSON.stringify({
            index: i,
            offset: rect.top,
          }));
          return;
        }
      }
    } catch { }
  });

  discoverObserver = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting) {
      const loaded = discoverPage * ITEMS_PER_PAGE;
      if (loaded < discoverFiltered.length) {
        appendDiscoverPage();
        _onDiscoverPageChange?.();
      }
    }
  }, { rootMargin: '200px' });

  discoverObserver.observe(sentinel);
}

/* ---- Fight View ---- */

let currentFight = null;

export function initFightView() {
  const leftEl = document.getElementById('fight-left');
  const rightEl = document.getElementById('fight-right');
  leftEl.addEventListener('click', () => handleFightPick('left'));
  rightEl.addEventListener('click', () => handleFightPick('right'));
  leftEl.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleFightPick('left'); } });
  rightEl.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleFightPick('right'); } });
  document.getElementById('fight-skip').addEventListener('click', startNewFight);
}

export function renderFightView() {
  const arena = document.getElementById('fight-arena');
  const empty = document.getElementById('fight-empty');
  const ranked = storage.getRankedList();

  if (ranked.length < 2) {
    arena.classList.add('hidden');
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');
  arena.classList.remove('hidden');
  updateFightStats();
  startNewFight();
}

function startNewFight() {
  const pair = ranking.pickFightPair();
  if (!pair) return;

  currentFight = pair;
  const leftRamen = data.getRamenById(pair.left);
  const rightRamen = data.getRamenById(pair.right);

  const leftEl = document.getElementById('fight-left');
  const rightEl = document.getElementById('fight-right');

  leftEl.classList.remove('winner', 'loser');
  rightEl.classList.remove('winner', 'loser');

  if (leftRamen) renderCompareCard(leftRamen, leftEl);
  if (rightRamen) renderCompareCard(rightRamen, rightEl);
}

function handleFightPick(side) {
  if (!currentFight) return;

  const winnerId = side === 'left' ? currentFight.left : currentFight.right;
  const loserId = side === 'left' ? currentFight.right : currentFight.left;

  const leftEl = document.getElementById('fight-left');
  const rightEl = document.getElementById('fight-right');

  if (side === 'left') {
    leftEl.classList.add('winner');
    rightEl.classList.add('loser');
  } else {
    rightEl.classList.add('winner');
    leftEl.classList.add('loser');
  }

  ranking.processFight(winnerId, loserId);
  updateFightStats();

  setTimeout(startNewFight, 600);
}

function updateFightStats() {
  const stats = storage.getStats();
  const streakEl = document.getElementById('fight-streak');
  const totalEl = document.getElementById('fight-total');
  streakEl.textContent = `\u{1F525} ${stats.fightStreak || 0}`;
  totalEl.textContent = `\u{2694}\u{FE0F} ${stats.totalFights || 0}`;
  streakEl.setAttribute('aria-label', `Current win streak: ${stats.fightStreak || 0}`);
  totalEl.setAttribute('aria-label', `Total fights: ${stats.totalFights || 0}`);
}

/* ---- Settings Modal ---- */

export function initSettingsModal() {
  const modal = document.getElementById('modal-settings');
  const openBtn = document.getElementById('settings-btn');
  const hideScoreToggle = document.getElementById('settings-hide-rater-score');

  applyCardSize(storage.getCardSize());

  const closeSettings = () => { modal.classList.add('hidden'); releaseFocus(modal); };

  openBtn.addEventListener('click', () => {
    updateSettingsStats();
    hideScoreToggle.checked = storage.getHideRaterScore();
    updateCardSizeButtons(storage.getCardSize());
    modal.classList.remove('hidden');
    trapFocus(modal);
  });

  modal.querySelector('.modal-close').addEventListener('click', closeSettings);
  modal.querySelector('.modal-backdrop').addEventListener('click', closeSettings);
  setupModalA11y(modal, closeSettings);

  hideScoreToggle.addEventListener('change', () => {
    storage.setHideRaterScore(hideScoreToggle.checked);
  });

  document.querySelectorAll('.card-size-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const size = btn.dataset.size;
      storage.setCardSize(size);
      applyCardSize(size);
      updateCardSizeButtons(size);
    });
  });

  document.getElementById('backup-download').addEventListener('click', () => {
    storage.exportBackup();
    document.getElementById('backup-status').textContent = 'Backup downloaded!';
    hideBanner();
  });

  document.getElementById('backup-upload').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      await storage.importBackup(file);
      document.getElementById('backup-status').textContent = 'Backup restored! Refreshing...';
      setTimeout(() => location.reload(), 800);
    } catch (err) {
      document.getElementById('backup-status').textContent = `Error: ${err.message}`;
    }
  });

  document.getElementById('data-clear').addEventListener('click', () => {
    if (confirm('Are you sure? This will delete ALL your ratings and rankings permanently.')) {
      storage.clearAll();
      location.reload();
    }
  });
}

function applyCardSize(size) {
  document.body.dataset.cardSize = size;
}

function updateCardSizeButtons(size) {
  document.querySelectorAll('.card-size-btn').forEach(btn => {
    const match = btn.dataset.size === size;
    btn.classList.toggle('active', match);
    btn.setAttribute('aria-checked', match ? 'true' : 'false');
  });
}

function updateSettingsStats() {
  document.getElementById('stats-count').textContent = storage.getRatedCount();
  document.getElementById('stats-fights').textContent = storage.getStats().totalFights || 0;
}

/* ---- Backup Banner ---- */

export function checkBackupBanner() {
  if (storage.shouldShowBackupReminder()) {
    document.getElementById('backup-banner').classList.remove('hidden');
  }
}

function hideBanner() {
  document.getElementById('backup-banner').classList.add('hidden');
}

export function initBanner() {
  document.getElementById('banner-dismiss').addEventListener('click', () => {
    storage.dismissBackupReminder();
    hideBanner();
  });

  document.getElementById('banner-backup').addEventListener('click', () => {
    storage.exportBackup();
    hideBanner();
  });
}

/* ---- Share Modal ---- */

let _onShareDismiss = null;

export function setShareDismissCallback(fn) { _onShareDismiss = fn; }

export function initShareModal() {
  const settingsModal = document.getElementById('modal-settings');
  const shareModal = document.getElementById('modal-share');
  const nameInput = document.getElementById('share-name');
  const generateBtn = document.getElementById('share-generate');
  const stepName = document.getElementById('share-step-name');
  const stepResult = document.getElementById('share-step-result');
  const urlInput = document.getElementById('share-url');
  const copyBtn = document.getElementById('share-copy');
  const copyStatus = document.getElementById('share-copy-status');
  const nativeBtn = document.getElementById('share-native');
  const changeNameBtn = document.getElementById('share-new');

  const closeShare = () => { shareModal.classList.add('hidden'); releaseFocus(shareModal); };

  shareModal.querySelector('.modal-close').addEventListener('click', closeShare);
  shareModal.querySelector('.modal-backdrop').addEventListener('click', closeShare);
  setupModalA11y(shareModal, closeShare);

  nameInput.addEventListener('input', () => {
    generateBtn.disabled = !nameInput.value.trim();
  });

  document.getElementById('share-open').addEventListener('click', () => {
    if (storage.getRatedCount() === 0) {
      alert('Rate some ramen first before sharing!');
      return;
    }
    settingsModal.classList.add('hidden');
    releaseFocus(settingsModal);
    stepName.classList.remove('hidden');
    stepResult.classList.add('hidden');
    copyStatus.textContent = '';
    generateBtn.disabled = !nameInput.value.trim();
    shareModal.classList.remove('hidden');
    trapFocus(shareModal);
  });

  generateBtn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    if (!name) return;
    generateBtn.disabled = true;
    generateBtn.textContent = 'GENERATING...';

    try {
      const d = storage.getData();
      const encoded = await share.encode(name, d.rankedList, d.ratings, d.customRamen);
      const base = location.origin + location.pathname;
      const fullUrl = `${base}#share=${encoded}`;
      urlInput.value = fullUrl;

      stepName.classList.add('hidden');
      stepResult.classList.remove('hidden');

      if (navigator.share) nativeBtn.classList.remove('hidden');
      else nativeBtn.classList.add('hidden');
    } catch (err) {
      console.error('Share encode error:', err);
      alert('Failed to generate share link. Try again.');
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = 'GENERATE LINK';
    }
  });

  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(urlInput.value);
      copyStatus.textContent = 'Link copied!';
      copyStatus.classList.add('success');
      announce('Link copied to clipboard');
    } catch {
      urlInput.select();
      document.execCommand('copy');
      copyStatus.textContent = 'Link copied!';
      copyStatus.classList.add('success');
    }
    setTimeout(() => { copyStatus.textContent = ''; copyStatus.classList.remove('success'); }, 3000);
  });

  nativeBtn.addEventListener('click', async () => {
    try {
      await navigator.share({ title: 'My Ramen Rankings', url: urlInput.value });
    } catch { /* user cancelled */ }
  });

  changeNameBtn.addEventListener('click', () => {
    stepResult.classList.add('hidden');
    stepName.classList.remove('hidden');
    nameInput.focus();
  });
}

/* ---- Shared View ---- */

let sharedData = null;

export function getSharedData() { return sharedData; }

export function showSharedView(decoded) {
  sharedData = decoded;
  const tab = document.getElementById('tab-shared');
  const label = document.getElementById('tab-shared-label');
  const section = document.getElementById('view-shared');
  const title = document.getElementById('shared-view-title');

  const displayName = decoded.name.length > 15 ? decoded.name.slice(0, 14) + '\u2026' : decoded.name;
  label.textContent = `${displayName}'s`;
  tab.title = `${decoded.name}'s Ramen Rankings`;
  tab.classList.remove('hidden');
  section.classList.remove('hidden');
  title.textContent = `${decoded.name}'s Ramen`;

  populateSharedFilters(decoded);
  renderSharedCollection();
}

export function hideSharedView() {
  sharedData = null;
  document.getElementById('tab-shared').classList.add('hidden');
  const section = document.getElementById('view-shared');
  section.classList.add('hidden');
  section.classList.remove('active');
  document.getElementById('shared-list').innerHTML = '';
  if (_onShareDismiss) _onShareDismiss();
}

export function initSharedView() {
  const sortSelect = document.getElementById('shared-sort');
  const brandSelect = document.getElementById('shared-brand');
  const countrySelect = document.getElementById('shared-country');
  const styleSelect = document.getElementById('shared-style');
  const searchInput = document.getElementById('shared-search');
  const clearBtn = document.getElementById('shared-search-clear');
  const clearFiltersBtn = document.getElementById('shared-clear-filters');

  const refresh = () => {
    renderSharedCollection();
    const active = sortSelect.value !== 'rank' || brandSelect.value || countrySelect.value
      || styleSelect.value || searchInput.value.trim();
    clearFiltersBtn.classList.toggle('hidden', !active);
  };

  sortSelect.addEventListener('change', refresh);
  brandSelect.addEventListener('change', refresh);
  countrySelect.addEventListener('change', refresh);
  styleSelect.addEventListener('change', refresh);

  searchInput.addEventListener('input', () => {
    clearBtn.classList.toggle('hidden', !searchInput.value.trim());
    refresh();
  });

  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchInput.focus();
    searchInput.dispatchEvent(new Event('input'));
  });

  clearFiltersBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    sortSelect.value = 'rank';
    brandSelect.value = '';
    countrySelect.value = '';
    styleSelect.value = '';
    refresh();
  });

  document.getElementById('shared-dismiss').addEventListener('click', () => {
    hideSharedView();
  });

  // Shared detail modal
  const detailModal = document.getElementById('modal-shared-detail');
  const closeDetail = () => { detailModal.classList.add('hidden'); releaseFocus(detailModal); };
  detailModal.querySelector('.modal-close').addEventListener('click', closeDetail);
  detailModal.querySelector('.modal-backdrop').addEventListener('click', closeDetail);
  setupModalA11y(detailModal, closeDetail);
}

function populateSharedFilters(decoded) {
  const brands = new Set();
  const countries = new Set();
  const styles = new Set();

  for (const entry of decoded.entries) {
    const ramen = entry.custom ? entry : data.getRamenById(entry.id);
    if (!ramen) continue;
    if (ramen.brand) {
      if (ramen.brand.includes('/')) {
        for (const part of ramen.brand.split('/')) {
          const trimmed = part.trim();
          if (trimmed) brands.add(trimmed);
        }
      } else {
        brands.add(ramen.brand);
      }
    }
    if (ramen.country) countries.add(ramen.country);
    if (ramen.style) styles.add(ramen.style);
  }

  const populateSelect = (id, values) => {
    const sel = document.getElementById(id);
    while (sel.options.length > 1) sel.remove(1);
    [...values].sort().forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  };

  populateSelect('shared-brand', brands);
  populateSelect('shared-country', countries);
  populateSelect('shared-style', styles);
}

function sharedScoreFromPosition(idx, total) {
  if (total <= 1) return 7.0;
  const rawPct = (total - 1 - idx) / (total - 1);
  const minScore = Math.max(5.8, 7.3 - (total - 2) * 0.15);
  const maxScore = Math.min(10.0, 9.3 + (total - 2) * 0.07);
  return parseFloat((minScore + rawPct * (maxScore - minScore)).toFixed(1));
}

export function renderSharedCollection() {
  if (!sharedData) return;

  const list = document.getElementById('shared-list');
  const empty = document.getElementById('shared-empty');
  const sort = document.getElementById('shared-sort').value;
  const brandFilter = document.getElementById('shared-brand').value;
  const countryFilter = document.getElementById('shared-country').value;
  const styleFilter = document.getElementById('shared-style').value;
  const searchQuery = document.getElementById('shared-search').value.trim().toLowerCase();

  const total = sharedData.entries.length;
  let items = sharedData.entries.map((entry, idx) => {
    let ramen;
    if (entry.custom) {
      ramen = { ...entry, image: false };
    } else {
      const dbRamen = data.getRamenById(entry.id);
      if (!dbRamen) return null;
      ramen = { ...dbRamen };
    }
    ramen._flavor = entry.flavor;
    ramen._noodle = entry.noodle;
    ramen._rank = idx + 1;
    ramen._score = sharedScoreFromPosition(idx, total);
    return ramen;
  }).filter(Boolean);

  if (brandFilter) items = items.filter(r => data.brandMatches(r.brand, brandFilter));
  if (countryFilter) items = items.filter(r => r.country === countryFilter);
  if (styleFilter) items = items.filter(r => r.style === styleFilter);
  if (searchQuery.length >= 2) {
    const numId = /^\d+$/.test(searchQuery) ? Number(searchQuery) : null;
    if (numId !== null) {
      items = items.filter(r => r.id === numId);
    } else {
      const terms = searchQuery.split(/\s+/);
      items = items.filter(r => {
        const haystack = `${r.variety} ${r.brand} ${r.country}`.toLowerCase();
        return terms.every(t => haystack.includes(t));
      });
    }
  }

  switch (sort) {
    case 'rank': break;
    case 'flavor': items.sort((a, b) => (b._flavor || 0) - (a._flavor || 0)); break;
    case 'noodle': items.sort((a, b) => (b._noodle || 0) - (a._noodle || 0)); break;
    case 'popular-desc': items.sort((a, b) => (b.popularity || 0) - (a.popularity || 0)); break;
    case 'popular-asc': items.sort(data.comparePopularAsc); break;
  }

  list.innerHTML = '';
  if (items.length === 0) {
    empty.classList.remove('hidden');
  } else {
    empty.classList.add('hidden');
  }

  items.forEach(item => {
    const card = renderSharedCard(item);
    card.addEventListener('click', () => openSharedDetailModal(item));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openSharedDetailModal(item); } });
    list.appendChild(card);
  });
  announce(`${items.length} ramen in shared collection`);
}

function renderSharedCard(ramen) {
  const grade = scoreToGrade(ramen._score);
  const el = document.createElement('div');
  el.className = 'ramen-card';
  el.setAttribute('tabindex', '0');
  el.setAttribute('role', 'button');

  const a11yParts = [ramen.variety, ramen.brand];
  if (ramen.country) a11yParts.push(ramen.country);
  a11yParts.push(`Rank ${ramen._rank}, grade ${grade}`);
  a11yParts.push(`Flavor: ${FLAVOR_LABELS[ramen._flavor]}, Noodles/Ingredients: ${NOODLE_LABELS[ramen._noodle]}`);
  const sharedPopTier = popularityTier(ramen.popularity);
  if (sharedPopTier) a11yParts.push(`Popularity: ${POP_LABELS[sharedPopTier]}`);
  el.setAttribute('aria-label', a11yParts.join(', '));
  el.setAttribute('title', a11yParts.join(' \u00b7 '));

  const starGrade = starsToGrade(ramen.stars);
  const gradeOverlay = starGrade && !ramen.custom
    ? `<span class="card-rater-grade ${gradeClass(starGrade)}" title="Ramen Rater grade: ${starGrade}">${starGrade}</span>`
    : '';

  const customBadge = ramen.custom ? '<span class="badge badge-custom" title="Custom entry">Custom</span>' : '';
  const scoreHtml = `<div class="card-score ${gradeClass(grade)}" title="Grade: ${grade}, ranked #${ramen._rank}"><span>${grade}</span><span class="score-rank">#${ramen._rank}</span></div>`;

  el.innerHTML = `
    <div class="card-image">${ramenImage(ramen)}${gradeOverlay}${popularityBadge(ramen)}</div>
    <div class="card-body">
      <div class="card-variety">${ramen.variety}</div>
      <div class="card-brand">${brandHtml(ramen.brand)}</div>
      <div class="card-meta">
        ${customBadge}
        ${ramen.style ? `<span class="badge badge-style" title="Style: ${ramen.style}">${ramen.style}</span>` : ''}
        <span class="badge badge-tier" data-tier="${ramen._flavor}" title="Flavor: ${FLAVOR_LABELS[ramen._flavor]}"><span class="badge-label">Flavor:</span> ${FLAVOR_LABELS[ramen._flavor]}</span>
        <span class="badge badge-tier" data-tier="${ramen._noodle}" title="Noodles/Ingredients: ${NOODLE_LABELS[ramen._noodle]}"><span class="badge-label">Noodles:</span> ${NOODLE_LABELS[ramen._noodle]}</span>
      </div>
      <div class="card-country">${flag(ramen.country)} ${ramen.country || 'Unknown'}</div>
    </div>
    ${scoreHtml}
  `;
  return el;
}

function openSharedDetailModal(ramen) {
  const modal = document.getElementById('modal-shared-detail');
  document.getElementById('shared-detail-name').textContent = ramen.variety;
  document.getElementById('shared-detail-meta').textContent = `${ramen.brand} \u00b7 ${flag(ramen.country)} ${ramen.country || ''}`;

  const imgEl = document.getElementById('shared-detail-image');
  imgEl.innerHTML = ramenImage(ramen);

  const chips = [];
  if (ramen.style) chips.push(`<span class="detail-chip">${ramen.style}</span>`);

  if (!ramen.custom && ramen.stars != null) {
    const sg = starsToGrade(ramen.stars);
    chips.push(`<span class="detail-chip detail-grade ${gradeClass(sg)}">Rater: ${sg} (${ramen.stars}\u2605)</span>`);
  }

  const grade = scoreToGrade(ramen._score);
  chips.push(`<span class="detail-chip detail-user-grade ${gradeClass(grade)}">${sharedData.name}: ${grade} #${ramen._rank}</span>`);
  chips.push(`<span class="detail-chip" data-tier="${ramen._flavor}">\u{1F35C} Flavor: ${FLAVOR_LABELS[ramen._flavor]}</span>`);
  chips.push(`<span class="detail-chip" data-tier="${ramen._noodle}">\u{1F962} Noodles/Ingredients: ${NOODLE_LABELS[ramen._noodle]}</span>`);

  document.getElementById('shared-detail-chips').innerHTML = chips.join('');

  const creditEl = document.getElementById('shared-detail-credit');
  if (ramen.custom) {
    creditEl.innerHTML = `<span class="badge badge-custom">Custom entry by ${sharedData.name}</span>`;
  } else {
    const url = ramen.url || `https://www.theramenrater.com/?s=%23${ramen.id}%3A`;
    creditEl.innerHTML = `<a href="${url}" target="_blank" rel="noopener" class="rater-link">View on The Ramen Rater \u2197</a>`;
  }

  const wishBtn = document.getElementById('shared-detail-wishlist');
  if (storage.isRated(ramen.id)) {
    wishBtn.classList.add('hidden');
  } else {
    wishBtn.classList.remove('hidden');
    const wishlisted = storage.isWishlisted(ramen.id);
    wishBtn.classList.toggle('active', wishlisted);
    wishBtn.innerHTML = wishlisted ? '&#x2665; On Your List' : '&#x2661; Want to Try';
    wishBtn.onclick = () => {
      if (storage.isWishlisted(ramen.id)) {
        storage.removeFromWishlist(ramen.id);
        wishBtn.classList.remove('active');
        wishBtn.innerHTML = '&#x2661; Want to Try';
      } else {
        const customPayload = ramen.custom
          ? { variety: ramen.variety, brand: ramen.brand, style: ramen.style || '', country: ramen.country || '', imageData: ramen.imageData || null }
          : undefined;
        storage.addToWishlist(ramen.id, customPayload);
        wishBtn.classList.add('active');
        wishBtn.innerHTML = '&#x2665; On Your List';
      }
    };
  }

  modal.classList.remove('hidden');
  trapFocus(modal);
}

/* ---- Navigation Helpers ---- */

let refreshCurrentView = () => { };

export function setRefreshCallback(fn) {
  refreshCurrentView = fn;
}

export function initGoToButtons() {
  document.querySelectorAll('[data-goto]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.goto;
      document.querySelector(`.tab-btn[data-tab="${tab}"]`)?.click();
    });
  });
}

/* ---- Barcode Scanner ---- */

let html5Qrcode = null;
let scannerContext = 'rate';

function openBarcodeScanner(context) {
  if (typeof Html5Qrcode === 'undefined') {
    announce('Barcode scanner not available');
    return;
  }
  scannerContext = context;
  const modal = document.getElementById('modal-barcode');
  const statusEl = document.getElementById('barcode-status');
  statusEl.textContent = '';
  statusEl.className = 'barcode-status';
  modal.classList.remove('hidden');
  trapFocus(modal);

  if (!html5Qrcode) {
    html5Qrcode = new Html5Qrcode('barcode-reader');
  }

  const config = {
    fps: 10,
    qrbox: { width: 280, height: 140 },
    formatsToSupport: [
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.UPC_E,
      Html5QrcodeSupportedFormats.EAN_8,
    ],
  };

  html5Qrcode.start(
    { facingMode: 'environment' },
    config,
    (decodedText) => {
      try {
        const ramen = data.lookupBarcode(decodedText);
        if (ramen) {
          closeBarcodeScanner();
          if (scannerContext === 'rate') openRatingModal(ramen);
          else expandCard(ramen);
        } else {
          statusEl.textContent = `No match: ${decodedText}`;
          statusEl.className = 'barcode-status barcode-not-found';
        }
      } catch (e) {
        statusEl.textContent = `Error: ${e.message} (barcode: ${decodedText})`;
        statusEl.className = 'barcode-status barcode-error';
      }
    },
    () => {}
  ).catch(err => {
    statusEl.textContent = `Camera error: ${err}`;
    statusEl.className = 'barcode-status barcode-error';
  });
}

function closeBarcodeScanner() {
  const modal = document.getElementById('modal-barcode');
  if (html5Qrcode && html5Qrcode.isScanning) {
    html5Qrcode.stop().catch(() => { });
  }
  modal.classList.add('hidden');
  releaseFocus(modal);
}

export function initBarcodeScanner() {
  const modal = document.getElementById('modal-barcode');
  modal.querySelector('.modal-close').addEventListener('click', closeBarcodeScanner);
  modal.querySelector('.modal-backdrop').addEventListener('click', closeBarcodeScanner);

  document.getElementById('rate-barcode-btn')?.addEventListener('click', () => openBarcodeScanner('rate'));
  document.getElementById('discover-barcode-btn')?.addEventListener('click', () => openBarcodeScanner('discover'));
}
