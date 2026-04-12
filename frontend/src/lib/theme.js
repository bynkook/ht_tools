/**
 * FabriX Chat Theme Utility
 *
 * Canonical theme source: html.dark class on document.documentElement
 * Storage key: 'fabrix-theme'
 * Values: 'light' | 'dark'
 * Policy: 2-state Light/Dark only (no system-mode tri-state)
 *
 * Scope contract:
 *   html.dark is ONLY active while the /chat route is mounted (ChatLayout).
 *   ChatLayout applies initTheme() on mount and removes html.dark on unmount,
 *   ensuring all other apps (/agent-chat, /data-explorer, /image-compare, etc.)
 *   always render in light mode regardless of the stored preference.
 *
 * No React context. Call these functions directly from components or event handlers.
 */

const STORAGE_KEY = 'fabrix-theme';

/** Returns the current theme: 'dark' or 'light' */
export function getTheme() {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

/** Sets theme to 'dark' or 'light', updates DOM class and persists to storage */
export function setTheme(value) {
  if (value === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
  try {
    localStorage.setItem(STORAGE_KEY, value === 'dark' ? 'dark' : 'light');
  } catch (_) {
    // Storage may be unavailable (private browsing, quota exceeded) — DOM class is still applied
  }
}

/** Toggles between light and dark */
export function toggleTheme() {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

/**
 * Initializes theme on ChatLayout mount.
 * Reads storage and applies html.dark — called by ChatLayout useEffect on /chat entry.
 * In normal browser flow the <head> inline script in index.html also handles FOUC
 * prevention for /chat, but initTheme() ensures correctness after SPA navigation
 * (e.g., user navigates from /agent-chat to /chat without a hard reload).
 */
export function initTheme() {
  let stored;
  try {
    stored = localStorage.getItem(STORAGE_KEY);
  } catch (_) {
    // Storage may be unavailable (private browsing, quota exceeded) — default to light
  }
  setTheme(stored === 'dark' ? 'dark' : 'light');
}
