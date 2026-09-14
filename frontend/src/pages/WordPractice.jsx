import { useEffect, useRef, useState } from "react";
import Mascot from "../components/Mascot";
import WordCard from "../components/WordCard";
import FloatingDecor from "../components/FloatingDecor";
import Doodles from "../components/Doodles";
import MicButton from "../components/MicButton";
import Tooltip from "../components/Tooltip";
import SpeechModeToggle from "../components/SpeechModeToggle";
import { useApp } from "../lib/AppContext";
import { useRecorder } from "../lib/useRecorder";
import { speak } from "../lib/tts";
import { highlightSegments } from "../lib/graphemeHighlight";
import { playSuccessChime, playGentleRetryTone, playLevelCompleteFanfare } from "../lib/sound";
import * as api from "../lib/api";

const MAX_WRONG_RETRIES = 3;
const MAX_UNCLEAR_IN_ROW = 2;

// Maps the new scorer's status vocabulary to what the child sees. Per the
// measured operating point (RESULTS.md), the overwhelming majority of
// attempts are "correct" and "unclear" - "wrong" is rare and deliberately
// treated as a valuable, non-punitive moment when it happens, not a
// failure state. Progress (stars/streak) is driven by ATTEMPTS, not by
// this status - see handleMicClick below.
function mascotStateFor(status) {
  if (status === "correct") return "celebrating";
  if (status === "wrong") return "demonstrating";
  if (status === "unclear_recording") return "thinking";
  return "encouraging"; // unclear
}

