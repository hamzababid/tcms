---
inclusion: fileMatch
fileMatchPattern: ["backend/migrations/**", "backend/src/tcms/**/models.py", "docs/schema/**"]
---
The SQL in docs/schema is the executable baseline; migrations must reproduce it and 99_verify.sql must pass.
#[[file:docs/05-Database-Design.md]]
#[[file:docs/schema/01_baseline.sql]]
