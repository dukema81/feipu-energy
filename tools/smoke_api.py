# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 接口冒烟脚本

对运行中的实例做端到端体检（不建库、不播种），用于部署后验收。
用法：
    python tools/smoke_api.py                     # 默认 http://localhost:8021/pu
    python tools/smoke_api.py --base http://localhost:8931
    python tools/smoke_api.py --base https://example.com/pu --user admin --pwd energy@2026
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PWD = "energy@2026"

OK, FAIL = [], []


def call(base, method, path, body=None, token="", key="", timeout=20, raw=False):
    url = base.rstrip("/") + urllib.parse.quote(path, safe="/?:=&%+,")
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if key:
        h["X-Fp-Key"] = key
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload, dict(r.headers)
            try:
                return r.status, json.loads(payload or b"{}"), dict(r.headers)
            except ValueError:
                return r.status, {"message": "非 JSON 响应（%d 字节）" % len(payload)}, dict(r.headers)
    except urllib.error.HTTPError as e:
        payload = e.read() or b""
        try:
            return e.code, json.loads(payload), dict(e.headers or {})
        except Exception:  # noqa: BLE001
            return e.code, {"message": payload[:200].decode("utf-8", "ignore")}, dict(e.headers or {})
    except Exception as e:  # noqa: BLE001
        return 0, {"message": str(e)}, {}


