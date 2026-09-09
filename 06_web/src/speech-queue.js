/**
 * SpeechQueue - makes the avatar start talking sooner.
 *
 * THE PROBLEM
 * -----------
 * The obvious way to speak a reply is: send the whole thing to the TTS server,
 * wait, play what comes back. The user therefore waits for the WHOLE reply to
 * be synthesised before hearing the first syllable. For a four-sentence answer
 * that is four times longer than it needs to be, and it is dead air with a
 * motionless avatar in it, which is the worst kind of waiting.
 *
 * THE FIX
 * -------
 * Speech is naturally divided at sentence boundaries. Split there, synthesise
 * the first sentence alone, and start playing it while the rest are still
 * being made. Time-to-first-sound stops depending on the length of the reply:
 *
 *     one shot   [------- synthesise whole reply -------][play ...]
 *     queued     [synth 1][play 1.............][play 2.......][play 3...]
 *                         [synth 2][synth 3]  (overlapped, ahead of playback)
 *
 * With a streaming LLM it gets better still: feed() accepts text as it
 * arrives and dispatches each sentence the moment it is closed by punctuation,
 * so synthesis of sentence 1 overlaps generation of sentence 2.
 *
 * IT ALSO SOUNDS BETTER
 * ---------------------
 * Every TTS clip is padded with silence, and the server already measures where
 * the real speech starts and ends (`speech: [t0, t1]`). Playing a queue lets
 * us seek past the leading padding and cut at the trailing one, replacing two
 * unpredictable silences with one controlled `gap`. Less dead air than the
 * single long clip it replaces.
 *
 *   const q = new SpeechQueue(tanuki, { api: '/api/say' });
 *   await q.say('こんにちは。きょうはいいてんきですね。');
 *
 *   // streaming:
 *   for await (const delta of llm) q.feed(delta);
 *   await q.end();
 *
 *   q.cancel();        // user sent a new message: drop everything in flight
 */

const ENDERS = '。．.！!？?\n';

export class SpeechQueue {
  /**
   * @param {object} tanuki  a TanukiLipSync instance
   */
  constructor(tanuki, opts = {}) {
    this.tanuki = tanuki;
    this.api = opts.api ?? '/api/say';
    this.body = opts.body ?? { blink: true };   // extra fields for /api/say

    // How many chunks to have synthesising ahead of the one playing. 2 keeps
    // the pipeline full without opening a connection per sentence at once.
    this.lookahead = opts.lookahead ?? 2;
    this.maxChars = opts.maxChars ?? 60;   // split long clauses at 、 too
    this.minChars = opts.minChars ?? 6;    // never emit a two-syllable clip
    this.gap = opts.gap ?? 0.12;           // seconds between sentences
    this.preroll = opts.preroll ?? 0.05;   // keep this much silence before speech
    this.tail = opts.tail ?? 0.06;         // ...and after it
    this.timeout = opts.timeout ?? 20000;  // ms per chunk request
    this.trimPadding = opts.trimPadding ?? true;

    this.onChunk = opts.onChunk ?? null;   // (text, index) => void, for captions
    this.onError = opts.onError ?? null;

    // Two elements, alternating. createMediaElementSource can be called only
    // once per element, so a pool keeps the audio graph at exactly two source
    // nodes however long the conversation runs.
    this._pool = [new Audio(), new Audio()];
    for (const el of this._pool) { el.crossOrigin = 'anonymous'; el.preload = 'auto'; }

    this._pending = '';        // text fed but not yet closed by punctuation
    this._queue = [];          // {text, promise, result, error}
    this._playing = false;
    this._done = null;         // resolve when the queue drains
    this._gen = 0;             // bumped by cancel(); stale work checks it
    this._warmed = false;
  }

  /**
   * Measure output latency before it is needed, not on the critical path.
   *
   * speak() no longer waits for this, so on a cold start the first line could
   * begin with the figure still unmeasured and be a few tens of milliseconds
   * out. Firing it when text is first queued - which in a chat is after the
   * user has clicked Send, so the AudioContext is allowed to resume - means it
   * has long since landed by the time audio starts.
   */
  _warm() {
    if (this._warmed) return;
    this._warmed = true;
    this.tanuki.measureLatency?.().catch(() => {});
  }

  /** Speak a complete string. Resolves when the last sentence finishes. */
  async say(text) {
    this.feed(text);
    return this.end();
  }

  /** Push text as it arrives. Dispatches every completed sentence at once. */
  feed(delta) {
    if (!delta) return this;
    this._warm();
    this._pending += delta;
    for (;;) {
      const cut = this._nextCut(this._pending, false);
      if (cut <= 0) break;
      this._enqueue(this._pending.slice(0, cut));
      this._pending = this._pending.slice(cut);
    }
    this._pump();
    return this;
  }

  /** Flush whatever is left and wait for the queue to drain. */
  end() {
    const rest = this._pending.trim();
    this._pending = '';
    if (rest) this._enqueue(rest);
    this._pump();
    if (!this._queue.length && !this._playing) return Promise.resolve();
    return new Promise((res) => { this._done = res; });
  }

