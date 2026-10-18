# Gboard offline investigation

Reproducible experimental APK patch and emulator evidence using free standard GitHub Actions runners in this public repository.

**This is not yet a verified offline dictation solution.** Removing Gboard's INTERNET permission blocks its direct network access; it does not revoke a separate Google speech service's permissions. A successful workflow means the stated build and keyboard checks passed, not that speech works offline.

## What the workflow checks

1. Downloads pinned ARM64 and x86-64 Gboard 17.3.3 standalone APKs from APKMirror. These are May 2026 releases selected because both architectures have complete APKs. Downloading uses the normal page flow with a pinned browser-compatible HTTP client; downloaded content must still pass Google's signature check.
2. Verifies each file's SHA-256 and Android APK signature against Google's certificate (`f0fd6c5b410f25cb25c3b53346c8972fae30f8ee7411df910480ad6b2d60db83`). A compromised mirror cannot substitute an unsigned or differently signed APK without failing this check.
3. Produces an APK with only the INTERNET declaration removed from binary Android XML, plus the required signature changes. Every other app payload byte stays intact. Separately produces a coexistence variant named **Gboard Offline** (`com.google.android.inputmethod.local`): this changes package references in the manifest, DEX strings, and resource table; preserves DEX string ordering; and updates DEX checksums. The clone also replaces one embedded development-certificate trust slot with its actual signing certificate digest, preserving the production Google certificate; otherwise Gboard throws a certificate error after re-signing. Native libraries stay unchanged in both variants. Both are aligned and signed with a persistent private key stored in GitHub Actions secrets.
4. Verifies the resulting signature, ZIP alignment, permission list, and absence of unexpected payload changes. Checks ARM64 ELF load-segment alignment for compatibility with 16 KiB memory pages.
5. Tests the coexistence variant in Android 12 (API 31) and Android 17 (API 37) Google APIs emulators, selects it as the keyboard, taps actual keyboard keys, and checks the resulting text. Checks that stock Gboard remains installed in the same location. Saves screenshots, package state, logs, and speech-service discovery. These are Android platform checks, not Samsung One UI hardware tests.
6. Routes synthetic “hello world” speech through a virtual microphone after blocking **all** IPv4 and IPv6 emulator egress using root firewall rules. First records the guest microphone and checks that it contains the known source waveform; then records whether Gboard produces the expected text. A missing transcript is explicitly reported as unverified. These root rules are an emulator experiment, not a firewall provided for your unrooted phone; separate speech services on your phone would retain their own internet permissions.

ARM64 receives static verification only. The x86-64 emulator result does not establish ARM64 compatibility on your phone. No recognition result is assumed from speech-service availability or from tapping a microphone.

## Downloads and installation limitations

Open the latest workflow run and download an `experimental-gboard-and-evidence-api…` artifact. Files under `arm64/` are intended for the Galaxy S10 and S25. The **coexist** APK uses a separate package name and keyboard label so it can be installed alongside official Gboard; the other APK retains Google's package name and cannot update an official installation because the signing key differs. Keep a working keyboard installed before experimenting. Current CI builds share a persistent signing identity so updates can preserve app data; early experimental runs used disposable keys. No signing keys or upstream APKs are stored in git or published artifacts. Local builds without the signing secrets use a disposable test key.

The user confirmed that official Gboard already dictates successfully on the S10 in airplane mode with Wi-Fi off. This establishes an existing offline setup, but a separately installed clone cannot inherit official Gboard's private model files.

The user's targets are English dictation on a Galaxy S10 with its last official Android release and on a future Galaxy S25 with the latest supported release. The initial platform test matrix is Android 12 and Android 17; actual installed versions and One UI behavior still require device verification.

## What must pass before calling this finished

- Confirm the exact installed Android/One UI versions on the user's S10 and S25; English is the requested dictation language.
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
