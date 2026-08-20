---
id: component:git
title: git
state: specified
confidence: verified
owner: vfeenstr
level: component
responsibility: Thin git reads — show a revision, compute a diff, read a sha
  — so every feature needing --rev or --diff-base goes through one wrapper
  instead of building its own subprocess.
parent: component:ab
implemented_by:
- absicht#src/absicht/git.py
relates:
- to: resource:git-repository
  type: depends_on
---
