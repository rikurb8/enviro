# Local Enviro dashboard

The dashboard is managed by the repository's root uv project. From the
repository root, start it with:

```sh
task server
```

This command uses uv to install the server dependency group when needed and
starts the dashboard at `http://localhost:5001`. To install every desktop
dependency ahead of time, run `task setup`.

## Development helpers

Run `task help` to list the available helpers:

- `task setup` — sync all uv-managed desktop dependencies.
- `task test` — run the firmware testbench.
- `task server` — start this local dashboard.
- `task server:migrate` — apply pending database migrations (also run automatically on `task server` startup). Pass `-- status` to inspect which migrations are applied without changing anything, e.g. `task server:migrate -- status`.
- `task check` — compile desktop Python code and run all tests.

Open `http://<your-computer-LAN-IP>:5001`. During provisioning, set **Provisioning call-home URL** to `http://<your-computer-LAN-IP>:5001/api/provisioned`.

To receive normal reading uploads, choose **A custom HTTP endpoint** and set its URL to `http://<your-computer-LAN-IP>:5001/api/readings`.

Events are kept in a SQLite database at `server/data.db`. Each event stores
its raw JSON payload verbatim in a JSON column, so nothing is lost to the
schema. If a `server/data.json` from the old JSON store exists, its events are
imported into the database by the first migration; the file itself is left
untouched.

### Migrations

Schema changes live as ordered steps in `server/migrations.py`, tracked via
SQLite's `PRAGMA user_version`. `task server` applies any pending migrations
automatically before serving requests, so day to day you don't need to think
about this. Run migrations by hand with `task server:migrate`, or check what's
applied with `task server:migrate -- status`:

```
$ task server:migrate -- status
database: server/data.db
applied 1 of 1 migrations
  [x] 1: initial_schema
```

To add a migration: write a function in `server/migrations.py` that takes the
SQLAlchemy engine and makes the change (e.g. `ALTER TABLE ...` via
`engine.connect().exec_driver_sql(...)`), then append it to the `MIGRATIONS`
list. Never reorder or remove existing entries — each database records its
progress as an index into that list.
