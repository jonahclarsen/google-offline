package art.jonah.offlineprobe;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.speech.RecognitionService;
import android.speech.SpeechRecognizer;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.widget.EditText;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileWriter;

public class ProbeActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        EditText input = new EditText(this);
        input.setSingleLine(false);
        input.setHint("Offline Gboard test");
        input.setTextSize(24);
        input.setGravity(android.view.Gravity.TOP);
        input.addTextChangedListener(new android.text.TextWatcher() {
            public void beforeTextChanged(CharSequence value, int start, int count, int after) {}
            public void onTextChanged(CharSequence value, int start, int before, int count) {}
            public void afterTextChanged(android.text.Editable value) { saveText(value.toString()); }
        });
        setContentView(input);
        saveText("");
        input.requestFocus();
        input.postDelayed(() -> ((InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(input, InputMethodManager.SHOW_IMPLICIT), 1000);
        if (getIntent().getBooleanExtra("record_audio", false)) {
            input.postDelayed(() -> new Thread(this::recordControl).start(), 500);
        }
        try {
            JSONObject report = new JSONObject();
            report.put("speech_recognizer_available", SpeechRecognizer.isRecognitionAvailable(this));
            report.put("on_device_recognizer_available", SpeechRecognizer.isOnDeviceRecognitionAvailable(this));
            JSONArray services = new JSONArray();
            for (ResolveInfo info : getPackageManager().queryIntentServices(new Intent(RecognitionService.SERVICE_INTERFACE), 0)) {
                JSONObject service = new JSONObject();
                service.put("package", info.serviceInfo.packageName);
                service.put("class", info.serviceInfo.name);
                service.put("internet_granted", getPackageManager().checkPermission("android.permission.INTERNET", info.serviceInfo.packageName) == 0);
                services.put(service);
            }
            report.put("speech_services", services);
            report.put("offline_dictation", "NOT VERIFIED: service discovery is not a transcription test");
            try (FileWriter writer = new FileWriter(new File(getExternalFilesDir(null), "speech-services.json"))) {
                writer.write(report.toString(2));
            }
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    private void saveText(String text) {
        try {
            File temporary = new File(getExternalFilesDir(null), "input.tmp");
            try (FileWriter writer = new FileWriter(temporary)) { writer.write(text); }
            temporary.renameTo(new File(getExternalFilesDir(null), "input.txt"));
        } catch (Exception error) { android.util.Log.e("OfflineProbe", "Cannot save actual editor text", error); }
    }

    private void recordControl() {
        android.media.AudioRecord recorder = null;
        try {
            int buffer = Math.max(4096, android.media.AudioRecord.getMinBufferSize(16000, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT));
            recorder = new android.media.AudioRecord(android.media.MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT, buffer);
            recorder.startRecording();
            long end = android.os.SystemClock.uptimeMillis() + 7000;
            byte[] samples = new byte[buffer];
            try (java.io.FileOutputStream output = new java.io.FileOutputStream(new File(getExternalFilesDir(null), "microphone-control.pcm"))) {
                while (android.os.SystemClock.uptimeMillis() < end) {
                    int count = recorder.read(samples, 0, samples.length);
                    if (count < 0) throw new IllegalStateException("AudioRecord error " + count);
                    output.write(samples, 0, count);
                }
            }
        } catch (Exception e) {
            android.util.Log.e("OfflineProbe", "Microphone control failed", e);
        } finally {
            if (recorder != null) { recorder.stop(); recorder.release(); }
        }
    }
}
