"""Locate only the selected emulator's private gRPC discovery settings."""
import configparser
import os
import subprocess
from pathlib import Path


def settings():
    explicit = os.environ.get("GBOARD_EMULATOR_GRPC_CONFIG")
    serial = subprocess.check_output(["adb", "get-serialno"], text=True).strip()
    if not serial.startswith("emulator-"):
        raise RuntimeError("Microphone injection is restricted to an emulator")
    roots = [Path.home() / "Library/Caches/TemporaryItems", Path(f"/run/user/{os.getuid()}"), Path("/tmp")]
    for key in ("XDG_RUNTIME_DIR", "ANDROID_EMULATOR_HOME", "ANDROID_USER_HOME", "TMPDIR"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]))
    paths = [Path(explicit)] if explicit else [p for root in roots for p in (root / "avd/running").glob("pid_*.ini")]
    for path in paths:
        config = configparser.ConfigParser(interpolation=None)
        config.read_string("[emulator]\n" + path.read_text())
        values = config["emulator"]
        if not explicit and values.get("port.serial") not in (serial, serial.removeprefix("emulator-")):
            continue
        if values.get("grpc.token") and 0 < int(values.get("grpc.port", "0")) < 65536:
            return values
    raise RuntimeError("No authenticated gRPC discovery settings for the selected emulator")
