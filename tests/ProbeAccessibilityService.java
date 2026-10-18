package art.jonah.offlineprobe;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.graphics.Rect;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.File;
import java.io.FileWriter;
import org.json.JSONArray;
import org.json.JSONObject;

/** Test-emulator helper: inspect IME windows, which shell uiautomator omits. */
public class ProbeAccessibilityService extends AccessibilityService {
    private final android.os.Handler handler = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable save = this::snapshot;

    @Override public void onServiceConnected() {
        AccessibilityServiceInfo info = getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
        setServiceInfo(info);
        snapshot();
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        handler.removeCallbacks(save);
        handler.postDelayed(save, 100);
    }

    @Override public void onInterrupt() {}

    private String string(CharSequence value) { return value == null ? "" : value.toString(); }

    private void collect(AccessibilityNodeInfo node, JSONArray nodes, int depth) throws Exception {
        if (node == null || depth > 40 || nodes.length() > 4096) return;
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        JSONObject item = new JSONObject();
        item.put("package", string(node.getPackageName()));
        item.put("class", string(node.getClassName()));
        item.put("text", string(node.getText()));
        item.put("content-desc", string(node.getContentDescription()));
        item.put("resource-id", string(node.getViewIdResourceName()));
        item.put("bounds", "["+bounds.left+","+bounds.top+"]["+bounds.right+","+bounds.bottom+"]");
        item.put("clickable", Boolean.toString(node.isClickable()));
        nodes.put(item);
        for (int i = 0; i < node.getChildCount(); i++) collect(node.getChild(i), nodes, depth + 1);
    }

    private void snapshot() {
        try {
            JSONArray nodes = new JSONArray();
            for (AccessibilityWindowInfo window : getWindows()) {
                AccessibilityNodeInfo root = window.getRoot();
                if (window.getType() == AccessibilityWindowInfo.TYPE_INPUT_METHOD && root != null) {
                    Rect bounds = new Rect();
                    window.getBoundsInScreen(bounds);
                    JSONObject item = new JSONObject();
                    item.put("class", "_IME_WINDOW");
                    item.put("package", string(root.getPackageName()));
                    item.put("bounds", "["+bounds.left+","+bounds.top+"]["+bounds.right+","+bounds.bottom+"]");
                    nodes.put(item);
                }
                collect(root, nodes, 0);
            }
            File temporary = new File(getExternalFilesDir(null), "accessibility.tmp");
            try (FileWriter writer = new FileWriter(temporary)) { writer.write(nodes.toString()); }
            temporary.renameTo(new File(getExternalFilesDir(null), "accessibility.json"));
        } catch (Exception e) { android.util.Log.e("OfflineProbe", "Cannot inspect windows", e); }
    }
}
