# Gboard offline investigation

Reproducible experimental APK patch and emulator evidence using free standard GitHub Actions runners in this public repository.

**This is not yet a verified offline dictation solution.** Removing Gboard's INTERNET permission blocks its direct network access; it does not revoke a separate Google speech service's permissions. A successful workflow means the stated build and keyboard checks passed, not that speech works offline.

## What the workflow checks

1. Downloads pinned ARM64 and x86-64 Gboard 17.3.3 standalone APKs from APKMirror. These are May 2026 releases selected because both architectures have complete APKs. Downloading uses the normal page flow with a pinned browser-compatible HTTP client; downloaded content must still pass Google's signature check.
2. Verifies each file's SHA-256 and Android APK signature against Google's certificate (`f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`). A compromised mirror cannot substitute an unsigned or differently signed APK without failing this check.
3. Removes the INTERNET declaration directly from binary Android XML. Keeps every other payload byte intact, including resources, DEX, and native libraries. Removes old signatures, aligns, and signs with an ephemeral test key.
4. Verifies the resulting signature, alignment, permission list, and the absence of unexpected payload changes.
5. Installs x86-64 Gboard on an Android 13 Google APIs emulator, selects it as the keyboard, taps actual keyboard keys, and checks the resulting text. Saves screenshots, package state, logs, and speech-service discovery.

ARM64 receives static verification only. The x86-64 emulator result does not establish ARM64 compatibility on your phone. No recognition result is assumed from speech-service availability or from tapping a microphone.

## Downloads and installation limitations

Open the latest workflow run and download `experimental-gboard-and-evidence`. Files under `arm64/` are intended for ARM64 devices. Keep another working keyboard installed before experimenting. The package name remains Google's original, but the signing key differs: this APK cannot update official Gboard or replace a factory-installed copy through ordinary installation. Each workflow uses a new signing key, so its artifacts cannot update each other either. No signing keys or upstream APKs are stored in git.

## What must pass before calling this finished

- Identify the user's phone, Android version, and dictation language.
- Obtain and verify a suitable current Gboard APK and any speech-service APKs needed for that device.
- Load the offline language models, then isolate **all** involved components from the network.
- Feed a known audio sample through Gboard's microphone flow and assert the actual recognized text, with networking available to the rest of the device.
- Test installation and dictation on the user's device, including reboot and airplane-mode behavior.

If the required Google service refuses to run after re-signing, or the phone prevents replacing system Gboard, permission removal alone will not solve the problem. Reports must retain that limitation.

## Sources

- [GitHub: free standard runners for public repositories](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Open GApps project and APK source submodules](https://github.com/opengapps/opengapps)
- [Google signing certificate independently listed on APKMirror](https://www.apkmirror.com/apk/google-inc/gboard/gboard-the-google-keyboard-16-0-5-804347959-release/)
- [Android speech recognizer and external recognition services](https://developer.android.com/reference/android/speech/SpeechRecognizer)
- [Google's advanced voice typing documentation](https://support.google.com/gboard/answer/11197787?hl=en)
