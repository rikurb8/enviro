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
- `task check` — compile desktop Python code and run all tests.

Open `http://<your-computer-LAN-IP>:5001`. During provisioning, set **Provisioning call-home URL** to `http://<your-computer-LAN-IP>:5001/api/provisioned`.

To receive normal reading uploads, choose **A custom HTTP endpoint** and set its URL to `http://<your-computer-LAN-IP>:5001/api/readings`.

Events are kept in `server/data.json`, which is created on the first request.
