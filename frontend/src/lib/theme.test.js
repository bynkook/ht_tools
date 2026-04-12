// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';

import { getTheme, setTheme, toggleTheme, initTheme } from './theme';

describe('theme module', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark');
    localStorage.clear();
  });

  describe('getTheme', () => {
    it('returns "light" when html does not have dark class', () => {
      document.documentElement.classList.remove('dark');
      expect(getTheme()).toBe('light');
    });

    it('returns "dark" when html has dark class', () => {
      document.documentElement.classList.add('dark');
      expect(getTheme()).toBe('dark');
    });
  });

  describe('setTheme', () => {
    it('adds dark class and persists to storage when set to dark', () => {
      setTheme('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
      expect(localStorage.getItem('fabrix-theme')).toBe('dark');
    });

    it('removes dark class and persists to storage when set to light', () => {
      document.documentElement.classList.add('dark');
      setTheme('light');
      expect(document.documentElement.classList.contains('dark')).toBe(false);
      expect(localStorage.getItem('fabrix-theme')).toBe('light');
    });
  });

  describe('toggleTheme', () => {
    it('switches from light to dark', () => {
      document.documentElement.classList.remove('dark');
      toggleTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('switches from dark to light', () => {
      document.documentElement.classList.add('dark');
      toggleTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });
  });

  describe('initTheme', () => {
    it('applies dark mode when storage has dark', () => {
      localStorage.setItem('fabrix-theme', 'dark');
      initTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('applies light mode when storage has light', () => {
      localStorage.setItem('fabrix-theme', 'light');
      initTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('defaults to light when storage is empty', () => {
      localStorage.clear();
      initTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('defaults to light when storage has malformed value', () => {
      localStorage.setItem('fabrix-theme', 'banana');
      initTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });
  });
});
