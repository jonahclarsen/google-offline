"""Bundle Google's pinned English model and restrict the legacy ASR factory."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import urllib.request
import zipfile
from clone_apk import backup_disabled
from remap_resources import remap_resources

ROOT = Path("work/offline")


def command(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def fetch(path, source):
    if not path.exists():
        with urllib.request.urlopen(source["url"], timeout=120) as response:
            path.write_bytes(response.read())
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError(f"Pinned dependency hash mismatch: {path.name}")


def bundle(source, destination, sdk):
    ROOT.mkdir(parents=True, exist_ok=True)
    sources = json.loads(Path("offline-sources.json").read_text())
    for name, spec in sources["jars"].items():
        fetch(ROOT / name, spec)
    model = ROOT / "english-model.zip"
    fetch(model, sources["model"])
    if hashlib.md5(model.read_bytes()).hexdigest() != sources["model"]["official_md5"]:
        raise ValueError("Model differs from Google's manifest")
    classpath = os.pathsep.join(str(ROOT / name) for name in sources["jars"])
    platform = sdk / "platforms/android-35/android.jar"
    d8 = sdk / "build-tools/35.0.0/d8"
    for folder in ("helper", "donors", "patcher", "helper-dex", "donors-dex"):
        (ROOT / folder).mkdir(exist_ok=True)
    command("javac", "-source", "11", "-target", "11", "-classpath", platform, "-d", ROOT / "helper", "patches/OfflineModels.java")
    command("javac", "-source", "11", "-target", "11", "-classpath", str(platform) + os.pathsep + str(ROOT / "helper"), "-d", ROOT / "donors", "patches/donors/ize.java", "patches/donors/ixi.java")
    command("javac", "-classpath", classpath, "-d", ROOT / "patcher", "patches/PatchDex.java", "patches/RemapBrokerStrings.java")
    command(d8, "--min-api", "26", "--lib", platform, "--output", ROOT / "helper-dex", *sorted((ROOT / "helper").rglob("*.class")))
    command(d8, "--min-api", "26", "--lib", platform, "--classpath", ROOT / "helper", "--output", ROOT / "donors-dex", *sorted((ROOT / "donors").rglob("*.class")))
    with zipfile.ZipFile(source) as archive:
        (ROOT / "original.dex").write_bytes(archive.read("classes.dex"))
    command("java", "-cp", str(ROOT / "patcher") + os.pathsep + classpath, "PatchDex", ROOT / "original.dex", ROOT / "donors-dex/classes.dex", ROOT / "patched.dex")
    aliases = json.loads(Path("broker-aliases.json").read_text())
    aliases_file = ROOT / "broker-aliases.properties"
    aliases_file.write_text("".join(f"{key}={value}\n" for key, value in aliases.items()))
    broker_counts = {}
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w") as dst:
        if "classes5.dex" in src.namelist():
            raise ValueError("Unexpected upstream DEX layout")
        for info in src.infolist():
            name = info.filename
            data = (ROOT / "patched.dex").read_bytes() if name == "classes.dex" else src.read(info)
            if name.endswith(".dex"):
                input_dex, output_dex = ROOT / "brokers-input.dex", ROOT / "brokers-output.dex"
                input_dex.write_bytes(data)
                result = subprocess.check_output(["java", "-cp", str(ROOT / "patcher") + os.pathsep + classpath, "RemapBrokerStrings", str(input_dex), str(output_dex), str(aliases_file)], text=True)
                print(result.strip(), flush=True)
                broker_counts[name] = int(re.search(r"identifiers: (\d+)", result)[1])
                data = output_dex.read_bytes()
            elif name in ("AndroidManifest.xml", "resources.arsc"):
                data, broker_counts[name] = remap_resources(data, aliases)
                if name == "AndroidManifest.xml" and not backup_disabled(data):
                    raise ValueError("Clone still allows cloud backup")
            dst.writestr(info, data)
        dst.write(ROOT / "helper-dex/classes.dex", "classes5.dex", compress_type=zipfile.ZIP_DEFLATED)
        dst.write(model, "assets/offline-english-v311.zip", compress_type=zipfile.ZIP_STORED)
    return {"cloud_backup_disabled": True, "blocked_explicit_broker_packages": aliases, "remapped_identifiers": broker_counts, "english_model_sha256": sources["model"]["sha256"], "patched_methods": 5, "network_and_external_voice_ime_providers": "disabled", "english_locales": "English locales use the bundled en-US model"}
