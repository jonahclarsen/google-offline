import android.content.Context;
import java.io.File;
import art.jonah.offline.OfflineModels;

// Compilation stubs: only selected method bodies are copied into original DEX.
public class ize {
    String f;
    public static ize b(Context context, String family) {
        OfflineModels.initialize(context);
        return offlineOriginalB(context, family);
    }
    public static ize offlineOriginalB(Context context, String family) { return null; }
    public File d(qah language) { return OfflineModels.getPack(f, language); }
    public boolean i(qah language) { return OfflineModels.getPack(f, language) != null; }
}
class qah {}
