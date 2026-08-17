---
id: component:git
title: git
state: specified
confidence: verified
owner: vfeenstr
responsibility: Thin git reads — show a revision, compute a diff, read a sha
  — so every feature needing --rev or --diff-base goes through one wrapper
  instead of building its own subprocess.
implemented_by:
- absicht#src/absicht/git.py
---
