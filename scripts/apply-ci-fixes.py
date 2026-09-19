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
mods = root / "forgematica/src/main/resources/META-INF/mods.toml"
text = mods.read_text(encoding="utf-8")
old = '''[[dependencies.forgematica]]
modId="mafglib"
mandatory=true
versionRange="[0.5.4,)"
ordering="BEFORE"
side="CLIENT"'''
new = '''[[dependencies.forgematica]]
modId="mafglib"
mandatory=true
versionRange="[0.5.4,)"
ordering="AFTER"
side="CLIENT"'''
if old not in text:
    raise SystemExit("Expected MaFgLib dependency block not found")
mods.write_text(text.replace(old, new), encoding="utf-8")

print("Applied Forge 26.2 post-overlay source fixes")
