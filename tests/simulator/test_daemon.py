import asyncio
from aiohttp import web

from enviro_simulator.daemon import SimulatorDaemon


def test_provision_read_command_ack_and_restart(tmp_path):
    async def scenario():
        received = {"provisioned": [], "readings": [], "acks": []}
        routes = web.RouteTableDef()

        @routes.post("/api/provisioned")
        async def provisioned(request):
            received["provisioned"].append(await request.json())
            return web.json_response({"ok": True}, status=201)

        @routes.post("/api/readings")
        async def readings(request):
            payload = await request.json()
            received["readings"].append(payload)
            base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
            return web.json_response({
                "watering_command": {
                    "id": "command-1", "amounts": {"A": 10},
                    "ack_url": base + "/api/watering-commands/command-1/ack",
                }
            }, status=201)

        @routes.post("/api/watering-commands/{command}/ack")
        async def ack(request):
            received["acks"].append(await request.json())
            return web.json_response({"ok": True})

        app = web.Application(); app.add_routes(routes)
        runner = web.AppRunner(app); await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]

        db = tmp_path / "sim.db"
        daemon = SimulatorDaemon(db); await daemon.start()
        device = await daemon.create_device({
            "nickname": "integration-grow", "dashboard_url": f"http://127.0.0.1:{port}",
            "upload_frequency": 1, "pump_ml_per_second": 2,
        })
        before = device["state"]["values"]["moisture_a"]
        await daemon.generate_reading(device)
        after = daemon.store.get_device(device["uid"])["state"]["values"]["moisture_a"]

        assert received["provisioned"][0]["model"] == "grow"
        assert received["readings"][0]["capabilities"]["remote_watering"]["ready"] is True
        assert received["acks"][0]["result"]["status"] == "completed"
        assert after > before
        assert daemon.store.outbox_count(device["uid"]) == 0
        assert daemon.store.get_command("command-1")["acknowledged"] == 1
        await daemon.close()

        reopened = SimulatorDaemon(db)
        assert reopened.store.get_device(device["uid"])["state"]["values"]["moisture_a"] == after
        assert reopened.store.get_command("command-1")["acknowledged"] == 1
        reopened.store.close()
        await runner.cleanup()

    asyncio.run(scenario())


def test_offline_device_keeps_reading_in_outbox(tmp_path):
    async def scenario():
        daemon = SimulatorDaemon(tmp_path / "sim.db"); await daemon.start()
        device = await daemon.create_device({"nickname": "offline-grow", "dashboard_url": "http://127.0.0.1:9"})
        daemon.store.update_device(device["uid"], online=False)
        device = daemon.store.get_device(device["uid"])
        await daemon.generate_reading(device)
        assert daemon.store.outbox_count(device["uid"]) == 1
        await daemon.close()
    asyncio.run(scenario())
