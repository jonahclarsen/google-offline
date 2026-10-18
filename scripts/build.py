#!/usr/bin/env python3
"""Fetch a pinned Google-signed fixture, patch, sign, and produce an audit report."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from patch_manifest import patch_apk

GOOGLE_CERT = "f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83"


def run(*args):
    return subprocess.check_output([str(x) for x in args], text=True, stderr=subprocess.STDOUT)


def build(arch):
    source = json.loads(Path("sources.json").read_text())[arch]
    work, dist = Path("work") / arch, Path("dist") / arch
    work.mkdir(parents=True, exist_ok=True)
    dist.mkdir(parents=True, exist_ok=True)
    sdk = Path(os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", "")))
    tools = sdk / "build-tools" / "35.0.0"
    original = work / "original.apk"
    if not original.exists():
        print(f"Downloading pinned {arch} APK from {source['source']}", flush=True)
        if source.get("fetcher") == "apkmirror":
            from fetch_apkmirror import fetch_apkmirror
            original.write_bytes(fetch_apkmirror(source["url"]))
        else:
            with urllib.request.urlopen(source["url"], timeout=120) as response:
                original.write_bytes(response.read())
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    if original_hash != source["sha256"]:
        raise RuntimeError("Original APK SHA-256 mismatch")
    signature = run(tools / "apksigner", "verify", "--verbose", "--print-certs", original)
    (dist / "original-signature.txt").write_text(signature)
    # Google rotated its Android 13+ signing key. Independently verify the
    # complete APK with its pinned legacy v2 signer rather than trusting a new
    # certificate merely because the downloaded file contains it.
    legacy_signature = run(tools / "apksigner", "verify", "--verbose", "--print-certs", "--min-sdk-version", "24", "--max-sdk-version", "31", original)
    (dist / "original-legacy-signature.txt").write_text(legacy_signature)
    fingerprints = re.findall(r"^Signer(?: #\d+| \([^\n]+\)) certificate SHA-256 digest: ([0-9a-fA-F]+)", legacy_signature, re.MULTILINE)
    fingerprints = [value.lower() for value in fingerprints]
    if fingerprints != [GOOGLE_CERT]:
        raise RuntimeError(f"Unexpected original signer: {fingerprints}\n{signature}")
    before = run(tools / "aapt2", "dump", "badging", original)
    if "package: name='com.google.android.inputmethod.latin'" not in before:
        raise RuntimeError("Wrong package")
    unsigned, aligned = work / "unsigned.apk", work / "aligned.apk"
    removed = patch_apk(original, unsigned)
    run(tools / "zipalign", "-P", "16", "-f", "4", unsigned, aligned)
    key = work / "test-signing.jks"
    if not key.exists():
        run("keytool", "-genkeypair", "-keystore", key, "-storepass", "android", "-keypass", "android", "-alias", "offline-test", "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650", "-dname", "CN=Gboard Offline Experimental")
    output = dist / "gboard-no-internet-experimental.apk"
    run(tools / "apksigner", "sign", "--ks", key, "--ks-pass", "pass:android", "--key-pass", "pass:android", "--out", output, aligned)
    output_signature = run(tools / "apksigner", "verify", "--verbose", "--print-certs", output)
    run(tools / "zipalign", "-c", "-P", "16", "4", output)
    after = run(tools / "aapt2", "dump", "badging", output)
    permissions = run(tools / "aapt2", "dump", "permissions", output)
    if "android.permission.INTERNET" in permissions:
        raise RuntimeError("Patched APK still requests INTERNET")
    with zipfile.ZipFile(original) as src, zipfile.ZipFile(output) as dst:
        changed = [n for n in dst.namelist() if not n.startswith("META-INF/") and (n not in src.namelist() or src.read(n) != dst.read(n))]
        missing = [n for n in src.namelist() if not n.startswith("META-INF/") and n != "stamp-cert-sha256" and n not in dst.namelist()]
    if changed != ["AndroidManifest.xml"] or missing:
        raise RuntimeError(f"Unexpected payload changes: {changed}, missing: {missing}")
    report = {"source": source, "original_sha256": original_hash, "original_google_signature_verified": True, "original_certificate_sha256": GOOGLE_CERT, "original_package": before.splitlines()[0], "patched_package": after.splitlines()[0], "removed_internet_declarations": removed, "changed_payload_files": changed, "patched_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "patched_signature": output_signature, "keyboard_runtime": "not tested", "offline_dictation": "NOT VERIFIED", "privacy_scope": "Removes direct INTERNET permission from Gboard only. External speech services retain their own permissions.", "signing": "Ephemeral experimental key; builds cannot update each other."}
    (dist / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (dist / "permissions.txt").write_text(permissions)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arch", choices=["arm64", "x86_64"])
    build(parser.parse_args().arch)
