import { describe, it, expect } from 'vitest';

import { resolvePersist } from './systemMessageState';

describe('resolvePersist', () => {
  // --- 'always' policy phases ---
  it('runtime phase always returns true regardless of isTestMode', () => {
    expect(resolvePersist('runtime', false)).toBe(true);
    expect(resolvePersist('runtime', true)).toBe(true);
    expect(resolvePersist('runtime', undefined)).toBe(true);
  });

  // --- 'test_only' policy phases ---
  it('command phase returns false when isTestMode is false', () => {
    expect(resolvePersist('command', false)).toBe(false);
  });

  it('command phase returns true when isTestMode is true', () => {
    expect(resolvePersist('command', true)).toBe(true);
  });

  it('memory phase returns true when isTestMode is true', () => {
    expect(resolvePersist('memory', true)).toBe(true);
  });

  it('memory phase returns false when isTestMode is false', () => {
    expect(resolvePersist('memory', false)).toBe(false);
  });

  // --- 'never' policy phases ---
  it('command_error phase always returns false (never policy)', () => {
    expect(resolvePersist('command_error', true)).toBe(false);
    expect(resolvePersist('command_error', false)).toBe(false);
  });

  // --- unknown phase fallback ---
  it('unknown phase falls back to always (returns true) to prevent data loss', () => {
    expect(resolvePersist('unknown_phase', undefined)).toBe(true);
    expect(resolvePersist('unknown_phase', false)).toBe(true);
    expect(resolvePersist('some_future_phase', true)).toBe(true);
  });

  // --- runtimeConfig not yet loaded (undefined isTestMode) ---
  it('test_only phase with undefined isTestMode returns false (safe default)', () => {
    expect(resolvePersist('command', undefined)).toBe(false);
    expect(resolvePersist('memory', undefined)).toBe(false);
  });

  // --- additional always policy phases ---
  it('conversation and persistence phases always return true', () => {
    expect(resolvePersist('conversation', false)).toBe(true);
    expect(resolvePersist('persistence', false)).toBe(true);
  });
});
