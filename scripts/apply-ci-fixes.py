#!/usr/bin/env python3
from pathlib import Path
import json

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
version="${file.jarVersion}"
displayName="MaLiLib Stub"
logoFile="assets/malilib/icon.png"
authors="masa, CagayakeGirls; Forge port adaptation"
displayTest="NONE"
description="MaLiLib compatibility ID provided by the Forge MaFgLib port."

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


# NeoForge adds a 3-argument Language.loadFromJson overload for component
# translations. Forge 26.2 keeps vanilla's 2-argument method. Retarget the
# MaLiLib translation-format mixin to the vanilla/Forge method.
language_mixin = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/client/MixinLanguage.java"
text = language_mixin.read_text(encoding="utf-8")
text = text.replace(
    'loadFromJson(Ljava/io/InputStream;Ljava/util/function/BiConsumer;Ljava/util/function/BiConsumer;)V',
    'loadFromJson(Ljava/io/InputStream;Ljava/util/function/BiConsumer;)V'
)
language_mixin.write_text(text, encoding="utf-8")



# Forge Mixin 0.8.7 does not allow arbitrary @Inject points inside a constructor.
# Move MaLiLib pre-game initialization into the Forge mod entrypoint and remove
# the illegal Minecraft.<init> INVOKE injection while keeping the RETURN hook.
entry = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/MaFgLib.java"
text = entry.read_text(encoding="utf-8")
if "fi.dy.masa.malilib.event.InitializationHandler" not in text:
    text = text.replace(
        "import fi.dy.masa.malilib.compat.modmenu.ModMenuImpl;",
        "import fi.dy.masa.malilib.compat.modmenu.ModMenuImpl;\nimport fi.dy.masa.malilib.event.InitializationHandler;"
    )
if "net.minecraftforge.fml.loading.FMLPaths" not in text:
    text = text.replace(
        "import net.minecraftforge.fml.common.Mod;",
        "import net.minecraftforge.fml.common.Mod;\nimport net.minecraftforge.fml.loading.FMLPaths;"
    )
old_init = "        new MaLiLib().onInitialize();"
new_init = """        new MaLiLib().onInitialize();
        ((InitializationHandler) InitializationHandler.getInstance()).onPreGameInit(FMLPaths.GAMEDIR.get());"""
if new_init not in text:
    if old_init not in text:
        raise SystemExit("MaFgLib initialization call not found while moving pre-game init")
    text = text.replace(old_init, new_init, 1)
entry.write_text(text, encoding="utf-8")

minecraft_mixin = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/client/MixinMinecraft.java"
text = minecraft_mixin.read_text(encoding="utf-8")
pre_hook = re.compile(
    r'\n\s*@Inject\(method = "<init>\(Lnet/minecraft/client/main/GameConfig;\)V",\s*'
    r'at = @At\(value = "INVOKE",\s*'
    r'target = "Lnet/minecraft/world/level/storage/LevelStorageSource;parseValidator\(Ljava/nio/file/Path;\)Lnet/minecraft/world/level/validation/DirectoryValidator;"\)\)\s*'
    r'private void malilib_onPreGameInit\(GameConfig gameConfig, CallbackInfo ci\)\s*'
    r'\{[\s\S]*?\n\s*\}\n',
    re.MULTILINE
)
text, removed = pre_hook.subn("\n", text, count=1)
if removed == 0 and "malilib_onPreGameInit" in text:
    raise SystemExit("Could not remove illegal Minecraft constructor pre-game injection")
minecraft_mixin.write_text(text, encoding="utf-8")



