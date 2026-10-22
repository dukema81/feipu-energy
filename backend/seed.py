# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 演示数据播种（空库自播，12 个月真实口径数据）"""
import datetime
import hashlib
import random

import db
import energy as E

random.seed(20261022)
PWD = "energy@2026"
CUR = "2026-10"


def h(pw):
    return hashlib.sha256(("feipu$" + pw).encode()).hexdigest()


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def recent_periods(n=12, end=CUR):
    out, y, m = [], int(end[:4]), int(end[5:7])
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


PERIODS = recent_periods(12)

# ---------------- 用户 ----------------
USERS = [
    ("admin", "系统管理员", "admin", "13800000001"),
    ("manager", "能源主管·李工", "manager", "13800000002"),
    ("staff", "能源专员·王敏", "staff", "13800000003"),
    ("reader", "抄表员·赵强", "reader", "13800000004"),
    ("engineer", "设备工程师·陈涛", "engineer", "13800000005"),
    ("prod", "生产经理·刘阳", "prod", "13800000006"),
    ("finance", "财务·周琳", "finance", "13800000007"),
]

# ---------------- 能源介质 ----------------
ENERGY_TYPES = [
    # code, name, unit, tce, co2, scope, price, mode
    ("ELEC", "电力", "kWh", 0.0001229, 0.0005810, "范围二", 0.72, "分时"),
    ("WATER", "自来水", "t", 0.0000857, 0.0001940, "范围二", 4.20, "单一"),
    ("STEAM", "蒸汽", "t", 0.09286, 0.2620, "范围二", 215.0, "单一"),
    ("AIR", "压缩空气", "Nm³", 0.0000400, 0.0000113, "范围二", 0.16, "单一"),
    ("GAS", "天然气", "千m³", 1.3300, 2.1622, "范围一", 3100.0, "单一"),
    ("DIESEL", "柴油", "t", 1.4571, 3.0959, "范围一", 7850.0, "单一"),
]

TARIFF = {"尖峰": 1.28, "峰": 1.02, "平": 0.68, "谷": 0.34}

# ---------------- 成本中心 ----------------
CENTERS = [
    ("CC101", "注塑车间", "生产", "", "刘阳"),
    ("CC102", "冲压车间", "生产", "", "刘阳"),
    ("CC103", "装配车间", "生产", "", "刘阳"),
    ("CC104", "表面处理车间", "生产", "", "孙磊"),
    ("CC201", "动力站", "辅助", "", "陈涛"),
    ("CC202", "空压站", "辅助", "", "陈涛"),
    ("CC301", "生产管理部", "管理", "", "刘阳"),
    ("CC401", "研发中心", "研发", "", "吴静"),
    ("CC501", "仓储物流", "辅助", "", "郑海"),
    ("CC601", "办公综合楼", "办公", "", "周琳"),
]

LINES = [
    ("L1", "注塑一线", "CC101", "P1001", 1800, "件"),
    ("L2", "注塑二线", "CC101", "P1002", 1500, "件"),
    ("L3", "冲压一线", "CC102", "P2001", 2400, "件"),
    ("L4", "装配一线", "CC103", "P3001", 900, "台"),
    ("L5", "装配二线", "CC103", "P3002", 700, "台"),
    ("L6", "表面处理线", "CC104", "P4001", 1200, "件"),
]

