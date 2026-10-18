# Gboard Offline — experimental

A separately installed Gboard with a bundled English (US) speech model and direct internet access removed. It needs **no root and no VPN**, so an existing VPN can stay connected. Builds and platform tests run on free standard GitHub Actions runners in this public repository.

**The released ARM64 APK passed the full native Android 12 emulator scenario. Android 17/S25 and physical Samsung hardware remain unverified.**

[Download the experimental ARM64 APK](https://github.com/jonahclarsen/google-offline/releases/download/v0.1.0-experimental/gboard-offline-arm64.apk) · [Release, checksums, and evidence](https://github.com/jonahclarsen/google-offline/releases/tag/v0.1.0-experimental)

## Verified results

| Target | Result | Evidence |
| --- | --- | --- |
| Native ARM64 Android 12 / API 31 | Full scenario passed on the **exact released APK** | [Report and screenshot](evidence/native-arm64-api31/) |
| x86-64 Android 12 / API 31 | Full scenario passed | [Latest CI report](evidence/39104618445/api31-runtime.json) |
| x86-64 Android 17 / API 37 | Earlier isolated transcription passed; latest run failed, complete reboot scenario unverified | [Latest failed report](evidence/39104618445/api37-runtime.json) |
| Native ARM64 Android 17 / API 37 | Unverified: emulator microphone transport failed | [Recorded limitations](evidence/native-arm64-api37/) |
| Samsung S10/S25 hardware and One UI | Not tested; the user requested emulator tests for now | Device validation remains outstanding |

The full scenario requires real `qwe` keyboard taps, actual “hello world” transcription with **all guest IPv4/IPv6 egress blocked**, a reboot preserving the selected keyboard, and another local transcription while a separate helper successfully fetches HTTPS. The expected phrase is never inserted by a text API. Runtime reports retain every attempted transcription; the current harness permits up to three attempts per phase and still requires an actual local transcript with no keyboard crash.

Free Linux runners test x86-64 Android images. Their ARM translation crashes even with the untouched Google-signed APK, so translation is never reported as an ARM64 pass. Native ARM testing additionally used an Apple Silicon Mac with Hypervisor.Framework. Google's original ARM APK and the clone both crashed in `DecoderWrapper` under translation; the actual ARM64 clone remained crash-free in the native Android 12 test.

The released APK SHA-256 is:

```
afbedff3881af822aa0646bd3487edf712f8616360237ce0b7c9c1da4dfa57db
```

The [committed reports](evidence/) preserve results beyond temporary Actions artifact expiry. Build reports describe static checks only; separate runtime reports establish transcription. The release evidence archive contains the native Android 12 logs and synthetic microphone fixtures. Android 17 audio transport is still being investigated; no failed attempt is treated as a pass.

## Install the experimental build

1. Keep an existing working keyboard installed, then install [gboard-offline-arm64.apk](https://github.com/jonahclarsen/google-offline/releases/download/v0.1.0-experimental/gboard-offline-arm64.apk).
2. Enable **Gboard Offline** in Android's keyboard settings and select it as the active keyboard.
3. Set the keyboard language to **English (US)** and allow microphone access.
4. Open a text field and tap its microphone. The English model is included in the APK; no model download or VPN switch is needed.

The clone has package ID `com.google.android.inputmethod.local`, so it installs beside official Gboard. It cannot inherit official Gboard's private settings or downloaded models. CI uses a persistent signing identity, allowing compatible future builds to update the clone. Its signing certificate SHA-256 is:

```
cfcbfc031313595e83681ddc8bac07ecd8d0d5c6b51de95871dc1ea9c619bdae
```

[Actions](https://github.com/jonahclarsen/google-offline/actions/workflows/build-test.yml) also publishes a short-lived ARM64 coexist APK after successful Android 12 checks and retains small runtime evidence from both versions. The local build additionally produces `gboard-no-internet-experimental.apk`, a minimal permission-patch audit artifact. That variant lacks bundled-model/provider hardening and cannot update official Gboard because its signature differs. Use the **coexist** variant or the release APK for this experiment.

## What changes

- Removes `android.permission.INTERNET` and sets `allowBackup=false`.
- Bundles Google's pinned English v311 small-RNNT model and supplies it directly to the internal model manager.
- Disables network and external Voice IME recognizer providers by replacing five Java method bodies, retaining original model-manager initialization.
- Redirects nine explicit Google broker package identities, content authorities, and component references to uninstalled offline aliases. SDK class names remain intact; other installed apps are unaffected.
- Changes the package ID and visible keyboard name, and updates one internal certificate trust slot to the clone's actual signing certificate. Google's production certificate remains trusted.

Native libraries remain byte-for-byte unchanged. The build checks APK signatures, permission declarations, ZIP alignment, changed payloads, and ARM64 ELF alignment for 16 KiB pages.

These changes block direct networking and the identified service routes. They are **not a complete audit of every possible IPC route, dynamically constructed broker identity, Android backup mechanism, or Samsung system service**. Other apps retain their own permissions. Text dictated into a networked app is still available to that app.

## Inputs and builds

[sources.json](sources.json) pins complete ARM64 and x86-64 Gboard 17.3.3 APKs from APKMirror, including SHA-256 hashes. Every input must pass Google's APK signature verification and an independent check against Google's pinned legacy signing certificate. [offline-sources.json](offline-sources.json) pins the Google-hosted model and build dependencies. Original APKs, private signing keys, and downloaded tools are excluded from git.

To build locally, install Python, JDK 21, Android SDK platform 35 and build-tools 35.0.0, set `ANDROID_HOME`, and run:

```sh
python3 -m pip install -r requirements-build.txt
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/build.py arm64
```

Local builds without signing secrets use a disposable test key. The [workflow](.github/workflows/build-test.yml) contains the full emulator setup. Its root firewall rules isolate only the disposable emulator during the first phase; installed phone APKs need neither root nor firewall configuration.

The test injects a known audio fixture through the emulator microphone and requires real editor callbacks, local recognizer logs, the expected transcript, and no keyboard crash. The fixture text is never inserted by a text API. After reboot, another app must successfully fetch HTTPS while Gboard repeats local transcription. Microphone waveform comparisons are diagnostic because emulator scheduling can distort timing; an actual local transcript independently proves audio transport.

## Repeat native ARM tests

On an ARM host with a supported native Android emulator, install JDK 21, current Android command-line tools (22), SDK platform/build-tools 35, and the Google APIs ARM64 image for API 31 or 37.0. Build the ARM APK, then prepare the helper and fixture:

```sh
python3 -m pip install -r requirements-native-test.txt
bash scripts/build_probe.sh
espeak-ng -v en-us -s 135 -w work/hello-world.wav 'hello world'
python3 scripts/native_emulator_test.py 31
```

Set `ANDROID_HOME` and `JAVA_HOME` and put their tools on `PATH`. The helper can generate its own local test signing key. The wrapper generates the audio protocol bindings, starts a headless emulator on the permanent fixture ports in [emulator-settings.json](tests/emulator-settings.json), runs the scenario, and shuts it down. Its gRPC endpoint uses ephemeral token authentication and loopback binding; tokens are excluded from evidence. Passing `37.0` runs the currently unverified native Android 17 microphone experiment.

## Remaining validation

The user confirmed official Gboard already dictates offline on the S10, requested English, chose emulator testing for now, and needs to retain an existing VPN. Physical testing has therefore not been performed. Native ARM64 Android 12 is verified at the emulator level. An installation and dictation on the S10/S25 themselves, their exact Android/One UI versions, and complete Android 17 behavior remain outstanding. Do not describe this prototype as verified on either Samsung phone.

## Sources

- [GitHub standard hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Google signing certificate independently listed on APKMirror](https://www.apkmirror.com/apk/google-inc/gboard/gboard-the-google-keyboard-16-0-5-804347959-release/)
- [Android speech recognizer and external recognition services](https://developer.android.com/reference/android/speech/SpeechRecognizer)
- [Google's English model manifest](https://dl.google.com/android/voice/gboard/terse/superpacks-manifest-20210519.json)
- [Android emulator ARM translation](https://android-developers.googleblog.com/2020/03/run-arm-apps-on-android-emulator.html)
