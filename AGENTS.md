Always commit and push after making a change.

This project investigates offline Gboard dictation. Do not describe permission removal, a successful build, or a keyboard smoke test as proof of offline speech recognition. Keep explicit evidence and limitations in reports.
Never commit APKs, signing keys, tokens, or downloaded SDK files. Verify original APK signatures against Google's pinned certificate before patching. Prefer pnpm if JavaScript tooling is needed.

Targets: English dictation on Galaxy S10 (last official Android release) and Galaxy S25 (latest supported release). Emulator checks cover Android versions, not Samsung hardware/One UI. The clone ID com.google.android.inputmethod.local deliberately preserves the original package length and DEX string sorting; arbitrary replacements can invalidate DEX files.

The user confirmed existing Gboard dictation works on the S10 with airplane mode enabled and Wi-Fi off. A separately installed clone does not inherit private Gboard model files. API 37 AVDs require current command-line tools at cmdline-tools/latest and target=android-37.0; older avdmanager can silently write target=android-0 and crash SurfaceFlinger. The helper accessibility service inspects IME windows omitted by shell uiautomator.

The user wants emulator testing for now and needs to keep their existing VPN. Do not substitute a VpnService firewall: it would compete with their VPN. Device validation remains outstanding.
