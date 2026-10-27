# SMS notifications: migration and local verification

## Migration history

The existing `f2c5d91a7e63_add_sms_notifications` revision follows
`e7b3f1a92c04`. It adds nullable `users.phone_number`, creates
`sms_queue`, and adds `SMS` to the existing `alerttype` enum. It does not
populate numbers or rewrite existing users.

The follow-up `c81a6b2d9e47_record_skipped_sms_recipients` revision follows
that SMS revision. It adds nullable recipient-account and skip-reason fields,
allows a NULL phone on skipped queue entries, adds the `SKIPPED` queue status,
and adds a partial unique index for one queue outcome per officer and alert.
Existing queue rows remain in place and have NULL in the new fields.

The code checkout cannot show whether either revision is already applied to
your local database. Check the live Alembic revision and inspect the schema
before running an upgrade. Never edit the first revision to repair an applied
migration; use a new revision instead.

## Tests

From PowerShell:

```powershell
Set-Location D:\forest-detection-system\backend
.\.venv\Scripts\python.exe -m pytest tests\test_user_phone_management.py tests\test_sms_recipients.py tests\test_sms_service.py tests\test_sms_worker.py -p no:cacheprovider --basetemp .pytest-tmp-sms-focused
.\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider --basetemp .pytest-tmp-sms-full

Set-Location D:\forest-detection-system\frontend
npm run build
```

The SMS tests replace the Africa's Talking client with local stubs. They do
not connect to PostgreSQL or submit SMS messages.

## Before changing the database

First try the configured read-only role for a custom-format backup. It must
have SELECT access to every table; if `pg_dump` reports a permission error,
ask your database administrator for an approved backup role and substitute
that role name. `pg_dump --password` prompts in the terminal; do not put a
password in a command, project file, or chat.

```powershell
Set-Location D:\forest-detection-system
pg_dump --host localhost --port 5432 --username forestwatch_reader --password --format=custom --file .\forest_detection_before_sms.dump forest_detection
pg_restore --list .\forest_detection_before_sms.dump
```

Record the current revision and user count before an upgrade. These are
read-only checks; the PostgreSQL password prompt is handled by `psql`.

```powershell
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT version_num FROM alembic_version;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT COUNT(*) AS users_before FROM users;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT to_regclass('public.sms_queue') AS sms_queue_table, EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='phone_number') AS users_phone_number_exists;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='sms_queue' AND column_name IN ('recipient_phone','recipient_user_id','skip_reason') ORDER BY column_name;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid WHERE t.typname IN ('alerttype','smsqueuestatus') ORDER BY t.typname, e.enumsortorder;"
```

If `sms_queue` or `users.phone_number` exists while Alembic reports a
revision before `f2c5d91a7e63`, stop and reconcile the schema and
`alembic_version` with a database administrator. Do not stamp or rerun a
revision based on the column check alone.

Also stop if Alembic reports f2c5d91a7e63 but recipient_user_id or
skip_reason already exists, or the SKIPPED label is already present. If
Alembic reports c81a6b2d9e47, the follow-up migration is already applied;
do not rerun it.

## Apply and verify the migration

Run the upgrade with the backend's configured migration-capable database
account. Do not use the read-only account. The command reads the backend's
local application settings and may request database credentials through the
configured local mechanism; keep them out of terminal arguments and logs.

```powershell
Set-Location D:\forest-detection-system\backend
.\.venv\Scripts\python.exe -m alembic history --verbose
.\.venv\Scripts\python.exe -m alembic current --verbose
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current --verbose
```

Verify the final revision, nullable phone field, queue status labels, and
unchanged user count using the supplied read-only role. `psql --password`
prompts rather than printing a password.

```powershell
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT version_num FROM alembic_version;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='phone_number';"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT to_regclass('public.sms_queue') AS sms_queue_table, column_name, is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='sms_queue' AND column_name IN ('recipient_phone','recipient_user_id','skip_reason') ORDER BY column_name;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT COUNT(*) AS users_after FROM users;"
psql --host localhost --port 5432 --username forestwatch_reader --password --dbname forest_detection --command "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.oid = t.oid WHERE t.typname IN ('alerttype','smsqueuestatus') ORDER BY t.typname, e.enumsortorder;"
```

The user count should match the recorded pre-upgrade count. The nullable
`phone_number` field should contain NULL for accounts whose numbers have not
been explicitly entered. Review the dump before removing it, and keep a copy
according to the project's backup policy.

## SMS activation

Keep the Africa's Talking API key in the backend's local environment or
secret store. Leave `SMS_ENABLED=false` while validating configuration and
queue records. Begin with the provider sandbox, verify the recipient and
status fields in `sms_queue`, and enable production only after confirming the
provider account, sender ID, priority threshold, and officer numbers.

`SUBMITTED` means Africa's Talking accepted the request. It does not mean the
message was delivered to the handset. Connection failures after submission
may have an unknown outcome; those are recorded and not automatically retried
because a retry could send a duplicate.
