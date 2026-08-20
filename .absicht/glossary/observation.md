---
id: term:observation
title: Observation
state: specified
confidence: reviewed
owner: vfeenstr
definition: >-
  One expectation about how the system acts, anchored to its behavior: a
  statement, the element it is `at`, an outcome of `must`, `must_not` or
  `should`, and when it becomes true.
---

A negative observation is the reason the type exists. "No row appears in the
audit log" catches the double write, the leak and the side effect nobody
wanted, and it never survives being written as prose.
