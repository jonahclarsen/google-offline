import java.io.File;
import java.io.FileInputStream;
import java.util.*;
import org.jf.dexlib2.*;
import org.jf.dexlib2.dexbacked.DexBackedDexFile;
import org.jf.dexlib2.iface.*;
import org.jf.dexlib2.iface.instruction.*;
import org.jf.dexlib2.iface.reference.*;
import org.jf.dexlib2.iface.value.*;
import org.jf.dexlib2.immutable.instruction.*;
import org.jf.dexlib2.immutable.reference.ImmutableStringReference;
import org.jf.dexlib2.immutable.value.ImmutableStringEncodedValue;
import org.jf.dexlib2.rewriter.*;
import org.jf.dexlib2.writer.pool.DexPool;

/** Redirect explicit Google broker identities to uninstalled offline aliases.
 * SDK Java class names and type descriptors remain unchanged. */
public final class RemapBrokerStrings {
    private static final Map<String, String> packages = new LinkedHashMap<>();
    private static final Set<String> changed = new TreeSet<>();
    private static String remap(String value) {
        String result = packages.get(value);
        if (result == null) {
            for (Map.Entry<String, String> entry : packages.entrySet()) {
                if (value.startsWith(entry.getKey() + "/")) {
                    result = entry.getValue() + value.substring(entry.getKey().length());
                    break;
                }
                String prefix = "content://" + entry.getKey();
                if (value.startsWith(prefix) && (value.length() == prefix.length() || "/.?".indexOf(value.charAt(prefix.length())) >= 0)) {
                    result = "content://" + entry.getValue() + value.substring(prefix.length());
                    break;
                }
                // Authorities are lower-case names, not SDK class names.
                if (value.equals(entry.getKey() + ".chimera") || value.equals(entry.getKey() + ".phenotype") || value.equals(entry.getKey() + ".gservices")) {
                    result = entry.getValue() + value.substring(entry.getKey().length());
                    break;
                }
            }
        }
        if (result != null) { changed.add(value); return result; }
        return value;
    }
    public static void main(String[] args) throws Exception {
        Properties aliases = new Properties();
        try (FileInputStream input = new FileInputStream(args[2])) { aliases.load(input); }
        for (String name : aliases.stringPropertyNames()) packages.put(name, aliases.getProperty(name));
        DexFile source = DexFileFactory.loadDexFile(new File(args[0]), null);
        DexRewriter rewriter = new DexRewriter(new RewriterModule() {
            @Override public Rewriter<Instruction> getInstructionRewriter(Rewriters rewriters) {
                return new InstructionRewriter(rewriters) {
                    @Override public Instruction rewrite(Instruction instruction) {
                        Opcode opcode = instruction.getOpcode();
                        if (opcode == Opcode.CONST_STRING || opcode == Opcode.CONST_STRING_JUMBO) {
                            String value = ((StringReference)((ReferenceInstruction)instruction).getReference()).getString();
                            ImmutableStringReference reference = new ImmutableStringReference(remap(value));
                            int register = ((OneRegisterInstruction)instruction).getRegisterA();
                            return opcode == Opcode.CONST_STRING ? new ImmutableInstruction21c(opcode, register, reference) : new ImmutableInstruction31c(opcode, register, reference);
                        }
                        return super.rewrite(instruction);
                    }
                };
            }
            @Override public Rewriter<EncodedValue> getEncodedValueRewriter(Rewriters rewriters) {
                return new EncodedValueRewriter(rewriters) {
                    @Override public EncodedValue rewrite(EncodedValue value) {
                        if (value.getValueType() == ValueType.STRING) return new ImmutableStringEncodedValue(remap(((StringEncodedValue)value).getValue()));
                        return super.rewrite(value);
                    }
                };
            }
        });
        DexPool.writeTo(args[1], rewriter.getDexFileRewriter().rewrite(source));
        DexBackedDexFile output = DexFileFactory.loadDexFile(new File(args[1]), null);
        for (StringReference reference : output.getStringReferences()) {
            if (!remap(reference.getString()).equals(reference.getString())) throw new IllegalStateException("Unchanged broker string survived rewriting");
        }
        System.out.println("Remapped explicit broker identifiers: " + changed.size());
    }
}
