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
        setContentView(input);
        input.requestFocus();
        input.postDelayed(() -> ((InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(input, InputMethodManager.SHOW_IMPLICIT), 1000);
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
}
