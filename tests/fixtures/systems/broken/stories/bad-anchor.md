---
# A criterion anchored to another story. Story's own validator in models.py
# rejects this at parse time, so it is exercised at the load/codec layer
# and can never reach the check layer.
id: story:bad-anchor
title: Criteria belong to their story
acceptance:
- id: story:other-story#ac-1
  when: the loader reads this story
  then:
  - it reports one error, not a crash
---
