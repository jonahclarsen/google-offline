#!/usr/bin/env python3
"""Exercise the real keyboard UI; report speech service prerequisites honestly."""
import json
import hashlib
import array
import os
import re
import subprocess
import sys
import time
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from audio_control import verify_capture
from arm_translation_baseline import crashes_for_package, run_baseline

PACKAGE = "com.google.android.inputmethod.local"
ORIGINAL_PACKAGE = "com.google.android.inputmethod.latin"
TEST_ARCH = "x86_64"
OUT = Path("dist") / TEST_ARCH
AUDIO_TRANSPORT = os.environ.get("GBOARD_AUDIO_TRANSPORT", "pulse")


def microphone_on():
    adb("emu", "avd", "hostmicoff" if AUDIO_TRANSPORT == "grpc" else "hostmicon")


def play_audio(path):
    if AUDIO_TRANSPORT == "grpc":
        return subprocess.Popen([sys.executable, "scripts/inject_microphone.py", str(path)])
    if AUDIO_TRANSPORT != "pulse":
        raise RuntimeError("Unknown microphone transport")
    return subprocess.Popen(["paplay", "--device=speech_input", "--latency-msec=50", str(path)])


def adb(*args, check=True):
    timeout = 60 if args and args[0] in ("install", "wait-for-device") else 20
    result = subprocess.run(["adb", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and result.returncode:
        print(result.stdout, flush=True)
        result.check_returncode()
    return result.stdout


def ui():
    # UiAutomation suppresses other accessibility services while connected.
    # Prefer the helper's full window tree, including the IME window.
    root = ET.Element("hierarchy")
    raw = adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/accessibility.json", check=False)
    try:
        for item in json.loads(raw):
            ET.SubElement(root, "node", item)
        if len(root):
            return root
    except (ValueError, TypeError):
        pass
    adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
    return ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))


def tap(node):
    left, top, right, bottom = map(int, re.findall(r"\d+", node.attrib["bounds"]))
    adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))


def screenshot(name):
    with (OUT / name).open("wb") as file:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=file, check=True)


def ensure_emulator_root():
    # Some current adbd versions close the transport before `adb root` gets
    # its acknowledgement. Verify the resulting UID after reconnecting.
    for _ in range(3):
        adb("root", check=False)
        adb("wait-for-device")
        if adb("shell", "id", "-u", check=False).strip() == "0":
            return
        time.sleep(2)
    raise RuntimeError("Disposable emulator did not provide root for isolation")


def probe_file(name):
    return adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/" + name, check=False)


def layout_target(key):
    # Fixed Pixel 2 portrait fixture, visually checked in saved screenshots.
    # These remain real touch events, including when accessibility hides keys.
    if "1080x1920" not in adb("shell", "wm", "size"):
        raise RuntimeError("Unexpected display geometry for coordinate fallback")
    x, y = {"q": (54, 1244), "w": (162, 1244), "e": (270, 1244), "voice": (1020, 1106)}[key]
    return ET.Element("node", {"bounds": f"[{x-1},{y-1}][{x+1},{y+1}]", "class": "_FIXED_EMULATOR_LAYOUT", "content-desc": key})


def start_probe(*extras):
    adb("shell", "am", "start", "-W", "-f", "0x10008000", "-n", "art.jonah.offlineprobe/.ProbeActivity", *extras)


def wait_keyboard():
    for _ in range(25):
        tree = ui()
        if probe_file("ime-visible.txt").strip() == "true" or any(n.attrib.get("class") == "_IME_WINDOW" for n in tree.iter("node")):
            return tree
        editor = next((n for n in tree.iter("node") if n.attrib.get("class") == "android.widget.EditText"), None)
        if editor is not None:
            tap(editor)
        time.sleep(1)
    raise RuntimeError("The test editor did not report a visible keyboard")


def network_control():
    for _ in range(20):
        try:
            return json.loads(probe_file("network-control.json"))
        except (ValueError, TypeError):
            time.sleep(1)
    raise RuntimeError("Network control did not finish")


