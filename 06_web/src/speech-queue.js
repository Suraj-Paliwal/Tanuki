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

    // How many chunks to have synthesising ahead of the one playing.
    //
    // This has to beat the ratio of synthesis time to playback time. A
    // sentence takes ~1.5 s to say; if the engine needs longer than that to
    // make the next one, the queue starves and you hear a hole between
    // sentences. 3 covers an engine running at up to ~3x realtime behind us;
    // raise it for a slow remote engine, lower it if you are being rate
    // limited. onStall fires when it was not enough, so you can see it rather
    // than guess.
    this.lookahead = opts.lookahead ?? 3;
    this.onStall = opts.onStall ?? null;
    this.maxChars = opts.maxChars ?? 60;   // split long clauses at 、 too
    this.minChars = opts.minChars ?? 6;    // never emit a two-syllable clip
    // The FIRST chunk is the only one anybody waits for, so it is cut short
    // and allowed to break at a comma. Every later chunk is already being
    // synthesised behind the one playing, so length costs nothing there and
    // longer chunks give the engine more context for its intonation.
    this.firstMaxChars = opts.firstMaxChars ?? 18;
    this.firstMinChars = opts.firstMinChars ?? 4;
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
    this._emitted = 0;         // chunks handed to the queue so far
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
      const cut = this._nextCut(this._pending);
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
    this._emitted = 0;
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
  _nextCut(s) {
    const first = this._emitted === 0;
    const enders = first ? ENDERS + '、,' : ENDERS;
    const min = first ? this.firstMinChars : this.minChars;
    const max = first ? this.firstMaxChars : this.maxChars;

    for (let i = 0; i < s.length; i++) {
      if (enders.includes(s[i])) {
        // include any run of closing punctuation/quotes
        let j = i + 1;
        while (j < s.length && '」』）)”"…・、 '.includes(s[j])) j++;
        if (j >= min) return j;
      }
    }
    if (s.length > max) {
      const at = s.lastIndexOf('、', max);
      if (at >= min) return at + 1;
      return max;                           // no punctuation at all: hard cut
    }
    return 0;
  }

  _enqueue(text) {
    text = text.trim();
    if (!text) return;
    this._queue.push({ text, result: null, error: null, ctrl: null, promise: null });
    this._emitted++;
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
      if (item.error) {
        // The audio is lost, but the words are not: still surface the text so
        // a failed sentence goes missing from the SOUND and not from the
        // conversation.
        this.onChunk?.(item.text, null);
        continue;
      }

      const el = this._pool[slot % this._pool.length];
      const spare = this._pool[(slot + 1) % this._pool.length];
      slot++;
      // Hand the next clip's URL to the idle element now, so the browser
      // fetches and decodes it during this sentence instead of at the moment
      // it is needed.
      const next = this._queue[0];
      if (next && next.result && spare !== el) {
        try { spare.src = next.result.audio; spare.load(); } catch (_) {}
      }
      const wasReady = !!(next && next.result);
      try {
        await this._speakOne(el, item, gen);
      } catch (e) {
        this.onError?.(e, item.text);
      }
      // If the next sentence still is not synthesised, the listener is about
      // to hear a hole. Report it: that is a lookahead or an engine problem,
      // and it is invisible otherwise.
      if (gen === this._gen && next && !wasReady && !next.result && !next.error) {
        this.onStall?.(next.text);
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
        // Put the rig back to rest. Without this the mouth FREEZES in
        // whatever shape it held at the cut and stays there through the gap
        // between sentences - measured at 0.85 open for the whole pause - and
        // hangs open for good after the last one. The driver samples the
        // track at audio.currentTime, and a paused element's currentTime does
        // not move, so nothing else was ever going to close it.
        this.tanuki.stop();
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