# 计量点：code, name, energy, center, line, level, ratio, capacity
METERS = [
    ("EM000", "全厂总表", "ELEC", "CC201", "", 1, 80, 6300),
    ("EM101", "注塑车间总表", "ELEC", "CC101", "", 2, 60, 1200),
    ("EM1011", "注塑一线表", "ELEC", "CC101", "L1", 3, 40, 600),
    ("EM1012", "注塑二线表", "ELEC", "CC101", "L2", 3, 40, 500),
    ("EM102", "冲压车间总表", "ELEC", "CC102", "", 2, 60, 1600),
    ("EM1021", "冲压一线表", "ELEC", "CC102", "L3", 3, 50, 900),
    ("EM103", "装配车间总表", "ELEC", "CC103", "", 2, 60, 900),
    ("EM1031", "装配一线表", "ELEC", "CC103", "L4", 3, 40, 450),
    ("EM1032", "装配二线表", "ELEC", "CC103", "L5", 3, 40, 400),
    ("EM104", "表面处理总表", "ELEC", "CC104", "", 2, 60, 1100),
    ("EM1041", "表面处理线表", "ELEC", "CC104", "L6", 3, 40, 800),
    ("EM201", "动力站辅机表", "ELEC", "CC201", "", 2, 40, 700),
    ("EM202", "空压站总表", "ELEC", "CC202", "", 2, 40, 850),
    ("EM401", "研发中心表", "ELEC", "CC401", "", 2, 40, 300),
    ("EM501", "仓储物流表", "ELEC", "CC501", "", 2, 40, 250),
    ("EM601", "办公综合楼表", "ELEC", "CC601", "", 2, 40, 350),
    ("WM000", "全厂水总表", "WATER", "CC201", "", 1, 1, 0),
    ("WM101", "注塑用水表", "WATER", "CC101", "", 2, 1, 0),
    ("WM104", "表处用水表", "WATER", "CC104", "", 2, 1, 0),
    ("WM601", "办公用水表", "WATER", "CC601", "", 2, 1, 0),
    ("SM000", "蒸汽总表", "STEAM", "CC201", "", 1, 1, 0),
    ("SM104", "表处蒸汽表", "STEAM", "CC104", "L6", 2, 1, 0),
    ("SM103", "装配蒸汽表", "STEAM", "CC103", "", 2, 1, 0),
    ("AM000", "压缩空气总表", "AIR", "CC202", "", 1, 1, 0),
    ("AM101", "注塑用气表", "AIR", "CC101", "", 2, 1, 0),
    ("AM102", "冲压用气表", "AIR", "CC102", "", 2, 1, 0),
    ("AM103", "装配置气表", "AIR", "CC103", "", 2, 1, 0),
    ("GM000", "天然气总表", "GAS", "CC201", "", 1, 1, 0),
    ("GM104", "表处燃气表", "GAS", "CC104", "L6", 2, 1, 0),
    ("DM000", "柴油总表", "DIESEL", "CC501", "", 1, 1, 0),
]

# 月度用量基准（按介质类型给出典型量级）
BASE_USAGE = {
    "ELEC": {"EM000": 0, "CC": 1.0},
}

# 各计量点月基准用量
METER_BASE = {
    "EM000": 620000, "EM101": 148000, "EM1011": 86000, "EM1012": 62000,
    "EM102": 152000, "EM1021": 118000, "EM103": 96000, "EM1031": 52000, "EM1032": 44000,
    "EM104": 134000, "EM1041": 106000, "EM201": 48000, "EM202": 92000,
    "EM401": 26000, "EM501": 18000, "EM601": 32000,
    "WM000": 8600, "WM101": 3200, "WM104": 3600, "WM601": 1800,
    "SM000": 1180, "SM104": 760, "SM103": 420,
    "AM000": 286000, "AM101": 108000, "AM102": 96000, "AM103": 82000,
    "GM000": 46, "GM104": 38,
    "DM000": 3.2,
}

# 节能降耗趋势：越靠后期用量略有下降（体现节能项目成效）
def trend_factor(i, n):
    return 1.0 + (n - 1 - i) * 0.006


EQUIPMENTS = [
    ("EQ-A01", "螺杆空压机 1#", "空压机", "CC202", 132, 22.0, "132kW / 22 m³/min"),
    ("EQ-A02", "螺杆空压机 2#", "空压机", "CC202", 110, 19.5, "110kW / 19.5 m³/min"),
    ("EQ-A03", "离心空压机 3#", "空压机", "CC202", 250, 42.0, "250kW / 42 m³/min"),
    ("EQ-P01", "循环水泵 1#", "水泵", "CC201", 45, 0, "45kW / 380 m³/h / 32m"),
    ("EQ-P02", "循环水泵 2#", "水泵", "CC201", 37, 0, "37kW / 320 m³/h / 28m"),
    ("EQ-B01", "燃气蒸汽锅炉", "锅炉", "CC201", 0, 0, "4 t/h 燃气"),
    ("EQ-C01", "离心式冷水机 1#", "制冷机", "CC601", 185, 0, "185kW / 1000RT"),
    ("EQ-C02", "螺杆冷水机 2#", "制冷机", "CC601", 110, 0, "110kW / 620RT"),
]

