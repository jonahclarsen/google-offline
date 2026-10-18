#!/usr/bin/env bash
set -euo pipefail
tools="$ANDROID_HOME/build-tools/35.0.0"
platform="$ANDROID_HOME/platforms/android-35/android.jar"
mkdir -p work/probe/classes work/probe/dex
javac -source 11 -target 11 -classpath "$platform" -d work/probe/classes tests/ProbeActivity.java
"$tools/d8" --lib "$platform" --output work/probe/dex work/probe/classes/art/jonah/offlineprobe/ProbeActivity.class
"$tools/aapt2" link -o work/probe/unsigned.apk -I "$platform" --manifest tests/AndroidManifest.xml
python3 - <<'PY'
import zipfile
with zipfile.ZipFile('work/probe/unsigned.apk', 'a') as apk:
    apk.write('work/probe/dex/classes.dex', 'classes.dex')
PY
"$tools/zipalign" -f 4 work/probe/unsigned.apk work/probe/aligned.apk
"$tools/apksigner" sign --ks work/x86_64/test-signing.jks --ks-pass pass:android --out work/probe/probe.apk work/probe/aligned.apk
