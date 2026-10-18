import android.content.Context;

public class ixi {
    static jad c, f;
    Context e;
    // Reject both the network recognizer and external Voice IME. Keep the
    // original native on-device providers and their capability checks.
    private static boolean p(jad provider, Context context, jam request) {
        return provider != null && provider != c && provider != f && provider.b(context, request);
    }
    public jah d(jad provider, jam request) {
        if (provider == null || provider == c || provider == f) return null;
        return provider.a(e, request);
    }
}
interface jad {
    jah a(Context context, jam request);
    boolean b(Context context, jam request);
}
class jam {}
interface jah {}
