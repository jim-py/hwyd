# Feedback schema upgrade

The inspected local database already records `hwyd.0001_initial` as applied.
That migration source existed locally but was ignored by Git. The exception in
`.gitignore` now retains Python migrations for `hwyd` only. The existing baseline
is preserved unchanged; `0002_feedback` only creates the feedback table and its
nullable user relation. It does not alter or delete tracker data.

The local upgrade was applied with Django's migration command after creating a
consistent SQLite backup in the Windows temporary directory. UI verification
used a separate disposable database in memory, not real tracker records.

Run from the directory containing `manage.py`, using the existing environment:

```powershell
& ..\venv\Scripts\python.exe -B manage.py showmigrations hwyd
& ..\venv\Scripts\python.exe -B manage.py migrate hwyd --plan
& ..\venv\Scripts\python.exe -B manage.py migrate hwyd
```

Back up the selected database before deployment and confirm its path: project
settings select SQLite/MySQL based on the checkout directory. Fresh installs
apply both migrations normally. If legacy tracker tables exist without a
`0001_initial` record, verify columns, constraints and indexes against that
baseline before adopting only the initial migration with `--fake-initial`.
Never fake `0002_feedback`: its new table must be created.

Feedback is available to signed-in Habitus users, stores only category, message,
session user and creation time, and is visible in Django admin under
**Hwyd → Обратная связь**. The POST endpoint uses normal Django CSRF protection.