# MixinExtras @Local capture in LevelExtractor.extract is brittle on Forge's
# Mixin 0.8.7 and crashed with an ArrayIndexOutOfBoundsException. Retarget the
# per-frame Litematica preparation to extractVisibleEntities, where the Frustum
# is an explicit method parameter in Minecraft 26.2.
level_extractor_mixin = root / "forgematica/src/main/java/fi/dy/masa/litematica/mixin/render/MixinLevelExtractor.java"
text = level_extractor_mixin.read_text(encoding="utf-8")
text = text.replace("import com.llamalad7.mixinextras.sugar.Local;\n", "")
old_extract_hook = re.compile(
    r'\n\s*// was "cullTerrain"\s*'
    r'@Inject\(method = "extract",\s*'
    r'at = @At\(value = "INVOKE",\s*'
    r'target = "Lnet/minecraft/util/profiling/ProfilerFiller;popPush\(Ljava/lang/String;\)V",\s*'
    r'ordinal = 2, shift = At\.Shift\.BEFORE\)\)\s*'
    r'private void litematica_onExtractLevel\(DeltaTracker deltaTracker, Camera camera, float deltaPartialTick, CallbackInfo ci,\s*'
    r'@Local Frustum cullFrustum\)\s*'
    r'\{([\s\S]*?)\n\s*\}\n',
    re.MULTILINE
)
match = old_extract_hook.search(text)
if match:
    body = match.group(1).replace("cullFrustum", "frustum")
    replacement = """
	@Inject(method = "extractVisibleEntities", at = @At("HEAD"))
	private void litematica_onExtractLevel(Camera camera, Frustum frustum, DeltaTracker deltaTracker, LevelRenderState output, CallbackInfo ci)
	{""" + body + """
	}
"""
    text = text[:match.start()] + replacement + text[match.end():]
elif "@Local Frustum cullFrustum" in text:
    raise SystemExit("Could not retarget LevelExtractor local-capture injection")
level_extractor_mixin.write_text(text, encoding="utf-8")



# MaFgLib's LevelExtractor mixin also used MixinExtras @Local to capture the
# active ProfilerFiller. On Forge's Mixin 0.8.7 that local capture crashes while
# preparing the injection. Use Profiler.get() instead; it returns the current
# active profiler without depending on local variable table indexes.
malilib_level_extractor = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/render/MixinLevelExtractor.java"
text = malilib_level_extractor.read_text(encoding="utf-8")
text = text.replace("import com.llamalad7.mixinextras.sugar.Local;\n", "")
if "import net.minecraft.util.profiling.Profiler;" not in text:
    text = text.replace(
        "import net.minecraft.util.profiling.ProfilerFiller;",
        "import net.minecraft.util.profiling.Profiler;\nimport net.minecraft.util.profiling.ProfilerFiller;"
    )
text = re.sub(
    r',\s*CallbackInfo ci,\s*@Local\(name = "profiler"\) ProfilerFiller profiler\)',
    ', CallbackInfo ci)',
    text
)
text = text.replace(
    "runExtractWorldPreWeather(deltaTracker, camera, deltaPartialTick, profiler);",
    "runExtractWorldPreWeather(deltaTracker, camera, deltaPartialTick, Profiler.get());"
)
text = text.replace(
    "runExtractWorldLast(deltaTracker, camera, deltaPartialTick, profiler);",
    "runExtractWorldLast(deltaTracker, camera, deltaPartialTick, Profiler.get());"
)
if "@Local(" in text:
    raise SystemExit("MaFgLib LevelExtractor still contains @Local capture")
malilib_level_extractor.write_text(text, encoding="utf-8")



# Forge 26.2's LevelExtractor.extractVisibleBlockEntities includes an explicit
# Frustum parameter. NeoForge's staged source handler omitted it, which makes
# Mixin reject the callback descriptor at runtime.
litematica_level_extractor = root / "forgematica/src/main/java/fi/dy/masa/litematica/mixin/render/MixinLevelExtractor.java"
text = litematica_level_extractor.read_text(encoding="utf-8")
old_sig = """private void litematica_onPostPrepareBlockEntities(Camera camera, float deltaPartialTick, LevelRenderState levelRenderState, CallbackInfo ci)"""
new_sig = """private void litematica_onPostPrepareBlockEntities(Camera camera, float deltaPartialTick, LevelRenderState levelRenderState, Frustum cullFrustum, CallbackInfo ci)"""
if old_sig in text:
    text = text.replace(old_sig, new_sig, 1)
elif new_sig not in text:
    raise SystemExit("Could not update Litematica extractVisibleBlockEntities callback signature")
litematica_level_extractor.write_text(text, encoding="utf-8")



