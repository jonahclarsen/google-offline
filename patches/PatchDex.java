import java.io.File;
import java.util.*;
import org.jf.dexlib2.Opcodes;
import org.jf.dexlib2.DexFileFactory;
import org.jf.dexlib2.iface.*;
import org.jf.dexlib2.immutable.*;
import org.jf.dexlib2.writer.pool.DexPool;

/** Rebuild references using dexlib2; no constant-pool index surgery. */
public final class PatchDex {
    private static String key(Method method) {
        return method.getDefiningClass() + "->" + method.getName() + method.getParameterTypes() + method.getReturnType();
    }
    private static ImmutableMethod copy(Method original, String name, MethodImplementation code) {
        return new ImmutableMethod(original.getDefiningClass(), name, original.getParameters(), original.getReturnType(), original.getAccessFlags(), original.getAnnotations(), original.getHiddenApiRestrictions(), code);
    }
    public static void main(String[] args) throws Exception {
        DexFile original = DexFileFactory.loadDexFile(new File(args[0]), null);
        DexFile donors = DexFileFactory.loadDexFile(new File(args[1]), null);
        Map<String, Method> replacements = new HashMap<>();
        for (ClassDef type : donors.getClasses()) for (Method method : type.getMethods()) {
            if ((type.getType().equals("Lize;") && Arrays.asList("b", "d", "i").contains(method.getName())) ||
                (type.getType().equals("Lixi;") && Arrays.asList("p", "d").contains(method.getName()))) replacements.put(key(method), method);
        }
        if (replacements.size() != 5) throw new IllegalStateException("Wrong donor method set");
        List<ClassDef> classes = new ArrayList<>();
        int count = 0;
        for (ClassDef type : original.getClasses()) {
            List<Method> methods = new ArrayList<>();
            for (Method method : type.getMethods()) {
                Method replacement = replacements.remove(key(method));
                if (replacement == null) { methods.add(method); continue; }
                if (type.getType().equals("Lize;") && method.getName().equals("b")) {
                    methods.add(copy(method, "offlineOriginalB", method.getImplementation()));
                }
                methods.add(copy(method, method.getName(), replacement.getImplementation()));
                count++;
            }
            classes.add(new ImmutableClassDef(type.getType(), type.getAccessFlags(), type.getSuperclass(), type.getInterfaces(), type.getSourceFile(), type.getAnnotations(), type.getFields(), methods));
        }
        if (count != 5 || !replacements.isEmpty()) throw new IllegalStateException("Upstream method signatures changed");
        DexPool.writeTo(args[2], new ImmutableDexFile(original.getOpcodes(), classes));
        System.out.println("Patched five model/recognizer methods; preserved original model-manager initialization");
    }
}
