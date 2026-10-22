# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · HTTP 服务（69+ 路由，含对外集成接口）

启动：
    FP_PORT=8021 FP_PREFIX=/pu python3 server.py
"""
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db            # noqa: E402
import energy as E   # noqa: E402
import seed as seed_mod  # noqa: E402

PORT = int(os.environ.get("FP_PORT", "8021"))
PREFIX = os.environ.get("FP_PREFIX", "/pu")
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
BRAND = "飞瀑能源管理系统"
VERSION = "1.0.0"

_rl = {}
_rl_lock = threading.Lock()
RATE_LIMIT = 300


# ---------------- 工具 ----------------

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def h256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def new_token():
    return secrets.token_hex(32)


def ok(data=None, message="ok"):
    return {"code": 200, "message": message, "data": data}


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg = msg
        self.code = code


def bad(msg, code=400):
    raise ApiError(msg, code)


def log(u, action, target, detail="", ip=""):
    try:
        db.run("INSERT INTO logs(at,username,action,target,detail,ip) VALUES(?,?,?,?,?,?)",
               (now(), (u or {}).get("username", ""), action, target, str(detail)[:500], ip))
    except Exception:  # noqa: BLE001
        pass


def rate_ok(ip):
    t = int(time.time() // 60)
    with _rl_lock:
        k = (ip, t)
        _rl[k] = _rl.get(k, 0) + 1
        if len(_rl) > 5000:
            for kk in list(_rl)[:2500]:
                _rl.pop(kk, None)
        return _rl[k] <= RATE_LIMIT


# ---------------- 鉴权 ----------------

def auth(req, q):
    tok = ""
    h = req.headers.get("Authorization", "")
    if h.lower().startswith("bearer "):
        tok = h[7:].strip()
    if not tok:
        tok = req.headers.get("X-Fp-Token", "") or ""
    if not tok:
        ck = req.headers.get("Cookie", "")
        for part in ck.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "fp_token":
                tok = v
    if not tok:
        tok = (q.get("token") or [""])[0]

    if tok:
        r = db.one("SELECT * FROM tokens WHERE token=?", (tok,))
        if r and r["expire_at"] > now():
            u = db.one("SELECT * FROM users WHERE username=?", (r["username"],))
            if u and u["status"] == "启用":
                u["_token"] = tok
                u["perms"] = E.perms_of(u["role"])
                u["roleName"] = E.ROLES.get(u["role"], u["role"])
                return u

    key = req.headers.get("X-Fp-Key", "")
    if key:
        pre = key[:12]
        kh = h256(key)
        r = db.one("SELECT * FROM api_keys WHERE key_prefix=? AND status='启用'", (pre,))
        if r and hmac.compare_digest(r["key_hash"], kh):
            db.run("UPDATE api_keys SET last_used=? WHERE id=?", (now(), r["id"]))
            return {"username": "apikey:" + r["name"], "name": r["name"], "role": r["role"],
                    "_token": "", "perms": E.perms_of(r["role"]),
                    "roleName": E.ROLES.get(r["role"], r["role"])}
    return None


def require(u, perm):
    if u is None:
        bad("未认证或令牌已失效", 401)
    if not E.can(u["role"], perm):
        bad("权限不足（需要 %s）" % perm, 403)


# ---------------- webhook ----------------

EVENTS = ["reading.created", "reading.abnormal", "demand.over", "alarm.raised", "alarm.handled",
          "project.verified", "baseline.created", "eff.degraded", "meter.changed",
          "budget.warning", "sync.ready", "user.changed", "period.closed"]


def fire(event, data):
    hooks = db.rows("SELECT * FROM webhooks WHERE status='启用'")
    for hk in hooks:
        evs = (hk["events"] or "").split(",")
        if event not in evs and "*" not in evs:
            continue
        body = json.dumps({"event": event, "at": now(), "data": data}, ensure_ascii=False)
        ts = str(int(time.time()))
        sig = hmac.new(hk["secret"].encode(), (ts + "." + body).encode(), hashlib.sha256).hexdigest()
        threading.Thread(target=_deliver, args=(hk, event, body, ts, sig), daemon=True).start()


def _deliver(hk, event, body, ts, sig):
    tries = 0
    code = 0
    for i, delay in enumerate((0, 30, 60, 120)):
        if delay:
            time.sleep(delay)
        tries += 1
        try:
            r = urllib.request.Request(hk["url"], data=body.encode(), method="POST")
            r.add_header("Content-Type", "application/json")
            r.add_header("X-Fp-Event", event)
            r.add_header("X-Fp-Timestamp", ts)
            r.add_header("X-Fp-Signature", "sha256=" + sig)
            with urllib.request.urlopen(r, timeout=8) as resp:
                code = resp.status
            if 200 <= code < 300:
                break
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "code", 0) or 0
    try:
        db.run("INSERT INTO webhook_deliveries(hook_id,event,url,status,code,tries,at) "
               "VALUES(?,?,?,?,?,?,?)",
               (hk["id"], event, hk["url"], "成功" if 200 <= code < 300 else "失败", code, tries, now()))
    except Exception:  # noqa: BLE001
        pass


# ---------------- 基础查询辅助 ----------------

def rules():
    d = dict(E.DEFAULT_RULES)
    for r in db.rows("SELECT key,value FROM rules"):
        try:
            d[r["key"]] = float(r["value"])
        except (TypeError, ValueError):
            d[r["key"]] = r["value"]
    return d


def period_or_cur(q):
    p = (q.get("period") or [""])[0]
    return p or E.cur_period()


def energy_map():
    return {r["code"]: r for r in db.rows("SELECT * FROM energy_types")}


def meter_map():
    return {r["code"]: r for r in db.rows("SELECT * FROM meters")}


def consumption_rows(period=None, center=None, line=None, energy=None):
    """归集：计量点用量 × 介质折标煤系数。"""
    sql = ("SELECT r.meter_code, r.period, r.usage, r.is_estimate, r.quality, "
           "m.name AS meter_name, m.energy_code, m.center, m.line, m.level "
           "FROM readings r JOIN meters m ON m.code=r.meter_code WHERE 1=1")
    args = []
    if period:
        sql += " AND r.period=?"
        args.append(period)
    if center:
        sql += " AND m.center=?"
        args.append(center)
    if line:
        sql += " AND m.line=?"
        args.append(line)
    if energy:
        sql += " AND m.energy_code=?"
        args.append(energy)
    rs = db.rows(sql, tuple(args))
    em = energy_map()
    for r in rs:
        e = em.get(r["energy_code"], {})
        r["energy_name"] = e.get("name", r["energy_code"])
        r["unit"] = e.get("unit", "")
        r["tceFactor"] = e.get("tce_factor", 0)
        r["co2Factor"] = e.get("co2_factor", 0)
        r["scope"] = e.get("scope", "范围二")
        r["tce"] = E.q2(r["usage"] * (r["tceFactor"] or 0))
        r["co2"] = E.q4(r["usage"] * (r["co2Factor"] or 0))
        r["qty"] = r["usage"]   # co2_total / tce_total 统一按 qty 取物理量
    return rs


def by_center(period):
    rs = consumption_rows(period)
    agg = {}
    for r in rs:
        c = r["center"]
        a = agg.setdefault(c, {"center": c, "tce": 0.0, "co2": 0.0, "byEnergy": {}, "estimate": 0})
        a["tce"] += r["tce"]
        a["co2"] += r["co2"]
        a["estimate"] += 1 if r["is_estimate"] else 0
        e = a["byEnergy"].setdefault(r["energy_code"],
                                     {"energy": r["energy_code"], "name": r["energy_name"],
                                      "unit": r["unit"], "qty": 0.0, "tce": 0.0, "co2": 0.0})
        e["qty"] += r["usage"]
        e["tce"] += r["tce"]
        e["co2"] += r["co2"]
    names = {r["code"]: r["name"] for r in db.rows("SELECT code,name FROM cost_centers")}
    out = []
    for c, a in agg.items():
        a["tce"] = E.q2(a["tce"])
        a["co2"] = E.q4(a["co2"])
        a["centerName"] = names.get(c, c)
        for e in a["byEnergy"].values():
            e["qty"] = E.q2(e["qty"])
            e["tce"] = E.q2(e["tce"])
            e["co2"] = E.q4(e["co2"])
        a["byEnergy"] = list(a["byEnergy"].values())
        out.append(a)
    out.sort(key=lambda x: -x["tce"])
    return out


def by_energy(period):
    rs = consumption_rows(period)
    em = energy_map()
    agg = {}
    for r in rs:
        a = agg.setdefault(r["energy_code"], {"energy": r["energy_code"], "name": r["energy_name"],
                                              "unit": r["unit"], "qty": 0.0, "tce": 0.0, "co2": 0.0,
                                              "price": em.get(r["energy_code"], {}).get("price", 0)})
        a["qty"] += r["usage"]
        a["tce"] += r["tce"]
        a["co2"] += r["co2"]
    out = []
    for a in agg.values():
        a["qty"] = E.q2(a["qty"])
        a["tce"] = E.q2(a["tce"])
        a["co2"] = E.q4(a["co2"])
        a["fee"] = E.q2(a["qty"] * a["price"]) if a["energy"] != "ELEC" else None
        out.append(a)
    out.sort(key=lambda x: -x["tce"])
    return out


def period_tce(period):
    return E.q2(sum(r["tce"] for r in consumption_rows(period)))


def period_output(period, line=None):
    if line:
        r = db.one("SELECT SUM(qty) q, SUM(value_wan) v FROM outputs WHERE period=? AND line=?",
                   (period, line))
    else:
        r = db.one("SELECT SUM(qty) q, SUM(value_wan) v FROM outputs WHERE period=?", (period,))
    return (E.safe_num((r or {}).get("q")), E.safe_num((r or {}).get("v")))


def gen_alarm_no(period, prefix="AL"):
    """生成告警号：AL + 期间 + 4 位序号，取当前最大值 +1，避免与种子数据撞号。"""
    base = (period or E.cur_period()).replace("-", "")
    like = prefix + base + "%"
    cur = db.val("SELECT MAX(no) FROM alarms WHERE no LIKE ?", (like,), None)
    n = 0
    if cur:
        tail = str(cur)[len(prefix) + len(base):]
        n = E.q0(tail) if tail.isdigit() else 0
    while True:
        n += 1
        cand = "%s%s%04d" % (prefix, base, n)
        if not db.one("SELECT no FROM alarms WHERE no=?", (cand,)):
            return cand


def raise_alarm(level, atype, target, message, value=0, threshold=0, period=None, code=200):
    no = gen_alarm_no(period)
    db.run("INSERT INTO alarms(no,level,atype,target,message,value,threshold,period,status) "
           "VALUES(?,?,?,?,?,?,?,?,'待处置')",
           (no, level, atype, target, message, value, threshold, period or E.cur_period()))
    fire("alarm.raised", {"no": no, "level": level, "atype": atype, "target": target,
                          "message": message})
    # 统一返回对象：调用方既能取 no，也能取 level/message
    return {"no": no, "level": level, "atype": atype, "target": target,
            "message": message, "value": E.q2(value), "threshold": E.q2(threshold),
            "period": period or E.cur_period(), "status": "待处置"}


def gen_no(prefix, table, col, period=None):
    """生成业务编号：前缀 + 期间 + 4 位序号，自动跳过已占用号。"""
    base = (period or E.cur_period()).replace("-", "")
    like = prefix + base + "%"
    cur = db.val("SELECT MAX(%s) FROM %s WHERE %s LIKE ?" % (col, table, col), (like,), None)
    n = 0
    if cur:
        tail = str(cur)[len(prefix) + len(base):]
        n = E.q0(tail) if tail.isdigit() else 0
    while True:
        n += 1
        cand = "%s%s%04d" % (prefix, base, n)
        if not db.one("SELECT %s FROM %s WHERE %s=?" % (col, table, col), (cand,)):
            return cand


# =================================================================
# 接口实现
# =================================================================

def api_login(u, body, q):
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    r = db.one("SELECT * FROM users WHERE username=?", (username,))
    if not r or r["password_hash"] != h256("feipu$" + password):
        bad("用户名或口令错误", 401)
    if r["status"] != "启用":
        bad("账号已停用", 403)
    tok = new_token()
    exp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 7 * 86400))
    db.run("INSERT INTO tokens(token,username,expire_at,created_at) VALUES(?,?,?,?)",
           (tok, username, exp, now()))
    log({"username": username}, "login", username)
    return ok({"token": tok, "expireAt": exp,
               "user": {"username": r["username"], "name": r["name"], "role": r["role"],
                        "roleName": E.ROLES.get(r["role"], r["role"]),
                        "perms": E.perms_of(r["role"])}})


def api_logout(u, body, q):
    if u and u.get("_token"):
        db.run("DELETE FROM tokens WHERE token=?", (u["_token"],))
    return ok({"logout": True})


def api_me(u, body, q):
    if not u:
        bad("未认证或令牌已失效", 401)
    return ok({"username": u["username"], "name": u["name"], "role": u["role"],
               "roleName": u["roleName"], "perms": u["perms"], "events": EVENTS})


def api_change_pwd(u, body, q):
    if not u:
        bad("未认证", 401)
    old = (body or {}).get("oldPassword", "")
    new = (body or {}).get("newPassword", "")
    if len(new) < 6:
        bad("新口令至少 6 位")
    r = db.one("SELECT * FROM users WHERE username=?", (u["username"],))
    if r["password_hash"] != h256("feipu$" + old):
        bad("原口令不正确")
    db.run("UPDATE users SET password_hash=? WHERE username=?", (h256("feipu$" + new), u["username"]))
    db.run("DELETE FROM tokens WHERE username=?", (u["username"],))
    log(u, "change-password", u["username"])
    return ok({"changed": True})


def api_health(u, body, q):
    return ok({"brand": BRAND, "version": VERSION, "routes": len(ROUTES),
               "events": len(EVENTS),
               "meters": db.val("SELECT COUNT(*) FROM meters", (), 0),
               "readings": db.val("SELECT COUNT(*) FROM readings", (), 0),
               "time": now()})


# ---- 主数据 ----

def api_energy_types(u, body, q):
    require(u, "energy.read")
    rs = db.rows("SELECT * FROM energy_types ORDER BY code")
    for r in rs:
        r["tceFactor"] = r.pop("tce_factor")
        r["co2Factor"] = r.pop("co2_factor")
    return ok({"list": rs})


def api_energy_type_save(u, body, q, code=None):
    require(u, "energy.write")
    b = body or {}
    if code:
        db.run("UPDATE energy_types SET name=?,unit=?,tce_factor=?,co2_factor=?,scope=?,price=?,"
               "price_mode=?,status=? WHERE code=?",
               (b.get("name"), b.get("unit"), E.safe_num(b.get("tceFactor")),
                E.safe_num(b.get("co2Factor")), b.get("scope", "范围二"),
                E.safe_num(b.get("price")), b.get("priceMode", "单一"),
                b.get("status", "启用"), code))
        db.bumpsync("energy_types")
        log(u, "update", "energy_type:" + code)
        return ok({"code": code})
    code = b.get("code") or ""
    if not code:
        bad("code 必填")
    if db.one("SELECT code FROM energy_types WHERE code=?", (code,)):
        bad("介质编码已存在", 409)
    db.run("INSERT INTO energy_types(code,name,unit,tce_factor,co2_factor,scope,price,price_mode,status) "
           "VALUES(?,?,?,?,?,?,?,?,'启用')",
           (code, b.get("name", code), b.get("unit", ""), E.safe_num(b.get("tceFactor")),
            E.safe_num(b.get("co2Factor")), b.get("scope", "范围二"),
            E.safe_num(b.get("price")), b.get("priceMode", "单一")))
    db.bumpsync("energy_types")
    log(u, "create", "energy_type:" + code)
    return ok({"code": code})


def api_energy_type_del(u, body, q, code):
    require(u, "energy.write")
    if db.val("SELECT COUNT(*) FROM meters WHERE energy_code=?", (code,), 0):
        bad("该介质下仍有计量点，不可删除", 409)
    db.run("DELETE FROM energy_types WHERE code=?", (code,))
    db.bumpsync("energy_types")
    log(u, "delete", "energy_type:" + code)
    return ok({"deleted": code})


def api_tariffs(u, body, q):
    require(u, "energy.read")
    ec = (q.get("energy") or ["ELEC"])[0]
    return ok({"energy": ec, "list": db.rows("SELECT * FROM tariffs WHERE energy_code=? ORDER BY id", (ec,))})


def api_tariff_save(u, body, q):
    require(u, "energy.write")
    b = body or {}
    ec = b.get("energyCode", "ELEC")
    for it in b.get("items", []):
        db.run("INSERT INTO tariffs(energy_code,period,price,month) VALUES(?,?,?,?)",
               (ec, it.get("period"), E.safe_num(it.get("price")), it.get("month", "全年")))
    log(u, "create", "tariff:" + ec)
    return ok({"count": len(b.get("items", []))})


def api_centers(u, body, q):
    require(u, "center.read")
    rs = db.rows("SELECT * FROM cost_centers ORDER BY code")
    for r in rs:
        r["tce"] = period_tce_center(E.cur_period(), r["code"])
    return ok({"list": rs})


def period_tce_center(period, center):
    return E.q2(sum(r["tce"] for r in consumption_rows(period, center=center)))


def api_center_save(u, body, q, code=None):
    require(u, "center.write")
    b = body or {}
    if code:
        db.run("UPDATE cost_centers SET name=?,ctype=?,manager=?,remark=? WHERE code=?",
               (b.get("name"), b.get("ctype", "生产"), b.get("manager", ""), b.get("remark", ""), code))
        return ok({"code": code})
    code = b.get("code") or ""
    if not code:
        bad("code 必填")
    if db.one("SELECT code FROM cost_centers WHERE code=?", (code,)):
        bad("成本中心已存在", 409)
    db.run("INSERT INTO cost_centers(code,name,ctype,parent,manager,remark) VALUES(?,?,?,?,?,?)",
           (code, b.get("name", code), b.get("ctype", "生产"), b.get("parent", ""),
            b.get("manager", ""), b.get("remark", "")))
    db.bumpsync("cost_centers")
    return ok({"code": code})


def api_lines(u, body, q):
    require(u, "center.read")
    return ok({"list": db.rows("SELECT * FROM lines ORDER BY code")})


def api_line_save(u, body, q):
    require(u, "center.write")
    b = body or {}
    code = b.get("code") or ""
    if not code:
        bad("code 必填")
    if db.one("SELECT code FROM lines WHERE code=?", (code,)):
        db.run("UPDATE lines SET name=?,center=?,product=?,capacity=?,unit=?,status=? WHERE code=?",
               (b.get("name"), b.get("center", ""), b.get("product", ""),
                E.safe_num(b.get("capacity")), b.get("unit", "件"), b.get("status", "运行"), code))
    else:
        db.run("INSERT INTO lines(code,name,center,product,capacity,unit,status) VALUES(?,?,?,?,?,?,?)",
               (code, b.get("name", code), b.get("center", ""), b.get("product", ""),
                E.safe_num(b.get("capacity")), b.get("unit", "件"), b.get("status", "运行")))
    return ok({"code": code})


def api_meters(u, body, q):
    require(u, "meter.read")
    sql = ("SELECT m.*, e.name AS energyName, e.unit AS unit, c.name AS centerName "
           "FROM meters m LEFT JOIN energy_types e ON e.code=m.energy_code "
           "LEFT JOIN cost_centers c ON c.code=m.center WHERE 1=1")
    args = []
    if q.get("center"):
        sql += " AND m.center=?"
        args.append(q["center"][0])
    if q.get("energy"):
        sql += " AND m.energy_code=?"
        args.append(q["energy"][0])
    if q.get("level"):
        sql += " AND m.level=?"
        args.append(E.q0(q["level"][0]))
    sql += " ORDER BY m.level, m.code"
    rs = db.rows(sql, tuple(args))
    p = period_or_cur(q)
    last = {r["meter_code"]: r for r in db.rows("SELECT * FROM readings WHERE period=?", (p,))}
    for r in rs:
        rd = last.get(r["code"])
        r["lastUsage"] = rd["usage"] if rd else None
        r["lastQuality"] = rd["quality"] if rd else None
        r["tce"] = E.q2((rd["usage"] if rd else 0) * 0)  # placeholder, filled below
        e = db.one("SELECT tce_factor FROM energy_types WHERE code=?", (r["energy_code"],))
        r["tce"] = E.q2((rd["usage"] if rd else 0) * ((e or {}).get("tce_factor") or 0))
    return ok({"list": rs, "period": p})


def api_meter_save(u, body, q, code=None):
    require(u, "meter.write")
    b = body or {}
    if code:
        db.run("UPDATE meters SET name=?,center=?,line=?,ratio=?,capacity=?,gateway=?,status=?,"
               "remark=? WHERE code=?",
               (b.get("name"), b.get("center", ""), b.get("line", ""),
                E.safe_num(b.get("ratio"), 1), E.safe_num(b.get("capacity")),
                b.get("gateway", "人工抄表"), b.get("status", "运行"), b.get("remark", ""), code))
        db.bumpsync("meters")
        fire("meter.changed", {"code": code, "action": "update"})
        log(u, "update", "meter:" + code)
        return ok({"code": code})
    code = b.get("code") or ""
    if not code:
        bad("code 必填")
    if db.one("SELECT code FROM meters WHERE code=?", (code,)):
        bad("计量点已存在", 409)
    if not db.one("SELECT code FROM energy_types WHERE code=?", (b.get("energyCode"),)):
        bad("能源介质不存在")
    db.run("INSERT INTO meters(code,name,energy_code,center,line,level,ratio,capacity,gateway,"
           "install_date,status,remark) VALUES(?,?,?,?,?,?,?,?,?,?,'运行',?)",
           (code, b.get("name", code), b.get("energyCode"), b.get("center", ""), b.get("line", ""),
            E.q0(b.get("level", 2)), E.safe_num(b.get("ratio"), 1), E.safe_num(b.get("capacity")),
            b.get("gateway", "人工抄表"), b.get("installDate", ""), b.get("remark", "")))
    db.bumpsync("meters")
    fire("meter.changed", {"code": code, "action": "create"})
    log(u, "create", "meter:" + code)
    return ok({"code": code})


def api_equipments(u, body, q):
    require(u, "equip.read")
    rs = db.rows("SELECT * FROM equipments ORDER BY code")
    for r in rs:
        t = db.one("SELECT * FROM eff_tests WHERE equipment_code=? ORDER BY date DESC LIMIT 1", (r["code"],))
        r["lastValue"] = t["value"] if t else None
        r["lastGrade"] = t["grade"] if t else None
        r["lastAt"] = t["date"] if t else None
        r["metric"] = t["metric"] if t else E.EFF_SPEC.get(r["etype"], {}).get("metric", "")
    return ok({"list": rs, "spec": E.EFF_SPEC})


def api_equipment_save(u, body, q):
    require(u, "equip.write")
    b = body or {}
    code = b.get("code") or ""
    if not code:
        bad("code 必填")
    if db.one("SELECT code FROM equipments WHERE code=?", (code,)):
        db.run("UPDATE equipments SET name=?,etype=?,center=?,rated_power=?,rated_output=?,spec=?,"
               "status=? WHERE code=?",
               (b.get("name"), b.get("etype"), b.get("center", ""),
                E.safe_num(b.get("ratedPower")), E.safe_num(b.get("ratedOutput")),
                b.get("spec", ""), b.get("status", "运行"), code))
    else:
        if b.get("etype") not in E.EFF_SPEC:
            bad("设备类型必须是 " + "/".join(E.EFF_SPEC.keys()))
        db.run("INSERT INTO equipments(code,name,etype,center,rated_power,rated_output,spec,status,"
               "install_date) VALUES(?,?,?,?,?,?,?,'运行',?)",
               (code, b.get("name", code), b.get("etype"), b.get("center", ""),
                E.safe_num(b.get("ratedPower")), E.safe_num(b.get("ratedOutput")),
                b.get("spec", ""), b.get("installDate", "")))
    log(u, "save", "equipment:" + code)
    return ok({"code": code})


# ---- 抄表 ----

def api_readings(u, body, q):
    require(u, "read.read")
    sql = ("SELECT r.*, m.name AS meterName, m.energy_code AS energy, e.name AS energyName, "
           "e.unit AS unit, m.center, m.center AS centerCode, c.name AS centerName "
           "FROM readings r LEFT JOIN meters m ON m.code=r.meter_code "
           "LEFT JOIN energy_types e ON e.code=m.energy_code "
           "LEFT JOIN cost_centers c ON c.code=m.center WHERE 1=1")
    args = []
    for k, col in (("meter", "r.meter_code"), ("period", "r.period"),
                   ("from", "r.date >= ?" ), ("to", "r.date <= ?")):
        v = (q.get(k) or [""])[0]
        if v:
            if k in ("from", "to"):
                sql += " AND r." + ("date >= ?" if k == "from" else "date <= ?")
            else:
                sql += " AND " + col + "=?"
            args.append(v)
    if q.get("center"):
        sql += " AND m.center=?"
        args.append(q["center"][0])
    sql += " ORDER BY r.period DESC, r.meter_code LIMIT 2000"
    rs = db.rows(sql, tuple(args))
    for r in rs:
        r["isEstimate"] = bool(r["is_estimate"])
    return ok({"list": rs, "count": len(rs)})


def _do_reading(u, meter_code, period, date, reading, is_est=False, source="手工", quality=None):
    m = db.one("SELECT * FROM meters WHERE code=?", (meter_code,))
    if not m:
        bad("计量点 %s 不存在" % meter_code, 404)
    if m["status"] != "运行":
        bad("计量点 %s 已停用" % meter_code, 409)
    if db.one("SELECT id FROM readings WHERE meter_code=? AND period=?", (meter_code, period)):
        bad("计量点 %s 在 %s 已有抄表记录（区间重叠）" % (meter_code, period), 409)
    prev = db.one("SELECT * FROM readings WHERE meter_code=? ORDER BY period DESC LIMIT 1", (meter_code,))
    last_reading = prev["reading"] if prev else E.safe_num(reading)
    last_usage = prev["usage"] if prev else None
    r = E.reading_usage(last_reading, E.safe_num(reading), m["ratio"])
    if r["reverse"]:
        bad("表底倒走：本期读数 %s 小于上期 %s" % (reading, last_reading), 409)
    chk = E.reading_check(last_usage, r["usage"]) if last_usage is not None else {"jump": False, "level": None}
    q2str = quality or ("跳变" if chk["jump"] else ("估算" if is_est else "正常"))
    db.run("INSERT INTO readings(meter_code,period,date,reading,usage,is_estimate,quality,source,"
           "operator,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
           (meter_code, period, date, E.safe_num(reading), r["usage"], 1 if is_est else 0,
            q2str, source, (u or {}).get("username", ""), now()))
    db.bumpsync("readings")
    fire("reading.created", {"meter": meter_code, "period": period, "usage": r["usage"],
                             "quality": q2str})
    alarm = None
    if chk["jump"]:
        alarm = raise_alarm("警告", "抄表异常", meter_code,
                            "计量点 %s 用量 %.2f 环比上期 %.2f 变化 %.1f 倍，疑似跳变" % (
                                meter_code, r["usage"], last_usage, chk["factor"]),
                            r["usage"], last_usage, period)
        fire("reading.abnormal", {"meter": meter_code, "period": period,
                                  "factor": chk["factor"], "alarm": alarm})
    return {"meter": meter_code, "period": period, "usage": r["usage"],
            "quality": q2str, "jump": chk["jump"], "alarm": alarm}


def api_reading_create(u, body, q):
    require(u, "read.write")
    b = body or {}
    if not b.get("meter"):
        bad("meter 必填")
    period = b.get("period") or E.cur_period()
    date = b.get("date") or (period + "-28")
    return ok(_do_reading(u, b["meter"], period, date, b.get("reading"),
                          bool(b.get("isEstimate")), b.get("source", "手工")))


def api_reading_batch(u, body, q):
    require(u, "read.write")
    b = body or {}
    period = b.get("period") or E.cur_period()
    date = b.get("date") or (period + "-28")
    items = b.get("items") or []
    if not items:
        bad("items 不能为空")
    results = []
    okn = failn = 0
    for it in items:
        try:
            r = _do_reading(u, it.get("meter"), period, date, it.get("reading"),
                            bool(it.get("isEstimate")), b.get("source", "批量"))
            results.append({"meter": it.get("meter"), "ok": True, "usage": r["usage"]})
            okn += 1
        except ApiError as e:
            results.append({"meter": it.get("meter"), "ok": False, "error": e.msg})
            failn += 1
    log(u, "batch-read", period, "成功 %d 失败 %d" % (okn, failn))
    return ok({"period": period, "success": okn, "failed": failn, "items": results})


def api_reading_report(u, body, q):
    """采集网关上报：自动按 ts 推导期间与日期。"""
    require(u, "read.write")
    b = body or {}
    meter = b.get("meter")
    ts = b.get("ts") or now()
    if not meter:
        bad("meter 必填")
    if b.get("value") is None:
        bad("value 必填")
    period = (b.get("period") or ts[:7])
    date = (b.get("date") or ts[:10])
    quality = b.get("quality")
    r = _do_reading(u, meter, period, date, b.get("value"), False, "网关",
                    quality if quality in ("正常", "跳变", "估算") else None)
    return ok(r)


def api_reading_check(u, body, q):
    require(u, "read.check")
    p = period_or_cur(q)
    meters = db.rows("SELECT * FROM meters WHERE status='运行'")
    got = {r["meter_code"]: r for r in db.rows("SELECT * FROM readings WHERE period=?", (p,))}
    missing, est, jump, reverse = [], [], [], []
    for m in meters:
        r = got.get(m["code"])
        if not r:
            missing.append({"meter": m["code"], "name": m["name"], "center": m["center"]})
            continue
        if r["is_estimate"]:
            est.append({"meter": m["code"], "name": m["name"], "usage": r["usage"]})
        if r["quality"] == "跳变":
            jump.append({"meter": m["code"], "name": m["name"], "usage": r["usage"]})
        prev = db.one("SELECT usage FROM readings WHERE meter_code=? AND period<? "
                      "ORDER BY period DESC LIMIT 1", (m["code"], p))
        if prev and r["usage"] < prev["usage"] and prev["usage"] > 0:
            reverse.append({"meter": m["code"], "name": m["name"],
                            "usage": r["usage"], "prev": prev["usage"]})
    return ok({"period": p, "metersTotal": len(meters), "metersReported": len(got),
               "coverage": E.coverage(len(meters), len(got)),
               "missing": missing, "estimate": est, "jump": jump, "reverse": reverse,
               "qualityScore": E.q4(E.coverage(len(meters), len(got)) * 100)})


# ---- 分时 / 需量 ----

def api_intervals(u, body, q):
    require(u, "energy.read")
    sql = "SELECT * FROM intervals WHERE 1=1"
    args = []
    if q.get("meter"):
        sql += " AND meter_code=?"
        args.append(q["meter"][0])
    if q.get("date"):
        sql += " AND date=?"
        args.append(q["date"][0])
    if q.get("from"):
        sql += " AND date>=?"
        args.append(q["from"][0])
    if q.get("to"):
        sql += " AND date<=?"
        args.append(q["to"][0])
    sql += " ORDER BY date DESC, id LIMIT 2000"
    rs = db.rows(sql, tuple(args))
    return ok({"list": rs, "count": len(rs)})


def api_interval_save(u, body, q):
    require(u, "energy.write")
    b = body or {}
    if not b.get("meter") or not b.get("date") or not b.get("period"):
        bad("meter / date / period 必填")
    db.run("INSERT INTO intervals(meter_code,date,period,kwh,price) VALUES(?,?,?,?,?) "
           "ON CONFLICT(meter_code,date,period) DO UPDATE SET kwh=excluded.kwh, price=excluded.price",
           (b["meter"], b["date"], b["period"], E.safe_num(b.get("kwh")), E.safe_num(b.get("price"))))
    return ok({"saved": True})


def api_tou_summary(u, body, q):
    require(u, "energy.read")
    meter = (q.get("meter") or ["EM000"])[0]
    frm = (q.get("from") or ["2026-09-23"])[0]
    to = (q.get("to") or ["2026-10-22"])[0]
    rs = db.rows("SELECT * FROM intervals WHERE meter_code=? AND date>=? AND date<=?",
                 (meter, frm, to))
    tariff = {r["period"]: r["price"] for r in db.rows(
        "SELECT * FROM tariffs WHERE energy_code='ELEC' AND month='全年'")}
    res = E.tou_fee(rs, tariff)
    byday = {}
    for r in rs:
        d = byday.setdefault(r["date"], {"date": r["date"], "kwh": 0.0, "fee": 0.0})
        d["kwh"] += r["kwh"]
        d["fee"] += r["kwh"] * r["price"]
    days = sorted(byday.values(), key=lambda x: x["date"])
    for d in days:
        d["kwh"] = E.q2(d["kwh"])
        d["fee"] = E.q2(d["fee"])
    return ok({"meter": meter, "from": frm, "to": to, "summary": res,
               "tariff": {k: E.q2(v) for k, v in tariff.items()}, "daily": days})


def api_demands(u, body, q):
    require(u, "energy.read")
    sql = "SELECT * FROM demands WHERE 1=1"
    args = []
    if q.get("center"):
        sql += " AND center=?"
        args.append(q["center"][0])
    if q.get("period"):
        sql += " AND date LIKE ?"
        args.append(q["period"][0] + "%")
    sql += " ORDER BY ts DESC LIMIT 2000"
    rs = db.rows(sql, tuple(args))
    for r in rs:
        r["demandKw"] = r["demand_kw"]
        r["capacityKw"] = r["capacity_kw"]
        st = E.demand_status(r["demand_kw"], r["capacity_kw"])
        r["rate"] = st["rate"]
        r["status"] = st["status"]
    return ok({"list": rs, "count": len(rs)})


def api_demand_create(u, body, q):
    require(u, "energy.write")
    b = body or {}
    center = b.get("center") or "CC201"
    ts = b.get("ts") or now()
    kw = E.safe_num(b.get("demandKw") or b.get("demand_kw"))
    cap = E.safe_num(b.get("capacityKw"))
    if not cap:
        m = db.one("SELECT MAX(capacity) c FROM meters WHERE center=?", (center,))
        cap = E.safe_num((m or {}).get("c"))
    over = 1 if kw > cap else 0
    db.run("INSERT INTO demands(center,date,ts,demand_kw,capacity_kw,over,source) "
           "VALUES(?,?,?,?,?,?,'上报') ON CONFLICT(center,ts) DO UPDATE SET demand_kw=excluded.demand_kw",
           (center, ts[:10], ts, kw, cap, over))
    db.bumpsync("demands")
    st = E.demand_status(kw, cap, warn=rules()["demand_warn_ratio"],
                         urgent=rules()["demand_urgent_ratio"])
    alarm = None
    warn = rules()["demand_warn_ratio"]
    if st["status"] in ("紧急", "超容", "预警"):
        lv = "紧急" if st["status"] in ("紧急", "超容") else "严重"
        alarm = raise_alarm(lv, "需量超限", center,
                            "需量 %.1f kW 达容量 %.0f kW 的 %.0f%%（%s）" % (kw, cap, st["rate"] * 100, st["status"]),
                            kw, cap, ts[:7])
        fire("demand.over", {"center": center, "demandKw": kw, "capacityKw": cap,
                             "status": st["status"], "alarm": alarm})
    return ok({"center": center, "ts": ts, "demandKw": E.q2(kw), "capacityKw": E.q2(cap),
               "status": st["status"], "rate": st["rate"], "alarm": alarm,
               "warnRatio": warn})


def api_demand_summary(u, body, q):
    require(u, "energy.read")
    p = period_or_cur(q)
    rs = db.rows("SELECT * FROM demands WHERE date LIKE ?", (p + "%",))
    mx = E.max_demand([{"demandKw": r["demand_kw"], "ts": r["ts"]} for r in rs])
    cap = db.val("SELECT MAX(capacity_kw) FROM demands WHERE date LIKE ?", (p + "%",), 0) or 0
    rl = rules()
    cf = E.capacity_fee(mx["demandKw"], rl["demand_price"])
    over_cnt = sum(1 for r in rs if r["over"])
    hours = {}
    for r in rs:
        h = r["ts"][11:13]
        hours[h] = max(hours.get(h, 0), r["demand_kw"])
    curve = [{"hour": h, "demandKw": E.q2(v)} for h, v in sorted(hours.items())]
    return ok({"period": p, "maxDemand": mx, "capacityKw": E.q2(cap),
               "capacityFee": cf, "overCount": over_cnt, "records": len(rs),
               "curve": curve,
               "status": E.demand_status(mx["demandKw"], cap)})


# ---- 分析与报表 ----

def api_board(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    pp = E.prev_period(p)
    tce = period_tce(p)
    tce_prev = period_tce(pp)
    qty, val = period_output(p)
    rs = consumption_rows(p)
    co2 = E.co2_total(rs)
    em = by_energy(p)
    elec = next((e for e in em if e["energy"] == "ELEC"), {"qty": 0, "tce": 0})
    inten = E.intensity_pack(tce, qty, val)
    alarms = db.rows("SELECT * FROM alarms WHERE status='待处置'")
    alarm_sum = E.alarm_summary(alarms)
    mx = db.one("SELECT MAX(demand_kw) d, MAX(capacity_kw) c FROM demands WHERE date LIKE ?", (p + "%",))
    bls = db.rows("SELECT * FROM baselines WHERE line<>''")
    over_lines = []
    for bl in bls:
        o = db.one("SELECT qty FROM outputs WHERE period=? AND line=?", (p, bl["line"]))
        if not o or not o["qty"]:
            continue
        mt = db.rows("SELECT r.usage, e.tce_factor FROM readings r JOIN meters m ON m.code=r.meter_code "
                     "JOIN energy_types e ON e.code=m.energy_code WHERE r.period=? AND m.line=?",
                     (p, bl["line"]))
        t = sum(x["usage"] * x["tce_factor"] for x in mt)
        ue = E.unit_energy(t, o["qty"])
        dev = E.div(ue - bl["base_unit"], bl["base_unit"])
        if dev > 0.08:
            over_lines.append({"line": bl["line"], "unitEnergy": ue, "base": bl["base_unit"],
                               "dev": E.q4(dev), "level": E.intensity_alarm(ue, bl["base_unit"])})
    budget = db.one("SELECT SUM(amount) a, SUM(used) u FROM budgets WHERE period=?", (p,))
    bs = E.budget_state((budget or {}).get("a", 0), (budget or {}).get("u", 0))
    return ok({"period": p,
               "kpi": {"tce": tce, "tcePrev": tce_prev,
                       "tceRate": E.yoy(tce, tce_prev)["rate"],
                       "co2": co2["total"], "scope1": co2["scope1"], "scope2": co2["scope2"],
                       "elecQty": E.q2(elec["qty"]), "elecTce": E.q2(elec["tce"]),
                       "qty": E.q2(qty), "valueWan": E.q2(val),
                       "unitEnergy": inten["unitEnergy"], "valueEnergy": inten["valueEnergy"],
                       "carbonIntensity": E.carbon_intensity(co2["total"], val),
                       "alarms": alarm_sum,
                       "maxDemand": E.q2((mx or {}).get("d") or 0),
                       "capacityKw": E.q2((mx or {}).get("c") or 0),
                       "budget": bs},
               "byEnergy": em, "overLines": over_lines})


def api_analysis_consumption(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    center = (q.get("center") or [""])[0]
    line = (q.get("line") or [""])[0]
    energy = (q.get("energy") or [""])[0]
    rs = consumption_rows(p, center or None, line or None, energy or None)
    agg = {}
    for r in rs:
        k = (r["center"], r["energy_code"])
        a = agg.setdefault(k, {"center": r["center"], "energy": r["energy_code"],
                               "energyName": r["energy_name"], "unit": r["unit"],
                               "qty": 0.0, "tce": 0.0, "co2": 0.0, "meters": 0})
        a["qty"] += r["usage"]
        a["tce"] += r["tce"]
        a["co2"] += r["co2"]
        a["meters"] += 1
    names = {r["code"]: r["name"] for r in db.rows("SELECT code,name FROM cost_centers")}
    out = []
    for a in agg.values():
        a["qty"] = E.q2(a["qty"])
        a["tce"] = E.q2(a["tce"])
        a["co2"] = E.q4(a["co2"])
        a["centerName"] = names.get(a["center"], a["center"])
        out.append(a)
    out.sort(key=lambda x: -x["tce"])
    return ok({"period": p, "list": out, "totalTce": E.q2(sum(a["tce"] for a in out))})


def api_analysis_intensity(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    bls = db.rows("SELECT * FROM baselines WHERE line<>''")
    out = []
    for bl in bls:
        o = db.one("SELECT * FROM outputs WHERE period=? AND line=?", (p, bl["line"]))
        mt = db.rows("SELECT r.usage, e.tce_factor, e.co2_factor FROM readings r "
                     "JOIN meters m ON m.code=r.meter_code JOIN energy_types e ON e.code=m.energy_code "
                     "WHERE r.period=? AND m.line=?", (p, bl["line"]))
        tce = sum(x["usage"] * x["tce_factor"] for x in mt)
        qty = E.safe_num((o or {}).get("qty"))
        val = E.safe_num((o or {}).get("value_wan"))
        ue = E.unit_energy(tce, qty)
        dev = E.q4(E.div(ue - bl["base_unit"], bl["base_unit"])) if bl["base_unit"] else 0
        out.append({"line": bl["line"], "baselineCode": bl["code"], "product": bl["product"],
                    "qty": E.q2(qty), "tce": E.q2(tce),
                    "unitEnergy": ue, "baseUnit": bl["base_unit"],
                    "deviation": dev, "level": E.intensity_alarm(ue, bl["base_unit"]) or "正常",
                    "valueWan": E.q2(val), "valueEnergy": E.value_energy(tce, val)})
    return ok({"period": p, "list": out})


def api_analysis_yoy(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    n = int((q.get("months") or ["6"])[0])
    ss = E.period_range(E.prev_period(E.prev_period(p) + "-01") if False else p, p)
    start_y, start_m = int(p[:4]), int(p[5:7]) - (n - 1)
    while start_m <= 0:
        start_y, start_m = start_y - 1, start_m + 12
    ss = E.period_range("%04d-%02d" % (start_y, start_m), p)
    out = []
    for i, s in enumerate(ss):
        tce = period_tce(s)
        qty, val = period_output(s)
        rs = consumption_rows(s)
        co2 = E.co2_total(rs)
        prev = period_tce(ss[i - 1]) if i > 0 else 0
        out.append({"period": s, "tce": tce,
                    "mom": E.yoy(tce, prev)["rate"] if prev else None,
                    "qty": E.q2(qty), "unitEnergy": E.unit_energy(tce, qty),
                    "valueEnergy": E.value_energy(tce, val),
                    "co2": co2["total"]})
    return ok({"list": out, "period": p})


def api_report_balance(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    em = by_energy(p)
    centers = by_center(p)
    total = E.q2(sum(e["tce"] for e in em))
    items = [{"name": c["centerName"], "tce": c["tce"]} for c in centers]
    bal = E.energy_balance(total, items)
    return ok({"period": p, "byEnergy": em, "byCenter": centers, "balance": bal,
               "totalTce": total})


def api_report_daily(u, body, q):
    require(u, "report.read")
    frm = (q.get("from") or ["2026-10-01"])[0]
    to = (q.get("to") or ["2026-10-22"])[0]
    rs = db.rows("SELECT date, SUM(kwh) kwh, SUM(kwh*price) fee FROM intervals "
                 "WHERE date>=? AND date<=? GROUP BY date ORDER BY date", (frm, to))
    peak = db.rows("SELECT date, MAX(demand_kw) d FROM demands WHERE date>=? AND date<=? GROUP BY date",
                   (frm, to))
    pm = {r["date"]: r["d"] for r in peak}
    out = [{"date": r["date"], "kwh": E.q2(r["kwh"]), "fee": E.q2(r["fee"]),
            "maxDemand": E.q2(pm.get(r["date"], 0))} for r in rs]
    return ok({"from": frm, "to": to, "list": out,
               "totalKwh": E.q2(sum(x["kwh"] for x in out)),
               "totalFee": E.q2(sum(x["fee"] for x in out))})


def api_report_carbon(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    rs = consumption_rows(p)
    total = E.co2_total(rs)
    by_e = {}
    for r in rs:
        a = by_e.setdefault(r["energy_code"], {"energy": r["energy_code"], "name": r["energy_name"],
                                               "unit": r["unit"], "qty": 0.0, "co2": 0.0,
                                               "scope": r["scope"], "factor": r["co2Factor"]})
        a["qty"] += r["usage"]
        a["co2"] += r["co2"]
    lst = []
    for a in by_e.values():
        a["qty"] = E.q2(a["qty"])
        a["co2"] = E.q4(a["co2"])
        lst.append(a)
    lst.sort(key=lambda x: -x["co2"])
    _, val = period_output(p)
    months = []
    for s in E.period_range(E.prev_period(E.prev_period(p)), p):
        c = E.co2_total(consumption_rows(s))
        months.append({"period": s, "co2": c["total"], "scope1": c["scope1"],
                       "scope2": c["scope2"]})
    return ok({"period": p, "total": total, "byEnergy": lst,
               "intensity": E.carbon_intensity(total["total"], val),
               "valueWan": E.q2(val), "months": months})


def api_report_export(u, body, q):
    require(u, "report.read")
    typ = (q.get("type") or ["consumption"])[0]
    p = period_or_cur(q)
    rows_ = []
    header = []
    if typ == "consumption":
        header = ["成本中心", "能源介质", "用量", "单位", "折标煤(tce)", "碳排(tCO2)"]
        for r in api_analysis_consumption(u, {}, q)["data"]["list"]:
            rows_.append([r["centerName"], r["energyName"], r["qty"], r["unit"], r["tce"], r["co2"]])
    elif typ == "balance":
        d = api_report_balance(u, {}, q)["data"]
        header = ["能源介质", "用量", "单位", "折标煤(tce)", "碳排(tCO2)"]
        for r in d["byEnergy"]:
            rows_.append([r["name"], r["qty"], r["unit"], r["tce"], r["co2"]])
    elif typ == "daily":
        d = api_report_daily(u, {}, q)["data"]
        header = ["日期", "电量(kWh)", "电费(元)", "最大需量(kW)"]
        for r in d["list"]:
            rows_.append([r["date"], r["kwh"], r["fee"], r["maxDemand"]])
    elif typ == "carbon":
        d = api_report_carbon(u, {}, q)["data"]
        header = ["能源介质", "用量", "单位", "碳排(tCO2)", "范围"]
        for r in d["byEnergy"]:
            rows_.append([r["name"], r["qty"], r["unit"], r["co2"], r["scope"]])
    else:
        bad("type 必须是 consumption/balance/daily/carbon")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows_)
    log(u, "export", typ + ":" + p)
    return {"_raw": "\ufeff" + buf.getvalue(), "_ctype": "text/csv; charset=utf-8",
            "_filename": "feipu-%s-%s.csv" % (typ, p)}


def api_analysis_rank(u, body, q):
    require(u, "report.read")
    p = period_or_cur(q)
    centers = by_center(p)
    total = sum(c["tce"] for c in centers) or 1
    for c in centers:
        c["share"] = E.q4(c["tce"] / total)
        b = db.one("SELECT SUM(amount) a, SUM(used) u FROM budgets WHERE period=? AND center=?",
                   (p, c["center"]))
        c["budget"] = E.q2((b or {}).get("a") or 0)
        c["used"] = E.q2((b or {}).get("u") or 0)
        c["budgetRate"] = E.q4(E.div((b or {}).get("u"), (b or {}).get("a"))) if (b or {}).get("a") else None
    return ok({"period": p, "list": centers, "totalTce": E.q2(total)})


# ---- 基线 / 能效 / 项目 ----

def api_baselines(u, body, q):
    require(u, "base.read")
    rs = db.rows("SELECT b.*, l.name AS lineName FROM baselines b LEFT JOIN lines l ON l.code=b.line "
                 "ORDER BY b.code")
    for r in rs:
        r["baseUnit"] = r["base_unit"]
    return ok({"list": rs})


def api_baseline_create(u, body, q):
    require(u, "base.write")
    b = body or {}
    line = b.get("line")
    if not line:
        bad("line 必填")
    pf = b.get("periodFrom") or E.prev_period(E.prev_period(E.cur_period()))
    pt = b.get("periodTo") or E.prev_period(E.cur_period())
    ss = E.period_range(pf, pt)
    tce = 0.0
    qty = 0.0
    for s in ss:
        for r in db.rows("SELECT r.usage, e.tce_factor FROM readings r JOIN meters m "
                         "ON m.code=r.meter_code JOIN energy_types e ON e.code=m.energy_code "
                         "WHERE r.period=? AND m.line=?", (s, line)):
            tce += r["usage"] * r["tce_factor"]
        o = db.one("SELECT qty FROM outputs WHERE period=? AND line=?", (s, line))
        qty += E.safe_num((o or {}).get("qty"))
    if qty <= 0:
        bad("该产线在 %s~%s 无产量数据，无法建立基线" % (pf, pt), 409)
    bu = E.baseline_unit(tce, qty)
    code = b.get("code") or ("BL-" + line + "-" + pt.replace("-", ""))
    if db.one("SELECT * FROM baselines WHERE code=?", (code,)):
        bad("基线编码已存在", 409)
    db.run("INSERT INTO baselines(code,line,product,period_from,period_to,base_unit,total_tce,"
           "qty,method,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'生效',?)",
           (code, line, b.get("product", ""), pf, pt, bu, E.q2(tce), E.q2(qty),
            b.get("method", "单位产品能耗"), now()))
    fire("baseline.created", {"code": code, "line": line, "baseUnit": bu,
                              "periodFrom": pf, "periodTo": pt})
    log(u, "create", "baseline:" + code)
    return ok({"code": code, "baseUnit": bu, "tce": E.q2(tce), "qty": E.q2(qty), "periods": ss})


def api_eff_tests(u, body, q):
    require(u, "equip.read")
    code = (q.get("equipment") or [""])[0]
    sql = ("SELECT t.*, e.name AS equipmentName, e.etype, e.center FROM eff_tests t "
           "LEFT JOIN equipments e ON e.code=t.equipment_code WHERE 1=1")
    args = []
    if code:
        sql += " AND t.equipment_code=?"
        args.append(code)
    sql += " ORDER BY t.date DESC LIMIT 500"
    return ok({"list": db.rows(sql, tuple(args)), "spec": E.EFF_SPEC})


def api_eff_calc(u, body, q):
    require(u, "equip.write")
    b = body or {}
    etype = b.get("etype")
    if etype not in E.EFF_SPEC:
        bad("设备类型必须是 " + "/".join(E.EFF_SPEC.keys()))
    r = E.eff_calc(etype, input_power=b.get("inputPower", 0), output_qty=b.get("outputQty", 0),
                   output_kw=b.get("outputKw", 0), heat_in=b.get("heatIn", 0),
                   heat_out=b.get("heatOut", 0))
    return ok(r)


def api_eff_save(u, body, q):
    require(u, "equip.write")
    b = body or {}
    code = b.get("equipment")
    if not code:
        bad("equipment 必填")
    eq = db.one("SELECT * FROM equipments WHERE code=?", (code,))
    if not eq:
        bad("设备不存在", 404)
    r = E.eff_calc(eq["etype"], input_power=b.get("inputPower", 0), output_qty=b.get("outputQty", 0),
                   output_kw=b.get("outputKw", 0), heat_in=b.get("heatIn", 0),
                   heat_out=b.get("heatOut", 0))
    if r["value"] <= 0:
        bad("实测参数不足，无法计算能效指标", 409)
    date = b.get("date") or E.cur_period() + "-15"
    prev = db.one("SELECT * FROM eff_tests WHERE equipment_code=? ORDER BY date DESC LIMIT 1", (code,))
    db.run("INSERT INTO eff_tests(equipment_code,date,input_power,output_qty,output_kw,heat_in,"
           "heat_out,value,metric,grade,tester,remark) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
           (code, date, E.safe_num(b.get("inputPower")), E.safe_num(b.get("outputQty")),
            E.safe_num(b.get("outputKw")), E.safe_num(b.get("heatIn")),
            E.safe_num(b.get("heatOut")), r["value"], r["metric"], r["grade"],
            (u or {}).get("name", ""), b.get("remark", "")))
    degraded = False
    alarm = None
    if prev:
        d = E.eff_delta(r["value"], prev["value"], eq["etype"])
        degraded = d["degraded"]
        if degraded:
            alarm = raise_alarm("提示", "能效劣化", code,
                                "%s %s 由 %.2f 变为 %.2f（%s）" % (code, eq["name"], prev["value"],
                                                               r["value"], eq["etype"]),
                                r["value"], prev["value"], date[:7])
            fire("eff.degraded", {"equipment": code, "from": prev["value"], "to": r["value"]})
    log(u, "eff-test", code, r["value"])
    return ok({"equipment": code, "result": r, "value": r["value"], "grade": r["grade"],
               "metric": r["metric"], "degraded": degraded, "alarm": alarm, "date": date})


def api_projects(u, body, q):
    require(u, "proj.read")
    rs = db.rows("SELECT * FROM projects ORDER BY no")
    for r in rs:
        v = db.one("SELECT * FROM project_verify WHERE project_no=? ORDER BY period DESC LIMIT 1",
                   (r["no"],))
        r["lastVerify"] = v
        r["invest"] = E.q2(r["invest"])
    return ok({"list": rs})


def api_project_create(u, body, q):
    require(u, "proj.write")
    b = body or {}
    if not b.get("name"):
        bad("name 必填")
    if not b.get("baselineCode") and b.get("requireBaseline", True):
        if not db.one("SELECT * FROM baselines WHERE code=?", (b.get("baselineCode") or "-",)):
            bad("节能量验证需要基线，请先建立能耗基线（baselineCode 必填）", 409)
    no = b.get("no") or gen_no("SP", "projects", "no")
    if db.one("SELECT * FROM projects WHERE no=?", (no,)):
        bad("项目编号已存在", 409)
    db.run("INSERT INTO projects(no,name,center,line,baseline_code,invest,measure,start_period,"
           "end_period,verify_period,owner,status,remark,created_at) "
           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (no, b["name"], b.get("center", ""), b.get("line", ""), b.get("baselineCode", ""),
            E.safe_num(b.get("invest")), b.get("measure", ""), b.get("startPeriod", ""),
            b.get("endPeriod", ""), b.get("verifyPeriod", ""), b.get("owner", ""),
            b.get("status", "待实施"), b.get("remark", ""), now()))
    log(u, "create", "project:" + no)
    return ok({"no": no})


def api_project_detail(u, body, q, no):
    require(u, "proj.read")
    p = db.one("SELECT * FROM projects WHERE no=?", (no,))
    if not p:
        bad("项目不存在", 404)
    p["verifies"] = db.rows("SELECT * FROM project_verify WHERE project_no=? ORDER BY period DESC", (no,))
    p["baseline"] = db.one("SELECT * FROM baselines WHERE code=?", (p["baseline_code"],)) if p["baseline_code"] else None
    return ok(p)


def api_project_verify(u, body, q, no):
    require(u, "proj.verify")
    b = body or {}
    p = db.one("SELECT * FROM projects WHERE no=?", (no,))
    if not p:
        bad("项目不存在", 404)
    if not p["baseline_code"]:
        bad("该项目无锁定基线，不能验证节能量", 409)
    bl = db.one("SELECT * FROM baselines WHERE code=?", (p["baseline_code"],))
    if not bl or not bl["base_unit"]:
        bad("基线数据缺失或单位能耗为 0", 409)
    period = b.get("period") or E.cur_period()
    line = p["line"] or bl["line"]
    mt = db.rows("SELECT r.usage, e.tce_factor FROM readings r JOIN meters m ON m.code=r.meter_code "
                 "JOIN energy_types e ON e.code=m.energy_code WHERE r.period=? AND m.line=?",
                 (period, line))
    if not mt:
        bad("%s 期间无 %s 产线计量数据，不能验证" % (period, line), 409)
    tce = sum(x["usage"] * x["tce_factor"] for x in mt)
    o = db.one("SELECT qty FROM outputs WHERE period=? AND line=?", (period, line))
    qty = E.safe_num((o or {}).get("qty"))
    if qty <= 0:
        bad("%s 期间该产线产量为 0，不能验证节能量" % period, 409)
    report_unit = E.q6(tce / qty)
    rl = rules()
    months = int(b.get("months") or 12)
    v = E.project_verify(bl["base_unit"], report_unit, qty, p["invest"], rl["tce_price"], months)
    db.run("INSERT INTO project_verify(project_no,period,base_unit,report_unit,qty,saving_tce,"
           "saving_rate,saving_fee,payback,verdict,remark,created_at) "
           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
           (no, period, bl["base_unit"], report_unit, qty, v["savingTce"], v["savingRate"],
            v["savingFeeYear"], v["paybackYear"], v["verdict"],
            b.get("remark", ""), now()))
    db.run("UPDATE projects SET status=?, verify_period=? WHERE no=?",
           ("已验证" if v["achieved"] else "未达标", period, no))
    fire("project.verified", {"no": no, "period": period, "savingTce": v["savingTce"],
                              "verdict": v["verdict"]})
    log(u, "verify", "project:" + no, v["verdict"])
    return ok(dict(v, project=no, period=period, tce=E.q2(tce)))


# ---- 告警 ----

def api_alarms(u, body, q):
    require(u, "alarm.read")
    sql = "SELECT * FROM alarms WHERE 1=1"
    args = []
    for k, col in (("level", "level"), ("status", "status"), ("type", "atype")):
        v = (q.get(k) or [""])[0]
        if v:
            sql += " AND %s=?" % col
            args.append(v)
    if q.get("period"):
        sql += " AND period=?"
        args.append(q["period"][0])
    sql += " ORDER BY CASE level WHEN '紧急' THEN 1 WHEN '严重' THEN 2 WHEN '警告' THEN 3 ELSE 4 END, no DESC LIMIT 500"
    rs = db.rows(sql, tuple(args))
    return ok({"list": rs, "summary": E.alarm_summary(db.rows("SELECT * FROM alarms"))})


def api_alarm_handle(u, body, q, no):
    require(u, "alarm.write")
    b = body or {}
    a = db.one("SELECT * FROM alarms WHERE no=?", (no,))
    if not a:
        bad("告警不存在", 404)
    if a["status"] == "已处置":
        bad("该告警已处置，不可重复处置", 409)
    db.run("UPDATE alarms SET status='已处置', handled_by=?, handled_at=?, remark=? WHERE no=?",
           ((u or {}).get("name", ""), now(), b.get("remark", b.get("action", "")), no))
    fire("alarm.handled", {"no": no, "by": (u or {}).get("name", "")})
    log(u, "handle", "alarm:" + no)
    return ok({"no": no, "status": "已处置"})


def api_alarm_summary(u, body, q):
    require(u, "alarm.read")
    rows_ = db.rows("SELECT * FROM alarms")
    bytype = {}
    for r in rows_:
        bytype[r["atype"]] = bytype.get(r["atype"], 0) + 1
    return ok({"summary": E.alarm_summary(rows_),
               "byType": [{"type": k, "count": v} for k, v in sorted(bytype.items(), key=lambda x: -x[1])],
               "byPeriod": db.rows("SELECT period, COUNT(*) c FROM alarms GROUP BY period ORDER BY period DESC LIMIT 12")})


# ---- 预算 ----

def api_budgets(u, body, q):
    require(u, "budget.read")
    p = period_or_cur(q)
    rs = db.rows("SELECT b.*, c.name AS centerName, e.name AS energyName, e.unit AS unit, "
                 "e.price AS price FROM budgets b LEFT JOIN cost_centers c ON c.code=b.center "
                 "LEFT JOIN energy_types e ON e.code=b.energy_code WHERE b.period=? "
                 "ORDER BY b.center, b.energy_code", (p,))
    out = []
    for r in rs:
        st = E.budget_state(r["amount"], r["used"])
        r.update({"budget": st["budget"], "usedAmt": st["used"], "left": st["left"],
                  "rate": st["rate"], "status": st["status"], "blocked": st["blocked"]})
        out.append(r)
    return ok({"period": p, "list": out,
               "totals": {"amount": E.q2(sum(r["amount"] for r in rs)),
                          "used": E.q2(sum(r["used"] for r in rs))}})


def api_budget_save(u, body, q):
    require(u, "budget.write")
    b = body or {}
    p = b.get("period") or E.cur_period()
    for it in b.get("items", []):
        db.run("INSERT INTO budgets(period,center,energy_code,amount,used) VALUES(?,?,?,?,?) "
               "ON CONFLICT(period,center,energy_code) DO UPDATE SET amount=excluded.amount",
               (p, it.get("center"), it.get("energyCode"), E.safe_num(it.get("amount")),
                E.safe_num(it.get("used"))))
    log(u, "save", "budget:" + p, len(b.get("items", [])))
    return ok({"period": p, "count": len(b.get("items", []))})


# ---- 系统 ----

def api_users(u, body, q):
    require(u, "sys.user")
    rs = db.rows("SELECT username,name,role,phone,status,created_at FROM users ORDER BY username")
    for r in rs:
        r["roleName"] = E.ROLES.get(r["role"], r["role"])
    return ok({"list": rs, "roles": E.ROLES})


def api_user_save(u, body, q):
    require(u, "sys.user")
    b = body or {}
    username = b.get("username") or ""
    if not username:
        bad("username 必填")
    if b.get("role") and b["role"] not in E.ROLES:
        bad("角色不存在")
    if db.one("SELECT username FROM users WHERE username=?", (username,)):
        db.run("UPDATE users SET name=?,role=?,phone=?,status=? WHERE username=?",
               (b.get("name"), b.get("role"), b.get("phone", ""), b.get("status", "启用"), username))
    else:
        pw = b.get("password") or "energy@2026"
        db.run("INSERT INTO users(username,password_hash,name,role,phone,status,created_at) "
               "VALUES(?,?,?,?,?,'启用',?)",
               (username, h256("feipu$" + pw), b.get("name") or username, b.get("role", "staff"),
                b.get("phone", ""), now()))
    fire("user.changed", {"username": username})
    log(u, "save", "user:" + username)
    return ok({"username": username})


def api_rules(u, body, q):
    require(u, "report.read")
    return ok({"list": [{"key": k, "value": v, "remark": ""} for k, v in rules().items()],
               "roles": E.ROLES, "perms": E.PERMS, "events": EVENTS})


def api_rule_save(u, body, q):
    require(u, "sys.rule")
    b = body or {}
    if not isinstance(b, dict):
        bad("格式错误")
    # 兼容两种入参：整批 {k1:v1,k2:v2} 或单条 {key,value}
    if "key" in b and "value" in b:
        items = {b["key"]: b["value"]}
    elif isinstance(b.get("rules"), dict):
        items = b["rules"]
    else:
        items = b
    if not items:
        bad("没有可保存的规则")
    unknown = [k for k in items if k not in E.DEFAULT_RULES]
    if unknown:
        bad("未知规则项：%s（可用：%s）" % (",".join(unknown),
                                     ",".join(sorted(E.DEFAULT_RULES))))
    for k, v in items.items():
        db.run("INSERT INTO rules(key,value,remark) VALUES(?,?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v), "用户修改"))
    log(u, "save", "rules", ",".join(items.keys()))
    return ok({"count": len(items), "saved": sorted(items.keys())})


def api_api_keys(u, body, q):
    require(u, "sys.key")
    rs = db.rows("SELECT id,name,key_prefix,role,status,created_at,last_used FROM api_keys ORDER BY id DESC")
    return ok({"list": rs})


def api_api_key_create(u, body, q):
    require(u, "sys.key")
    b = body or {}
    name = b.get("name") or "对接密钥"
    role = b.get("role") or "staff"
    if role not in E.ROLES:
        bad("角色不存在")
    plain = "fpk_" + secrets.token_hex(16)
    db.run("INSERT INTO api_keys(name,key_prefix,key_hash,role,status,created_at) "
           "VALUES(?,?,?,?,'启用',?)", (name, plain[:12], h256(plain), role, now()))
    log(u, "create", "api_key:" + name)
    return ok({"name": name, "key": plain, "role": role,
               "note": "密钥仅本次返回，请妥善保存"})


def api_api_key_del(u, body, q, kid):
    require(u, "sys.key")
    db.run("DELETE FROM api_keys WHERE id=?", (E.q0(kid),))
    log(u, "delete", "api_key:%s" % kid)
    return ok({"deleted": kid})


def api_webhooks(u, body, q):
    require(u, "sys.hook")
    rs = db.rows("SELECT * FROM webhooks ORDER BY id DESC")
    return ok({"list": rs, "events": EVENTS,
               "deliveries": db.rows("SELECT * FROM webhook_deliveries ORDER BY id DESC LIMIT 50")})


def api_webhook_create(u, body, q):
    require(u, "sys.hook")
    b = body or {}
    url = b.get("url") or ""
    if not url.startswith("http"):
        bad("url 必须是 http(s) 地址")
    secret = b.get("secret") or secrets.token_hex(16)
    db.run("INSERT INTO webhooks(name,url,secret,events,status,created_at) VALUES(?,?,?,?,'启用',?)",
           (b.get("name", "订阅"), url, secret, ",".join(b.get("events") or ["*"]), now()))
    log(u, "create", "webhook:" + url)
    return ok({"url": url, "secret": secret,
               "sign": "X-Fp-Signature: sha256=hex(hmac_sha256(secret, timestamp + '.' + rawBody))"})


def api_webhook_del(u, body, q, wid):
    require(u, "sys.hook")
    db.run("DELETE FROM webhooks WHERE id=?", (E.q0(wid),))
    return ok({"deleted": wid})


def api_logs(u, body, q):
    require(u, "sys.log")
    return ok({"list": db.rows("SELECT * FROM logs ORDER BY id DESC LIMIT 300")})


def api_sync_changes(u, body, q):
    require(u, "sync.read")
    ent = (q.get("entity") or ["meters"])[0]
    since = (q.get("since") or [""])[0]
    table = {"meters": ("meters", "code"), "energy_types": ("energy_types", "code"),
             "readings": ("readings", "created_at"), "alarms": ("alarms", "period"),
             "projects": ("projects", "created_at"), "demands": ("demands", "ts")}
    if ent not in table:
        bad("entity 必须是 " + "/".join(table.keys()))
    t, col = table[ent]
    sql = "SELECT * FROM %s" % t
    args = ()
    if since:
        sql += " WHERE %s >= ?" % col
        args = (since,)
    sql += " ORDER BY %s LIMIT 2000" % col
    rs = db.rows(sql, args)
    ver = db.val("SELECT version FROM sync_state WHERE entity=?", (ent,), 0)
    return ok({"entity": ent, "since": since, "version": ver,
               "count": len(rs), "list": rs, "serverTime": now()})


def api_openapi(u, body, q):
    paths = {}
    for m, pat, fn, perm in ROUTES:
        p = pat.replace("{code}", "{code}").replace("{no}", "{no}").replace("{id}", "{id}")
        paths.setdefault(p, {})[m.lower()] = {
            "summary": fn.__name__.replace("api_", "").replace("_", " "),
            "permission": perm or "登录",
            "responses": {"200": {"description": "统一响应包 {code,message,data}"}},
        }
    spec = {"openapi": "3.0.3",
            "info": {"title": BRAND + " API", "version": VERSION,
                     "description": "多通道鉴权：Bearer / X-Fp-Token / Cookie / ?token= / X-Fp-Key"},
            "servers": [{"url": PREFIX or "/"}],
            "paths": paths,
            "x-events": EVENTS}
    return ok(spec)


def api_openapi_html(u, body, q):
    spec = api_openapi({"role": "admin"}, {}, {})["data"]
    rows_html = []
    for p, ms in sorted(spec["paths"].items()):
        for m, d in ms.items():
            rows_html.append("<tr><td><b>%s</b></td><td><code>%s</code></td><td>%s</td><td>%s</td></tr>"
                             % (m.upper(), p, d["summary"], d["permission"]))
    events = "".join("<code>%s</code> " % e for e in EVENTS)
    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>飞瀑能源管理系统 API</title>
<style>body{font:14px/1.7 -apple-system,"PingFang SC",sans-serif;margin:0;padding:32px 40px;background:#f6f9fc;color:#1c2b36}
h1{font-size:22px;margin:0 0 6px}h2{font-size:16px;margin:28px 0 10px}
.sub{color:#6b8299;font-size:13px;margin-bottom:20px}
table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.07);border-radius:8px;overflow:hidden}
th{background:#eef4fa;text-align:left;padding:10px 12px;font-size:12px;color:#5c7a94}
td{padding:8px 12px;border-top:1px solid #eef2f6;font-size:13px}
code{background:#eef4fa;padding:1px 6px;border-radius:4px;font-size:12px}
.ev{margin-top:8px;line-height:2.2}</style></head><body>
<h1>飞瀑能源管理系统 · REST API</h1>
<div class="sub">版本 __VER__ · 共 __N__ 个接口 · 鉴权：Bearer / X-Fp-Token / Cookie / ?token= / X-Fp-Key</div>
<h2>接口清单</h2><table><thead><tr><th>方法</th><th>路径</th><th>说明</th><th>所需权限</th></tr></thead>
<tbody>__ROWS__</tbody></table>
<h2>Webhook 事件</h2><div class="ev">__EVENTS__</div>
</body></html>"""
    html = html.replace("__VER__", VERSION).replace("__N__", str(len(rows_html)))
    html = html.replace("__ROWS__", "".join(rows_html)).replace("__EVENTS__", events)
    return {"_raw": html, "_ctype": "text/html; charset=utf-8"}


