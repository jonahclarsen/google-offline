"""Verify the guest microphone captured the known host waveform, not just noise."""
import array
import math
import wave
from pathlib import Path


def verify_capture(pcm_path, wav_path):
    recorded = array.array("h", Path(pcm_path).read_bytes())
    with wave.open(str(wav_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Expected mono 16-bit source audio")
        rate = wav.getframerate()
        original = array.array("h", wav.readframes(wav.getnframes()))
    # Linear interpolation suffices for a transport control. The actual engine
    # receives PulseAudio's normal resampling, not this reference waveform.
    reference = []
    for index in range(int((len(original) - 1) * 16000 / rate)):
        pos = index * rate / 16000
        left = int(pos)
        fraction = pos - left
        reference.append(original[left] * (1 - fraction) + original[left + 1] * fraction)
    short = reference[::8]
    energy = sum(value * value for value in short)

    def correlation(offset):
        segment = recorded[offset:offset + len(reference):8]
        if len(segment) != len(short):
            return 0.0
        denominator = math.sqrt(energy * sum(value * value for value in segment))
        return sum(a * b for a, b in zip(short, segment)) / denominator if denominator else 0.0

    # Locate the utterance using its energy envelope first. A coarse scan of
    # the raw waveform can miss the correct delay due to pitch phase changes.
    block = 80
    def envelope(values):
        return [math.sqrt(sum(value * value for value in values[start:start + block]) / block) for start in range(0, len(values) - block + 1, block)]
    source_envelope, capture_envelope = envelope(reference), envelope(recorded)
    source_energy = sum(value * value for value in source_envelope)
    coarse, envelope_best = 0, 0.0
    for index in range(max(0, len(capture_envelope) - len(source_envelope)) + 1):
        segment = capture_envelope[index:index + len(source_envelope)]
        if len(segment) != len(source_envelope):
            continue
        denominator = math.sqrt(source_energy * sum(value * value for value in segment))
        value = sum(a * b for a, b in zip(source_envelope, segment)) / denominator if denominator else 0.0
        if value > envelope_best:
            coarse, envelope_best = index * block, value
    maximum = max(0, len(recorded) - len(reference))
    best_offset, best = 0, 0.0
    for offset in range(max(0, coarse - block * 2), min(maximum, coarse + block * 2) + 1):
        value = correlation(offset)
        if value > best:
            best_offset, best = offset, value
    rms = math.sqrt(sum(value * value for value in recorded) / len(recorded)) if recorded else 0.0
    return {"passed": rms >= 100 and best >= 0.35, "samples": len(recorded), "rms": rms, "source_waveform_correlation": best, "best_offset_samples": best_offset}