PROJECTS = [
    ("SP2026-001", "空压机余热回收改造", "CC202", "", "BL-L6", 268000,
     "加装板式换热器回收螺杆机余热用于员工洗浴，替代燃气锅炉", "2026-03", "2026-05", "2026-09",
     "陈涛", "已验证"),
    ("SP2026-002", "注塑机伺服改造", "CC101", "L1", "BL-L1", 420000,
     "3 台注塑机液压系统改造为伺服驱动，降低空载损耗", "2026-02", "2026-04", "2026-09",
     "陈涛", "已验证"),
    ("SP2026-003", "LED 照明全面替换", "CC601", "", "", 86000,
     "厂区与办公楼 1200 套灯具替换为 LED，配人体感应", "2026-05", "2026-06", "",
     "王敏", "实施中"),
    ("SP2026-004", "空压管网泄漏治理", "CC202", "", "BL-L6", 52000,
     "全厂压缩空气管路泄漏点排查封堵，加装分区流量计", "2026-07", "2026-08", "",
     "陈涛", "实施中"),
    ("SP2026-005", "冲压线变频改造", "CC102", "L3", "BL-L3", 310000,
     "冲压主电机加装变频器，按节拍调速运行", "2026-06", "2026-09", "2026-10",
     "陈涛", "待验证"),
    ("SP2026-006", "表处槽液加热电改气", "CC104", "L6", "BL-L6", 175000,
     "表面处理槽液由电加热改为燃气加热", "2026-01", "2026-03", "2026-09",
     "陈涛", "未达标"),
]


