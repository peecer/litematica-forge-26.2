#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Forge 26.2 ModList is a static utility class.
platform = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/utils/ModPlatform.java"
text = platform.read_text(encoding="utf-8")
text = text.replace("ModList.get().isLoaded(modId)", "ModList.isLoaded(modId)")
text = text.replace("ModList.get().getMods()", "ModList.getMods()")
text = text.replace("ModList.get().getModContainerById(modId)", "ModList.getModContainerById(modId)")
platform.write_text(text, encoding="utf-8")

# Forgematica consumes MaFgLib, so MaFgLib must be ordered before it.
# Keep this tolerant of whitespace/version-range changes in the staged metadata.
mods = root / "forgematica/src/main/resources/META-INF/mods.toml"
text = mods.read_text(encoding="utf-8")
import re
pattern = re.compile(r'(modId\s*=\s*"mafglib"[\s\S]*?ordering\s*=\s*")BEFORE(")', re.MULTILINE)
new_text, count = pattern.subn(r'\1AFTER\2', text, count=1)
if count == 0 and 'modId="mafglib"' in text and 'ordering="AFTER"' in text:
    new_text = text
elif count == 0:
    print("Warning: MaFgLib dependency ordering block not found; leaving metadata unchanged")
    new_text = text
mods.write_text(new_text, encoding="utf-8")


# Complete the loader-neutral payload contract for the Servux handler.
servux = root / "forgematica/src/main/java/fi/dy/masa/litematica/network/ServuxLitematicaHandler.java"
text = servux.read_text(encoding="utf-8")
marker = """    @Override
    public void encodeWithSplitter(FriendlyByteBuf buffer, ClientPacketListener handler)
"""
if "public void tickFailures()" not in text:
    insert = """    @Override
    public void tickFailures()
    {
        this.failures++;
    }

    @Override
    public boolean checkFailures()
    {
        return this.failures <= MAX_FAILURES;
    }

"""
    if marker not in text:
        raise SystemExit("Servux fix insertion point not found")
    text = text.replace(marker, insert + marker, 1)
servux.write_text(text, encoding="utf-8")


# ForgeGradle's multi-project Minecraft transform can be reused between modules.
# Give both modules the same AT superset so whichever module transforms Minecraft
# first exposes every member required by MaFgLib and Forgematica.
maf_at = root / "mafglib/src/main/resources/META-INF/accesstransformer.cfg"
forg_at = root / "forgematica/src/main/resources/META-INF/accesstransformer.cfg"
def merge_at_text(*texts):
    comments = []
    entries = []
    seen = set()
    for source in texts:
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if stripped not in comments:
                    comments.append(stripped)
            elif stripped not in seen:
                seen.add(stripped)
                entries.append(stripped)
    return "\n".join(comments + entries) + "\n"

merged_at = merge_at_text(
    maf_at.read_text(encoding="utf-8"),
    forg_at.read_text(encoding="utf-8"),
)
maf_at.write_text(merged_at, encoding="utf-8")
forg_at.write_text(merged_at, encoding="utf-8")


# Minecraft 26.1+ ships unobfuscated Mojang names at runtime. Mixin defaults
# remap=true, which makes its annotation processor demand an obfuscation map
# that does not exist for 26.2. Mark every Minecraft mixin remap=false while
# retaining the processor's target hierarchy validation and runtime checks.
def disable_mixin_obfuscation_remap(java_text: str) -> tuple[str, int]:
    token = "@Mixin("
    pos = 0
    changed = 0
    out = []
    while True:
        start = java_text.find(token, pos)
        if start < 0:
            out.append(java_text[pos:])
            break
        open_paren = start + len(token) - 1
        depth = 0
        i = open_paren
        in_string = False
        in_char = False
        escaped = False
        while i < len(java_text):
            ch = java_text[i]
            if escaped:
                escaped = False
            elif (in_string or in_char) and ch == "\\":
                escaped = True
            elif not in_char and ch == '"':
                in_string = not in_string
            elif not in_string and ch == "'":
                in_char = not in_char
            elif not in_string and not in_char:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        if i >= len(java_text):
            raise SystemExit("Unbalanced @Mixin annotation while applying remap=false")
        inside = java_text[open_paren + 1:i]
        out.append(java_text[pos:open_paren + 1])
        if re.search(r"\bremap\s*=", inside):
            out.append(inside)
        elif re.search(r"\b(?:value|targets|priority)\s*=", inside):
            out.append(inside.rstrip() + ", remap = false")
            changed += 1
        else:
            # Shorthand @Mixin(Target.class) becomes the explicit value form.
            out.append("value = " + inside.strip() + ", remap = false")
            changed += 1
        out.append(")")
        pos = i + 1
    return "".join(out), changed

mixin_remap_changes = 0
for module in ("mafglib", "forgematica"):
    java_root = root / module / "src/main/java"
    for path in java_root.rglob("*.java"):
        source = path.read_text(encoding="utf-8")
        if "@Mixin(" not in source:
            continue
        rewritten, count = disable_mixin_obfuscation_remap(source)
        if count:
            path.write_text(rewritten, encoding="utf-8")
            mixin_remap_changes += count

if mixin_remap_changes < 100:
    raise SystemExit(f"Expected to mark at least 100 mixins remap=false, changed {mixin_remap_changes}")
print(f"Marked {mixin_remap_changes} Minecraft 26.2 mixins remap=false")


