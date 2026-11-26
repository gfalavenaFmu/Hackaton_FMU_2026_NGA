import argparse
from contextlib import closing, contextmanager
import csv
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
from pathlib import Path
import re
import sqlite3
from statistics import median
from time import time


ROOT = Path(__file__).resolve().parent
SP_TIME = timezone(timedelta(hours=-3))
DEMO_START = int(datetime(2026, 11, 25, 13, 6, tzinfo=SP_TIME).timestamp())
WINDOW_SECONDS = 15 * 60
DEMO_STEP_SECONDS = 60
STATIONS = {
    "buffet": ("Buffet", 180, "Organizar a passagem e checar os balcões com maior concentração."),
    "churrasqueira": ("Churrasqueira", 240, "Deslocar apoio para o corte, se houver alguém disponível."),
    "balanca": ("Balança", 120, "Acionar apoio para a conferência dos cartões e liberar a pesagem."),
}


SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
}
log = logging.getLogger("radar")


class InputError(Exception):
    """Dados enviados pelo cliente são inválidos."""


class MissingVisit(Exception):
    """A senha não está mais disponível para a transição pedida."""


class Radar:
    def __init__(self, data_dir, demo):
        self.demo = demo
        data_dir.mkdir(parents=True, exist_ok=True)
        self.database = data_dir / ("demo.sqlite3" if demo else "operacao.sqlite3")
        self.scenario = json.loads((ROOT / "demo/scenario.json").read_text(encoding="utf-8"))

        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))

        with self.connect(write=True) as db:
            if "departed" not in {row["name"] for row in db.execute("PRAGMA table_info(visits)")}:
                db.execute("ALTER TABLE visits ADD COLUMN departed INTEGER CHECK (departed IS NULL OR (departed >= arrival AND started IS NULL))")
            if "elapsed_seconds" not in {row["name"] for row in db.execute("PRAGMA table_info(demo_clock)")}:
                db.execute("ALTER TABLE demo_clock ADD COLUMN elapsed_seconds INTEGER NOT NULL DEFAULT 0 CHECK (elapsed_seconds >= 0)")
                db.execute(
                    "UPDATE demo_clock SET elapsed_seconds = MAX(0, "
                    "COALESCE((SELECT MAX(COALESCE(started, arrival)) FROM visits), ?) - ?)",
                    (DEMO_START, DEMO_START),
                )
            self.restore_limits(db)
            if demo and not db.execute("SELECT 1 FROM demo_clock WHERE id = 1").fetchone():
                self.seed(db)

    @contextmanager
    def connect(self, write=False):
        with closing(sqlite3.connect(self.database, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                if write:
                    db.execute("BEGIN IMMEDIATE")
                yield db

    def restore_limits(self, db):
        db.executemany(
            "INSERT OR IGNORE INTO stations (id, limit_seconds) VALUES (?, ?)",
            [(key, spec[1]) for key, spec in STATIONS.items()],
        )

    def seed(self, db):
        db.execute("DELETE FROM visits")
        db.executemany(
            "UPDATE stations SET limit_seconds = ? WHERE id = ?",
            [(spec[1], key) for key, spec in STATIONS.items()],
        )
        simulated_volume = self.scenario["reference_clients_per_day"] / self.scenario["assumed_lunch_minutes"]
        ticket_no = 1
        for station, config in self.scenario["stations"].items():
            count = max(1, round(simulated_volume * 15 * config["sample_share"]))
            rows = []
            for index in range(count):
                started = DEMO_START - 850 + index * (810 // count)
                wait = config["base_wait"] + ((index * 31) % 67) - 20
                rows.append((station, started - wait, started))
            rows.extend((station, DEMO_START - wait, None) for wait in config["active_waits"])
            db.executemany(
                "INSERT INTO visits(ticket_no, station_id, arrival, started) VALUES (?, ?, ?, ?)",
                [(number, *row) for number, row in enumerate(rows, start=ticket_no)],
            )
            ticket_no += len(rows)

        db.execute("INSERT OR REPLACE INTO demo_clock (id, reset_at) VALUES (1, ?)", (int(time()),))

    def now(self, db):
        if self.demo:
            elapsed = db.execute("SELECT elapsed_seconds FROM demo_clock WHERE id = 1").fetchone()[0]
            return DEMO_START + elapsed
        return int(time())

    def advance_demo(self):
        with self.connect(write=True) as db:
            db.execute("UPDATE demo_clock SET elapsed_seconds = elapsed_seconds + ? WHERE id = 1", (DEMO_STEP_SECONDS,))

    def snapshot(self):
        with self.connect() as db:
            db.execute("BEGIN")
            now = self.now(db)
            limits = dict(db.execute("SELECT id, limit_seconds FROM stations").fetchall())
            active = {station: [] for station in STATIONS}
            completed = {station: [] for station in STATIONS}
            departures = dict(db.execute(
                "SELECT station_id, COUNT(*) FROM visits WHERE departed BETWEEN ? AND ? GROUP BY station_id",
                (now - WINDOW_SECONDS, now),
            ).fetchall())
            for row in db.execute("SELECT id, ticket_no, station_id, arrival FROM visits WHERE started IS NULL AND departed IS NULL ORDER BY arrival, id"):
                active[row["station_id"]].append({"id": row["id"], "ticket": row["ticket_no"], "wait": max(0, now - row["arrival"])})
            for row in db.execute("SELECT station_id, started - arrival AS wait FROM visits WHERE started BETWEEN ? AND ?", (now - WINDOW_SECONDS, now)):
                completed[row["station_id"]].append(row["wait"])

        stations = []
        for key, (name, _, action) in STATIONS.items():
            queue = active[key]
            limit = limits[key]
            oldest = queue[0]["wait"] if queue else None
            waits = completed[key]
            stations.append({
                "id": key, "name": name, "queue": queue, "limit": limit, "oldest": oldest,
                "median": round(median(waits)) if waits else None, "completed": len(waits),
                "completed_over_limit": sum(wait > limit for wait in waits),
                "departures": departures.get(key, 0),
                "over_limit": sum(visit["wait"] > limit for visit in queue),
                "extra": sum(max(0, visit["wait"] - limit) for visit in queue), "action": action,
            })
        price = self.scenario["price_per_kg_cents"]
        weight = self.scenario["reference_weight_grams"]
        return {
            "stations": stations, "clock": datetime.fromtimestamp(now, SP_TIME).strftime("%H:%M:%S"),
            "demo": self.demo, "price_cents": price, "weight_grams": weight,
            "potential_sale_cents": (price * weight + 500) // 1000,
            "reference_clients": self.scenario["reference_clients_per_day"],
        }

    def arrival(self, body):
        station = body.get("station")
        request_id = body.get("request_id")
        if not isinstance(station, str) or station not in STATIONS:
            raise InputError("Escolha uma estação válida.")
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{12,80}", request_id):
            raise InputError("Identificador de registro inválido.")
        with self.connect(write=True) as db:
            previous = db.execute("SELECT id, ticket_no, station_id FROM visits WHERE request_id = ?", (request_id,)).fetchone()
            if previous:
                if previous["station_id"] != station:
                    raise InputError("O identificador já foi usado em outra estação.")
                return {"id": previous["id"], "ticket": previous["ticket_no"]}
            ticket_no = db.execute("SELECT COALESCE(MAX(ticket_no), 0) + 1 FROM visits").fetchone()[0]
            visit = db.execute(
                "INSERT INTO visits(ticket_no, station_id, arrival, request_id) VALUES (?, ?, ?, ?)",
                (ticket_no, station, self.now(db), request_id),
            )
            return {"id": visit.lastrowid, "ticket": ticket_no}

    def finish_wait(self, visit_id, action):
        column, other = ("started", "departed") if action == "start" else ("departed", "started")
        with self.connect(write=True) as db:
            result = db.execute(
                f"UPDATE visits SET {column} = COALESCE({column}, MAX(arrival, ?)) WHERE id = ? AND {other} IS NULL",
                (self.now(db), visit_id),
            )
            if not result.rowcount:
                raise MissingVisit("A senha saiu da fila ou já começou o atendimento. Confira a lista atualizada.")

    def export_csv(self):
        """Exporta todos os registros em CSV (separador ';' e BOM, para abrir direto no Excel em pt-BR)."""
        with self.connect() as db:
            db.execute("BEGIN")
            now = self.now(db)
            rows = db.execute(
                "SELECT ticket_no, station_id, arrival, started, departed FROM visits ORDER BY arrival, id"
            ).fetchall()

        def stamp(value):
            return "" if value is None else datetime.fromtimestamp(value, SP_TIME).strftime("%Y-%m-%d %H:%M:%S")

        out = io.StringIO()
        writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
        writer.writerow(["senha", "estacao", "chegada", "inicio_atendimento", "saida_da_fila", "situacao", "espera_segundos"])
        for row in rows:
            if row["started"] is not None:
                situation, end = "atendido", row["started"]
            elif row["departed"] is not None:
                situation, end = "saiu_da_fila", row["departed"]
            else:
                situation, end = "em_espera", now
            writer.writerow([
                row["ticket_no"], STATIONS[row["station_id"]][0], stamp(row["arrival"]),
                stamp(row["started"]), stamp(row["departed"]), situation, max(0, end - row["arrival"]),
            ])
        return ("\ufeff" + out.getvalue()).encode("utf-8")

    def limits(self, body):
        if set(body) != set(STATIONS) or any(type(value) is not int or not 1 <= value <= 30 for value in body.values()):
            raise InputError("Informe um limite inteiro de 1 a 30 minutos por estação.")
        with self.connect(write=True) as db:
            db.executemany("UPDATE stations SET limit_seconds = ? WHERE id = ?", [(m * 60, k) for k, m in body.items()])


PAGES = {"/": "dashboard.html", "/operacao": "operation.html"}
STATIC = {"/static/radar.css": "text/css", "/static/radar.js": "text/javascript"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # O painel consulta o estado a cada 5 s; registrar cada consulta poluiria o terminal.
        if not self.path.startswith("/api/state"):
            super().log_message(format, *args)

    def send_data(self, code, content_type, data, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in {**SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code, result):
        self.send_data(code, "application/json", json.dumps(result, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in PAGES:
                self.send_data(200, "text/html", (ROOT / "templates" / PAGES[path]).read_bytes())
            elif path in STATIC:
                self.send_data(200, STATIC[path], (ROOT / path.lstrip("/")).read_bytes())
            elif path == "/api/state":
                self.send_json(200, self.server.radar.snapshot())
            elif path == "/api/export.csv":
                self.send_data(200, "text/csv", self.server.radar.export_csv(),
                               {"Content-Disposition": 'attachment; filename="radar-do-almoco.csv"'})
            elif path == "/api/health":
                self.send_json(200, {"ok": True, "demo": self.server.radar.demo})
            else:
                self.send_json(404, {"error": "Página indisponível."})
        except Exception:
            self.fail()

    def fail(self):
        log.exception("Erro ao processar %s %s", self.command, self.path)
        self.send_json(500, {"error": "Erro interno. Tente novamente em instantes."})

    def read_json(self):
        if self.headers.get_content_type() != "application/json":
            raise InputError("Envie os dados em JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeError) as error:
            raise InputError("Dados inválidos.") from error

    def do_POST(self):
        radar = self.server.radar
        path = self.path
        try:
            if path in {"/api/demo/reset", "/api/demo/advance"} and not radar.demo:
                self.send_json(404, {"error": "Recurso disponível no modo demonstração."})
                return
            body = self.read_json()
            if path == "/api/arrivals":
                self.send_json(200, radar.arrival(body))
                return
            visit = re.fullmatch(r"/api/visits/([1-9][0-9]{0,15})/(start|depart)", path)
            if visit:
                radar.finish_wait(int(visit[1]), visit[2])
            elif path == "/api/limits":
                radar.limits(body)
            elif path == "/api/demo/reset":
                with radar.connect(write=True) as db:
                    radar.seed(db)
            elif path == "/api/demo/advance":
                radar.advance_demo()
            else:
                self.send_json(404, {"error": "Recurso indisponível."})
                return
            self.send_json(200, {"ok": True})
        except InputError as error:
            self.send_json(400, {"error": str(error)})
        except MissingVisit as error:
            self.send_json(409, {"error": str(error)})
        except sqlite3.OperationalError:
            log.exception("Banco indisponível em %s", path)
            self.send_json(503, {"error": "Banco de dados ocupado. Tente novamente."})
        except Exception:
            self.fail()


def main():
    parser = argparse.ArgumentParser(description="Radar do Almoço da Bovinu’S Augusta")
    parser.add_argument("--demo", action="store_true", help="Usa o cenário simulado das 13h06")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "instance")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    radar = Radar(args.data_dir, args.demo)
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        server.radar = radar
        print(f"Radar do Almoço disponível em http://{args.host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
