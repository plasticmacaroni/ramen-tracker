import * as storage from './storage.js';

const SESSION_KEY = 'ramen_insertion_session';

/**
 * Binary insertion: maintains state for an ongoing comparison session.
 * Session is persisted to localStorage so it survives modal close / page refresh.
 */
let session = null;

function saveSession() {
  if (session) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(SESSION_KEY);
  }
}

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    if (!s.newId || s.low == null || s.high == null) return null;
    return s;
  } catch {
    return null;
  }
}

export function startInsertion(newId) {
  const ranked = storage.getRankedList();

  if (ranked.length === 0) {
    storage.insertIntoRankedList(newId, 0);
    session = null;
    saveSession();
    return { done: true, rank: 1, total: 0 };
  }

  session = {
    newId,
    low: 0,
    high: ranked.length - 1,
    step: 0,
    totalSteps: Math.ceil(Math.log2(ranked.length + 1)),
  };
  saveSession();

  return nextComparison();
}

export function nextComparison() {
  if (!session) return null;

  const ranked = storage.getRankedList();

  if (session.low > session.high) {
    storage.insertIntoRankedList(session.newId, session.low);
    const rank = session.low + 1;
    const result = { done: true, rank, total: session.step };
    session = null;
    saveSession();
    return result;
  }

  const mid = Math.floor((session.low + session.high) / 2);
  const compareId = ranked[mid];

  if (!storage.getRating(compareId)) {
    ranked.splice(mid, 1);
    storage.setRankedList(ranked);
    if (session.high >= ranked.length) session.high = ranked.length - 1;
    saveSession();
    return nextComparison();
  }

  return {
    done: false,
    compareId,
    newId: session.newId,
    step: session.step + 1,
    totalSteps: session.totalSteps,
  };
}

/**
 * Process the user's choice in a binary insertion comparison.
 * preferNew = true means user prefers the new ramen over the shown one.
 */
export function processChoice(preferNew) {
  if (!session) return null;

  const ranked = storage.getRankedList();
  const mid = Math.floor((session.low + session.high) / 2);

  if (preferNew) {
    session.high = mid - 1;
  } else {
    session.low = mid + 1;
  }

  session.step++;
  saveSession();
  return nextComparison();
}

export function cancelInsertion() {
  session = null;
  saveSession();
}

export function isInsertionActive() {
  return session !== null;
}

/**
 * Check for an interrupted insertion session on startup.
 * Returns the session's newId if one exists, or null.
 */
export function getPendingInsertion() {
  const saved = loadSession();
  if (!saved) return null;
  const ranked = storage.getRankedList();
  if (ranked.includes(saved.newId)) {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
  if (!storage.getRating(saved.newId)) {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
  session = saved;
  return saved.newId;
}

/**
 * Ramen Fight: pick two random ramen from the ranked list.
 * Returns { left, right } with their IDs, or null if < 2 ramen.
 */
export function pickFightPair() {
  const ranked = storage.getRankedList();
  if (ranked.length < 2) return null;

  let a = Math.floor(Math.random() * ranked.length);
  let b;
  do {
    b = Math.floor(Math.random() * ranked.length);
  } while (b === a);

  return { left: ranked[a], right: ranked[b] };
}

/**
 * Process a fight result. Winner moves ahead of loser if ranked below.
 * Returns { changed, winnerRank, loserRank, jump } or null.
 */
export function processFight(winnerId, loserId) {
  const ranked = storage.getRankedList();
  const winIdx = ranked.indexOf(winnerId);
  const loseIdx = ranked.indexOf(loserId);

  if (winIdx === -1 || loseIdx === -1) return null;

  const stats = storage.getStats();
  stats.totalFights = (stats.totalFights || 0) + 1;

  if (winIdx > loseIdx) {
    ranked.splice(winIdx, 1);
    ranked.splice(loseIdx, 0, winnerId);
    storage.setRankedList(ranked);

    const jump = winIdx - loseIdx;
    stats.fightStreak = (stats.fightStreak || 0) + 1;

    if (!stats.biggestUpset || jump > stats.biggestUpset.jump) {
      stats.biggestUpset = { id: winnerId, jump };
    }

    storage.updateStats(stats);

    return {
      changed: true,
      winnerRank: loseIdx + 1,
      loserRank: loseIdx + 2,
      jump,
    };
  }

  stats.fightStreak = (stats.fightStreak || 0) + 1;
  storage.updateStats(stats);

  return {
    changed: false,
    winnerRank: winIdx + 1,
    loserRank: loseIdx + 1,
    jump: 0,
  };
}
