#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
MODULES = (ROOT / "mafglib", ROOT / "forgematica")

def balanced_annotation(text: str, token: str) -> str | None:
    start = text.find(token)
    if start < 0:
        return None
    open_paren = text.find("(", start)
    if open_paren < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(open_paren, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if in_string and ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1:i]
    raise SystemExit("Unbalanced @Mixin annotation")

def imports_for(text: str) -> tuple[dict[str, str], list[str]]:
    imports: dict[str, str] = {}
    wildcards: list[str] = []
    for match in re.finditer(r"^\s*import\s+([\w.]+(?:\.\*)?);", text, flags=re.M):
        fqcn = match.group(1)
        if fqcn.endswith(".*"):
            wildcards.append(fqcn[:-2])
        else:
            imports[fqcn.rsplit(".", 1)[-1]] = fqcn
    return imports, wildcards

def package_for(text: str) -> str:
    match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, flags=re.M)
    return match.group(1) if match else ""

RUNTIME_PREFIXES = ("net.minecraft.", "com.mojang.blaze3d.")

def resolve_class_expr(expr: str, imports: dict[str, str], wildcards: list[str], package: str) -> list[str]:
    expr = expr.strip()
    if expr.endswith(".class"):
        expr = expr[:-6]
    parts = expr.split(".")
    first = parts[0]
    base = imports.get(first)

    if base is not None:
        resolved = base + "".join("$" + part for part in parts[1:])
        return [resolved]

    # Fully-qualified class expression.
    if first in ("net", "com", "org", "java", "fi", "team"):
        return [expr]

    # Wildcard imports can name multiple classes in the same Minecraft package.
    wildcard_candidates = [
        pkg + "." + expr.replace(".", "$")
        for pkg in wildcards
        if (pkg + ".").startswith(RUNTIME_PREFIXES)
    ]
    if wildcard_candidates:
        return wildcard_candidates

    # Same-package fallback.
    return [f"{package}.{expr.replace('.', '$')}" if package else expr]
configured = []
source_by_fqcn = {}
for module in MODULES:
    java_root = module / "src/main/java"
    for path in java_root.rglob("*.java"):
        text = path.read_text(encoding="utf-8")
        package = package_for(text)
        if package:
            source_by_fqcn[f"{package}.{path.stem}"] = path

    for cfg in (module / "src/main/resources").glob("mixins.*.json"):
        data = json.loads(cfg.read_text(encoding="utf-8"))
        pkg = data.get("package", "")
        for section in ("mixins", "client", "server"):
            for short in data.get(section, []):
                configured.append((cfg.name, f"{pkg}.{short}"))

targets: set[str] = set()
failures = []
for cfg_name, fqcn in configured:
    path = source_by_fqcn.get(fqcn)
    if path is None:
        failures.append(f"{cfg_name}: source missing for {fqcn}")
        continue
    text = path.read_text(encoding="utf-8")
    body = balanced_annotation(text, "@Mixin")
    if body is None:
        failures.append(f"{fqcn}: no @Mixin annotation")
        continue

    found: set[str] = set()

    # String targets = "a.b.C" or targets = {"a.b.C", "x.y.Z"}
    targets_match = re.search(r'\btargets\s*=\s*(\{.*?\}|".*?")', body, flags=re.S)
    if targets_match:
        found.update(re.findall(r'"([^"]+)"', targets_match.group(1)))

    # value = Foo.class / value = {Foo.class, Bar.class}, or shorthand @Mixin(Foo.class)
    imports, wildcards = imports_for(text)
    package = package_for(text)
    class_exprs = re.findall(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.class", body)
    for expr in class_exprs:
        for resolved in resolve_class_expr(expr, imports, wildcards, package):
            if resolved.startswith(RUNTIME_PREFIXES):
                found.add(resolved)

    found = {x for x in found if x.startswith(RUNTIME_PREFIXES)}
    if not found:
        failures.append(f"{fqcn}: could not resolve any Minecraft runtime target from @Mixin({body.strip()})")
        continue
    targets.update(found)

if failures:
    raise SystemExit("Mixin target generation failed:\n" + "\n".join(failures))

out = ROOT / "smoke/src/main/resources/mixin-targets.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(sorted(targets)) + "\n", encoding="utf-8")
print(f"Generated {len(targets)} unique configured mixin targets from {len(configured)} mixin entries.")
if len(targets) < 60:
    raise SystemExit(f"Suspiciously low mixin target count: {len(targets)}")
)}" if package else expr]

configured = []
source_by_fqcn = {}
for module in MODULES:
    java_root = module / "src/main/java"
    for path in java_root.rglob("*.java"):
        text = path.read_text(encoding="utf-8")
        package = package_for(text)
        if package:
            source_by_fqcn[f"{package}.{path.stem}"] = path

    for cfg in (module / "src/main/resources").glob("mixins.*.json"):
        data = json.loads(cfg.read_text(encoding="utf-8"))
        pkg = data.get("package", "")
        for section in ("mixins", "client", "server"):
            for short in data.get(section, []):
                configured.append((cfg.name, f"{pkg}.{short}"))

targets: set[str] = set()
failures = []
for cfg_name, fqcn in configured:
    path = source_by_fqcn.get(fqcn)
    if path is None:
        failures.append(f"{cfg_name}: source missing for {fqcn}")
        continue
    text = path.read_text(encoding="utf-8")
    body = balanced_annotation(text, "@Mixin")
    if body is None:
        failures.append(f"{fqcn}: no @Mixin annotation")
        continue

    found: set[str] = set()

    # String targets = "a.b.C" or targets = {"a.b.C", "x.y.Z"}
    targets_match = re.search(r'\btargets\s*=\s*(\{.*?\}|".*?")', body, flags=re.S)
    if targets_match:
        found.update(re.findall(r'"([^"]+)"', targets_match.group(1)))

    # value = Foo.class / value = {Foo.class, Bar.class}, or shorthand @Mixin(Foo.class)
    imports = imports_for(text)
    package = package_for(text)
    class_exprs = re.findall(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.class", body)
    for expr in class_exprs:
        resolved = resolve_class_expr(expr, imports, package)
        if resolved.startswith("net.minecraft."):
            found.add(resolved)

    found = {x for x in found if x.startswith("net.minecraft.")}
    if not found:
        failures.append(f"{fqcn}: could not resolve any net.minecraft target from @Mixin({body.strip()})")
        continue
    targets.update(found)

if failures:
    raise SystemExit("Mixin target generation failed:\n" + "\n".join(failures))

out = ROOT / "smoke/src/main/resources/mixin-targets.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(sorted(targets)) + "\n", encoding="utf-8")
print(f"Generated {len(targets)} unique configured mixin targets from {len(configured)} mixin entries.")
if len(targets) < 60:
    raise SystemExit(f"Suspiciously low mixin target count: {len(targets)}")
