#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
MODULES = (ROOT / "mafglib", ROOT / "forgematica")
RUNTIME_PREFIXES = ("net.minecraft.", "com.mojang.")


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

    for index in range(open_paren, len(text)):
        ch = text[index]

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
                return text[open_paren + 1:index]

    raise SystemExit(f"Unbalanced {token} annotation")


def imports_for(text: str) -> tuple[dict[str, str], list[str]]:
    exact: dict[str, str] = {}
    wildcards: list[str] = []

    for match in re.finditer(r"^\s*import\s+([\w.]+(?:\.\*)?)\s*;", text, flags=re.M):
        imported = match.group(1)
        if imported.endswith(".*"):
            wildcards.append(imported[:-2])
        else:
            exact[imported.rsplit(".", 1)[-1]] = imported

    return exact, wildcards


def package_for(text: str) -> str:
    match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, flags=re.M)
    return match.group(1) if match else ""


def is_runtime_target(name: str) -> bool:
    return name.startswith(RUNTIME_PREFIXES)


def resolve_class_expr(
    expr: str,
    exact_imports: dict[str, str],
    wildcard_imports: list[str],
    package: str,
) -> list[str]:
    expr = expr.strip()
    parts = expr.split(".")
    first = parts[0]

    imported = exact_imports.get(first)
    if imported is not None:
        return [imported + "".join("$" + part for part in parts[1:])]

    if first in {"net", "com", "org", "java", "fi", "team"}:
        return [expr]

    candidates = []
    for imported_package in wildcard_imports:
        candidate = imported_package + "." + expr.replace(".", "$")
        if is_runtime_target(candidate):
            candidates.append(candidate)

    if candidates:
        return candidates

    same_package = f"{package}.{expr.replace('.', '$')}" if package else expr
    return [same_package]


configured_mixins: list[tuple[str, str]] = []
source_by_fqcn: dict[str, Path] = {}

for module in MODULES:
    java_root = module / "src/main/java"

    for path in java_root.rglob("*.java"):
        source = path.read_text(encoding="utf-8")
        package = package_for(source)
        if package:
            source_by_fqcn[f"{package}.{path.stem}"] = path

    for config_path in (module / "src/main/resources").glob("mixins.*.json"):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        mixin_package = config.get("package", "")

        for section in ("mixins", "client", "server"):
            for short_name in config.get(section, []):
                configured_mixins.append(
                    (config_path.name, f"{mixin_package}.{short_name}")
                )


targets: set[str] = set()
failures: list[str] = []

for config_name, mixin_fqcn in configured_mixins:
    source_path = source_by_fqcn.get(mixin_fqcn)

    if source_path is None:
        failures.append(f"{config_name}: source missing for {mixin_fqcn}")
        continue

    source = source_path.read_text(encoding="utf-8")
    annotation = balanced_annotation(source, "@Mixin")

    if annotation is None:
        failures.append(f"{mixin_fqcn}: no @Mixin annotation")
        continue

    found: set[str] = set()

    targets_argument = re.search(
        r'\btargets\s*=\s*(\{.*?\}|".*?")',
        annotation,
        flags=re.S,
    )
    if targets_argument:
        found.update(re.findall(r'"([^"]+)"', targets_argument.group(1)))

    exact_imports, wildcard_imports = imports_for(source)
    package = package_for(source)

    class_exprs = re.findall(
        r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.class",
        annotation,
    )

    for expr in class_exprs:
        for resolved in resolve_class_expr(
            expr,
            exact_imports,
            wildcard_imports,
            package,
        ):
            if is_runtime_target(resolved):
                found.add(resolved)

    found = {target for target in found if is_runtime_target(target)}

    if not found:
        failures.append(
            f"{mixin_fqcn}: could not resolve a Minecraft/Mojang runtime target "
            f"from @Mixin({annotation.strip()})"
        )
        continue

    targets.update(found)


if failures:
    raise SystemExit("Mixin target generation failed:\n" + "\n".join(failures))

output = ROOT / "smoke/src/main/resources/mixin-targets.txt"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(sorted(targets)) + "\n", encoding="utf-8")

print(
    f"Generated {len(targets)} unique configured mixin targets "
    f"from {len(configured_mixins)} mixin entries."
)

if len(targets) < 60:
    raise SystemExit(f"Suspiciously low mixin target count: {len(targets)}")
