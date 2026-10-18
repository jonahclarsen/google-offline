# Gboard Offline — experimental

A separately installed Gboard with a bundled English (US) speech model and direct internet access removed. It needs **no root and no VPN**, so an existing VPN can stay connected. Builds and emulator tests run on free standard GitHub Actions runners in this public repository.

**This is a prototype, not yet a verified S10/S25 solution.** Actual offline speech recognition passes in x86-64 Android emulators. ARM64 execution and Samsung One UI remain unverified.

## Verified results

[Run 39098533009](https://github.com/jonahclarsen/google-offline/actions/runs/39098533009), commit `fa4b76b`:

| Check | Android 12 / API 31 | Android 17 / API 37 |
| --- | --- | --- |
| Real keyboard taps produce `qwe` | Pass, x86-64 | Pass, x86-64 |
| Actual “hello world” transcription with all guest IPv4/IPv6 egress blocked | Pass, local engine | Pass, local engine |
| Keyboard selection survives reboot | Pass | Pass |
| Local transcription after reboot while another app fetches HTTPS | Pass | Failed: empty transcript, microphone underruns |
| ARM64 runtime | Unverified: untouched Google APK crashes under translation | Unverified: untouched Google APK crashes under translation |

[Committed reports and upstream crash controls](evidence/39098533009/) preserve these results beyond the temporary Actions artifacts. Build reports describe static checks only; the separate runtime reports establish transcription results. A newer workflow is investigating emulator microphone delivery after reboot.

Both translated ARM controls used the **untouched Google-signed APK**, which crashed in `DecoderWrapper` with SIGSEGV at address `0x8`. The test therefore uses the x86-64 APK for Android platform checks. This does not establish that either ARM APK works on a phone. Free ARM Linux runners were also probed: they expose no `/dev/kvm`, and the current official Linux emulator downloads are x86-64.

## Download and try

Open [Actions](https://github.com/jonahclarsen/google-offline/actions/workflows/build-test.yml), choose a completed run, and download its `experimental-gboard-and-evidence-api…` artifact. Runtime success/failure is recorded in `runtime-report.json`; a completed APK build alone is insufficient.

For an S10 or S25, the intended experimental file is:

```
arm64/gboard-offline-coexist-experimental.apk
```

1. Keep an existing working keyboard installed, then install the coexist APK.
2. Enable **Gboard Offline** in Android's keyboard settings and select it as the active keyboard.
3. Set the keyboard language to **English (US)** and allow microphone access.
4. Open a text field and tap its microphone. The English model is included in the APK; no model download or VPN switch is needed.

The clone has package ID `com.google.android.inputmethod.local`, so it installs beside official Gboard. It cannot inherit official Gboard's private settings or downloaded models. CI uses a persistent signing identity, allowing compatible future builds to update the clone. Its signing certificate SHA-256 is:

```
cfcbfc031313595e83681ddc8bac07ecd8d0d5c6b51de95871dc1ea9c619bdae
```

The separate `gboard-no-internet-experimental.apk` is a minimal permission-patch audit artifact. It lacks the bundled-model/provider hardening and cannot update official Gboard because its signature differs. Use the **coexist** variant for this experiment.

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

## Remaining validation

The user confirmed official Gboard already dictates offline on the S10, requested English, chose emulator testing for now, and needs to retain an existing VPN. Physical testing has therefore not been performed. A working ARM64 installation and dictation on the S10/S25, their exact Android/One UI versions, and complete Android 17 reboot behavior remain outstanding. Do not describe this prototype as fully verified on either Samsung phone.

## Sources

- [GitHub standard hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Google signing certificate independently listed on APKMirror](https://www.apkmirror.com/apk/google-inc/gboard/gboard-the-google-keyboard-16-0-5-804347959-release/)
- [Android speech recognizer and external recognition services](https://developer.android.com/reference/android/speech/SpeechRecognizer)
- [Google's English model manifest](https://dl.google.com/android/voice/gboard/terse/superpacks-manifest-20210519.json)
- [Android emulator ARM translation](https://android-developers.googleblog.com/2020/03/run-arm-apps-on-android-emulator.html)