# Forge 26.2's synthetic LevelRenderer.lambda$addMainPass$0 does not carry
# NeoForge's extra Matrix4fc parameter. Remove it from both Litematica callbacks
# so their descriptors match the actual Forge runtime method.
level_renderer_mixin = root / "forgematica/src/main/java/fi/dy/masa/litematica/mixin/render/MixinLevelRenderer.java"
text = level_renderer_mixin.read_text(encoding="utf-8")
text = text.replace(
    "ChunkSectionsToRender chunkSectionsToRender, Matrix4fc modelViewMatrix,\n\t\t\t\t\t\t\t\t\t\t\t\t ResourceHandle<RenderTarget> entityOutlineTarget",
    "ChunkSectionsToRender chunkSectionsToRender,\n\t\t\t\t\t\t\t\t\t\t\t\t ResourceHandle<RenderTarget> entityOutlineTarget"
)
text = text.replace(
    "ChunkSectionsToRender chunkSectionsToRender, Matrix4fc modelViewMatrix,\n\t                                                      ResourceHandle<RenderTarget> entityOutlineTarget",
    "ChunkSectionsToRender chunkSectionsToRender,\n\t                                                      ResourceHandle<RenderTarget> entityOutlineTarget"
)
# Fallback for formatting differences.
text = re.sub(
    r'(private void litematica_renderMainSection_Opaque\([\s\S]*?ChunkSectionsToRender chunkSectionsToRender),\s*Matrix4fc modelViewMatrix,',
    r'\1,',
    text,
    count=1
)
text = re.sub(
    r'(private void litematica_renderMainSection_Translucent\([\s\S]*?ChunkSectionsToRender chunkSectionsToRender),\s*Matrix4fc modelViewMatrix,',
    r'\1,',
    text,
    count=1
)
for method in ("litematica_renderMainSection_Opaque", "litematica_renderMainSection_Translucent"):
    m = re.search(rf'private void {method}\((.*?)CallbackInfo ci\)', text, flags=re.S)
    if not m:
        raise SystemExit(f"Could not find {method} callback after Forge lambda descriptor fix")
    if "Matrix4fc modelViewMatrix" in m.group(1):
        raise SystemExit(f"{method} still has NeoForge-only Matrix4fc parameter")
level_renderer_mixin.write_text(text, encoding="utf-8")



# Litematica's renderMainPass hook is a NeoForge-era no-op: its entire body is
# commented out, but its @Inject target references NeoForge's 3-argument
# addWeatherPass overload, which Forge does not have. Remove the dead hook.
# Also stop capturing the render() local profiler through MixinExtras; use
# Profiler.get() so this file no longer depends on fragile local indexes.
level_renderer_mixin = root / "forgematica/src/main/java/fi/dy/masa/litematica/mixin/render/MixinLevelRenderer.java"
text = level_renderer_mixin.read_text(encoding="utf-8")
text = text.replace("import com.llamalad7.mixinextras.sugar.Local;\n", "")

# Remove @Local profiler parameter from litematica_onPreRenderMain.
text = re.sub(
    r'(private void litematica_onPreRenderMain\([\s\S]*?boolean shouldRenderSky, CallbackInfo ci),\s*'
    r'@Local\(name = "profiler"\) ProfilerFiller profiler\)',
    r'\1)',
    text,
    count=1
)
old_line = "        this.profiler = profiler;"
if old_line in text:
    text = text.replace(
        old_line,
        "        ProfilerFiller profiler = Profiler.get();\n        this.profiler = profiler;",
        1
    )

# Remove the dead NeoForge-only weather-pass callback completely.
dead_hook = re.compile(
    r'\n\s*@Inject\(method = "render",\s*'
    r'at = @At\(value = "INVOKE",\s*'
    r'target = "Lnet/minecraft/client/renderer/LevelRenderer;addWeatherPass\(Lcom/mojang/blaze3d/framegraph/FrameGraphBuilder;Lcom/mojang/blaze3d/buffers/GpuBufferSlice;Lorg/joml/Matrix4fc;\)V",\s*'
    r'shift = At\.Shift\.BEFORE\)\)\s*'
    r'private void litematica_renderMainPass\([\s\S]*?\n\s*\}\n',
    re.MULTILINE
)
text, removed = dead_hook.subn("\n", text, count=1)
if removed == 0 and "litematica_renderMainPass" in text:
    raise SystemExit("Could not remove dead NeoForge-only litematica_renderMainPass hook")

