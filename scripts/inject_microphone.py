"""Deliver PCM to the emulator microphone, never to an Android text API."""
import sys
import wave
from pathlib import Path

import grpc
from grpc_discovery import settings

sys.path.insert(0, str(Path("work/microphone-proto").resolve()))
from microphone_pb2 import AudioFormat, AudioPacket, MicrophoneState
from microphone_pb2_grpc import EmulatorControllerStub


def packets(path):
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise ValueError("Expected mono signed 16-bit PCM")
        rate = source.getframerate()
        format = AudioFormat(samplingRate=rate, channels=AudioFormat.Mono,
                             format=AudioFormat.AUD_FMT_S16, mode=AudioFormat.MODE_UNSPECIFIED)
        frames = rate // 50
        while data := source.readframes(frames):
            yield AudioPacket(format=format, audio=data)


def main():
    # The emulator writes a discovery INI with its ephemeral authentication
    # token. Keep that token in memory; never include it in test evidence.
    values = settings()
    port = int(values["grpc.port"])
    metadata = (("authorization", "Bearer " + values["grpc.token"]),)
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = EmulatorControllerStub(channel)
        stub.setMicrophoneState(MicrophoneState(realAudioEnabled=False), metadata=metadata, timeout=5)
        stub.injectAudio(packets(Path(sys.argv[1])), metadata=metadata, timeout=35)


if __name__ == "__main__":
    main()
