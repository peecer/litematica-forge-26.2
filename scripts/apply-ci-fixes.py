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

print("Applied Forge 26.2 post-overlay source fixes")
