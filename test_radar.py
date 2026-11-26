from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase, main
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import DEMO_START, Handler, InputError, MissingVisit, Radar


class RadarTest(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        clock_patch = patch("app.time", return_value=DEMO_START)
        self.addCleanup(clock_patch.stop)
        self.clock = clock_patch.start()

    def test_migration_preserves_old_visits(self):
        with closing(sqlite3.connect(self.directory / "operacao.sqlite3")) as db, db:
            db.executescript("""
                CREATE TABLE visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_no INTEGER NOT NULL UNIQUE, station_id TEXT NOT NULL,
                    arrival INTEGER NOT NULL, started INTEGER, request_id TEXT UNIQUE
                );
                CREATE TABLE demo_clock (id INTEGER PRIMARY KEY, reset_at INTEGER NOT NULL);
            """)
            db.execute(
                "INSERT INTO visits(ticket_no, station_id, arrival, started) VALUES(1, 'buffet', ?, ?)",
                (DEMO_START - 90, DEMO_START),
            )
        buffet = Radar(self.directory, False).snapshot()["stations"][0]
        self.assertEqual((buffet["median"], buffet["completed"], buffet["departures"]), (90, 1, 0))

    def test_demo_clock_and_recording_sequence(self):
        demo = Radar(self.directory, True)
        initial = demo.snapshot()
        grill = initial["stations"][1]
        self.assertEqual((len(grill["queue"]), grill["over_limit"], grill["extra"]), (8, 5, 608))
        self.assertEqual(initial["potential_sale_cents"], 5779)
        self.clock.return_value += 350
        self.assertEqual(demo.snapshot()["clock"], "13:06:00")
        demo.advance_demo()
        self.assertEqual(Radar(self.directory, True).snapshot()["clock"], "13:07:00")
        with demo.connect(write=True) as db:
            demo.seed(db)
        self.assertEqual(demo.snapshot()["clock"], "13:06:00")
        with self.assertRaises(MissingVisit):
            demo.finish_wait(grill["queue"][0]["id"], "start")
        demo.arrival({"station": "churrasqueira", "request_id": "recording-test"})
        for item in demo.snapshot()["stations"][1]["queue"][:5]:
            demo.finish_wait(item["id"], "start")
        after = demo.snapshot()
        self.assertEqual(len(after["stations"][1]["queue"]), 4)
        self.assertFalse(any(station["over_limit"] for station in after["stations"]))

    def test_departure_is_idempotent_and_cannot_become_service(self):
        radar = Radar(self.directory, False)
        visit = radar.arrival({"station": "balanca", "request_id": "departure-test"})
        for _ in range(2):
            radar.finish_wait(visit["id"], "depart")
        with self.assertRaises(MissingVisit):
            radar.finish_wait(visit["id"], "start")
        scale = Radar(self.directory, False).snapshot()["stations"][2]
        self.assertEqual((scale["queue"], scale["departures"], scale["completed"]), ([], 1, 0))

    def test_simultaneous_actions_close_the_visit_once(self):
        radar = Radar(self.directory, False)
        visit = radar.arrival({"station": "balanca", "request_id": "concurrent-test"})

        def finish(action):
            try:
                radar.finish_wait(visit["id"], action)
            except MissingVisit:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(finish, ("start", "depart"))), 1)
        scale = radar.snapshot()["stations"][2]
        self.assertEqual(scale["departures"] + scale["completed"], 1)

    def test_arrival_validation_and_idempotency(self):
        radar = Radar(self.directory, False)
        for body in ({}, {"station": "cozinha", "request_id": "abcdefghijkl"},
                     {"station": "buffet", "request_id": "curto"}, {"station": 1, "request_id": "abcdefghijkl"}):
            with self.assertRaises(InputError):
                radar.arrival(body)
        first = radar.arrival({"station": "buffet", "request_id": "same-request-1"})
        self.assertEqual(radar.arrival({"station": "buffet", "request_id": "same-request-1"}), first)
        with self.assertRaises(InputError):
            radar.arrival({"station": "balanca", "request_id": "same-request-1"})
        self.assertEqual(len(radar.snapshot()["stations"][0]["queue"]), 1)

    def test_limits_validation(self):
        radar = Radar(self.directory, False)
        valid = {"buffet": 3, "churrasqueira": 5, "balanca": 2}
        for invalid in ({"buffet": 3}, {**valid, "buffet": 0}, {**valid, "buffet": 31}, {**valid, "buffet": 2.5}, {**valid, "buffet": True}):
            with self.assertRaises(InputError):
                radar.limits(invalid)
        radar.limits(valid)
        self.assertEqual([s["limit"] for s in radar.snapshot()["stations"]], [180, 300, 120])

    def test_completed_over_limit_and_csv_export(self):
        radar = Radar(self.directory, False)
        slow = radar.arrival({"station": "balanca", "request_id": "csv-slow-0001"})
        self.clock.return_value += 300
        radar.finish_wait(slow["id"], "start")
        radar.arrival({"station": "buffet", "request_id": "csv-open-0001"})
        scale = radar.snapshot()["stations"][2]
        self.assertEqual((scale["completed"], scale["completed_over_limit"], scale["median"]), (1, 1, 300))
        lines = radar.export_csv().decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0], "senha;estacao;chegada;inicio_atendimento;saida_da_fila;situacao;espera_segundos")
        self.assertIn("atendido;300", lines[1])
        self.assertIn("em_espera;0", lines[2])


class HttpTest(TestCase):
    def setUp(self):
        quiet = patch.object(Handler, "log_message")
        quiet.start()
        self.addCleanup(quiet.stop)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.radar = Radar(Path(temporary.name), True)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"

    def call(self, path, body=None, content_type="application/json"):
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, headers={"Content-Type": content_type})
        try:
            with urlopen(request) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    def test_pages_state_and_security_headers(self):
        for path in ("/", "/operacao", "/static/radar.js", "/static/radar.css"):
            status, headers, _ = self.call(path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, _, body = self.call("/api/state")
        self.assertEqual((status, json.loads(body)["clock"]), (200, "13:06:00"))
        self.assertEqual(self.call("/nada")[0], 404)
        self.assertEqual(json.loads(self.call("/api/health")[2]), {"ok": True, "demo": True})

    def test_api_errors_and_csv_download(self):
        self.assertEqual(self.call("/api/arrivals", {"station": "x"})[0], 400)
        self.assertEqual(self.call("/api/arrivals", {"station": "buffet"}, "text/plain")[0], 400)
        self.assertEqual(self.call("/api/visits/999999/start", {})[0], 409)
        self.assertEqual(self.call("/api/demo/advance", {})[0], 200)
        status, headers, body = self.call("/api/export.csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertTrue(body.startswith(b"\xef\xbb\xbfsenha;"))


if __name__ == "__main__":
    main()
