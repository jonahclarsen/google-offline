#!/usr/bin/env python3
"""Exercise the real keyboard UI; report speech service prerequisites honestly."""
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

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
    adb("shell", "uiautomator", "dump", "/sdcard/window.xml")
    return ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))


def tap(node):
    left, top, right, bottom = map(int, re.findall(r"\d+", node.attrib["bounds"]))
    adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))


def screenshot(name):
    with (OUT / name).open("wb") as file:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=file, check=True)


def main():
    adb("logcat", "-c")
    (OUT / "preinstalled-packages.txt").write_text(adb("shell", "pm", "list", "packages", "-f"))
    original_before = adb("shell", "pm", "path", ORIGINAL_PACKAGE)
    (OUT / "preinstall-package.txt").write_text(adb("shell", "dumpsys", "package", ORIGINAL_PACKAGE))
    adb("install", "--no-incremental", "-r", str(OUT / "gboard-offline-coexist-experimental.apk"))
    adb("install", "--no-incremental", "-r", "work/probe/probe.apk")
    services = adb("shell", "ime", "list", "-s").splitlines()
    ime = next(s.strip() for s in services if s.startswith(PACKAGE + "/"))
    adb("shell", "ime", "enable", ime)
    adb("shell", "ime", "set", ime)
    adb("shell", "pm", "grant", PACKAGE, "android.permission.RECORD_AUDIO", check=False)
    adb("shell", "am", "start", "-n", "art.jonah.offlineprobe/.ProbeActivity")
    time.sleep(8)
    # Dismiss first-run dialogs only when their labels are understood.
    for _ in range(3):
        tree = ui()
        buttons = [n for n in tree.iter("node") if n.attrib.get("text", "").lower() in ("got it", "no thanks", "not now", "ok") and n.attrib.get("clickable") == "true"]
        if not buttons:
            break
        tap(buttons[0])
        time.sleep(2)
    screenshot("keyboard.png")
    tree = ui()
    (OUT / "keyboard-ui.xml").write_text(ET.tostring(tree, encoding="unicode"))
    typed = []
    for letter in "qwe":
        node = next((n for n in tree.iter("node") if n.attrib.get("package") == PACKAGE and (n.attrib.get("text") == letter or n.attrib.get("content-desc") == letter)), None)
        if node is None:
            break
        tap(node)
        typed.append(letter)
        time.sleep(0.3)
    time.sleep(1)
    tree = ui()
    input_values = [n.attrib.get("text", "") for n in tree.iter("node") if n.attrib.get("class") == "android.widget.EditText"]
    keyboard_passed = typed == list("qwe") and "qwe" in input_values
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
    if mic is not None:
        tap(mic)
        time.sleep(5)
    screenshot("voice-attempt.png")
    (OUT / "voice-ui.xml").write_text(ET.tostring(ui(), encoding="unicode"))
    (OUT / "logcat.txt").write_text(adb("logcat", "-d", "-t", "2500"))
    report = {
        "keyboard_taps": typed, "input_values": input_values, "keyboard_typing_passed": keyboard_passed,
        "gboard_direct_internet_granted": direct_granted, "voice_button_found": mic is not None,
        "stock_gboard_unchanged": bool(original_before.strip()) and original_before == adb("shell", "pm", "path", ORIGINAL_PACKAGE),
        "speech": speech, "offline_dictation_passed": False,
        "offline_dictation_status": "NOT VERIFIED: requires a real audio-to-text result with all relevant speech components network-isolated",
    }
    (OUT / "runtime-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not keyboard_passed:
        raise RuntimeError("Actual Gboard key taps did not produce qwe in the test field; inspect screenshots")


if __name__ == "__main__":
    try:
        main()
    finally:
        (OUT / "logcat.txt").write_text(adb("logcat", "-d", "-t", "2500", check=False))
        screenshot("last-state.png")
