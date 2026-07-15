#!/usr/bin/env python3
"""Local 100-device end-to-end smoke benchmark."""
import asyncio
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aiohttp import web
from enviro_simulator.daemon import SimulatorDaemon


async def main():
    counts = {"provisioned": 0, "readings": 0}

    async def provisioned(request):
        await request.read()
        counts["provisioned"] += 1
        return web.json_response({"ok": True}, status=201)

    async def readings(request):
        await request.read()
        counts["readings"] += 1
        return web.json_response({"ok": True}, status=201)

    app = web.Application()
    app.router.add_post("/api/provisioned", provisioned)
    app.router.add_post("/api/readings", readings)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    with tempfile.TemporaryDirectory(prefix="enviro-sim-smoke-") as directory:
        daemon = SimulatorDaemon(Path(directory) / "sim.db")
        await daemon.start()
        started = time.perf_counter()
        devices = []
        for index in range(100):
            devices.append(await daemon.create_device({
                "nickname": f"smoke-{index:03d}",
                "dashboard_url": f"http://127.0.0.1:{port}",
                "seed": index,
                "upload_frequency": 1,
                "time_scale": 60,
            }, deterministic=True))

        # Three synchronized fleet cycles exercise concurrent model updates,
        # durable queue writes and actual HTTP delivery.
        for _ in range(3):
            await asyncio.gather(*(daemon.generate_reading(device) for device in devices))
            devices = daemon.store.list_devices()

        elapsed = time.perf_counter() - started
        assert len(devices) == 100
        assert counts == {"provisioned": 100, "readings": 300}
        assert sum(item["queued"] for item in devices) == 0
        await daemon.close()

    await runner.cleanup()
    print(f"100 devices completed three persisted HTTP reading cycles in {elapsed:.2f}s")
    if elapsed > 15:
        raise SystemExit("smoke benchmark exceeded 15 seconds")


if __name__ == "__main__":
    asyncio.run(main())