export default function WordPractice({ title, words, levelNumber = null, startIndex = 0, onExit }) {
  const { userId, user, saveSettings, refreshProgress } = useApp();

  const [index, setIndex] = useState(Math.min(startIndex, Math.max(words.length - 1, 0)));
  const [phase, setPhase] = useState("prompt"); // prompt | scoring | result | levelComplete
  const [result, setResult] = useState(null);
  const [mascotState, setMascotState] = useState("idle");
  const [micError, setMicError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [celebrateVariant, setCelebrateVariant] = useState(0);
  const [unclearStreak, setUnclearStreak] = useState(0);
  const [wrongTries, setWrongTries] = useState(0);
  const [wordsAttempted, setWordsAttempted] = useState(0);
  const [streak, setStreak] = useState(0);

  const appSpeechEnabled = user ? !!user.app_speech_enabled : true;
  const speakAloud = appSpeechEnabled && !!user?.speak_aloud;
  const speechRate = user?.speech_rate ?? 0.8;

  const { isRecording, level, start, stop } = useRecorder();

  const currentWord = words[index];
  const isLastWord = index === words.length - 1;

  const hasSpokenRef = useRef(false);

  useEffect(() => {
    setResult(null);
    setPhase("prompt");
    setMascotState("idle");
    setWrongTries(0);
    hasSpokenRef.current = false;
  }, [index]);

  useEffect(() => {
    if (phase === "prompt" && speakAloud && !hasSpokenRef.current && currentWord) {
      hasSpokenRef.current = true;
      const t = setTimeout(() => speak(currentWord.word, speechRate), 350);
      return () => clearTimeout(t);
    }
  }, [phase, speakAloud, speechRate, currentWord]);

  const handleReplay = () => {
    if (currentWord) speak(currentWord.word, speechRate);
  };

  const goToNextWordOrFinish = async () => {
    if (levelNumber !== null) {
      try {
        await api.advanceLevel(userId, levelNumber);
        refreshProgress().catch(() => {});
      } catch {
        // Non-fatal: the attempt itself was already recorded by /api/score.
      }
    }
    if (isLastWord) {
      if (levelNumber !== null) {
        setPhase("levelComplete");
        setMascotState("celebrating");
        playLevelCompleteFanfare();
      } else {
        onExit();
      }
      return;
    }
    setIndex((i) => i + 1);
  };

  const handleMicClick = async () => {
    setMicError("");
    if (!isRecording) {
      try {
        setMascotState("listening");
        await start();
      } catch (e) {
        setMicError("Couldn't access the microphone. Please allow mic access and try again.");
        setMascotState("idle");
      }
      return;
    }
    const blob = await stop();
    setMascotState("idle");
    if (!blob) return;
    setPhase("scoring");
    setMascotState("thinking");
    try {
      const res = await api.scoreWord({
        userId,
        word: currentWord.word,
        level: levelNumber,
        phonemesOverride: currentWord.phonemes_override,
        targetPhoneme: currentWord.target_phoneme,
        position: currentWord.position,
        audioBlob: blob,
      });
      setResult(res);
      setPhase("result");

      if (res.status === "unclear_recording") {
        setMascotState("thinking");
        return; // not scored - doesn't count as an attempt, no progress/streak change
      }

      // Progress comes from EFFORT, not from the model's verdict - the
      // model's signal is too sparse (measured recall on real errors is a
      // few percent - RESULTS.md) to carry a reward economy honestly.
      setWordsAttempted((n) => n + 1);
      setStreak((s) => s + 1);

      if (res.status === "correct") {
        setUnclearStreak(0);
        setWrongTries(0);
        setCelebrateVariant((v) => (v + 1) % 4);
        setMascotState("celebrating");
        playSuccessChime();
      } else if (res.status === "wrong") {
        setUnclearStreak(0);
        setMascotState("demonstrating");
        playGentleRetryTone();
        if (speakAloud || true) speak(currentWord.word, 0.7); // model the target word slowly regardless of the hear-it-first setting - this is the corrective moment
      } else {
        // unclear
        setUnclearStreak((n) => n + 1);
        setMascotState("encouraging");
        playGentleRetryTone();
      }
    } catch (e) {
      setMicError(e.message || "Something went wrong scoring that. Please try again.");
      setPhase("prompt");
      setMascotState("idle");
    }
  };

  const handleTryAgain = () => {
    setResult(null);
    setPhase("prompt");
    setMascotState("idle");
    setMicError("");
  };

  const handleNext = () => {
    goToNextWordOrFinish();
  };

  // After 2 unclears in a row, or after MAX_WRONG_RETRIES on a "wrong"
  // word, move on positively rather than let the child get stuck - per
  // the brief's explicit product rule.
  useEffect(() => {
    if (phase !== "result" || !result) return;
    if (result.status === "unclear" && unclearStreak >= MAX_UNCLEAR_IN_ROW) {
      const t = setTimeout(() => {
        setUnclearStreak(0);
        goToNextWordOrFinish();
      }, 1400);
      return () => clearTimeout(t);
    }
  }, [phase, result, unclearStreak]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggleSpeakAloud = (value) => saveSettings(value, speechRate).catch(() => {});
  const handleRateChange = (value) => saveSettings(speakAloud, value).catch(() => {});
  const handleToggleAppSpeech = (value) => saveSettings(!!user?.speak_aloud, speechRate, value).catch(() => {});

  if (!currentWord) {
    return (
      <div className="screen screen-practice">
        <p>No words in this set yet.</p>
        <button className="btn btn-secondary" onClick={onExit}>Back</button>
      </div>
    );
  }

  if (phase === "levelComplete") {
    return (
      <div className="screen screen-level-complete">
        <FloatingDecor variant="celebration" />
        <Doodles variant="celebration" />
        <Mascot state="celebrating" size={200} celebrateVariant={celebrateVariant} />
        <h1 className="level-complete-title">Level {levelNumber} complete!</h1>
        <p className="level-complete-sub">You practiced all {words.length} words. Great job!</p>
        <button className="btn btn-primary btn-large" onClick={onExit}>Back to map</button>
      </div>
    );
  }

  const segments = highlightSegments(currentWord.word, currentWord.target_phoneme);
  const showTryAgainAfterWrong = phase === "result" && result?.status === "wrong" && wrongTries < MAX_WRONG_RETRIES;
  const movingOnAfterUnclearStreak = phase === "result" && result?.status === "unclear" && unclearStreak >= MAX_UNCLEAR_IN_ROW;

  return (
    <div className="screen screen-practice screen-practice--v2">
      <FloatingDecor variant="practice" />
      <Doodles variant="practice" />

      <div className="practice-top">
        <button className="btn-icon" onClick={onExit} aria-label="Exit practice">✕</button>
        <div className="practice-progress-bar">
          <div className="practice-progress-bar-fill" style={{ width: `${((index + 1) / words.length) * 100}%` }} />
        </div>
        <span className="practice-progress-label">Word {index + 1} of {words.length}</span>
        {streak > 0 && <span className="practice-streak" title="Words practiced this session">🔥 {streak}</span>}
        <button className="btn-icon" onClick={() => setSettingsOpen((v) => !v)} aria-label="Settings">⚙</button>
      </div>

      {settingsOpen && (
        <div className="practice-settings-panel">
          <SpeechModeToggle enabled={appSpeechEnabled} onChange={handleToggleAppSpeech} />
          <div className="speak-aside-modes">
            <button className={`speak-mode-btn ${speakAloud ? "speak-mode-btn--active" : ""}`} onClick={() => handleToggleSpeakAloud(true)}>Hear it first</button>
            <button className={`speak-mode-btn ${!speakAloud ? "speak-mode-btn--active" : ""}`} onClick={() => handleToggleSpeakAloud(false)}>Read it myself</button>
            <Tooltip text="Hearing the word first is called imitation practice. Reading it alone tests independent production." />
          </div>
          {speakAloud && <button className="btn-icon replay-btn" onClick={handleReplay} aria-label="Replay word">🔊</button>}
          <div className="rate-slider-wrap">
            <label htmlFor="rate-slider">Speech rate: {speechRate.toFixed(1)}x</label>
            <input id="rate-slider" type="range" min="0.5" max="1.0" step="0.1" value={speechRate} onChange={(e) => handleRateChange(parseFloat(e.target.value))} />
          </div>
        </div>
      )}

      <div className="practice-hero">
        <div className="practice-hero-row">
          <div className="practice-word-card-wrap">
            <WordCard word={currentWord.word} size={220} />
          </div>

          <div className="practice-info-col">
            <div className="practice-word-row">
              <h2 className="target-word">
                {segments.map((seg, i) =>
                  seg.highlight ? <span key={i} className="target-word-highlight">{seg.text}</span> : <span key={i}>{seg.text}</span>
                )}
              </h2>
              {currentWord.target_phoneme && <span className="target-sound-chip">/{currentWord.target_phoneme}/</span>}
            </div>

            <Mascot state={mascotState} size={110} micLevel={level} celebrateVariant={celebrateVariant} />
          </div>
        </div>

        <div className="practice-feedback-area">
          {phase === "scoring" && <p className="scoring-hint">Checking your sounds...</p>}

          {phase === "result" && result?.status === "correct" && <p className="feedback-text feedback-text--correct">{result.feedback}</p>}

          {phase === "result" && result?.status === "unclear" && (
            <p className="feedback-text feedback-text--unclear">
              {movingOnAfterUnclearStreak ? "No worries - we'll come back to this one!" : result.feedback}
            </p>
          )}

          {phase === "result" && result?.status === "wrong" && (
            <p className="feedback-text feedback-text--wrong">{result.feedback}</p>
          )}

          {phase === "result" && result?.status === "unclear_recording" && (
            <p className="feedback-text feedback-text--mic">🎤 {result.feedback}</p>
          )}

          {micError && <p className="error-text">{micError}</p>}
        </div>
      </div>

      {phase !== "result" && !movingOnAfterUnclearStreak && (
        <div className="practice-bottom-bar">
          <MicButton isRecording={isRecording} level={level} onClick={handleMicClick} disabled={phase === "scoring"} />
          <p className="practice-hint">{isRecording ? "Listening... tap again when done" : "Tap the microphone and say the word"}</p>
        </div>
      )}

      {phase === "result" && !movingOnAfterUnclearStreak && (
        <div className="practice-bottom-bar practice-bottom-bar--actions">
          {result?.status === "unclear_recording" || result?.status === "unclear" || showTryAgainAfterWrong ? (
            <button className="btn btn-secondary btn-large" onClick={handleTryAgain}>Try again</button>
          ) : null}
          <button className="btn btn-primary btn-large" onClick={handleNext}>
            {isLastWord ? "Finish" : "Next word"}
          </button>
        </div>
      )}
    </div>
  );
}
