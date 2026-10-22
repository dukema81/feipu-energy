# -*- coding: utf-8 -*-
"""从运行中的飞瀑实例抓真实数据，生成单文件离线 DEMO（双击即开、无需服务端）。"""
import json
import os
import sys
import urllib.request
import zipfile

BASE = "http://localhost:8931"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "demo")

TOK = ""


def login():
    global TOK
    body = json.dumps({"username": "admin", "password": "energy@2026"}).encode()
    req = urllib.request.Request(BASE + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        TOK = json.loads(r.read())["data"]["token"]
    print("login ok")


def get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", "Bearer " + TOK)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            js = json.loads(r.read().decode("utf-8"))
            return js.get("data") if isinstance(js, dict) and "code" in js else js
    except Exception as e:  # noqa: BLE001
        print("  !! %s -> %s" % (path, e))
        return {}


login()

P = "2026-10"
SNAP = {
    "board": get("/api/board?period=%s" % P),
    "energy": get("/api/energy-types"),
    "centers": get("/api/cost-centers"),
    "lines": get("/api/lines"),
    "meters": get("/api/meters?period=%s" % P),
    "readings": get("/api/readings?period=%s" % P),
    "tou": get("/api/tou-summary?period=%s" % P),
    "demands": get("/api/demands/summary?period=%s" % P),
    "consumption": get("/api/analysis/consumption?period=%s" % P),
    "intensity": get("/api/analysis/intensity?period=%s" % P),
    "yoy": get("/api/analysis/yoy?period=%s&months=12" % P),
    "balance": get("/api/reports/energy-balance?period=%s" % P),
    "carbon": get("/api/reports/carbon?period=%s" % P),
    "baselines": get("/api/baselines"),
    "efftests": get("/api/eff-tests"),
    "equipments": get("/api/equipments"),
    "projects": get("/api/projects"),
    "alarms": get("/api/alarms"),
    "alarmSummary": get("/api/alarms/summary"),
    "budgets": get("/api/budgets?period=%s" % P),
    "periods": {"list": [{"period": "%04d-%02d" % (2025 + i // 12, i % 12 + 11 if i < 2 else (i - 1) % 12 + 1)}
                         for i in range(14)]},
}

for k, v in SNAP.items():
    n = len(v.get("list", [])) if isinstance(v, dict) and isinstance(v.get("list"), list) \
        else ("dict" if isinstance(v, dict) else len(v))
    print("  %-13s %s" % (k, n))

os.makedirs(OUT, exist_ok=True)
data = json.dumps(SNAP, ensure_ascii=False, separators=(",", ":"))
tpl = open(os.path.join(ROOT, "tools", "demo_template.html"), encoding="utf-8").read()
html = tpl.replace("__DATA__", data)
out_html = os.path.join(OUT, "feipu-energy-demo.html")
open(out_html, "w", encoding="utf-8").write(html)
print("html: %.1f KB -> %s" % (len(html) / 1024, out_html))

out_zip = os.path.join(OUT, "feipu-energy-demo.zip")
with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(out_html, "feipu-energy-demo.html")
print("zip: %.1f KB" % (os.path.getsize(out_zip) / 1024))
