import { useEffect, useMemo, useRef, useState } from "react";
import Mascot from "../components/Mascot";
import FloatingDecor from "../components/FloatingDecor";
import Doodles from "../components/Doodles";
import MicButton from "../components/MicButton";
import ProgressRing from "../components/ProgressRing";
import PhonemeChips from "../components/PhonemeChips";
import Tooltip from "../components/Tooltip";
import SpeechModeToggle from "../components/SpeechModeToggle";
import { useApp } from "../lib/AppContext";
import { useRecorder } from "../lib/useRecorder";
import { speak } from "../lib/tts";
import { playSuccessChime, playGentleRetryTone, playLevelCompleteFanfare } from "../lib/sound";
import * as api from "../lib/api";

export default function WordPractice({ title, words, levelNumber = null, startIndex = 0, onExit }) {
  const { userId, user, saveSettings, refreshProgress } = useApp();

  const [index, setIndex] = useState(Math.min(startIndex, Math.max(words.length - 1, 0)));
  const [phase, setPhase] = useState("prompt"); // prompt | scoring | result | levelComplete
  const [result, setResult] = useState(null);
  const [mascotState, setMascotState] = useState("idle");
  const [micError, setMicError] = useState("");

  // app_speech_enabled comes back from the API as a SQLite integer (0/1),
  // not a boolean, so it must be coerced explicitly - `0 && <jsx/>` in the
  // render below would otherwise print a literal "0" instead of rendering
  // nothing, since only `false`/`null`/`undefined` short-circuit silently.
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
      if (res.percent_correct === 100) {
        setMascotState("celebrating");
        playSuccessChime();
      } else {
        setMascotState("encouraging");
        playGentleRetryTone();
      }
      refreshProgress().catch(() => {});
    } catch (e) {
      setMicError(e.message || "Something went wrong scoring that. Please try again.");
      setPhase("prompt");
    }
  };

  const handleTryAgain = () => {
    setResult(null);
    setPhase("prompt");
    setMascotState("idle");
    setMicError("");
  };

  const handleNext = async () => {
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

  const handleToggleSpeakAloud = (value) => {
    saveSettings(value, speechRate).catch(() => {});
  };

  const handleRateChange = (value) => {
    saveSettings(speakAloud, value).catch(() => {});
  };

  const handleToggleAppSpeech = (value) => {
    saveSettings(!!user?.speak_aloud, speechRate, value).catch(() => {});
  };

  if (!currentWord) {
    return (
      <div className="screen screen-practice">
        <p>No words in this set yet.</p>
        <button className="btn btn-secondary" onClick={onExit}>
          Back
        </button>
      </div>
    );
  }

  if (phase === "levelComplete") {
    return (
      <div className="screen screen-level-complete">
        <FloatingDecor variant="celebration" />
        <Doodles variant="celebration" />
        <Mascot state="celebrating" size={200} />
        <h1 className="level-complete-title">Level {levelNumber} complete!</h1>
        <p className="level-complete-sub">You practiced all {words.length} words. Great job!</p>
        <button className="btn btn-primary btn-large" onClick={onExit}>
          Back to map
        </button>
      </div>
    );
  }

  return (
    <div className="screen screen-practice">
      <FloatingDecor variant="practice" />
      <Doodles variant="practice" />
      <div className="practice-top">
        <button className="btn-icon" onClick={onExit} aria-label="Exit practice">
          ✕
        </button>
        <div className="practice-progress-bar">
          <div className="practice-progress-bar-fill" style={{ width: `${((index + 1) / words.length) * 100}%` }} />
        </div>
        <span className="practice-progress-label">
          Word {index + 1} of {words.length}
        </span>
        <SpeechModeToggle enabled={appSpeechEnabled} onChange={handleToggleAppSpeech} compact />
      </div>

      <h2 className="practice-title">{title}</h2>

      {appSpeechEnabled && (
        <SpeakAsideToggle
          speakAloud={speakAloud}
          speechRate={speechRate}
          onToggle={handleToggleSpeakAloud}
          onRateChange={handleRateChange}
          onReplay={handleReplay}
        />
      )}

      <div className="practice-main">
        <Mascot state={mascotState} size={150} />

        <div className="target-word">{currentWord.word}</div>
        {currentWord.target_phoneme && (
          <div className="target-phoneme-hint">Target sound: {currentWord.target_phoneme}</div>
        )}

        {phase === "prompt" && (
          <>
            <MicButton isRecording={isRecording} level={level} onClick={handleMicClick} />
            <p className="practice-hint">
              {isRecording ? "Listening... tap again when done" : "Tap the microphone and say the word"}
            </p>
            {micError && <p className="error-text">{micError}</p>}
          </>
        )}

        {phase === "scoring" && (
          <div className="scoring-spinner">
            <div className="spinner" />
            <p>Checking your sounds...</p>
          </div>
        )}

        {phase === "result" && result && (
          <div className="result-panel">
            <ProgressRing percent={result.percent_correct} />
            <PhonemeChips results={result.results} targetPhoneme={currentWord.target_phoneme} />
            <p className="feedback-text">{result.feedback}</p>

            <div className="result-actions">
              <button className="btn btn-secondary" onClick={handleTryAgain}>
                Try again
              </button>
              <button className="btn btn-primary btn-large" onClick={handleNext}>
                {isLastWord ? "Finish" : "Next word"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SpeakAsideToggle({ speakAloud, speechRate, onToggle, onRateChange, onReplay }) {
  return (
    <div className="speak-aside">
      <div className="speak-aside-modes">
        <button
          className={`speak-mode-btn ${speakAloud ? "speak-mode-btn--active" : ""}`}
          onClick={() => onToggle(true)}
        >
          Hear it first
        </button>
        <button
          className={`speak-mode-btn ${!speakAloud ? "speak-mode-btn--active" : ""}`}
          onClick={() => onToggle(false)}
        >
          Read it myself
        </button>
        <Tooltip text="Hearing the word first is called imitation practice. Reading it alone tests independent production. Therapists may want to switch between them." />
      </div>
      {speakAloud && (
        <button className="btn-icon replay-btn" onClick={onReplay} aria-label="Replay word">
          🔊
        </button>
      )}
      <div className="rate-slider-wrap">
        <label htmlFor="rate-slider">Speech rate: {speechRate.toFixed(1)}x</label>
        <input
          id="rate-slider"
          type="range"
          min="0.5"
          max="1.0"
          step="0.1"
          value={speechRate}
          onChange={(e) => onRateChange(parseFloat(e.target.value))}
        />
      </div>
    </div>
  );
}
