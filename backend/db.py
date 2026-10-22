# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 数据层（sqlite3 WAL，21 表）"""
import os
import sqlite3
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FP_DB") or os.path.join(BASE_DIR, "feipu.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  phone TEXT DEFAULT '',
  status TEXT DEFAULT '启用',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tokens (
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  expire_at TEXT NOT NULL,
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  status TEXT DEFAULT '启用',
  created_at TEXT DEFAULT '',
  last_used TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS energy_types (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  tce_factor REAL DEFAULT 0,
  co2_factor REAL DEFAULT 0,
  scope TEXT DEFAULT '范围二',
  price REAL DEFAULT 0,
  price_mode TEXT DEFAULT '单一',
  status TEXT DEFAULT '启用',
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tariffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  energy_code TEXT NOT NULL,
  period TEXT NOT NULL,
  price REAL DEFAULT 0,
  month TEXT DEFAULT '全年'
);

CREATE TABLE IF NOT EXISTS cost_centers (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  ctype TEXT DEFAULT '生产',
  parent TEXT DEFAULT '',
  manager TEXT DEFAULT '',
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS lines (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  center TEXT DEFAULT '',
  product TEXT DEFAULT '',
  capacity REAL DEFAULT 0,
  unit TEXT DEFAULT '件',
  status TEXT DEFAULT '运行'
);

CREATE TABLE IF NOT EXISTS meters (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  energy_code TEXT NOT NULL,
  center TEXT DEFAULT '',
  line TEXT DEFAULT '',
  level INTEGER DEFAULT 2,
  ratio REAL DEFAULT 1,
  capacity REAL DEFAULT 0,
  gateway TEXT DEFAULT '人工抄表',
  install_date TEXT DEFAULT '',
  status TEXT DEFAULT '运行',
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  meter_code TEXT NOT NULL,
  period TEXT NOT NULL,
  date TEXT NOT NULL,
  reading REAL DEFAULT 0,
  usage REAL DEFAULT 0,
  is_estimate INTEGER DEFAULT 0,
  quality TEXT DEFAULT '正常',
  source TEXT DEFAULT '手工',
  operator TEXT DEFAULT '',
  created_at TEXT DEFAULT '',
  UNIQUE(meter_code, period)
);

CREATE TABLE IF NOT EXISTS intervals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  meter_code TEXT NOT NULL,
  date TEXT NOT NULL,
  period TEXT NOT NULL,
  kwh REAL DEFAULT 0,
  price REAL DEFAULT 0,
  UNIQUE(meter_code, date, period)
);

CREATE TABLE IF NOT EXISTS demands (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  center TEXT NOT NULL,
  date TEXT NOT NULL,
  ts TEXT NOT NULL,
  demand_kw REAL DEFAULT 0,
  capacity_kw REAL DEFAULT 0,
  over INTEGER DEFAULT 0,
  source TEXT DEFAULT '采集',
  UNIQUE(center, ts)
);

CREATE TABLE IF NOT EXISTS outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period TEXT NOT NULL,
  center TEXT DEFAULT '',
  line TEXT DEFAULT '',
  product TEXT DEFAULT '',
  qty REAL DEFAULT 0,
  unit TEXT DEFAULT '件',
  value_wan REAL DEFAULT 0,
  UNIQUE(period, line, center)
);