if "@Local(" in text:
    raise SystemExit("MixinLevelRenderer still contains fragile @Local capture")
level_renderer_mixin.write_text(text, encoding="utf-8")



# Rebuild MaFgLib's LevelRenderer bridge around vanilla/Forge 26.2 helper
# methods. NeoForge adds render helper overloads and the staged mixin also
# relied on MixinExtras locals; both are wrong for Forge 65.1.0.
malilib_level_renderer = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/render/MixinLevelRenderer.java"
malilib_level_renderer.write_text("""package fi.dy.masa.malilib.mixin.render;

import org.joml.Matrix4fc;
import org.joml.Vector4f;

import com.mojang.blaze3d.buffers.GpuBufferSlice;
import com.mojang.blaze3d.framegraph.FrameGraphBuilder;
import com.mojang.blaze3d.resource.GraphicsResourceAllocator;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.GameRenderer;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.LevelTargetBundle;
import net.minecraft.client.renderer.RenderBuffers;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import net.minecraft.util.profiling.Profiler;
import net.minecraft.util.profiling.ProfilerFiller;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import fi.dy.masa.malilib.event.RenderEventHandler;

@Mixin(value = LevelRenderer.class, priority = 900, remap = false)
public abstract class MixinLevelRenderer
{
    @Shadow @Final private LevelTargetBundle targets;
    @Shadow @Final private RenderBuffers renderBuffers;
    @Shadow @Final private GameRenderer gameRenderer;

    @Unique private CameraRenderState mafglib$cameraState;
    @Unique private Matrix4fc mafglib$modelViewMatrix;
    @Unique private Vector4f mafglib$fogColor;

    @Inject(method = "render", at = @At("HEAD"))
    private void mafglib$captureRenderState(GraphicsResourceAllocator resourceAllocator, DeltaTracker deltaTracker,
                                            boolean renderOutline, CameraRenderState cameraState, Matrix4fc modelViewMatrix,
                                            GpuBufferSlice terrainFog, Vector4f fogColor, boolean shouldRenderSky,
                                            CallbackInfo ci)
    {
        this.mafglib$cameraState = cameraState;
        this.mafglib$modelViewMatrix = modelViewMatrix;
        this.mafglib$fogColor = fogColor;
    }

    @Inject(
        method = "addWeatherPass(Lcom/mojang/blaze3d/framegraph/FrameGraphBuilder;Lcom/mojang/blaze3d/buffers/GpuBufferSlice;)V",
        at = @At("HEAD")
    )
    private void mafglib$onRenderWorldPreWeather(FrameGraphBuilder frame, GpuBufferSlice terrainFog, CallbackInfo ci)
    {
        if (this.mafglib$cameraState == null || this.mafglib$modelViewMatrix == null || this.mafglib$fogColor == null)
        {
            return;
        }

        ProfilerFiller profiler = Profiler.get();
        ((RenderEventHandler) RenderEventHandler.getInstance()).runRenderWorldPreWeather(
                this.mafglib$modelViewMatrix,
                Minecraft.getInstance(),
                frame,
                this.targets,
                this.gameRenderer.mainCamera().getCullFrustum(),
                this.mafglib$cameraState,
                this.renderBuffers,
                terrainFog,
                this.mafglib$fogColor,
                profiler
        );
    }

    @Inject(
        method = "addLateDebugPass(Lcom/mojang/blaze3d/framegraph/FrameGraphBuilder;Lnet/minecraft/client/renderer/state/level/CameraRenderState;Lcom/mojang/blaze3d/buffers/GpuBufferSlice;Lorg/joml/Matrix4fc;)V",
        at = @At("HEAD")
    )
    private void mafglib$onRenderWorldLast(FrameGraphBuilder frame, CameraRenderState cameraState,
                                           GpuBufferSlice terrainFog, Matrix4fc modelViewMatrix,
                                           CallbackInfo ci)
    {
        Vector4f fogColor = this.mafglib$fogColor;
        if (fogColor == null)
        {
            return;
        }

        ProfilerFiller profiler = Profiler.get();
        ((RenderEventHandler) RenderEventHandler.getInstance()).runRenderWorldLast(
                modelViewMatrix,
                Minecraft.getInstance(),
                frame,
                this.targets,
                this.gameRenderer.mainCamera().getCullFrustum(),
                cameraState,
                this.renderBuffers,
                terrainFog,
                fogColor,
                profiler
        );
    }
}
""", encoding="utf-8")