def check(name, method, path, expect=200, token="", key="", body=None, probe=None, raw=False):
    res = call(BASE, method, path, body=body, token=token, key=key, raw=raw)
    st, js = res[0], (res[1] if not raw else {})
    detail = js.get("message", "") if isinstance(js, dict) else ""
    if st == expect:
        if probe:
            try:
                probe(js.get("data") or {})
            except AssertionError as e:
                FAIL.append((name, "%s %s → 数据断言失败: %s" % (method, path, e)))
                return None
        OK.append(name)
        return js.get("data") if isinstance(js, dict) else None
    FAIL.append((name, "%s %s 期望 %s 实际 %s · %s" % (method, path, expect, st, detail)))
    return None


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8021/pu")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--pwd", default=PWD)
    a = ap.parse_args()
    BASE = a.base.rstrip("/")

    print("冒烟目标：%s" % BASE)
    t0 = time.time()

    # 1. 健康检查
    health = check("健康检查", "GET", "/api/health",
                   probe=lambda d: (
                       _assert(d.get("brand") == "飞瀑能源管理系统", "brand 不符"),
                       _assert(d.get("routes", 0) >= 69, "路由数不足"),
                       _assert(d.get("meters", 0) >= 30, "计量点为空"),
                       _assert(d.get("readings", 0) >= 300, "抄表数据不足"),
                   ))

    # 2. 登录
    st, js, _h = call(BASE, "POST", "/api/auth/login",
                      body={"username": a.user, "password": a.pwd})
    if st != 200:
        FAIL.append(("登录", "HTTP %s · %s" % (st, js.get("message"))))
        report()
        return 1
    tok = js["data"]["token"]
    OK.append("登录 (%s/%s)" % (a.user, js["data"]["user"]["roleName"]))

    # 3. 主数据
    check("能源介质", "GET", "/api/energy-types", token=tok,
          probe=lambda d: _assert(len(d["list"]) >= 6, "介质不足 6 种"))
    check("成本中心", "GET", "/api/cost-centers", token=tok,
          probe=lambda d: _assert(len(d["list"]) >= 10, "中心不足 10 个"))
    check("计量点", "GET", "/api/meters", token=tok,
          probe=lambda d: _assert(len(d["list"]) >= 30, "计量点不足 30 个"))
    check("产线", "GET", "/api/lines", token=tok)
    check("设备台账", "GET", "/api/equipments", token=tok,
          probe=lambda d: _assert(len(d["spec"]) == 4, "能效规范应为 4 类"))

    # 4. 核心看板
    period = (health or {}).get("time", "")[:7]
    check("经营看板", "GET", "/api/board?period=" + period, token=tok,
          probe=lambda d: (
              _assert(d["kpi"]["tce"] > 0, "综合能耗为 0"),
              _assert(d["kpi"]["co2"] > 0, "碳排为 0（co2Factor 未生效）"),
              _assert(abs(d["kpi"]["scope1"] + d["kpi"]["scope2"] - d["kpi"]["co2"]) < 0.02,
                      "范围一二之和与总量不符"),
              _assert(d["byEnergy"], "介质拆分为空"),
          ))
    check("能耗分析", "GET", "/api/analysis/consumption?period=" + period, token=tok)
    check("单耗基线", "GET", "/api/analysis/intensity?period=" + period, token=tok,
          probe=lambda d: _assert(d["list"], "产线单耗为空"))
    check("同比环比", "GET", "/api/analysis/yoy?period=%s&months=6" % period, token=tok)
    check("中心排名", "GET", "/api/analysis/rank?period=" + period, token=tok)
    check("能源平衡", "GET", "/api/reports/energy-balance?period=" + period, token=tok,
          probe=lambda d: _assert(abs(d["balance"]["totalIn"] - d["balance"]["usedTce"]
                                      - d["balance"]["lossTce"]) < 0.02, "平衡校验差不为 0"))
    check("碳排报表", "GET", "/api/reports/carbon?period=" + period, token=tok,
          probe=lambda d: _assert(d["total"]["total"] > 0, "碳排总量为 0"))
    check("分时电费", "GET", "/api/tou-summary?period=" + period, token=tok,
          probe=lambda d: _assert(set(d["summary"]["byPeriod"]) == {"尖峰", "峰", "平", "谷"},
                                  "四时段不全"))
    check("需量汇总", "GET", "/api/demands/summary?period=" + period, token=tok)
    check("抄表质检", "GET", "/api/readings/check?period=" + period, token=tok,
          probe=lambda d: _assert(0 < d["coverage"] <= 1, "覆盖率异常"))

    # 5. 业务单据
    check("基线列表", "GET", "/api/baselines", token=tok)
    check("能效测试", "GET", "/api/eff-tests", token=tok)
    check("节能项目", "GET", "/api/projects", token=tok)
    check("告警列表", "GET", "/api/alarms", token=tok,
          probe=lambda d: _assert(d["summary"]["合计"] >= 40, "告警种子数据不足"))
    check("告警统计", "GET", "/api/alarms/summary", token=tok)
    check("能源预算", "GET", "/api/budgets?period=" + period, token=tok)

    # 6. 计算类接口
    check("能效计算", "POST", "/api/eff-tests/calc", token=tok,
          body={"etype": "空压机", "inputPower": 118, "outputQty": 20.5},
          probe=lambda d: (
              _assert(d["value"] == 5.76, "比功率应为 5.76"),
              _assert(d["grade"] == "优", "评级应为优"),
          ))

    # 7. 对接能力
    check("OpenAPI", "GET", "/api/openapi.json",
          probe=lambda d: _assert(len(d["paths"]) >= 45, "OpenAPI 路径不足"))
    check("接口文档页", "GET", "/apidoc", raw=True)
    check("增量同步", "GET", "/api/sync/changes?entity=meters", token=tok,
          probe=lambda d: _assert(d["count"] >= 30, "同步数据不足"))
    check("业务规则", "GET", "/api/rules", token=tok,
          probe=lambda d: _assert(len(d["events"]) == 13, "Webhook 事件应为 13 种"))

    # 8. 权限边界
    check("未授权拦截", "GET", "/api/meters", expect=401)
    check("越权拦截", "GET", "/api/users", expect=403, token=tok_reader(a))

    # 9. CSV 导出（带 UTF-8 BOM，Excel 直接可读）
    st, payload, _h = call(BASE, "GET", "/api/reports/export?type=consumption&period=" + period,
                           token=tok, raw=True)
    if st == 200 and payload.startswith(b"\xef\xbb\xbf"):
        OK.append("CSV 导出（含 BOM）")
    else:
        FAIL.append(("CSV 导出", "HTTP %s / BOM=%s" % (st, payload[:3])))

    report(time.time() - t0)
    return 0 if not FAIL else 1


def tok_reader(a):
    st, js, _h = call(BASE, "POST", "/api/auth/login",
                      body={"username": "reader", "password": PWD})
    return js["data"]["token"] if st == 200 else ""


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def report(elapsed=0.0):
    total = len(OK) + len(FAIL)
    print("\n" + "=" * 62)
    for name in OK:
        print("  [通过] %s" % name)
    for name, why in FAIL:
        print("  [失败] %s — %s" % (name, why))
    print("=" * 62)
    print("合计 %d 项 · 通过 %d · 失败 %d · 耗时 %.2fs"
          % (total, len(OK), len(FAIL), elapsed))
    print("结论：%s" % ("冒烟通过，可以交付" if not FAIL else "存在失败项，需修复后重跑"))


if __name__ == "__main__":
    sys.exit(main())
