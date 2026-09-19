#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MODULES = {"mafglib": ROOT / "mafglib", "forgematica": ROOT / "forgematica"}
TEXT_SUFFIXES = {".java", ".json", ".toml", ".cfg", ".gradle", ".properties", ".mcmeta", ".md", ".py", ".sh"}

errors = []
warnings = []
stats = Counter()
texts = {}

def fail(message):
    errors.append(message)

def strip_java_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)

def read(path):
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    stats["text_files"] += 1
    stats["text_lines"] += len(value.splitlines())
    if path.suffix == ".java":
        stats["java_files"] += 1
        stats["java_lines"] += len(value.splitlines())
    return value

# Read every line of every Java file and every textual resource/build file.
for module, base in MODULES.items():
    for source_root in (base / "src/main/java", base / "src/main/resources"):
        if not source_root.is_dir():
            fail(f"Missing source root: {source_root.relative_to(ROOT)}")
            continue
        for path in sorted(p for p in source_root.rglob("*") if p.is_file()):
            if path.suffix not in TEXT_SUFFIXES:
                stats["binary_resources"] += 1
                continue
            value = read(path)
            if value is not None:
                texts[path] = value
    build = base / "build.gradle"
    if not build.is_file():
        fail(f"Missing {module}/build.gradle")
    else:
        texts[build] = read(build) or ""

for path in (ROOT / "build.gradle", ROOT / "settings.gradle", ROOT / "gradle.properties"):
    if path.is_file():
        texts[path] = read(path) or ""

# Full-tree sanity: fail if CI accidentally stages only a skeleton.
for module, minimum in (("forgematica", 300), ("mafglib", 550)):
    count = len(list((MODULES[module] / "src/main/java").rglob("*.java")))
    stats[f"java_{module}"] = count
    if count < minimum:
        fail(f"{module}: only {count} Java files staged; expected at least {minimum}")

# Loader namespace/API audit. Comments are removed before checking Java.
checks = (
    (r"^\s*import\s+net\.neoforged\.", "active NeoForge import"),
    (r"^\s*import\s+net\.fabricmc\.(?:fabric|loader)\.", "active Fabric import"),
    (r"^\s*import\s+org\.quiltmc\.", "active Quilt import"),
    (r"\bClientPlayNetworking\b", "Fabric ClientPlayNetworking API"),
    (r"\bPayloadTypeRegistry\b", "Fabric PayloadTypeRegistry API"),
    (r"\bPictureInPictureRendererPool\b", "NeoForge PiP pool API"),
    (r"\bFMLLoader\.getCurrent\s*\(", "obsolete FMLLoader.getCurrent call"),
)
for path, text in texts.items():
    active = strip_java_comments(text) if path.suffix == ".java" else text
    for pattern, label in checks:
        if re.search(pattern, active, flags=re.M):
            fail(f"{path.relative_to(ROOT)}: {label}")

for module, base in MODULES.items():
    wideners = list((base / "src/main/resources").rglob("*.accesswidener"))
    if wideners:
        fail(f"{module}: active access widener left in Forge resources")

# Java package/path integrity and FQCN map.
fqcn = {}
for path, text in texts.items():
    if path.suffix != ".java":
        continue
    active = strip_java_comments(text).strip()
    if not active:
        continue
    package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", active, flags=re.M)
    if not package_match:
        fail(f"{path.relative_to(ROOT)}: active Java source has no package declaration")
        continue
    package = package_match.group(1)
    module = path.relative_to(ROOT).parts[0]
    src_root = MODULES[module] / "src/main/java"
    relative = path.relative_to(src_root)
    expected_parent = Path(*package.split("."))
    if relative.parent != expected_parent:
        fail(f"{path.relative_to(ROOT)}: package/path mismatch ({package})")
    name = package + "." + path.stem
    if name in fqcn:
        fail(f"Duplicate source class {name}")
    fqcn[name] = path

# Every configured mixin and plugin must exist as source.
mixin_owner = {}
for module, base in MODULES.items():
    configs = sorted((base / "src/main/resources").glob("mixins.*.json"))
    if not configs:
        fail(f"{module}: no mixin config")
    for cfg in configs:
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"{cfg.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        if data.get("required") is not True:
            fail(f"{cfg.relative_to(ROOT)}: required must be true")
        if data.get("compatibilityLevel") != "JAVA_21":
            fail(f"{cfg.relative_to(ROOT)}: compatibilityLevel must be JAVA_21 for Mixin 0.8.7")
        package = data.get("package", "")
        plugin = data.get("plugin")
        if plugin and plugin not in fqcn:
            fail(f"{cfg.relative_to(ROOT)}: missing plugin source {plugin}")
        seen = set()
        for section in ("mixins", "client", "server"):
            for short_name in data.get(section, []):
                if short_name in seen:
                    fail(f"{cfg.relative_to(ROOT)}: duplicate mixin entry {short_name}")
                seen.add(short_name)
                full_name = package + "." + short_name
                if full_name not in fqcn:
                    fail(f"{cfg.relative_to(ROOT)}: missing mixin source {full_name}")
                previous = mixin_owner.setdefault(full_name, cfg.name)
                if previous != cfg.name:
                    fail(f"{full_name}: listed by both {previous} and {cfg.name}")
        stats["mixin_entries"] += len(seen)

