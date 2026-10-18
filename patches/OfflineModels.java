package art.jonah.offline;

import android.content.Context;
import android.util.Log;
import java.io.*;
import java.util.Locale;
import java.util.zip.*;

/** Supplies the pinned English model from APK assets without network access. */
public final class OfflineModels {
    private static Context context;
    public static synchronized void initialize(Context value) {
        context = value.getApplicationContext();
    }

    public static synchronized File getPack(String family, Object language) {
        if (context == null || !"gboard-small-speech-packs".equals(family) || language == null) return null;
        String tag = language.toString().toLowerCase(Locale.ROOT);
        if (!(tag.equals("en") || tag.startsWith("en-") || tag.startsWith("en_"))) return null;
        File target = new File(context.getFilesDir(), "offline-english-v311");
        File marker = new File(target, ".complete");
        try {
            if (!marker.isFile()) {
                target.mkdirs();
                long total = 0;
                int count = 0;
                try (ZipInputStream zip = new ZipInputStream(context.getAssets().open("offline-english-v311.zip"))) {
                    ZipEntry entry;
                    byte[] buffer = new byte[32768];
                    while ((entry = zip.getNextEntry()) != null) {
                        File output = new File(target, entry.getName());
                        if (!output.getCanonicalPath().startsWith(target.getCanonicalPath() + File.separator) || ++count > 64) throw new IOException("Unsafe model archive");
                        if (entry.isDirectory()) { output.mkdirs(); continue; }
                        output.getParentFile().mkdirs();
                        try (FileOutputStream file = new FileOutputStream(output)) {
                            int size;
                            while ((size = zip.read(buffer)) != -1) {
                                total += size;
                                if (total > 25000000) throw new IOException("Oversized model archive");
                                file.write(buffer, 0, size);
                            }
                        }
                    }
                }
                if (count != 16 || total != 20827210 || !new File(target, "dictation.config").isFile()) throw new IOException("Incomplete model archive");
                if (!marker.createNewFile()) throw new IOException("Cannot finalize model");
                Log.i("OfflineModels", "Prepared bundled English model without network access");
            }
            return target;
        } catch (IOException error) {
            Log.e("OfflineModels", "Bundled model unavailable; failing closed", error);
            return null;
        }
    }
}
