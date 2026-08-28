# Test suite

Two layers:

- `unit/` — no Docker, no network. Pure logic: validators, redaction, retention
  arithmetic, tar safety. Runs in about a second.
- `integration/` — spins up real Docker containers, volumes and storage services
  (MinIO, SFTP) and exercises backup and restore end to end against them.

## Running

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt

pytest tests/unit                 # fast, no Docker needed
pytest tests/integration          # needs a working Docker daemon
pytest tests                      # everything
```

Integration tests are marked `@pytest.mark.integration` and skip automatically
when the Docker daemon is unreachable, so `pytest tests` is safe in an
environment without Docker.

These run the backend in-process against the host's Docker daemon, so they need
your user to be able to reach the socket (typically membership of the `docker`
group). They do not build or run the application container, and so are
unaffected by the `DOCKER_GID` build argument that a source build needs.

Useful selections:

```bash
pytest tests/integration -k localfs        # one backend
pytest tests/integration -k "backup_and_restore"
pytest tests/integration -m "not slow"     # skip the large-volume test
pytest tests -v --tb=short
```

## What the integration suite creates

Everything is namespaced with a per-run id and torn down afterwards, including
on failure:

- Docker volumes named `dvbmtest-<runid>-*`
- Containers named `dvbmtest-<runid>-*` (busybox workloads, MinIO, SFTP)
- A temporary directory holding the SQLite database, staging area and
  local-filesystem backup target

If a run is killed hard (SIGKILL) and leaves anything behind:

```bash
docker rm -f $(docker ps -aq --filter name=dvbmtest-) 2>/dev/null
docker volume rm $(docker volume ls -q --filter name=dvbmtest-) 2>/dev/null
```

## What is covered

`unit/` (60 tests, no Docker):

| Area | Checks |
|---|---|
| Schema validation | `min_backups` floor, `max_backups >= min_backups`, cron parsing, path-unsafe job names |
| Secret handling | redaction on read, placeholder merge-back on write, export redaction |
| rclone flags | tuning flags allowed, `--config` / `--log-file` / injection attempts rejected |
| localfs paths | confinement to the allowed roots |
| SSRF guard | metadata, loopback, RFC1918 and non-HTTP targets blocked |
| Auth | password comparison, rate limiter lockout and reset |
| Retention | the last backup is never deleted, floor vs max interaction, failed remote deletes keep their row |

`integration/` (32 tests, real Docker):

| File | Checks |
|---|---|
| `test_backup_restore.py` | Full backup -> wipe -> restore -> byte-compare round trip for **all four backends**; upload size verification; remote deletion; multi-volume and shared-volume handling; a 32 MB streaming case |
| `test_detection.py` | Only labelled containers are selected; custom label keys; already-stopped containers are backed up but not started; running containers are restarted; **containers are restarted when the upload fails**; clear errors for no-match and no-volumes; staging cleaned on both success and failure |
| `test_integrity.py` | Total export failure is not recorded as success; partial failure is `warning`; truncated uploads are caught; restore ignores volumes not on the record; path traversal and symlink escapes rejected; interrupted jobs recovered at startup |

The round-trip tests destroy the source volume between backup and restore, so
they cannot pass unless the archive genuinely contains the data.

### These tests were checked against the bugs they describe

Each of the significant integration tests was verified by reverting the
corresponding fix and confirming the test fails. Reverting the restore scoping
guard, the retention floor, the keep-row-on-failed-delete behaviour, or the
restart-in-`finally` each produces a failure in the matching test.

One caveat worth knowing: `test_restore_rejects_path_traversal_in_archive`
passes even without the `filter="data"` fix **when run on Python 3.14**, because
that version rejects escaping members by default. The shipped image uses Python
3.12, where it does not. `test_extraction_helper_rejects_escaping_members`
asserts the behaviour directly so the protection is covered on any interpreter.

## Requirements

| Backend | Needs |
|---|---|
| `localfs` | nothing |
| `s3` | MinIO image (`minio/minio`), pulled automatically |
| `ftp` (SFTP mode) | `atmoz/sftp` image, pulled automatically |
| `rclone` | an `rclone` binary on PATH; the suite writes its own config |

Backends whose prerequisites are missing are skipped individually rather than
failing the run.

## Notes for anyone extending this

**Workload containers must handle SIGTERM.** The helper in `harness.py` traps it
and exits immediately. A bare `sleep` ignores SIGTERM, so Docker waits out the
full 30-second stop timeout — which took one early version of this suite from
4 seconds to over two minutes.

**Names must be unique per test.** `env.run_id` combines the session id with a
per-test suffix, and job names (which become Docker label values) are derived
from it. Without that, a container left behind by an interrupted run can still
carry a matching label and silently join a later backup.

**Patch the handler registry, not the class.** `storage_service._HANDLERS`
captures function objects at import time, so `patch.object(StorageService,
"_localfs_size", ...)` has no effect on dispatch. See
`test_truncated_upload_is_caught_by_verification` for the working pattern.

**Foreign keys are enforced.** `PRAGMA foreign_keys=ON` means backup records
must be deleted before the jobs they reference; the `_cleanup_rows` fixture
handles the ordering.