# Correct MaFgLib's loader identity and IDE/development detection for Forge.
reference = root / "mafglib/src/main/java/fi/dy/masa/malilib/MaLiLibReference.java"
text = reference.read_text(encoding="utf-8")
text = text.replace('public static final String MOD_TYPE = "fabric";',
                    'public static final String MOD_TYPE = "forge";')
if "team.cagayakegirls.mafglib.utils.ModPlatform" not in text:
    text = text.replace("import fi.dy.masa.malilib.util.StringUtils;",
                        "import fi.dy.masa.malilib.util.StringUtils;\nimport team.cagayakegirls.mafglib.utils.ModPlatform;")
start = text.find("\tprivate static boolean isRunningInIde()")
if start >= 0:
    brace = text.find("{", start)
    depth = 0
    end = brace
    while end < len(text):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                end += 1
                break
        end += 1
    replacement = """\tprivate static boolean isRunningInIde()
\t{
\t\treturn ModPlatform.isDevelopmentEnvironment();
\t}"""
    text = text[:start] + replacement + text[end:]
reference.write_text(text, encoding="utf-8")

# NeoForge splits ItemStack tooltip generation into an extra private method.
# Forge 26.2 does not have that NeoForge-only injection target. Keep MaLiLib's
# final tooltip callback on the vanilla/Forge addDetailsToTooltip method tail.
itemstack = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/item/MixinItemStack.java"
text = itemstack.read_text(encoding="utf-8")
method_sig = 'addDetailsToTooltipComponents(Lnet/minecraft/world/item/Item$TooltipContext;Lnet/minecraft/world/item/component/TooltipDisplay;Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/item/TooltipFlag;Ljava/util/function/Consumer;)V'
if method_sig in text:
    text = text.replace(method_sig,
        'addDetailsToTooltip(Lnet/minecraft/world/item/Item$TooltipContext;Lnet/minecraft/world/item/component/TooltipDisplay;Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/item/TooltipFlag;Ljava/util/function/Consumer;)V')
    old_at = """at = @At(value = "INVOKE",
                     target = "Lnet/minecraft/world/item/ItemStack;addToTooltip(Lnet/minecraft/core/component/DataComponentType;Lnet/minecraft/world/item/Item$TooltipContext;Lnet/minecraft/world/item/component/TooltipDisplay;Ljava/util/function/Consumer;Lnet/minecraft/world/item/TooltipFlag;)V",
                     ordinal = 23,
                     shift = At.Shift.AFTER)"""
    text = text.replace(old_at, 'at = @At("TAIL")')
    text = text.replace("// fk u neoforge patch, see: https://github.com/neoforged/NeoForge/pull/3132/changes\n", "")
itemstack.write_text(text, encoding="utf-8")


# Preserve upstream's logical "malilib" stub ID alongside the loader-facing
# "mafglib" wrapper ID. MaLiLibReference and downstream mods query "malilib".
maf_mods = root / "mafglib/src/main/resources/META-INF/mods.toml"
text = maf_mods.read_text(encoding="utf-8")
if 'modId="malilib"' not in text:
    stub = '''[[mods]]
modId="malilib"
version="\${file.jarVersion}"
displayName="MaLiLib Stub"
logoFile="assets/malilib/icon.png"
authors="masa, CagayakeGirls; Forge port adaptation"
displayTest="NONE"
description='''MaLiLib compatibility ID provided by the Forge MaFgLib port.'''

'''
    anchor = '[[mixins]]\nconfig="mixins.malilib.json"'
    if anchor not in text:
        raise SystemExit("MaFgLib mixin metadata anchor not found while adding malilib stub")
    text = text.replace(anchor, stub + anchor, 1)
maf_mods.write_text(text, encoding="utf-8")

malilib_stub = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/MalilibCompatMod.java"
if not malilib_stub.exists():
    malilib_stub.write_text("""package team.cagayakegirls.mafglib;

import net.minecraftforge.fml.common.Mod;

/**
 * Compatibility mod id retained from upstream MaFgLib.
 * Initialization is owned by the mafglib entrypoint.
 */
@Mod("malilib")
public final class MalilibCompatMod
{
    public MalilibCompatMod() {}
}
""", encoding="utf-8")


# Mixin 0.8.7 recognizes compatibility levels only through JAVA_21.
# Run on JDK 25 but emit Java 21-compatible mod/mixin bytecode.
for module in ("mafglib", "forgematica"):
    mixin_cfg = root / module / "src/main/resources" / f"mixins.{'malilib' if module == 'mafglib' else 'litematica'}.json"
    cfg_text = mixin_cfg.read_text(encoding="utf-8")
    cfg_text = cfg_text.replace('"compatibilityLevel": "JAVA_25"', '"compatibilityLevel": "JAVA_21"')
    mixin_cfg.write_text(cfg_text, encoding="utf-8")

# Java 22 introduced unnamed variables/patterns. The upstream 26.2 source uses
# them in only a few places; name them explicitly so the complete mod can emit
# Java 21 class files which Mixin 0.8.7 can transform safely.
java21_replacements = {
    "catch (Exception _) {}": "catch (Exception ignored) {}",
    "((_, screen) ->": "((ignoredMinecraft, screen) ->",
}
for module in ("mafglib", "forgematica"):
    for path in (root / module / "src/main/java").rglob("*.java"):
        source = path.read_text(encoding="utf-8")
        rewritten = source
        for old, new in java21_replacements.items():
            rewritten = rewritten.replace(old, new)
        if rewritten != source:
            path.write_text(rewritten, encoding="utf-8")

print("Applied Forge 26.2 post-overlay source fixes")
