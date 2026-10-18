Always commit and push after making a change.

This project investigates offline Gboard dictation. Do not describe permission removal, a successful build, or a keyboard smoke test as proof of offline speech recognition. Keep explicit evidence and limitations in reports.
Never commit APKs, signing keys, tokens, or downloaded SDK files. Verify original APK signatures against Google's pinned certificate before patching. Prefer pnpm if JavaScript tooling is needed.

Targets: English dictation on Galaxy S10 (last official Android release) and Galaxy S25 (latest supported release). Emulator checks cover Android versions, not Samsung hardware/One UI. The clone ID com.google.android.inputmethod.local deliberately preserves the original package length and DEX string sorting; arbitrary replacements can invalidate DEX files.

The user confirmed existing Gboard dictation works on the S10 with airplane mode enabled and Wi-Fi off. A separately installed clone does not inherit private Gboard model files. API 37 AVDs require current command-line tools at cmdline-tools/latest and target=android-37.0; older avdmanager can silently write target=android-0 and crash SurfaceFlinger. The helper accessibility service inspects IME windows omitted by shell uiautomator.

The user wants emulator testing for now and needs to keep their existing VPN. Do not substitute a VpnService firewall: it would compete with their VPN. Device validation remains outstanding.

The coexistence variant now bundles the pinned Google English v311 small-RNNT model. patches/PatchDex.java copies five donor method bodies into Lize (model lookup/availability/initialization) and Lixi (provider eligibility/creation), retaining original model-manager initialization under an alias. Network and external Voice IME providers are rejected; native libraries remain intact. The initial supported dictation locale is English (US).

Do not infer editor contents from accessibility snapshots: Android can return stale hints while screenshots show typed text. The test Activity writes actual TextWatcher contents and IME visibility. Coordinate fallbacks are real UI taps for the fixed 1080x1920 Pixel 2 fixture, never adb input text. Whole-wave correlation is a diagnostic: emulator timing can disrupt it while actual native recognition succeeds. The expected phrase never enters the Android helper through a text API. Scenario verification includes blocked guest networking, actual local transcription, a reboot with selected IME preserved, and another local transcription while the separate helper can fetch HTTPS.

The clone also sets allowBackup=false and redirects explicit Google broker app IDs/content authorities/component strings using broker-aliases.json. SDK class names/type descriptors must remain intact. Resource string pools can contain CESU-8 surrogate sequences; preserve them with surrogatepass. Actual APK resource checks pass for both architectures.

Runtime tests prefer ARM64 only when the image advertises it, first running the untouched Google-signed ARM64 APK as a translation baseline. If that upstream baseline crashes, use x86-64 for platform tests and clearly retain ARM64-unverified status. Native crashes must be detected from Cmdline/>>> headers as well as Java Process headers. App input readiness is verified by real qwe taps and deletion before each speech session, since stale accessibility windows can precede usable keyboard handlers after reboot.
