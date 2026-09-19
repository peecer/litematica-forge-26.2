#!/usr/bin/env python3
"""Audit active Forge source for loader leftovers and required port artifacts."""
from pathlib import Path
import re, sys
ROOT=Path(__file__).resolve().parents[1]
PROJECTS=[ROOT/'mafglib',ROOT/'forgematica']
checks=[
 ('NeoForge import', re.compile(r'^\s*import\s+net\.neoforged\.'), 'Remove NeoForge API imports.'),
 ('Fabric API import', re.compile(r'^\s*import\s+net\.fabricmc\.fabric\.'), 'Remove Fabric API imports.'),
 ('Fabric Loader import', re.compile(r'^\s*import\s+net\.fabricmc\.loader\.'), 'Remove Fabric Loader imports.'),
 ('NeoForge metadata', re.compile(r'neoforge\.mods\.toml|dev\.architectury\.loom|net\.neoforged\.moddev'), 'Remove NeoForge/Loom build metadata.'),
 ('NeoForge PiP pool', re.compile(r'PictureInPictureRendererPool|PictureInPictureRendererRegistration'), 'Use Forge/vanilla PiP renderers.'),
 ('Old FML loader call', re.compile(r'FMLLoader\.getCurrent\('), 'Use Forge 26.2 FMLLoader APIs.'),
]
hits=[]
for project in PROJECTS:
 for p in project.rglob('*'):
  if not p.is_file() or p.suffix not in {'.java','.gradle','.toml','.json','.properties','.cfg'}: continue
  try: lines=p.read_text(encoding='utf-8').splitlines()
  except UnicodeDecodeError: continue
  rel=p.relative_to(ROOT)
  for n,line in enumerate(lines,1):
   st=line.strip()
   if st.startswith('//') or st.startswith('*'): continue
   for label,pat,note in checks:
    if pat.search(line): hits.append((label,rel,n,st,note))
required=[]
for project in PROJECTS:
 for rel in ['src/main/resources/META-INF/mods.toml','src/main/resources/META-INF/accesstransformer.cfg']:
  if not (project/rel).is_file(): required.append(f'{project.name}/{rel}')
java_counts={p.name:len(list((p/'src/main/java').rglob('*.java'))) for p in PROJECTS}
out=['# Forge 26.2 port audit','',f'Java source counts: `{java_counts}`.','']
if hits:
 out += ['## Blocking active loader leftovers','']
 for label,rel,n,line,note in hits:
  out.append(f'- **{label}** `{rel}:{n}` — `{line}` — {note}')
else:
 out += ['## Active loader namespace audit','', 'No active NeoForge/Fabric loader imports or NeoForge PiP APIs found.','']
if required:
 out += ['## Missing required Forge files','']+[f'- `{x}`' for x in required]+['']
out += ['## Manual review items','',
'- Forge 65.1.0 compilation requires Java 25.',
'- The Forge-native Servux payload bridge still requires a real client/server runtime test.',
'', f'Blocking hits: **{len(hits)+len(required)}**', '']
(ROOT/'PORT_AUDIT.md').write_text('\n'.join(out))
print(f"Port audit: {len(hits)+len(required)} blocking hits")
raise SystemExit(2 if hits or required else 0)
