"""Check the untouched Google ARM64 APK before attributing bridge crashes."""
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

PACKAGE = "com.google.android.inputmethod.latin"
OUT = Path("dist/translation-baseline")


def adb(*args, check=True):
    return subprocess.run(["adb", *args], check=check, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout


def crashes_for_package(log, package):
    return bool(re.search(r"(?:Process:|Cmdline:)\s*" + re.escape(package) + r"(?=[:,\s]|$)", log) or re.search(r">>> " + re.escape(package) + r"(?::[^ ]+)? <<<", log))


def reboot():
    adb("reboot")
    time.sleep(3)
    adb("wait-for-device")
    for _ in range(90):
        if adb("shell", "getprop", "sys.boot_completed", check=False).strip() == "1":
            adb("shell", "input", "keyevent", "82")
            return
        time.sleep(2)
    raise RuntimeError("Baseline emulator did not reboot")


def root():
    for _ in range(3):
        adb("root", check=False)
        adb("wait-for-device")
        if adb("shell", "id", "-u", check=False).strip() == "0":
            return
        time.sleep(2)
    raise RuntimeError("Baseline emulator did not provide root")


def remove_test_preinstall():
    # Strictly limited to the disposable GitHub Actions AVD. A differently
    # signed emulator preload otherwise prevents a valid untouched-APK control.
    if os.environ.get("GITHUB_ACTIONS") != "true" or adb("shell", "getprop", "ro.kernel.qemu").strip() != "1":
        raise RuntimeError("Preinstall removal is restricted to the CI emulator")
    paths = adb("shell", "pm", "path", PACKAGE).strip().splitlines()
    expected = "package:/product/app/LatinIMEGooglePrebuilt/LatinIMEGooglePrebuilt.apk"
    if paths != [expected]:
        raise RuntimeError("Unexpected preload path; refusing to remove anything")
    root()
    verity = adb("disable-verity", check=False)
    mount = subprocess.run(["adb", "remount"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (OUT / "remount.txt").write_text(verity + mount.stdout)
    if mount.returncode or "reboot" in mount.stdout.lower():
        reboot()
        root()
        mount = subprocess.run(["adb", "remount"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with (OUT / "remount.txt").open("a") as file:
            file.write(mount.stdout)
    mount.check_returncode()
    adb("shell", "rm", expected.removeprefix("package:"))
    reboot()


def run_baseline():
    OUT.mkdir(parents=True, exist_ok=True)
    apk = Path("work/arm64/original.apk")
    report = {"apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(), "source": "Unmodified Google-signed APK already verified by build.py", "tested_abi": "arm64-v8a"}
    adb("logcat", "-c")
    install = subprocess.run(["adb", "install", "--no-incremental", "--abi", "arm64-v8a", "-r", str(apk)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (OUT / "install.txt").write_text(install.stdout)
    if install.returncode and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in install.stdout:
        try:
            remove_test_preinstall()
            report["differently_signed_emulator_preload_removed"] = True
            install = subprocess.run(["adb", "install", "--no-incremental", "--abi", "arm64-v8a", "-r", str(apk)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            with (OUT / "install.txt").open("a") as file:
                file.write("\nAfter removing CI preload:\n" + install.stdout)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            report["preinstall_removal_error"] = str(error)
    if install.returncode:
        report.update(status="INCONCLUSIVE: upstream APK could not update emulator preinstall", upstream_crashed=False)
    else:
        adb("install", "--no-incremental", "-r", "work/probe/probe.apk")
        ime = next(line.strip() for line in adb("shell", "ime", "list", "-a", "-s").splitlines() if line.startswith(PACKAGE + "/"))
        adb("shell", "ime", "enable", ime)
        adb("shell", "ime", "set", ime)
        adb("shell", "am", "start", "-W", "-f", "0x10008000", "-n", "art.jonah.offlineprobe/.ProbeActivity")
        time.sleep(8)
        typed = ""
        for _ in range(6):
            for x in (54, 162, 270):
                adb("shell", "input", "tap", str(x), "1244")
                time.sleep(0.25)
            time.sleep(1)
            typed = adb("shell", "cat", "/sdcard/Android/data/art.jonah.offlineprobe/files/input.txt", check=False).strip()
            if typed == "qwe":
                break
            if typed:
                adb("shell", "input", "keyevent", *(["67"] * min(len(typed), 32)))
        time.sleep(8)
        crash = adb("logcat", "-d", "-b", "crash")
        (OUT / "upstream-crashes.txt").write_text(crash)
        (OUT / "upstream-package.txt").write_text(adb("shell", "dumpsys", "package", PACKAGE))
        (OUT / "upstream-logcat.txt").write_text(adb("logcat", "-d", "-t", "3000"))
        with (OUT / "upstream-keyboard.png").open("wb") as file:
            subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=file, check=True)
        crashed = crashes_for_package(crash, PACKAGE)
        report.update(actual_typed=typed, upstream_crashed=crashed, status="UNAVAILABLE: unmodified upstream APK crashes in this ARM translation environment" if crashed else ("PASS: upstream ARM64 typing remained crash-free" if typed == "qwe" else "INCONCLUSIVE: upstream keyboard did not produce expected text"))
    (OUT / "baseline-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    return report
