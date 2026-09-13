let cachedVoice = null;

function pickVoice() {
  if (cachedVoice) return cachedVoice;
  const voices = window.speechSynthesis.getVoices();
  cachedVoice =
    voices.find((v) => /en-US/i.test(v.lang) && /female|samantha|victoria/i.test(v.name)) ||
    voices.find((v) => /en/i.test(v.lang)) ||
    voices[0] ||
    null;
  return cachedVoice;
}

if (typeof window !== "undefined" && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    cachedVoice = null;
  };
}

export function speak(text, rate = 0.8) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = rate;
  utter.pitch = 1.1;
  const voice = pickVoice();
  if (voice) utter.voice = voice;
  window.speechSynthesis.speak(utter);
}