  /** Drop everything: in-flight requests, the queue, and the current clip. */
  cancel() {
    this._gen++;
    this._warmed = false;
    for (const item of this._queue) item.ctrl?.abort();
    this._queue.length = 0;
    this._pending = '';
    for (const el of this._pool) { try { el.pause(); } catch (_) {} }
    this.tanuki.stop();
    this._playing = false;
    const d = this._done; this._done = null;
    if (d) d();
    return this;
  }

  /* ---------------------------------------------------------------- */

  /**
   * Where to cut `s` into a speakable chunk. Returns 0 if there is no complete
   * sentence yet (and `force` is false).
   *
   * Sentence enders first. Only if a run is longer than maxChars do we fall
   * back to a comma - splitting every clause makes the delivery choppy,
   * because the engine gives each clip its own phrase-final intonation.
   */
  _nextCut(s, force) {
    for (let i = 0; i < s.length; i++) {
      if (ENDERS.includes(s[i])) {
        // include any run of closing punctuation/quotes
        let j = i + 1;
        while (j < s.length && '」』）)”"…・、 '.includes(s[j])) j++;
        if (j >= this.minChars) return j;
      }
    }
    if (s.length > this.maxChars) {
      const at = s.lastIndexOf('、', this.maxChars);
      if (at >= this.minChars) return at + 1;
      return this.maxChars;                 // no punctuation at all: hard cut
    }
    return force && s.trim() ? s.length : 0;
  }

  _enqueue(text) {
    text = text.trim();
    if (!text) return;
    this._queue.push({ text, result: null, error: null, ctrl: null, promise: null });
  }

  /** Keep `lookahead` requests in flight, and start playback if idle. */
  _pump() {
    let inFlight = 0;
    for (const item of this._queue) {
      if (item.promise && !item.result && !item.error) inFlight++;
    }
    for (const item of this._queue) {
      if (inFlight >= this.lookahead) break;
      if (item.promise) continue;
      this._fetch(item);
      inFlight++;
    }
    if (!this._playing) this._play();
  }

  _fetch(item) {
    const gen = this._gen;
    const ctrl = new AbortController();
    item.ctrl = ctrl;
    const timer = setTimeout(() => ctrl.abort(), this.timeout);
    item.promise = fetch(this.api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...this.body, text: item.text }),
      signal: ctrl.signal,
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error);
        if (gen === this._gen) item.result = data;
      })
      .catch((e) => {
        if (gen === this._gen) {
          item.error = e;
          // One bad sentence must not silence the rest of the reply.
          this.onError?.(e, item.text);
        }
      })
      .finally(() => { clearTimeout(timer); if (gen === this._gen) this._pump(); });
  }

  async _play() {
    if (this._playing) return;
    this._playing = true;
    const gen = this._gen;
    let slot = 0;

    while (gen === this._gen) {
      const item = this._queue[0];
      if (!item) break;
      if (!item.promise) { this._fetch(item); }
      if (!item.result && !item.error) { await item.promise; }
      if (gen !== this._gen) break;
      this._queue.shift();
      this._pump();                       // keep the pipeline full while we play
      if (item.error) continue;           // skipped: already reported

      const el = this._pool[slot % this._pool.length];
      slot++;
      try {
        await this._speakOne(el, item, gen);
      } catch (e) {
        this.onError?.(e, item.text);
      }
      if (gen === this._gen && this._queue.length) await sleep(this.gap * 1000);
    }

    this._playing = false;
    if (gen === this._gen && !this._queue.length && !this._pending) {
      const d = this._done; this._done = null;
      if (d) d();
    }
  }

  /**
   * Play one chunk, cutting the engine's silence padding off both ends.
   *
   * `getTime` is passed deliberately: it tells speak() that we own the
   * lifecycle, so its own completion handling will not reset the mouth to idle
   * underneath the NEXT chunk.
   */
  _speakOne(el, item, gen) {
    const d = item.result;
    const span = this.trimPadding && Array.isArray(d.speech) ? d.speech : null;
    const start = span ? Math.max(0, span[0] - this.preroll) : 0;
    const stop = span ? Math.min(d.duration || 1e9, span[1] + this.tail) : Infinity;

    this.onChunk?.(item.text, d);
    el.src = d.audio;

    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearInterval(watch);
        clearTimeout(guard);
        el.removeEventListener('ended', finish);
        el.removeEventListener('error', finish);
        try { el.pause(); } catch (_) {}
        resolve();
      };
      // Cut at the end of the actual speech instead of the end of the file.
      const watch = setInterval(() => {
        if (gen !== this._gen) return finish();
        if (el.currentTime >= stop) finish();
      }, 20);
      // Same safety net as speak(): `ended` is not guaranteed to fire.
      const guard = setTimeout(finish, ((d.duration || 10) + 2) * 1000);
      el.addEventListener('ended', finish);
      el.addEventListener('error', finish);

      // startAt does the seek inside speak(), after it has taken ownership of
      // the element - doing it here first only to have speak() reset it was
      // how the leading-silence trim silently did nothing.
      this.tanuki.speak({
        audio: el, track: d.track, startAt: start,
        getTime: () => el.currentTime,
      }).catch((e) => this.onError?.(e, item.text));
    });
  }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

export default SpeechQueue;
