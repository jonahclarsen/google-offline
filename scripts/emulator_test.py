#!/usr/bin/env python3
"""Exercise the real keyboard UI; report speech service prerequisites honestly."""
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from audio_control import verify_capture

PACKAGE = "com.google.android.inputmethod.local"
ORIGINAL_PACKAGE = "com.google.android.inputmethod.latin"
OUT = Path("dist/x86_64")


def adb(*args, check=True):
    result = subprocess.run(["adb", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
    adb("shell", "am", "start", "-f", "0x10008000", "-n", "art.jonah.offlineprobe/.ProbeActivity", *extras)


def wait_keyboard():
    for _ in range(25):
        tree = ui()
        if probe_file("ime-visible.txt").strip() == "true":
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


def dictation_attempt(prefix=""):
    adb("emu", "avd", "hostmicon")
    wait_keyboard()
    tree = ui()
    mic = next((n for n in tree.iter("node") if n.attrib.get("package") == PACKAGE and any(word in n.attrib.get("content-desc", "").lower() for word in ("voice", "microphone", "dictat"))), None)
    if mic is None and probe_file("ime-visible.txt").strip() == "true":
        mic = layout_target("voice")
    pid = adb("shell", "pidof", "-s", PACKAGE).strip()
    with (OUT / f"{prefix}gboard-voice-logcat.txt").open("w") as voice_log:
        capture = subprocess.Popen(["adb", "logcat", "--pid", pid, "-v", "threadtime"], stdout=voice_log, stderr=subprocess.STDOUT)
        try:
            if mic is not None:
                tap(mic)
                time.sleep(0.5)
                for _ in range(4):
                    subprocess.run(["paplay", "--device=speech_input", "work/hello-world.wav"], check=True)
                    time.sleep(0.3)
                time.sleep(5)
        finally:
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
    crash_free = f"Process: {PACKAGE}, PID:" not in crash_log
    speech_passed = crash_free and local_engine_confirmed and not network_recognizer_started and mic is not None and any("hello world" in re.sub(r"[^a-z ]", "", value.lower()) for value in [actual_dictated])
    # The fixture phrase is never inserted by any text API. A real local
    # transcript proves the microphone path even when the separate whole-wave
    # correlation diagnostic is disrupted by emulator audio timing jitter.
    return {"passed": speech_passed, "actual_dictated": actual_dictated,
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
    (OUT / "preinstalled-packages.txt").write_text(adb("shell", "pm", "list", "packages", "-f"))
    original_before = adb("shell", "pm", "path", ORIGINAL_PACKAGE)
    (OUT / "preinstall-package.txt").write_text(adb("shell", "dumpsys", "package", ORIGINAL_PACKAGE))
    adb("install", "--no-incremental", "-r", str(OUT / "gboard-offline-coexist-experimental.apk"))
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
    adb("shell", "am", "start", "-n", "art.jonah.offlineprobe/.ProbeActivity")
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
        adb("shell", "am", "start", "-n", "art.jonah.offlineprobe/.ProbeActivity")
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
    adb("root")
    adb("wait-for-device")
    adb("shell", "iptables", "-I", "OUTPUT", "1", "-j", "DROP")
    adb("shell", "ip6tables", "-I", "OUTPUT", "1", "-j", "DROP")
    (OUT / "network-isolation.txt").write_text(adb("shell", "iptables", "-S", "OUTPUT") + adb("shell", "ip6tables", "-S", "OUTPUT"))
    adb("emu", "avd", "hostmicon")
    start_probe("--ez", "record_audio", "true", "--ez", "check_network", "true")
    time.sleep(2)
    for _ in range(2):
        subprocess.run(["paplay", "--device=speech_input", "work/hello-world.wav"], check=True)
        time.sleep(0.5)
    time.sleep(4)
    adb("pull", "/sdcard/Android/data/art.jonah.offlineprobe/files/microphone-control.pcm", str(OUT / "microphone-control.pcm"))
    microphone_control = verify_capture(OUT / "microphone-control.pcm", "work/hello-world.wav")
    isolated_network = network_control()
    offline_voice = dictation_attempt()
    report = {
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
    start_probe("--ez", "check_network", "true")
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
    probe_log = (OUT / "probe-logcat.txt").open("w")
    probe_capture = subprocess.Popen(["adb", "logcat", "-v", "threadtime", "OfflineProbe:V", "OfflineModels:V", "AudioRecord:V", "ActivityTaskManager:I", "*:S"], stdout=probe_log, stderr=subprocess.STDOUT)
    try:
        main()
    finally:
        probe_capture.terminate()
        probe_capture.wait(timeout=5)
        probe_log.close()
        (OUT / "logcat.txt").write_text(adb("logcat", "-d", "-t", "2500", check=False))
        screenshot("last-state.png")
