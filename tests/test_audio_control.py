import array
import math
import random
import tempfile
import unittest
import wave
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audio_control import verify_capture


class AudioControlTests(unittest.TestCase):
    def test_detects_delayed_waveform_with_gain_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            values = [int(8000 * math.sin(2 * math.pi * (250 * i / 16000 + 700 * (i / 16000) ** 2))) for i in range(4000)]
            with wave.open(str(folder / "source.wav"), "wb") as output:
                output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                output.writeframes(array.array("h", values).tobytes())
            captured = [0] * 1003 + [int(value * 0.4) for value in values] + [0] * 500
            (folder / "capture.pcm").write_bytes(array.array("h", captured).tobytes())
            result = verify_capture(folder / "capture.pcm", folder / "source.wav")
            self.assertTrue(result["passed"])
            self.assertGreater(result["source_waveform_correlation"], 0.95)

    def test_silence_and_unrelated_noise_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            values = [int(8000 * math.sin(2 * math.pi * (250 * i / 16000 + 700 * (i / 16000) ** 2))) for i in range(4000)]
            with wave.open(str(folder / "source.wav"), "wb") as output:
                output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                output.writeframes(array.array("h", values).tobytes())
            generator = random.Random(1537)
            for captured in [[0] * 8000, [generator.randint(-5000, 5000) for _ in range(8000)]]:
                (folder / "capture.pcm").write_bytes(array.array("h", captured).tobytes())
                self.assertFalse(verify_capture(folder / "capture.pcm", folder / "source.wav")["passed"])


if __name__ == "__main__":
    unittest.main()
