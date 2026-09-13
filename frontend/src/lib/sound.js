let audioCtx = null;

function getCtx() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioCtx;
}

function tone(freq, startTime, duration, ctx, gainPeak = 0.15) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0, startTime);
  gain.gain.linearRampToValueAtTime(gainPeak, startTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(startTime);
  osc.stop(startTime + duration);
}

export function playSuccessChime() {
  const ctx = getCtx();
  const now = ctx.currentTime;
  [523.25, 659.25, 783.99].forEach((freq, i) => tone(freq, now + i * 0.09, 0.3, ctx));
}

export function playGentleRetryTone() {
  const ctx = getCtx();
  const now = ctx.currentTime;
  tone(392.0, now, 0.25, ctx, 0.1);
  tone(329.63, now + 0.14, 0.3, ctx, 0.1);
}

export function playLevelCompleteFanfare() {
  const ctx = getCtx();
  const now = ctx.currentTime;
  [523.25, 587.33, 659.25, 783.99, 1046.5].forEach((freq, i) => tone(freq, now + i * 0.11, 0.4, ctx, 0.14));
}
