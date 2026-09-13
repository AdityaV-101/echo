import { useCallback, useRef, useState } from "react";

// Records mic audio with MediaRecorder and reports a live 0-1 volume level
// (via an AnalyserNode) so the UI can pulse a ring while the child is talking.
export function useRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [level, setLevel] = useState(0);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);

  const tickLevel = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);
    let sumSquares = 0;
    for (let i = 0; i < data.length; i++) {
      const normalized = (data[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / data.length);
    setLevel(Math.min(1, rms * 4));
    rafRef.current = requestAnimationFrame(tickLevel);
  }, []);

  const start = useCallback(async () => {
    // Chrome (and most browsers) apply echo cancellation, noise suppression,
    // and auto gain control to mic audio by default.
    //
    // Echo cancellation and noise suppression are turned off: both are
    // adaptive filters tuned for human-to-human call quality, not machine
    // recognition, and both calibrate against the incoming signal in real
    // time - which means the least-settled moment for either is right at
    // the onset of speech (going from room-noise-only to an actual voice
    // signal). Noise suppression in particular can mistake a short, weak
    // consonant burst (a plosive like P's release, especially) for noise
    // during that calibration window and suppress it outright, which reads
    // to the recognizer as the sound never having happened at all.
    //
    // Auto gain control is left ON, unlike the other two: unlike EC/NS it
    // doesn't reshape the signal's spectral content, it just brings a quiet
    // recording up to an audible level - and a soft-spoken take (very
    // common from kids, or from a laptop mic at a normal distance) can
    // otherwise be too quiet for the recognizer to pick up a short
    // consonant burst at all, which looks identical to "the sound was left
    // out" in the app. See _convert_to_wav in backend/scorer.py for a
    // second, server-side safety net on top of this (loudness
    // normalization), since browser AGC behavior isn't something this app
    // can fully control or verify per device.
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
      },
    });
    streamRef.current = stream;

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    audioCtxRef.current = audioCtx;
    analyserRef.current = analyser;

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setIsRecording(true);
    tickLevel();
  }, [tickLevel]);

  const stop = useCallback(() => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder) {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        audioCtxRef.current?.close().catch(() => {});
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        setIsRecording(false);
        setLevel(0);
        resolve(blob);
      };
      recorder.stop();
    });
  }, []);

  return { isRecording, level, start, stop };
}