# Minecraft 26.2 has unobfuscated Mojang names at runtime, so mixins must not
# request legacy obfuscation remapping.
for path, text in texts.items():
    if path.suffix != ".java" or "@Mixin(" not in text:
        continue
    for annotation in re.findall(r"@Mixin\\((.*?)\\)", text, flags=re.S):
        if not re.search(r"\\bremap\\s*=\\s*false", annotation):
            fail(f"{path.relative_to(ROOT)}: all @Mixin declarations must use remap=false on Minecraft 26.2")

# MixinExtras local-capture audit. These are not automatically illegal, but
# they are fragile on Forge's Mixin 0.8.7 and must be explicitly accounted for.
local_capture_sites = []
for path, text in texts.items():
    if path.suffix != ".java" or "@Local" not in text:
        continue
    for number, line in enumerate(text.splitlines(), 1):
        if "@Local" in line:
            local_capture_sites.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
stats["mixin_local_captures"] = len(local_capture_sites)
for site in local_capture_sites:
    fail("MixinExtras @Local capture is forbidden on this Forge/Mixin 0.8.7 port: " + site)

# Forge metadata.
def parse_mod_ids(text):
    result = []
    in_mod = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[mods]]":
            in_mod = True
            continue
        if stripped.startswith("[[") and stripped != "[[mods]]":
            in_mod = False
        if in_mod:
            match = re.match(r'modId\s*=\s*"([^"]+)"', stripped)
            if match:
                result.append(match.group(1))
                in_mod = False
    return result

for module, expected_ids in (("mafglib", {"mafglib", "malilib"}), ("forgematica", {"forgematica", "litematica"})):
    metadata = MODULES[module] / "src/main/resources/META-INF/mods.toml"
    if not metadata.is_file():
        fail(f"{module}: missing META-INF/mods.toml")
        continue
    text = metadata.read_text(encoding="utf-8")
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        fail(f"{module}: invalid mods.toml: {exc}")
    if set(parse_mod_ids(text)) != expected_ids:
        fail(f"{module}: unexpected mod IDs {parse_mod_ids(text)}")
    for needle in ('loaderVersion="[65,)"', 'clientSideOnly=true', 'versionRange="[26.2,26.3)"'):
        if needle not in text:
            fail(f"{module}: metadata missing {needle}")

forgematica_meta = (MODULES["forgematica"] / "src/main/resources/META-INF/mods.toml").read_text(encoding="utf-8")
if not re.search(r'modId\s*=\s*"mafglib"[\s\S]*?ordering\s*=\s*"AFTER"', forgematica_meta):
    fail("forgematica: MaFgLib dependency must load BEFORE Forgematica (ordering=AFTER on the dependency)")

# Loader identity must match the actual Forge port.
reference = MODULES["mafglib"] / "src/main/java/fi/dy/masa/malilib/MaLiLibReference.java"
if reference.is_file():
    reference_text = reference.read_text(encoding="utf-8")
    if 'MOD_TYPE = "forge"' not in reference_text:
        fail("MaLiLibReference must identify Forge, not Fabric/NeoForge")
    if 'MOD_ID = "malilib"' not in reference_text:
        fail("MaLiLibReference must retain the upstream logical malilib id")
else:
    fail("MaLiLibReference.java missing")

# Entry points.
entrypoints = {
    MODULES["mafglib"] / "src/main/java/team/cagayakegirls/mafglib/MaFgLib.java": ("@Mod(MaFgLib.MOD_ID)", 'MOD_ID = "mafglib"'),
    MODULES["forgematica"] / "src/main/java/team/cagayakegirls/forgematica/Forgematica.java": ("@Mod(Forgematica.MOD_ID)", 'MOD_ID = "forgematica"'),
    MODULES["forgematica"] / "src/main/java/team/cagayakegirls/forgematica/LitematicaCompatMod.java": ('@Mod("litematica")',),
}
for path, needles in entrypoints.items():
    if not path.is_file():
        fail(f"Missing Forge entrypoint {path.relative_to(ROOT)}")
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path.relative_to(ROOT)}: missing {needle}")

