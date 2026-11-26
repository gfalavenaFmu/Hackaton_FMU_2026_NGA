CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY,
    limit_seconds INTEGER NOT NULL CHECK (limit_seconds BETWEEN 60 AND 1800)
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_no INTEGER NOT NULL UNIQUE,
    station_id TEXT NOT NULL REFERENCES stations(id),
    arrival INTEGER NOT NULL,
    started INTEGER CHECK (started >= arrival),
    departed INTEGER CHECK (departed IS NULL OR (departed >= arrival AND started IS NULL)),
    request_id TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS visits_station_started ON visits(station_id, started, arrival);

CREATE TABLE IF NOT EXISTS demo_clock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    reset_at INTEGER NOT NULL,
    elapsed_seconds INTEGER NOT NULL DEFAULT 0 CHECK (elapsed_seconds >= 0)
);