def exercise_keyboard(prefix=""):
    # A visible IME surface can precede usable touch handlers after cold boot.
    # Wait for real key taps to change the real editor; stale accessibility
    # windows and requested insets are insufficient readiness signals.
    if probe_file("input.txt").strip():
        raise RuntimeError("Keyboard readiness test must start with an empty editor")
    for attempt in range(15):
        if attempt:
            value = probe_file("input.txt").strip()
            if value:
                adb("shell", "input", "keyevent", *(["67"] * min(len(value), 32)))
                time.sleep(0.3)
        for letter in "qwe":
            tap(layout_target(letter))
            time.sleep(0.25)
        time.sleep(1)
        value = probe_file("input.txt").strip()
        if value == "qwe":
            screenshot(f"{prefix}keyboard-ready.png")
            adb("shell", "input", "keyevent", "67", "67", "67")
            for _ in range(20):
                if not probe_file("input.txt").strip():
                    return {"passed": True, "actual_typed": value, "attempts": attempt + 1}
                time.sleep(0.1)
            raise RuntimeError("Could not clear readiness keystrokes before speech")
        time.sleep(1)
    raise RuntimeError("Real keyboard taps did not become interactive after startup")


def prepare_speech_loop():
    with wave.open("work/hello-world.wav", "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise RuntimeError("Expected a mono 16-bit speech fixture")
        rate = source.getframerate()
        original = array.array("h", source.readframes(source.getnframes()))
    # Feed the microphone at the recognizer's native sample rate. Avoid the
    # emulator's additional real-time resampler during transport diagnostics.
    normalized = array.array("h")
    for index in range(int((len(original) - 1) * 16000 / rate)):
        position = index * rate / 16000
        left = int(position)
        fraction = position - left
        normalized.append(round(original[left] * (1 - fraction) + original[left + 1] * fraction))
    samples = normalized.tobytes()
    with wave.open("work/hello-world-16k.wav", "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(samples)
    with wave.open("work/speech-loop.wav", "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        gap = bytes(4000 * 2)
        output.writeframes((samples + gap) * 8)


def capture_microphone_control(prefix=""):
    # Repeat after reboot too: host playback success does not establish that
    # Android's restarted audio HAL receives anything other than silence.
    microphone_on()
    start_probe("--ez", "record_audio", "true", "--ez", "check_network", "true")
    time.sleep(2)
    for _ in range(2):
        player = play_audio("work/hello-world-16k.wav")
        if player.wait(timeout=40):
            raise RuntimeError("Microphone control playback failed")
        time.sleep(0.5)
    time.sleep(4)
    output = OUT / f"{prefix}microphone-control.pcm"
    adb("pull", "/sdcard/Android/data/art.jonah.offlineprobe/files/microphone-control.pcm", str(output))
    return verify_capture(output, "work/hello-world.wav")


def dictation_attempt(prefix=""):
    microphone_on()
    readiness = exercise_keyboard(prefix)
    tree = ui()
    time.sleep(1)
    if probe_file("input.txt").strip():
        raise RuntimeError("Speech test must start from an empty real editor")
    mic = next((n for n in tree.iter("node") if n.attrib.get("package") == PACKAGE and any(word in n.attrib.get("content-desc", "").lower() for word in ("voice", "microphone", "dictat"))), None)
    if mic is None:
        mic = layout_target("voice")
    pid = adb("shell", "pidof", "-s", PACKAGE).strip()
    with (OUT / f"{prefix}gboard-voice-logcat.txt").open("w") as voice_log:
        capture = subprocess.Popen(["adb", "logcat", "--pid", pid, "-v", "threadtime"], stdout=voice_log, stderr=subprocess.STDOUT)
        player = None
        try:
            if mic is not None:
                # Keep one live PulseAudio stream running across mic startup,
                # avoiding source suspension between tiny playback processes.
                if AUDIO_TRANSPORT == "pulse":
                    player = play_audio("work/speech-loop.wav")
                    time.sleep(1)
                tap(mic)
                time.sleep(1)
                # Recent ARM audio HALs destroy their input between recordings.
                # Opening the gRPC forwarder before the guest has an input can
                # crash the emulator itself in audio_forwarder_enable.
                if AUDIO_TRANSPORT == "grpc":
                    player = play_audio("work/speech-loop.wav")
                screenshot(f"{prefix}voice-listening.png")
                (OUT / f"{prefix}audio-state.txt").write_text(adb("shell", "dumpsys", "audio"))
                if AUDIO_TRANSPORT == "pulse":
                    (OUT / f"{prefix}pulse-source-outputs.txt").write_text(subprocess.check_output(["pactl", "list", "source-outputs"], text=True))
                # Blocking gRPC delivery follows guest audio consumption. Once
                # the recognizer finishes, the guest may stop consuming while
                # repeated fixture audio remains queued. Stop the producer
                # only after the actual editor contains a recognized phrase.
                deadline = time.monotonic() + 40
                while player.poll() is None:
                    text = re.sub(r"[^a-z ]", "", probe_file("input.txt").lower())
                    if "hello world" in text:
                        player.terminate()
                        player.wait(timeout=5)
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Synthetic speech delivery timed out")
                    time.sleep(0.5)
                time.sleep(3)
        finally:
            if player is not None and player.poll() is None:
                player.terminate()
                player.wait(timeout=5)
            capture.terminate()
            capture.wait(timeout=5)
    screenshot(f"{prefix}voice-attempt.png")
    voice_tree = ui()
    (OUT / f"{prefix}voice-ui.xml").write_text(ET.tostring(voice_tree, encoding="unicode"))
    after_speech = [n.attrib.get("text", "") for n in voice_tree.iter("node") if n.attrib.get("class") == "android.widget.EditText"]
    actual_dictated = adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/input.txt").strip()
    voice_log_text = (OUT / f"{prefix}gboard-voice-logcat.txt").read_text()
    local_engine_confirmed = "Using Fallback on-device recognizer." in voice_log_text or "Using the OnDevice recognizer." in voice_log_text
    network_recognizer_started = "Online recognizer - start listening" in voice_log_text
    crash_log = adb("logcat", "-d", "-b", "crash")
    (OUT / f"{prefix}crashes.txt").write_text(crash_log)
    crash_free = not crashes_for_package(crash_log, PACKAGE)
    speech_passed = crash_free and local_engine_confirmed and not network_recognizer_started and mic is not None and any("hello world" in re.sub(r"[^a-z ]", "", value.lower()) for value in [actual_dictated])
    # The fixture phrase is never inserted by any text API. A real local
    # transcript proves the microphone path even when the separate whole-wave
    # correlation diagnostic is disrupted by emulator audio timing jitter.
    return {"passed": speech_passed, "actual_dictated": actual_dictated, "keyboard_readiness": readiness,
            "microphone_path_verified_by_transcript": "hello world" in re.sub(r"[^a-z ]", "", actual_dictated.lower()),
            "local_engine_confirmed": local_engine_confirmed,
            "network_recognizer_started": network_recognizer_started,
            "gboard_crash_free": crash_free, "voice_button_found": mic is not None,
            "voice_button": mic.attrib if mic is not None else None,
            "accessibility_input_values": after_speech}


def main():
    adb("logcat", "-c")
    import shutil
    shutil.copyfile("work/hello-world.wav", OUT / "source-speech.wav")
    prepare_speech_loop()
    shutil.copyfile("work/speech-loop.wav", OUT / "speech-loop.wav")
    (OUT / "preinstalled-packages.txt").write_text(adb("shell", "pm", "list", "packages", "-f"))
    original_before = adb("shell", "pm", "path", ORIGINAL_PACKAGE)
    (OUT / "preinstall-package.txt").write_text(adb("shell", "dumpsys", "package", ORIGINAL_PACKAGE))
    requested_abi = "arm64-v8a" if TEST_ARCH == "arm64" else "x86_64"
    adb("install", "--no-incremental", "--abi", requested_abi, "-r", str(OUT / "gboard-offline-coexist-experimental.apk"))
    adb("install", "--no-incremental", "-r", "work/probe/probe.apk")
    adb("shell", "pm", "grant", "art.jonah.offlineprobe", "android.permission.RECORD_AUDIO")
    adb("shell", "settings", "put", "secure", "enabled_accessibility_services", "art.jonah.offlineprobe/.ProbeAccessibilityService")
    adb("shell", "settings", "put", "secure", "accessibility_enabled", "1")
    services = [line.strip() for line in adb("shell", "ime", "list", "-a", "-s").splitlines()]
    (OUT / "ime-services.txt").write_text("\n".join(services))
    ime = next(s for s in services if s.startswith(PACKAGE + "/"))
    adb("shell", "ime", "enable", ime)
    adb("shell", "ime", "set", ime)
    adb("shell", "pm", "grant", PACKAGE, "android.permission.RECORD_AUDIO", check=False)
    adb("shell", "am", "force-stop", ORIGINAL_PACKAGE)
    start_probe()
    time.sleep(8)
    # A fresh API 37 image may show a launcher ANR during first boot. Only
    # close that known unrelated process; Gboard/probe failures remain visible.
    for _ in range(3):
        tree = ui()
        launcher_anr = any("Pixel Launcher isn't responding" in n.attrib.get("text", "") for n in tree.iter("node"))
        close = next((n for n in tree.iter("node") if n.attrib.get("package") == "android" and n.attrib.get("text", "").lower() == "close app"), None)
        if not launcher_anr or close is None:
            break
        screenshot("launcher-anr.png")
        tap(close)
        start_probe()
        time.sleep(5)
    # Dismiss first-run dialogs only when their labels are understood.
    for _ in range(3):
        tree = ui()
        buttons = [n for n in tree.iter("node") if n.attrib.get("text", "").lower() in ("got it", "no thanks", "not now", "ok") and n.attrib.get("clickable") == "true"]
        if not buttons:
            break
        tap(buttons[0])
        time.sleep(2)
    # A first IME service startup can finish after showSoftInput was requested.
    # Refocus the real editor while waiting, rather than treating its absence
    # after a fixed sleep as a failed keyboard implementation.
    wait_keyboard()
    screenshot("keyboard.png")
    tree = ui()
    (OUT / "keyboard-ui.xml").write_text(ET.tostring(tree, encoding="unicode"))
    typed = []
    for letter in "qwe":
        node = next((n for n in tree.iter("node") if n.attrib.get("package") == PACKAGE and (n.attrib.get("text") == letter or n.attrib.get("content-desc") == letter)), None)
        if node is None:
            node = layout_target(letter)
        tap(node)
        typed.append(letter)
        time.sleep(0.3)
    time.sleep(1)
    tree = ui()
    input_values = [n.attrib.get("text", "") for n in tree.iter("node") if n.attrib.get("class") == "android.widget.EditText"]
    actual_typed = adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/input.txt").strip()
    keyboard_passed = typed == list("qwe") and actual_typed == "qwe"
    screenshot("typed.png")
    dump = adb("shell", "dumpsys", "package", PACKAGE)
    (OUT / "package.txt").write_text(dump)
    primary_abi = re.search(r"primaryCpuAbi=(\S+)", dump)
    if primary_abi is None or primary_abi[1] != requested_abi:
        raise RuntimeError("Installed APK did not select the requested native ABI")
    cloud_backup_allowed = any("ALLOW_BACKUP" in line for line in dump.splitlines() if "pkgFlags=" in line)
    if cloud_backup_allowed:
        raise RuntimeError("Installed Gboard still allows cloud backup")
    # A permission declaration and a runtime grant are distinct checks.
    direct_granted = "android.permission.INTERNET: granted=true" in dump
    if direct_granted:
        raise RuntimeError("Installed Gboard has INTERNET permission")
    speech = json.loads(adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/speech-services.json"))
    (OUT / "speech-services.json").write_text(json.dumps(speech, indent=2) + "\n")
    mic = next((n for n in tree.iter("node") if n.attrib.get("package") == PACKAGE and any(word in n.attrib.get("content-desc", "").lower() for word in ("voice", "microphone", "dictat"))), None)
    # Root is available only on this disposable Google APIs emulator. Deny all
    # guest egress, including external Google recognition services, before
    # playing synthetic speech. This does not configure the user's phone.
    ensure_emulator_root()
    adb("shell", "iptables", "-I", "OUTPUT", "1", "-j", "DROP")
    adb("shell", "ip6tables", "-I", "OUTPUT", "1", "-j", "DROP")
    (OUT / "network-isolation.txt").write_text(adb("shell", "iptables", "-S", "OUTPUT") + adb("shell", "ip6tables", "-S", "OUTPUT"))
    microphone_control = capture_microphone_control()
    isolated_network = network_control()
    offline_voice = dictation_attempt()
    report = {
        "arm64_translation_baseline": ARM_BASELINE,
        "tested_apk_sha256": hashlib.sha256((OUT / "gboard-offline-coexist-experimental.apk").read_bytes()).hexdigest(),
        "audio_transport": AUDIO_TRANSPORT,
        "tested_apk_arch": TEST_ARCH, "installed_primary_cpu_abi": primary_abi[1],
        "emulator_supported_abis": adb("shell", "getprop", "ro.product.cpu.abilist").strip(),
        "native_bridge": adb("shell", "getprop", "ro.dalvik.vm.native.bridge").strip(),
        "cloud_backup_allowed": cloud_backup_allowed,
        "keyboard_taps": typed, "actual_typed": actual_typed,
        "keyboard_typing_passed": keyboard_passed,
        "gboard_direct_internet_granted": direct_granted,
        "stock_gboard_unchanged": bool(original_before.strip()) and original_before == adb("shell", "pm", "path", ORIGINAL_PACKAGE),
        "speech": speech, "expected_speech": "hello world",
        "microphone_waveform_diagnostic": microphone_control,
        "microphone_diagnostic_scope": "Separate whole-wave timing comparison; actual local transcription independently verifies speech transport.",
        "isolated_network_control": isolated_network,
        "offline_voice": offline_voice,
        "offline_dictation_passed": offline_voice["passed"] and not isolated_network["success"],
        "post_reboot_online_dictation_passed": False,
        "isolation_scope": "First phase blocks all emulator IPv4/IPv6 egress. Second phase reboots and verifies another app has network access. The APK requires no phone firewall or VPN.",
    }
    (OUT / "runtime-report.json").write_text(json.dumps(report, indent=2) + "\n")
    # Reboot preserves installed APK, data, selected IME and permissions, while
    # clearing our temporary guest firewall rules. Do not reinstall or select
    # the IME again: its persistence is part of this check.
    adb("reboot")
    time.sleep(3)
    adb("wait-for-device")
    for _ in range(90):
        if adb("shell", "getprop", "sys.boot_completed", check=False).strip() == "1":
            break
        time.sleep(2)
    else:
        raise RuntimeError("Emulator failed to boot again")
    adb("shell", "input", "keyevent", "82")
    selected = adb("shell", "settings", "get", "secure", "default_input_method").strip()
    report["selected_keyboard_persisted_after_reboot"] = selected.startswith(PACKAGE + "/")
    report["post_reboot_microphone_waveform_diagnostic"] = capture_microphone_control("post-reboot-")
    online_network = network_control()
    online_voice = dictation_attempt("post-reboot-")
    report["post_reboot_network_control"] = online_network
    report["post_reboot_voice"] = online_voice
    report["post_reboot_online_dictation_passed"] = online_network["success"] and online_voice["passed"] and report["selected_keyboard_persisted_after_reboot"]
    report["scenario_passed"] = keyboard_passed and report["offline_dictation_passed"] and report["post_reboot_online_dictation_passed"] and report["stock_gboard_unchanged"]
    (OUT / "runtime-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["scenario_passed"]:
        raise RuntimeError("Offline/online/reboot scenario did not pass; inspect runtime-report.json")


if __name__ == "__main__":
    supported_abis = adb("shell", "getprop", "ro.product.cpu.abilist").strip().split(",")
    requested_arch = os.environ.get("GBOARD_TEST_ARCH", "auto")
    ARM_BASELINE = None
    if requested_arch == "auto" and "arm64-v8a" in supported_abis:
        ARM_BASELINE = run_baseline()
    TEST_ARCH = ("arm64" if "arm64-v8a" in supported_abis else "x86_64") if requested_arch == "auto" else requested_arch
    if ARM_BASELINE and ARM_BASELINE["upstream_crashed"]:
        TEST_ARCH = "x86_64"
        print("ARM64 translation cannot run the unmodified Google APK; using x86-64 for platform checks, ARM64 remains unverified.", flush=True)
    if TEST_ARCH not in ("arm64", "x86_64"):
        raise RuntimeError("Unsupported test architecture")
    OUT = Path("dist") / TEST_ARCH
    (OUT / "device-properties.txt").write_text(adb("shell", "getprop"))
    print("Runtime APK architecture:", TEST_ARCH, "guest ABI support:", supported_abis, flush=True)
    probe_log = (OUT / "probe-logcat.txt").open("w")
    probe_capture = subprocess.Popen(["adb", "logcat", "-v", "threadtime", "OfflineProbe:V", "OfflineModels:V", "AudioRecord:V", "ActivityTaskManager:I", "*:S"], stdout=probe_log, stderr=subprocess.STDOUT)
    try:
        main()
    finally:
        probe_capture.terminate()
        probe_capture.wait(timeout=5)
        probe_log.close()
        (OUT / "logcat.txt").write_text(adb("logcat", "-d", "-t", "2500", check=False))
        (OUT / "ime-state.json").write_text(probe_file("ime-state.json"))
        screenshot("last-state.png")
