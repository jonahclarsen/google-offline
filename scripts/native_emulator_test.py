"""Run the ARM64 scenario on a host with a native ARM Android emulator."""
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("api", choices=("31", "37.0"))
    args = parser.parse_args()
    if platform.machine().lower() not in ("arm64", "aarch64"):
        raise RuntimeError("This scenario requires a native ARM64 host")
    root = Path.cwd()
    sdk = Path(os.environ["ANDROID_HOME"]).resolve()
    avdmanager = sdk / "cmdline-tools/latest/bin/avdmanager"
    if not avdmanager.exists():
        avdmanager = sdk / "cmdline-tools/22.0/bin/avdmanager"
    for path in (Path("work/probe/probe.apk"), Path("work/hello-world.wav"),
                 Path("dist/arm64/gboard-offline-coexist-experimental.apk")):
        if not path.exists():
            raise RuntimeError(f"Missing test input: {path}")
    generated = Path("work/microphone-proto")
    generated.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "grpc_tools.protoc", "-I", "tests",
                    f"--python_out={generated}", f"--grpc_python_out={generated}",
                    "tests/microphone.proto"], check=True)
    # These ports were selected once with secrets.randbelow and are permanent.
    settings = json.loads(Path("tests/emulator-settings.json").read_text())
    for port in (settings["console_port"], settings["console_port"] + 1, settings["grpc_port"]):
        with socket.socket() as check:
            try:
                check.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(f"Fixture port {port} is in use; stop its existing test emulator first") from error
    name = "offline-arm" + args.api.replace(".", "-")
    env = dict(os.environ, ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               ANDROID_AVD_HOME=str(root / "work/native-avd"),
               ANDROID_USER_HOME=str(root / "work/native-android"),
               ANDROID_SERIAL=f"emulator-{settings['console_port']}",
               GBOARD_TEST_ARCH="arm64", GBOARD_AUDIO_TRANSPORT="grpc")
    for key in ("ANDROID_AVD_HOME", "ANDROID_USER_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    subprocess.run([str(avdmanager), "create", "avd", "--force", "-n", name,
                    "-k", f"system-images;android-{args.api};google_apis;arm64-v8a",
                    "-d", "pixel_2"], input="no\n", text=True, env=env, check=True)
    config = Path(env["ANDROID_AVD_HOME"]) / (name + ".avd") / "config.ini"
    with config.open("a") as file:
        file.write("\ndisk.dataPartition.size=4G\nhw.keyboard=no\n")
    logpath = root / f"work/native-{args.api}-emulator.log"
    with logpath.open("w") as log:
        process = subprocess.Popen([str(sdk / "emulator/emulator"), "-avd", name,
            "-no-window", "-gpu", "software", "-no-snapshot", "-no-boot-anim",
            "-writable-system", "-camera-back", "none", "-memory", "4096", "-cores", "4",
            "-grpc-use-token", "-grpc", str(settings["grpc_port"]),
            "-port", str(settings["console_port"])], env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(180):
                if process.poll() is not None:
                    raise RuntimeError(f"Emulator exited; inspect {logpath}")
                boot = subprocess.run(["adb", "shell", "getprop", "sys.boot_completed"],
                    env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
                if boot.stdout.strip() == "1":
                    break
                time.sleep(2)
            else:
                raise RuntimeError("Native emulator did not finish booting")
            subprocess.run(["adb", "shell", "input", "keyevent", "82"], env=env, check=True)
            for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
                subprocess.run(["adb", "shell", "settings", "put", "global", key, "0"], env=env, check=True)
            subprocess.run([sys.executable, "scripts/emulator_test.py"], env=env, check=True)
        finally:
            try:
                subprocess.run(["adb", "emu", "kill"], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.terminate()


if __name__ == "__main__":
    main()