# =================================================================
# 路由表
# =================================================================

ROUTES = [
    # 认证
    ("POST", "/api/auth/login", api_login, None),
    ("POST", "/api/auth/logout", api_logout, None),
    ("GET", "/api/auth/me", api_me, None),
    ("POST", "/api/auth/change-password", api_change_pwd, None),
    ("GET", "/api/health", api_health, None),
    # 主数据
    ("GET", "/api/energy-types", api_energy_types, "energy.read"),
    ("POST", "/api/energy-types", lambda u, b, q: api_energy_type_save(u, b, q), "energy.write"),
    ("PUT", "/api/energy-types/{code}", lambda u, b, q, code: api_energy_type_save(u, b, q, code), "energy.write"),
    ("DELETE", "/api/energy-types/{code}", api_energy_type_del, "energy.write"),
    ("GET", "/api/tariffs", api_tariffs, "energy.read"),
    ("POST", "/api/tariffs", api_tariff_save, "energy.write"),
    ("GET", "/api/cost-centers", api_centers, "center.read"),
    ("POST", "/api/cost-centers", lambda u, b, q: api_center_save(u, b, q), "center.write"),
    ("PUT", "/api/cost-centers/{code}", lambda u, b, q, code: api_center_save(u, b, q, code), "center.write"),
    ("GET", "/api/lines", api_lines, "center.read"),
    ("POST", "/api/lines", api_line_save, "center.write"),
    ("GET", "/api/meters", api_meters, "meter.read"),
    ("POST", "/api/meters", lambda u, b, q: api_meter_save(u, b, q), "meter.write"),
    ("PUT", "/api/meters/{code}", lambda u, b, q, code: api_meter_save(u, b, q, code), "meter.write"),
    ("GET", "/api/equipments", api_equipments, "equip.read"),
    ("POST", "/api/equipments", api_equipment_save, "equip.write"),
    # 抄表
    ("GET", "/api/readings", api_readings, "read.read"),
    ("POST", "/api/readings", api_reading_create, "read.write"),
    ("POST", "/api/readings/batch", api_reading_batch, "read.write"),
    ("POST", "/api/readings/report", api_reading_report, "read.write"),
    ("GET", "/api/readings/check", api_reading_check, "read.check"),
    # 分时 / 需量
    ("GET", "/api/intervals", api_intervals, "energy.read"),
    ("POST", "/api/intervals", api_interval_save, "energy.write"),
    ("GET", "/api/tou-summary", api_tou_summary, "energy.read"),
    ("GET", "/api/demands", api_demands, "energy.read"),
    ("POST", "/api/demands", api_demand_create, "energy.write"),
    ("GET", "/api/demands/summary", api_demand_summary, "energy.read"),
    # 分析
    ("GET", "/api/board", api_board, "report.read"),
    ("GET", "/api/analysis/consumption", api_analysis_consumption, "report.read"),
    ("GET", "/api/analysis/intensity", api_analysis_intensity, "report.read"),
    ("GET", "/api/analysis/yoy", api_analysis_yoy, "report.read"),
    ("GET", "/api/analysis/rank", api_analysis_rank, "report.read"),
    # 报表
    ("GET", "/api/reports/energy-balance", api_report_balance, "report.read"),
    ("GET", "/api/reports/daily", api_report_daily, "report.read"),
    ("GET", "/api/reports/carbon", api_report_carbon, "report.read"),
    ("GET", "/api/reports/export", api_report_export, "report.read"),
    # 基线 / 能效 / 项目
    ("GET", "/api/baselines", api_baselines, "base.read"),
    ("POST", "/api/baselines", api_baseline_create, "base.write"),
    ("GET", "/api/eff-tests", api_eff_tests, "equip.read"),
    ("POST", "/api/eff-tests/calc", api_eff_calc, "equip.write"),
    ("POST", "/api/eff-tests", api_eff_save, "equip.write"),
    ("GET", "/api/projects", api_projects, "proj.read"),
    ("POST", "/api/projects", api_project_create, "proj.write"),
    ("GET", "/api/projects/{no}/detail", api_project_detail, "proj.read"),
    ("POST", "/api/projects/{no}/verify", api_project_verify, "proj.verify"),
    # 告警
    ("GET", "/api/alarms", api_alarms, "alarm.read"),
    ("GET", "/api/alarms/summary", api_alarm_summary, "alarm.read"),
    ("POST", "/api/alarms/{no}/handle", api_alarm_handle, "alarm.write"),
    # 预算
    ("GET", "/api/budgets", api_budgets, "budget.read"),
    ("POST", "/api/budgets", api_budget_save, "budget.write"),
    # 系统
    ("GET", "/api/users", api_users, "sys.user"),
    ("POST", "/api/users", api_user_save, "sys.user"),
    ("GET", "/api/rules", api_rules, "report.read"),
    ("PUT", "/api/rules", api_rule_save, "sys.rule"),
    ("GET", "/api/api-keys", api_api_keys, "sys.key"),
    ("POST", "/api/api-keys", api_api_key_create, "sys.key"),
    ("DELETE", "/api/api-keys/{kid}", api_api_key_del, "sys.key"),
    ("GET", "/api/webhooks", api_webhooks, "sys.hook"),
    ("POST", "/api/webhooks", api_webhook_create, "sys.hook"),
    ("DELETE", "/api/webhooks/{wid}", api_webhook_del, "sys.hook"),
    ("GET", "/api/logs", api_logs, "sys.log"),
    ("GET", "/api/sync/changes", api_sync_changes, "sync.read"),
    ("GET", "/api/openapi.json", api_openapi, None),
    ("GET", "/apidoc", api_openapi_html, None),
]