# Replace MaFgLib's remaining LevelRenderer helper-method injections with
# Forge 26.2's public AddFramePassEvent. A tiny render-HEAD mixin only captures
# frame-specific values that the Forge pass API does not expose directly.
malilib_level_renderer = root / "mafglib/src/main/java/fi/dy/masa/malilib/mixin/render/MixinLevelRenderer.java"
malilib_level_renderer.write_text("""package fi.dy.masa.malilib.mixin.render;

import org.joml.Matrix4fc;
import org.joml.Vector4f;

import com.mojang.blaze3d.buffers.GpuBufferSlice;
import com.mojang.blaze3d.resource.GraphicsResourceAllocator;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import team.cagayakegirls.mafglib.render.ForgeFramePassBridge;

@Mixin(value = LevelRenderer.class, priority = 900, remap = false)
public abstract class MixinLevelRenderer
{
    @Inject(method = "render", at = @At("HEAD"))
    private void mafglib$captureRenderState(GraphicsResourceAllocator resourceAllocator, DeltaTracker deltaTracker,
                                            boolean renderOutline, CameraRenderState cameraState, Matrix4fc modelViewMatrix,
                                            GpuBufferSlice terrainFog, Vector4f fogColor, boolean shouldRenderSky,
                                            CallbackInfo ci)
    {
        ForgeFramePassBridge.capture(modelViewMatrix, terrainFog, fogColor);
    }
}
""", encoding="utf-8")

forge_pass_bridge = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/render/ForgeFramePassBridge.java"
forge_pass_bridge.parent.mkdir(parents=True, exist_ok=True)
forge_pass_bridge.write_text("""package team.cagayakegirls.mafglib.render;

import org.joml.Matrix4f;
import org.joml.Matrix4fc;
import org.joml.Vector4f;

import com.mojang.blaze3d.buffers.GpuBufferSlice;
import com.mojang.blaze3d.framegraph.FramePass;
import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.resource.ResourceHandle;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.LevelTargetBundle;
import net.minecraft.client.renderer.state.level.LevelRenderState;
import net.minecraft.resources.Identifier;
import net.minecraft.util.profiling.Profiler;
import net.minecraftforge.client.FramePassManager;
import net.minecraftforge.client.event.AddFramePassEvent;

import fi.dy.masa.malilib.event.RenderEventHandler;

public final class ForgeFramePassBridge
{
    private static Matrix4fc modelViewMatrix;
    private static GpuBufferSlice terrainFog;
    private static Vector4f fogColor;

    private ForgeFramePassBridge() {}

    public static void capture(Matrix4fc matrix, GpuBufferSlice fog, Vector4f color)
    {
        modelViewMatrix = new Matrix4f(matrix);
        terrainFog = fog;
        fogColor = new Vector4f(color);
    }

    public static void register(AddFramePassEvent event)
    {
        event.addPass(
                Identifier.fromNamespaceAndPath("mafglib", "world_last"),
                new FramePassManager.PassDefinition()
                {
                    private ResourceHandle<RenderTarget> mainTarget;

                    @Override
                    public void extracts(LevelTargetBundle bundle, FramePass pass, DeltaTracker deltaTracker)
                    {
                        bundle.main = pass.readsAndWrites(bundle.main);
                        this.mainTarget = bundle.main;
                    }

                    @Override
                    public void executes(LevelRenderState state)
                    {
                        Matrix4fc matrix = modelViewMatrix;
                        GpuBufferSlice fog = terrainFog;
                        Vector4f color = fogColor;
                        ResourceHandle<RenderTarget> target = this.mainTarget;

                        if (matrix == null || fog == null || color == null || target == null)
                        {
                            return;
                        }

                        Minecraft mc = Minecraft.getInstance();
                        ((RenderEventHandler) RenderEventHandler.getInstance()).runRenderWorldLastForge(
                                target.get(),
                                matrix,
                                state.cameraRenderState,
                                mc.gameRenderer.mainCamera().getCullFrustum(),
                                mc.renderBuffers(),
                                fog,
                                color,
                                Profiler.get()
                        );
                    }
                }
        );
    }
}
""", encoding="utf-8")

