---
name: Bug report
about: Incorrect parsing or unexpected result
title: "[bug] "
labels: bug
---

**Input phrase**
```
<the exact text you passed to parse()>
```

**`now` used** (reference time), and `language` / `TimeConfig` if non-default:
```python
parser.parse("...", now=datetime(2026, 2, 14, 14, 0))
```

**Actual result** (`type(r).__name__`, `r.to_dict()`):

**Expected result**:

**Version**: timesense 1.0.0, Python __