def seed():
    conn = db.connect()
    if db.val("SELECT COUNT(*) FROM users"):
        return False

    t = now()

    # 用户
    for u, name, role, phone in USERS:
        conn.execute("INSERT INTO users(username,password_hash,name,role,phone,status,created_at) "
                     "VALUES(?,?,?,?,?,'启用',?)", (u, h(PWD), name, role, phone, t))

    # 介质
    for code, name, unit, tce, co2, scope, price, mode in ENERGY_TYPES:
        conn.execute("INSERT INTO energy_types(code,name,unit,tce_factor,co2_factor,scope,price,price_mode,status) "
                     "VALUES(?,?,?,?,?,?,?,?,'启用')", (code, name, unit, tce, co2, scope, price, mode))
        if mode == "分时":
            for p in E.PERIODS:
                conn.execute("INSERT INTO tariffs(energy_code,period,price,month) VALUES(?,?,?,?)",
                             (code, p, TARIFF[p], "全年"))

    # 中心 / 产线
    for code, name, ctype, parent, mgr in CENTERS:
        conn.execute("INSERT INTO cost_centers(code,name,ctype,parent,manager) VALUES(?,?,?,?,?)",
                     (code, name, ctype, parent, mgr))
    for code, name, center, product, cap, unit in LINES:
        conn.execute("INSERT INTO lines(code,name,center,product,capacity,unit,status) "
                     "VALUES(?,?,?,?,?,?,'运行')", (code, name, center, product, cap, unit))

    # 计量点
    for code, name, ec, center, line, level, ratio, cap in METERS:
        gw = "采集网关" if level <= 2 and ec == "ELEC" else ("采集网关" if code in ("WM000", "SM000", "AM000", "GM000") else "人工抄表")
        conn.execute("INSERT INTO meters(code,name,energy_code,center,line,level,ratio,capacity,gateway,"
                     "install_date,status) VALUES(?,?,?,?,?,?,?,?,?,?,'运行')",
                     (code, name, ec, center, line, level, ratio, cap, gw, "2023-06-01"))

    # 产量与产值
    line_qty_base = {"L1": 82000, "L2": 66000, "L3": 96000, "L4": 1800, "L5": 1400, "L6": 42000}
    line_price = {"L1": 28.0, "L2": 34.0, "L3": 16.0, "L4": 1280.0, "L5": 980.0, "L6": 12.0}
    out_rows = []
    for i, p in enumerate(PERIODS):
        f = trend_factor(i, len(PERIODS))
        for code, name, center, product, cap, unit in LINES:
            qty = line_qty_base[code] * (f + random.uniform(-0.03, 0.03))
            out_rows.append((p, center, code, product, round(qty, 0), unit,
                             round(qty * line_price[code] / 10000.0, 2)))
        # 中心级（无产线的中心）产值
        for cc in ("CC201", "CC301", "CC401", "CC501", "CC601"):
            out_rows.append((p, cc, "", "", 0, "件", round(random.uniform(18, 46), 2)))
    conn.executemany("INSERT INTO outputs(period,center,line,product,qty,unit,value_wan) "
                     "VALUES(?,?,?,?,?,?,?)", out_rows)

    # 抄表：12 个月
    reading_rows = []
    for i, p in enumerate(PERIODS):
        f = trend_factor(i, len(PERIODS))
        for code, name, ec, center, line, level, ratio, cap in METERS:
            base = METER_BASE.get(code, 0)
            usage = base * f * (1 + random.uniform(-0.055, 0.055))
            quality, est = "正常", 0
            if random.random() < 0.035:
                quality, est = "估算", 1
            reading_rows.append((code, p, p + "-28", round(random.uniform(10000, 99000) + i * 1000, 1),
                                 round(usage, 1), est, quality,
                                 "采集网关" if code.startswith(("EM", "WM0", "SM0", "AM0", "GM0")) else "手工",
                                 "system", t))
    conn.executemany("INSERT INTO readings(meter_code,period,date,reading,usage,is_estimate,quality,"
                     "source,operator,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", reading_rows)

    # 分时电量：近 40 天，主表 EM000
    interval_rows = []
    today = datetime.date(2026, 10, 22)
    for d in range(40):
        day = today - datetime.timedelta(days=39 - d)
        daily = 20500 * (1 + random.uniform(-0.06, 0.06))
        split = {"尖峰": 0.10, "峰": 0.28, "平": 0.37, "谷": 0.25}
        for p in E.PERIODS:
            interval_rows.append(("EM000", day.isoformat(), p,
                                  round(daily * split[p], 1), TARIFF[p]))
    conn.executemany("INSERT OR IGNORE INTO intervals(meter_code,date,period,kwh,price) "
                     "VALUES(?,?,?,?,?)", interval_rows)

    # 需量：近 30 天，每小时一条，早晚高峰抬高
    demand_rows = []
    for d in range(30):
        day = today - datetime.timedelta(days=29 - d)
        for hr in range(24):
            base = 3600 if 8 <= hr <= 18 else 2200
            k = 1.0
            if hr in (9, 10, 14, 15):
                k = 1.42
            if hr in (0, 1, 2, 3, 4, 5):
                k = 0.62
            v = base * k * (1 + random.uniform(-0.05, 0.07))
            cap = 6300
            over = 1 if v > cap else 0
            ts = "%s %02d:00:00" % (day.isoformat(), hr)
            demand_rows.append(("CC201", day.isoformat(), ts, round(v, 1), cap, over, "采集"))
    conn.executemany("INSERT OR IGNORE INTO demands(center,date,ts,demand_kw,capacity_kw,over,source) "
                     "VALUES(?,?,?,?,?,?,?)", demand_rows)

    # 基线
    baseline_rows = [
        ("BL-L1", "L1", "P1001", "2025-11", "2026-01",
         round(METER_BASE["EM1011"] * 0.0001229 / line_qty_base["L1"] * 1.10, 6), 0, 0, "单位产品能耗", "生效"),
        ("BL-L3", "L3", "P2001", "2025-11", "2026-01",
         round(METER_BASE["EM1021"] * 0.0001229 / line_qty_base["L3"] * 1.12, 6), 0, 0, "单位产品能耗", "生效"),
        ("BL-L6", "L6", "P4001", "2025-11", "2026-01",
         round((METER_BASE["EM1041"] * 0.0001229 + METER_BASE["SM104"] * 0.09286
                + METER_BASE["GM104"] * 1.33) / line_qty_base["L6"] * 1.15, 6), 0, 0, "综合能耗", "生效"),
        ("BL-L4", "L4", "P3001", "2025-11", "2026-01",
         round(METER_BASE["EM1031"] * 0.0001229 / line_qty_base["L4"] * 1.08, 6), 0, 0, "单位产品能耗", "生效"),
        ("BL-L5", "L5", "P3002", "2025-11", "2026-01",
         round(METER_BASE["EM1032"] * 0.0001229 / line_qty_base["L5"] * 1.08, 6), 0, 0, "单位产品能耗", "生效"),
        ("BL-CC202", "", "", "2025-11", "2026-01", 0.0, 0, 0, "综合能耗", "生效"),
    ]
    for code, line, prod, pf, pt, bu, tt, qq, m, st in baseline_rows:
        conn.execute("INSERT INTO baselines(code,line,product,period_from,period_to,base_unit,"
                     "total_tce,qty,method,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (code, line, prod, pf, pt, bu, tt, qq, m, st, t))

    # 设备
    for code, name, etype, center, rp, ro, spec in EQUIPMENTS:
        conn.execute("INSERT INTO equipments(code,name,etype,center,rated_power,rated_output,spec,"
                     "status,install_date) VALUES(?,?,?,?,?,?,?,'运行','2022-09-01')",
                     (code, name, etype, center, rp, ro, spec))

    # 能效测试：每台 3 次（递减趋势，部分劣化）
    eff_rows = []
    for idx, (code, name, etype, center, rp, ro, spec) in enumerate(EQUIPMENTS):
        for j, p in enumerate(["2026-02", "2026-06", "2026-10"]):
            age = j * (1 + idx % 3) * 0.015
            if etype == "空压机":
                ip, oq = rp * (0.86 + age), ro * (1 - age * 0.5)
                r = E.eff_calc(etype, input_power=ip, output_qty=oq)
            elif etype == "水泵":
                ip, okw = rp * (0.88 + age), rp * 0.70 * (1 - age)
                r = E.eff_calc(etype, input_power=ip, output_kw=okw)
            elif etype == "锅炉":
                r = E.eff_calc(etype, heat_in=2840, heat_out=2840 * (0.925 - age))
            else:
                ip, okw = rp * (0.87 + age), rp * 4.8 * (1 - age)
                r = E.eff_calc(etype, input_power=ip, output_kw=okw)
            eff_rows.append((code, p + "-15", round(ip if etype != "锅炉" else 2840, 1),
                             round(ro, 2) if etype == "空压机" else 0,
                             round(okw, 1) if etype in ("水泵", "制冷机") else 0,
                             2840 if etype == "锅炉" else 0,
                             round(2840 * (0.925 - age), 1) if etype == "锅炉" else 0,
                             r["value"], r["metric"], r["grade"], "陈涛", ""))
    conn.executemany("INSERT INTO eff_tests(equipment_code,date,input_power,output_qty,output_kw,"
                     "heat_in,heat_out,value,metric,grade,tester,remark) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     eff_rows)

    # 项目
    for (no, name, center, line, bl, inv, measure, sp, ep, vp, owner, st) in PROJECTS:
        conn.execute("INSERT INTO projects(no,name,center,line,baseline_code,invest,measure,"
                     "start_period,end_period,verify_period,owner,status,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (no, name, center, line, bl, inv, measure, sp, ep, vp, owner, st, t))

    # 项目验证记录（针对已验证/未达标）
    ver_rows = []
    for no, verdict_period, delta in [("SP2026-001", "2026-09", -0.072), ("SP2026-002", "2026-09", -0.061),
                                      ("SP2026-006", "2026-09", 0.038)]:
        p = db.one("SELECT * FROM projects WHERE no=?", (no,))
        if not p:
            continue
        bl = db.one("SELECT * FROM baselines WHERE code=?", (p["baseline_code"],)) if p["baseline_code"] else None
        base_unit = bl["base_unit"] if bl else 0.0
        report_unit = base_unit * (1 + delta)
        qty = {"SP2026-001": 3000, "SP2026-002": 82000, "SP2026-006": 42000}.get(no, 1000)
        r = E.project_verify(base_unit, report_unit, qty, p["invest"], E.DEFAULT_RULES["tce_price"])
        ver_rows.append((no, verdict_period, base_unit, round(report_unit, 6), qty,
                         r["savingTce"], r["savingRate"], r["savingFeeYear"],
                         r["paybackYear"], r["verdict"], ""))
    conn.executemany("INSERT INTO project_verify(project_no,period,base_unit,report_unit,qty,"
                     "saving_tce,saving_rate,saving_fee,payback,verdict,remark,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     [r + (t,) for r in ver_rows])

    # 预算
    budget_rows = []
    for p in PERIODS[-4:]:
        for cc, ec, amt in [("CC101", "ELEC", 112000), ("CC102", "ELEC", 118000),
                            ("CC103", "ELEC", 74000), ("CC104", "ELEC", 104000),
                            ("CC202", "ELEC", 70000), ("CC104", "STEAM", 96000),
                            ("CC101", "WATER", 15000), ("CC601", "WATER", 8000),
                            ("CC104", "GAS", 122000), ("CC501", "DIESEL", 26000),
                            ("CC202", "AIR", 46000), ("CC201", "ELEC", 38000)]:
            used = amt * (0.78 + random.uniform(0, 0.30))
            budget_rows.append((p, cc, ec, amt, round(used, 2)))
    conn.executemany("INSERT OR IGNORE INTO budgets(period,center,energy_code,amount,used) "
                     "VALUES(?,?,?,?,?)", budget_rows)

    # 规则
    for k, v in E.DEFAULT_RULES.items():
        conn.execute("INSERT OR REPLACE INTO rules(key,value,remark) VALUES(?,?,?)",
                     (k, str(v), "系统默认"))

    # 同步游标
    for ent in ("energy_types", "meters", "readings", "alarms", "projects", "demands"):
        conn.execute("INSERT OR REPLACE INTO sync_state(entity,version,updated_at) VALUES(?,?,?)",
                     (ent, 1, t))

    conn.commit()

    # 生成告警（基于真实数据）
    _gen_alarms(conn)
    conn.commit()
    return True


def _gen_alarms(conn):
    rows = []
    n = 0

    def add(level, atype, target, msg, value, threshold, period, status="待处置"):
        nonlocal n
        n += 1
        rows.append(("AL%s%04d" % (period.replace("-", "") if period else "202610", n),
                     level, atype, target, msg, value, threshold, period, status))

    # 需量告警：取最近 30 天大需量
    top = db.rows("SELECT * FROM demands ORDER BY demand_kw DESC LIMIT 6")
    for r in top:
        st = E.demand_status(r["demand_kw"], r["capacity_kw"])
        if st["status"] in ("紧急", "超容", "预警"):
            lv = "紧急" if st["status"] in ("紧急", "超容") else "严重"
            add(lv, "需量超限", "CC201",
                "需量 %.1f kW 达容量 %.0f kW 的 %.0f%%" % (r["demand_kw"], r["capacity_kw"], st["rate"] * 100),
                r["demand_kw"], r["capacity_kw"], r["date"][:7])

    # 单耗告警：本月各产线对比基线
    for bl in db.rows("SELECT * FROM baselines WHERE line<>''"):
        line = bl["line"]
        rt = db.one("SELECT * FROM readings WHERE period=? AND meter_code IN "
                    "(SELECT code FROM meters WHERE line=?) ", (CUR, line))
        if not rt:
            continue
        o = db.one("SELECT qty FROM outputs WHERE period=? AND line=?", (CUR, line))
        if not o or not o["qty"]:
            continue
        tce = rt["usage"] * 0.0001229
        ue = E.unit_energy(tce, o["qty"])
        lv = E.intensity_alarm(ue, bl["base_unit"])
        if lv:
            add(lv, "单耗异常", line, "%s 单位能耗 %.6f tce/单位，超基线 %.1f%%" % (
                line, ue, (ue / bl["base_unit"] - 1) * 100), ue, bl["base_unit"], CUR)

    # 抄表质量告警
    bad = db.rows("SELECT * FROM readings WHERE period=? AND quality<>'正常' LIMIT 5", (CUR,))
    for r in bad:
        add("警告", "抄表异常", r["meter_code"],
            "计量点 %s %s 抄表为%s口径，请核实" % (r["meter_code"], r["period"], r["quality"]),
            r["usage"], 0, r["period"])

    # 能效劣化告警
    for eq in db.rows("SELECT * FROM equipments"):
        ts = db.rows("SELECT * FROM eff_tests WHERE equipment_code=? ORDER BY date", (eq["code"],))
        if len(ts) >= 2:
            d = E.eff_delta(ts[-1]["value"], ts[-2]["value"], eq["etype"])
            if d["degraded"]:
                add("提示", "能效劣化", eq["code"],
                    "%s %s %s 由 %.2f 变为 %.2f" % (eq["code"], eq["name"], eq["etype"],
                                                   ts[-2]["value"], ts[-1]["value"]),
                    ts[-1]["value"], ts[-2]["value"], CUR)

    # 预算预警
    for b in db.rows("SELECT * FROM budgets WHERE period=?", (CUR,)):
        st = E.budget_state(b["amount"], b["used"])
        if st["status"] in ("预警", "超支", "阻断"):
            add("严重" if st["status"] != "预警" else "警告", "预算预警",
                b["center"] + "/" + b["energy_code"],
                "%s %s 预算执行率 %.1f%%（%s）" % (b["center"], b["energy_code"], st["rate"] * 100, st["status"]),
                st["rate"] * 100, 100, CUR)

    # 补足到 40 条（历史提示类）
    while len(rows) < 40:
        n += 1
        p = PERIODS[-(len(rows) % 6 + 2)]
        rows.append(("AL%s%04d" % (p.replace("-", ""), n), "提示", "抄表逾期",
                     "M-WM601", "办公用水表 %s 抄表日期晚于月末，已按估算值补录" % p, 0, 0, p,
                     "已处置" if len(rows) % 3 == 0 else "待处置"))

    for r in rows:
        conn.execute("INSERT OR IGNORE INTO alarms(no,level,atype,target,message,value,threshold,"
                     "period,status) VALUES(?,?,?,?,?,?,?,?,?)", r)