CREATE TABLE IF NOT EXISTS baselines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,
  line TEXT NOT NULL,
  product TEXT DEFAULT '',
  period_from TEXT NOT NULL,
  period_to TEXT NOT NULL,
  base_unit REAL DEFAULT 0,
  total_tce REAL DEFAULT 0,
  qty REAL DEFAULT 0,
  method TEXT DEFAULT '单位产品能耗',
  status TEXT DEFAULT '生效',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS equipments (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  etype TEXT NOT NULL,
  center TEXT DEFAULT '',
  rated_power REAL DEFAULT 0,
  rated_output REAL DEFAULT 0,
  spec TEXT DEFAULT '',
  status TEXT DEFAULT '运行',
  install_date TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS eff_tests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  equipment_code TEXT NOT NULL,
  date TEXT NOT NULL,
  input_power REAL DEFAULT 0,
  output_qty REAL DEFAULT 0,
  output_kw REAL DEFAULT 0,
  heat_in REAL DEFAULT 0,
  heat_out REAL DEFAULT 0,
  value REAL DEFAULT 0,
  metric TEXT DEFAULT '',
  grade TEXT DEFAULT '',
  tester TEXT DEFAULT '',
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projects (
  no TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  center TEXT DEFAULT '',
  line TEXT DEFAULT '',
  baseline_code TEXT DEFAULT '',
  invest REAL DEFAULT 0,
  measure TEXT DEFAULT '',
  start_period TEXT DEFAULT '',
  end_period TEXT DEFAULT '',
  verify_period TEXT DEFAULT '',
  owner TEXT DEFAULT '',
  status TEXT DEFAULT '待实施',
  remark TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS project_verify (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_no TEXT NOT NULL,
  period TEXT NOT NULL,
  base_unit REAL DEFAULT 0,
  report_unit REAL DEFAULT 0,
  qty REAL DEFAULT 0,
  saving_tce REAL DEFAULT 0,
  saving_rate REAL DEFAULT 0,
  saving_fee REAL DEFAULT 0,
  payback REAL DEFAULT 0,
  verdict TEXT DEFAULT '',
  remark TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alarms (
  no TEXT PRIMARY KEY,
  level TEXT NOT NULL,
  atype TEXT NOT NULL,
  target TEXT DEFAULT '',
  message TEXT DEFAULT '',
  value REAL DEFAULT 0,
  threshold REAL DEFAULT 0,
  period TEXT DEFAULT '',
  status TEXT DEFAULT '待处置',
  handled_by TEXT DEFAULT '',
  handled_at TEXT DEFAULT '',
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS budgets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period TEXT NOT NULL,
  center TEXT NOT NULL,
  energy_code TEXT NOT NULL,
  amount REAL DEFAULT 0,
  used REAL DEFAULT 0,
  UNIQUE(period, center, energy_code)
);

CREATE TABLE IF NOT EXISTS rules (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  remark TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT DEFAULT '',
  username TEXT DEFAULT '',
  action TEXT DEFAULT '',
  target TEXT DEFAULT '',
  detail TEXT DEFAULT '',
  ip TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS webhooks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  secret TEXT NOT NULL,
  events TEXT DEFAULT '',
  status TEXT DEFAULT '启用',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hook_id INTEGER DEFAULT 0,
  event TEXT DEFAULT '',
  url TEXT DEFAULT '',
  status TEXT DEFAULT '',
  code INTEGER DEFAULT 0,
  tries INTEGER DEFAULT 0,
  at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS idem_keys (
  key TEXT PRIMARY KEY,
  endpoint TEXT DEFAULT '',
  response TEXT DEFAULT '',
  created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sync_state (
  entity TEXT PRIMARY KEY,
  version INTEGER DEFAULT 0,
  updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_readings_meter ON readings(meter_code, period);
CREATE INDEX IF NOT EXISTS ix_readings_date ON readings(date);
CREATE INDEX IF NOT EXISTS ix_demands_center ON demands(center, ts);
CREATE INDEX IF NOT EXISTS ix_alarms_status ON alarms(status, level);
CREATE INDEX IF NOT EXISTS ix_intervals_meter ON intervals(meter_code, date);
CREATE INDEX IF NOT EXISTS ix_logs_at ON logs(at);
"""

_local = threading.local()


def connect():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def close_thread_conns():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        _local.conn = None


def init():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def rows(sql, args=()):
    cur = connect().execute(sql, args)
    return [dict(r) for r in cur.fetchall()]


def one(sql, args=()):
    cur = connect().execute(sql, args)
    r = cur.fetchone()
    return dict(r) if r else None


def val(sql, args=(), default=None):
    cur = connect().execute(sql, args)
    r = cur.fetchone()
    if r is None:
        return default
    v = r[0]
    return default if v is None else v


def run(sql, args=()):
    conn = connect()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def runmany(sql, seq):
    conn = connect()
    conn.executemany(sql, seq)
    conn.commit()


def bumpsync(entity):
    import datetime
    conn = connect()
    v = val("SELECT version FROM sync_state WHERE entity=?", (entity,), 0) or 0
    conn.execute("INSERT INTO sync_state(entity, version, updated_at) VALUES(?,?,?) "
                 "ON CONFLICT(entity) DO UPDATE SET version=version+1, updated_at=excluded.updated_at",
                 (entity, v + 1, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
