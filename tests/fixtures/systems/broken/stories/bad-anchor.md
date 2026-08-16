---
id: story:bad-anchor
title: Criteria belong to their story
acceptance:
- id: story:other-story#ac-1
  when: the loader reads this story
  then:
  - it reports one error, not a crash
---
