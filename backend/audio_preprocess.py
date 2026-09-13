"""Audio preprocessing for the GOP scorer: decode to 16kHz mono float32,
peak-normalize, trim leading/trailing silence, and pad short clips - all as
explicit, inspectable numpy steps rather than opaque ffmpeg filter chains,
so each step can be reasoned about (and logged) independently. ffmpeg is
used only for the one thing numpy can't do: decoding an arbitrary input
container/codec (webm/opus from the browser's MediaRecorder, aiff from
macOS `say` in testing, etc.) into raw PCM.
"""
import logging
import subprocess

import numpy as np

from gop_config import (
    MIN_AUDIO_SECONDS,
    SILENCE_TRIM_ENERGY_THRESHOLD,
    SILENCE_TRIM_MARGIN_SECONDS,
    SILENT_RECORDING_RMS_THRESHOLD,
    TARGET_SAMPLE_RATE,
)

logger = logging.getLogger("speechpal.audio_preprocess")


class SilentRecordingError(Exception):
    """Raised instead of scoring when a recording is silence or
    near-silence - Step 7's explicit requirement: reject with a clear
    message rather than let the scorer produce meaningless output on noise."""


def _decode_to_pcm(input_path: str) -> np.ndarray:
    """ffmpeg decodes whatever codec/container the upload is in, resamples
    to TARGET_SAMPLE_RATE, downmixes to mono, and emits raw 32-bit float PCM
    on stdout - piped directly rather than via a temp file."""
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", "1",
            "-f", "f32le",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {result.stderr[-2000:].decode(errors='replace')}")
    return np.frombuffer(result.stdout, dtype=np.float32).copy()


def _trim_silence(audio: np.ndarray, energy_threshold: float, margin_seconds: float = SILENCE_TRIM_MARGIN_SECONDS) -> np.ndarray:
    """Trim leading/trailing silence with a simple 20ms-window RMS energy
    threshold, on already peak-normalized audio (so the threshold means the
    same thing regardless of the recording's original loudness), then keep
    margin_seconds of extra audio beyond the detected boundary on each side
    rather than cutting flush against the threshold. A low-energy word-final
    sound (a nasal murmur, a fricative, an unreleased stop) can dip under
    the threshold before it's actually over - cutting flush there silently
    destroyed exactly those sounds. The margin costs a bit of extra silence
    around the speech (which forced alignment's own blank frames absorb
    harmlessly); it never costs any of the speech itself."""
    window = max(int(TARGET_SAMPLE_RATE * 0.02), 1)
    n_windows = len(audio) // window
    if n_windows == 0:
        return audio
    energies = np.sqrt(
        np.mean(audio[: n_windows * window].reshape(n_windows, window) ** 2, axis=1)
    )
    above = np.flatnonzero(energies > energy_threshold)
    if len(above) == 0:
        return audio[:0]  # nothing above threshold anywhere - caller's RMS check will reject
    margin_samples = int(margin_seconds * TARGET_SAMPLE_RATE)
    start = max(above[0] * window - margin_samples, 0)
    end = min((above[-1] + 1) * window + margin_samples, len(audio))
    return audio[start:end]


def preprocess_audio(input_path: str) -> np.ndarray:
    """Returns 16kHz mono float32 audio: peak-normalized, silence-trimmed,
    padded to at least MIN_AUDIO_SECONDS if needed. Raises
    SilentRecordingError instead of returning near-empty/near-silent audio."""
    audio = _decode_to_pcm(input_path)
    if len(audio) == 0:
        raise SilentRecordingError("No audio data was decoded from the recording.")

    peak = float(np.max(np.abs(audio)))
    if peak < 1e-6:
        raise SilentRecordingError("Recording is silent.")
    normalized = (audio / peak).astype(np.float32)

    trimmed = _trim_silence(normalized, SILENCE_TRIM_ENERGY_THRESHOLD)
    trimmed_rms = float(np.sqrt(np.mean(trimmed ** 2))) if len(trimmed) else 0.0
    logger.info(
        "preprocess_audio: raw=%.3fs peak=%.4f trimmed=%.3fs trimmed_rms=%.4f",
        len(audio) / TARGET_SAMPLE_RATE, peak, len(trimmed) / TARGET_SAMPLE_RATE, trimmed_rms,
    )
    if len(trimmed) == 0 or trimmed_rms < SILENT_RECORDING_RMS_THRESHOLD:
        raise SilentRecordingError(
            "Recording appears to be silence or near-silence - please try again closer to the microphone."
        )

    min_samples = int(MIN_AUDIO_SECONDS * TARGET_SAMPLE_RATE)
    if len(trimmed) < min_samples:
        pad_total = min_samples - len(trimmed)
        pad_left = pad_total // 2
        pad_right = pad_total - pad_left
        trimmed = np.pad(trimmed, (pad_left, pad_right), mode="constant")
        logger.info("preprocess_audio: padded short clip to %.3fs (+%.3fs)", MIN_AUDIO_SECONDS, pad_total / TARGET_SAMPLE_RATE)

    return trimmed