# AT files must be the same merged superset in this multi-project FG7 build.
at_text = {}
for module, base in MODULES.items():
    path = base / "src/main/resources/META-INF/accesstransformer.cfg"
    if not path.is_file():
        fail(f"{module}: missing access transformer")
        continue
    text = path.read_text(encoding="utf-8")
    at_text[module] = text
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(stripped)
        if not re.match(r"^(?:public|protected|default)(?:[+-]f)?\s+net\.minecraft\.", stripped):
            fail(f"{path.relative_to(ROOT)}:{number}: malformed/suspicious AT rule: {stripped}")
    duplicates = [rule for rule, count in Counter(entries).items() if count > 1]
    if duplicates:
        fail(f"{module}: duplicate AT rules ({len(duplicates)})")
    stats[f"at_{module}"] = len(entries)

if len(at_text) == 2 and at_text["mafglib"] != at_text["forgematica"]:
    fail("MaFgLib/Forgematica AT files are not identical; FG7 may reuse the wrong transformed Minecraft artifact")

for needle in (
    "net.minecraft.client.renderer.block.FluidRenderer fluidModels",
    "net.minecraft.client.renderer.block.FluidRenderer isNeighborSameFluid",
    "net.minecraft.client.renderer.block.FluidRenderer isFaceOccludedByNeighbor",
    "net.minecraft.client.renderer.block.FluidRenderer calculateAverageHeight",
    "net.minecraft.client.renderer.block.FluidRenderer getHeight",
    "net.minecraft.client.renderer.block.FluidRenderer getLightCoords",
):
    if at_text and not any(needle in value for value in at_text.values()):
        fail(f"Missing critical FluidRenderer AT: {needle}")

# Build invariants, including Mixin AP so bad shadows/injections do not silently compile.
for module, base in MODULES.items():
    build = (base / "build.gradle").read_text(encoding="utf-8")
    for needle in (
        "JavaLanguageVersion.of(25)",
        "mappings channel: 'official'",
        "accessTransformers = files('src/main/resources/META-INF/accesstransformer.cfg')",
        "annotationProcessor 'org.spongepowered:mixin:0.8.7:processor'",
        "options.release = 25",
    ):
        if needle not in build:
            fail(f"{module}/build.gradle: missing {needle}")

maf_build = (MODULES["mafglib"] / "build.gradle").read_text(encoding="utf-8")
for needle in ("net.minecraftforge.jarjar", "conditional-mixin-forge:0.6.4"):
    if needle not in maf_build:
        fail(f"mafglib/build.gradle: missing {needle}")
forg_build = (MODULES["forgematica"] / "build.gradle").read_text(encoding="utf-8")
if "compileOnly 'me.fallenbreath:conditional-mixin-forge:0.6.4'" not in forg_build:
    fail("forgematica/build.gradle: Conditional Mixin API is not on compile classpath")

# Forge/Servux bridge contract.
bridge = MODULES["mafglib"] / "src/main/java/fi/dy/masa/malilib/network/ForgePayloadBridge.java"
if not bridge.is_file():
    fail("ForgePayloadBridge.java missing")
else:
    bridge_text = bridge.read_text(encoding="utf-8")
    for needle in ("ChannelBuilder", ".optional().payloadChannel()", ".play()", ".flow(", ".send("):
        if needle not in bridge_text:
            fail(f"ForgePayloadBridge.java missing expected Forge networking operation {needle}")

servux = MODULES["forgematica"] / "src/main/java/fi/dy/masa/litematica/network/ServuxLitematicaHandler.java"
if not servux.is_file():
    fail("ServuxLitematicaHandler.java missing")
else:
    servux_text = servux.read_text(encoding="utf-8")
    for method in ("tickFailures", "checkFailures", "receivePlayPayload", "encodeWithSplitter"):
        if not re.search(rf"\b{method}\s*\(", servux_text):
            fail(f"ServuxLitematicaHandler.java missing {method}()")

props = (ROOT / "gradle.properties").read_text(encoding="utf-8")
for needle in ("minecraft_version=26.2", "forge_version=65.1.0", "java_version=25"):
    if needle not in props:
        fail(f"gradle.properties missing {needle}")

print(
    f"Deep audit scanned {stats['java_files']} Java files / {stats['java_lines']} Java lines "
    f"and {stats['text_files']} total text files / {stats['text_lines']} total text lines."
)
print(
    f"Mixins checked: {stats['mixin_entries']}; "
    f"MixinExtras @Local captures: {stats['mixin_local_captures']}; "
    f"AT rules: mafglib={stats['at_mafglib']}, forgematica={stats['at_forgematica']}."
)
if warnings:
    for warning in warnings:
        print("WARN:", warning)
if errors:
    print(f"Deep audit FAILED with {len(errors)} issue(s):")
    for error in errors:
        print("ERROR:", error)
    sys.exit(2)
print("Deep audit PASSED.")
