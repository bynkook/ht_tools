/**
 * opBatcher.js
 * Collects ops from onOp and flushes them as a batch after a debounce delay.
 */

export class OpBatcher {
  constructor({ flushFn, debounceMs = 300 }) {
    this._flushFn = flushFn;
    this._debounceMs = debounceMs;
    this._pending = [];
    this._timer = null;
  }

  push(ops) {
    this._pending.push(...ops);
    this._schedule();
  }

  _schedule() {
    if (this._timer) clearTimeout(this._timer);
    this._timer = setTimeout(() => this._flush(), this._debounceMs);
  }

  _flush() {
    this._timer = null;
    if (this._pending.length === 0) return;
    const batch = this._pending.splice(0, this._pending.length);
    this._flushFn(batch);
  }

  flushNow() {
    if (this._timer) clearTimeout(this._timer);
    this._flush();
  }

  cancel() {
    if (this._timer) clearTimeout(this._timer);
    this._timer = null;
    this._pending = [];
  }
}