# Add a direct execution path for Forge's native frame pass.
render_events = root / "mafglib/src/main/java/fi/dy/masa/malilib/event/RenderEventHandler.java"
text = render_events.read_text(encoding="utf-8")
marker = """    @ApiStatus.Internal
    public void runRenderWorldLast(Matrix4fc modelViewMatrix, Minecraft mc,
"""
forge_direct = """    @ApiStatus.Internal
    public void runRenderWorldLastForge(RenderTarget fb, Matrix4fc modelViewMatrix,
                                        CameraRenderState cameraState, Frustum cullFrustum,
                                        RenderBuffers buffers, GpuBufferSlice terrainFog,
                                        Vector4f fogColor, ProfilerFiller profiler)
    {
        if (this.worldLastRenderers.isEmpty() == false)
        {
            profiler.push(MaLiLibReference.MOD_ID+"_world_last");
            GpuBufferSlice previousFog = RenderSystem.getShaderFog();

            for (IRenderer renderer : this.worldLastRenderers)
            {
                profiler.push(renderer.getProfilerSectionSupplier());
                renderer.onRenderWorldLast(
                        fb,
                        modelViewMatrix,
                        cameraState,
                        cullFrustum,
                        buffers,
                        terrainFog,
                        fogColor,
                        profiler);
                profiler.pop();
            }

            RenderSystem.setShaderFog(previousFog);
            profiler.pop();
        }
    }

"""
if "runRenderWorldLastForge(" not in text:
    if marker not in text:
        raise SystemExit("RenderEventHandler world-last insertion point not found")
    text = text.replace(marker, forge_direct + marker, 1)
render_events.write_text(text, encoding="utf-8")

# Register the Forge frame pass listener before LevelRenderer is constructed.
entry = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/MaFgLib.java"
text = entry.read_text(encoding="utf-8")
if "net.minecraftforge.client.event.AddFramePassEvent" not in text:
    text = text.replace(
        "import net.minecraftforge.client.ConfigScreenHandler.ConfigScreenFactory;",
        "import net.minecraftforge.client.ConfigScreenHandler.ConfigScreenFactory;\nimport net.minecraftforge.client.event.AddFramePassEvent;\nimport team.cagayakegirls.mafglib.render.ForgeFramePassBridge;"
    )
registration = "        AddFramePassEvent.BUS.addListener(ForgeFramePassBridge::register);"
if registration not in text:
    init_line = "        new MaLiLib().onInitialize();"
    if init_line not in text:
        raise SystemExit("MaFgLib onInitialize call not found for frame-pass registration")
    text = text.replace(init_line, registration + "\n" + init_line, 1)
entry.write_text(text, encoding="utf-8")



# Replace the HUD local-capture mixin with Forge's native GUI layer event.
gui_bridge = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/render/ForgeGuiOverlayBridge.java"
gui_bridge.parent.mkdir(parents=True, exist_ok=True)
gui_bridge.write_text("""package team.cagayakegirls.mafglib.render;

import net.minecraft.resources.Identifier;
import net.minecraftforge.client.event.AddGuiOverlayLayersEvent;

import fi.dy.masa.malilib.event.RenderEventHandler;
import fi.dy.masa.malilib.render.GuiContext;

public final class ForgeGuiOverlayBridge
{
    private ForgeGuiOverlayBridge() {}

    public static void register(AddGuiOverlayLayersEvent event)
    {
        event.getLayeredDraw().add(
                Identifier.fromNamespaceAndPath("mafglib", "overlay_post"),
                (graphics, deltaTracker) ->
                        ((RenderEventHandler) RenderEventHandler.getInstance()).runExtractGuiOverlayPost(
                                GuiContext.fromGuiGraphics(graphics),
                                deltaTracker.getGameTimeDeltaPartialTick(false)
                        )
        );
    }
}
""", encoding="utf-8")