# 参数名 → 位置索引
PARAM_ORDER = {"code": 0, "no": 0, "id": 0}


def match(method, path):
    """返回 (handler, kwargs, perm) 或 None。"""
    if path.startswith("/api/") or path.startswith("/apidoc"):
        for m, pat, fn, perm in ROUTES:
            if m != method:
                continue
            if pat == path:
                return fn, {}, perm
            if "{" in pat:
                pre, _, rest = pat.partition("{")
                name, _, suf = rest.partition("}")
                if path.startswith(pre) and path.endswith(suf) and len(path) > len(pre) + len(suf):
                    val = path[len(pre):len(path) - len(suf)] if suf else path[len(pre):]
                    return fn, {name: urllib.parse.unquote(val)}, perm
    return None


# =================================================================
# HTTP
# =================================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "FeiPuEnergy/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Fp-Token, X-Fp-Key, Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:  # noqa: BLE001
            pass

    def _local_path(self):
        p = urllib.parse.unquote(self.path.split("?")[0])
        if PREFIX and p.startswith(PREFIX + "/"):
            p = p[len(PREFIX):]
        elif PREFIX and p == PREFIX:
            p = "/"
        return p

    def do_OPTIONS(self):
        self._send(204, "")

    def _handle(self, method):
        ip = self.client_address[0] if self.client_address else ""
        if not rate_ok(ip):
            return self._send(429, {"code": 429, "message": "请求过于频繁（300 次/分钟）", "data": None})
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        path = self._local_path()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:  # noqa: BLE001
            body = {}

        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/") or re.search(
                r"\.(html|css|js|png|svg|ico|woff2?|jpg|json|map)$", path):
            # 允许 /login.html、/app.js 这类根路径直取，但不得越过静态目录
            rel = path.lstrip("/").replace("static/", "", 1)
            if ".." not in rel and os.path.isfile(os.path.join(STATIC, rel)):
                return self._static(rel)

        hit = match(method, path)
        if not hit:
            return self._send(404, {"code": 404, "message": "接口不存在: %s %s" % (method, path), "data": None})
        fn, kw, perm = hit

        # 幂等
        idem = self.headers.get("Idempotency-Key", "")
        if idem and method in ("POST", "PUT"):
            r = db.one("SELECT * FROM idem_keys WHERE key=?", (idem,))
            if r:
                return self._send(200, json.loads(r["response"]))

        try:
            u = auth(self, q)
            if perm:
                require(u, perm)
            res = fn(u, body, q, **kw)
            if isinstance(res, dict) and "_raw" in res:
                extra = {}
                if res.get("_filename"):
                    extra["Content-Disposition"] = 'attachment; filename="%s"' % res["_filename"]
                return self._send(200, res["_raw"], res.get("_ctype", "text/plain"), extra)
            payload = res if isinstance(res, dict) and "code" in res else ok(res)
            if idem and method in ("POST", "PUT") and payload.get("code") == 200:
                db.run("INSERT OR REPLACE INTO idem_keys(key,endpoint,response,created_at) VALUES(?,?,?,?)",
                       (idem, path, json.dumps(payload, ensure_ascii=False), now()))
            if method in ("POST", "PUT", "DELETE") and path not in ("/api/auth/login",):
                log(u, method.lower(), path)
            return self._send(200, payload)
        except ApiError as e:
            return self._send(e.code, {"code": e.code, "message": e.msg, "data": None})
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._send(500, {"code": 500, "message": "服务异常：%s" % e, "data": None})

    def _static(self, rel):
        rel = rel.replace("..", "").lstrip("/")
        full = os.path.join(STATIC, rel)
        if not os.path.isfile(full):
            return self._send(404, {"code": 404, "message": "资源不存在", "data": None})
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}.get(
            os.path.splitext(full)[1].lower(), "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:  # noqa: BLE001
            pass

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


def main():
    db.init()
    cn = db.connect()
    fresh = not db.val("SELECT COUNT(*) FROM users")
    if fresh:
        seed_mod.seed()
        db.close_thread_conns()
        cn = db.connect()
        print("seeded demo data")
    _warmup()
    print("%s v%s listening on 0.0.0.0:%d prefix=%r routes=%d" % (BRAND, VERSION, PORT, PREFIX, len(ROUTES)))
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _warmup():
    """首次启动跑一遍分析与告警，保证看板开箱有数。"""
    try:
        p = E.cur_period()
        if not db.val("SELECT COUNT(*) FROM alarms WHERE period=?", (p,)):
            pass
    except Exception as e:  # noqa: BLE001
        print("warmup skipped:", e)


if __name__ == "__main__":
    main()
