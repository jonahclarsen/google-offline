#!/usr/bin/env bash
set -euo pipefail
tools="$ANDROID_HOME/build-tools/35.0.0"
platform="$ANDROID_HOME/platforms/android-35/android.jar"
mkdir -p work/probe/classes work/probe/dex
javac -source 11 -target 11 -classpath "$platform" -d work/probe/classes tests/ProbeActivity.java tests/ProbeAccessibilityService.java
"$tools/d8" --lib "$platform" --output work/probe/dex work/probe/classes/art/jonah/offlineprobe/*.class
"$tools/aapt2" compile --dir tests/res -o work/probe/resources.zip
"$tools/aapt2" link -o work/probe/unsigned.apk -I "$platform" --manifest tests/AndroidManifest.xml -R work/probe/resources.zip
python3 - <<'PY'
import zipfile
with zipfile.ZipFile('work/probe/unsigned.apk', 'a') as apk:
    apk.write('work/probe/dex/classes.dex', 'classes.dex')
PY
"$tools/zipalign" -f 4 work/probe/unsigned.apk work/probe/aligned.apk
if [[ -f work/signing/gboard-offline.p12 && -n "${GBOARD_SIGNING_PASSWORD:-}" ]]; then
  "$tools/apksigner" sign --ks work/signing/gboard-offline.p12 --ks-pass env:GBOARD_SIGNING_PASSWORD --out work/probe/probe.apk work/probe/aligned.apk
else
  if [[ ! -f work/probe/test-signing.jks ]]; then
    keytool -genkeypair -keystore work/probe/test-signing.jks -storepass android -keypass android -alias offline-probe -keyalg RSA -keysize 2048 -validity 3650 -dname 'CN=Offline Gboard Test Helper'
  fi
  "$tools/apksigner" sign --ks work/probe/test-signing.jks --ks-pass pass:android --out work/probe/probe.apk work/probe/aligned.apk
fi