entry = root / "mafglib/src/main/java/team/cagayakegirls/mafglib/MaFgLib.java"
text = entry.read_text(encoding="utf-8")
if "net.minecraftforge.client.event.AddGuiOverlayLayersEvent" not in text:
    text = text.replace(
        "import net.minecraftforge.client.event.AddFramePassEvent;",
        "import net.minecraftforge.client.event.AddFramePassEvent;\nimport net.minecraftforge.client.event.AddGuiOverlayLayersEvent;"
    )
if "team.cagayakegirls.mafglib.render.ForgeGuiOverlayBridge" not in text:
    text = text.replace(
        "import team.cagayakegirls.mafglib.render.ForgeFramePassBridge;",
        "import team.cagayakegirls.mafglib.render.ForgeFramePassBridge;\nimport team.cagayakegirls.mafglib.render.ForgeGuiOverlayBridge;"
    )
gui_registration = "        AddGuiOverlayLayersEvent.BUS.addListener(ForgeGuiOverlayBridge::register);"
if gui_registration not in text:
    frame_registration = "        AddFramePassEvent.BUS.addListener(ForgeFramePassBridge::register);"
    if frame_registration not in text:
        raise SystemExit("Frame-pass listener registration anchor missing")
    text = text.replace(frame_registration, frame_registration + "\n" + gui_registration, 1)
entry.write_text(text, encoding="utf-8")

# Remove the old Gui local-capture mixin from the active config.
mixin_cfg = root / "mafglib/src/main/resources/mixins.malilib.json"
cfg = json.loads(mixin_cfg.read_text(encoding="utf-8"))
for section in ("mixins", "client", "server"):
    if section in cfg:
        cfg[section] = [name for name in cfg[section] if name != "gui.MixinGui"]
mixin_cfg.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


# Remove Litematica's CameraRenderState @Local capture. GameRenderer exposes its
# GameRenderState, whose LevelRenderState contains the extracted camera state.
game_renderer_mixin = root / "forgematica/src/main/java/fi/dy/masa/litematica/mixin/render/MixinGameRenderer.java"
text = game_renderer_mixin.read_text(encoding="utf-8")
text = text.replace("import com.llamalad7.mixinextras.sugar.Local;\n\n", "")
if "import net.minecraft.client.Minecraft;" not in text:
    text = text.replace("import net.minecraft.client.DeltaTracker;", "import net.minecraft.client.DeltaTracker;\nimport net.minecraft.client.Minecraft;")
local_marker = '@Local(name = "cameraState") CameraRenderState cameraState'
local_pos = text.find(local_marker)
if local_pos >= 0:
    method_pos = text.rfind("private void litematica_updateCameraState(", 0, local_pos)
    comma_pos = text.rfind(",", method_pos, local_pos)
    if method_pos < 0 or comma_pos < 0:
        raise SystemExit("Could not locate camera @Local parameter boundary")
    text = text[:comma_pos] + text[local_pos + len(local_marker):]
old_call = "LitematicaRenderer.getInstance().updateCameraState(this.mainCamera, cameraEntityPartialTicks, cameraState);"
new_call = """CameraRenderState cameraState = Minecraft.getInstance().gameRenderer.gameRenderState().levelRenderState.cameraRenderState;
        LitematicaRenderer.getInstance().updateCameraState(this.mainCamera, cameraEntityPartialTicks, cameraState);"""
if old_call in text:
    text = text.replace(old_call, new_call, 1)
elif new_call not in text:
    raise SystemExit("Could not replace Litematica GameRenderer camera local capture")
if "@Local(" in text:
    raise SystemExit("Litematica MixinGameRenderer still contains @Local capture")
game_renderer_mixin.write_text(text, encoding="utf-8")

print("Applied Forge 26.2 post-overlay source fixes")
