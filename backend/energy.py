# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 业务内核（纯函数，零依赖，可单测）

覆盖：折标煤、能耗强度、分时电费、15 分钟需量、设备能效、节能量验证、
碳排核算、告警分级、抄表数据质量校验、能源平衡、预算。
"""

# ---------- 工具 ----------

def q2(v):
    """两位小数四舍五入（银行家舍入的实际业务口径：四舍五入）。"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return float("%.2f" % (x + (1e-9 if x >= 0 else -1e-9)))


def q4(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return float("%.4f" % (x + (1e-12 if x >= 0 else -1e-12)))


def q0(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def safe_num(v, default=0.0):
    if v is None or v == "" or v == "-":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def div(a, b, default=0.0):
    a, b = safe_num(a), safe_num(b)
    if b == 0:
        return default
    return a / b


def cur_period():
    import datetime
    return datetime.date.today().strftime("%Y-%m")


def prev_period(p):
    y, m = int(p[:4]), int(p[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return "%04d-%02d" % (y, m)


def period_range(p_from, p_to):
    """含两端的期间序列。"""
    out, y, m = [], int(p_from[:4]), int(p_from[5:7])
    ey, em = int(p_to[:4]), int(p_to[5:7])
    while (y, m) <= (ey, em):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def period_days(p):
    import calendar
    y, m = int(p[:4]), int(p[5:7])
    return calendar.monthrange(y, m)[1]


# ---------- 折标煤 / 碳排 ----------

# 常见介质的默认系数（可被介质表覆盖）
DEFAULT_TCE = {
    "ELEC": 0.0001229,      # tce / kWh（等价值）
    "WATER": 0.0000857,     # tce / t
    "STEAM": 0.09286,       # tce / t
    "AIR": 0.00004,         # tce / Nm³（压缩空气按等价值折算）
    "GAS": 1.33,            # tce / 千 m³
    "DIESEL": 1.4571,       # tce / t
}
DEFAULT_CO2 = {
    "ELEC": 0.0005810,      # tCO2 / kWh（区域电网排放因子）
    "WATER": 0.0001940,     # tCO2 / t
    "STEAM": 0.0000000,     # 由介质表覆盖（外购蒸汽按供方数据）
    "AIR": 0.0000113,
    "GAS": 2.1622,          # tCO2 / 千 m³
    "DIESEL": 3.0959,       # tCO2 / t
}
SCOPE_MAP = {"ELEC": "范围二", "STEAM": "范围二", "WATER": "范围二",
             "AIR": "范围二", "GAS": "范围一", "DIESEL": "范围一"}


def to_tce(qty, factor):
    """物理量 → 吨标煤。factor: tce/单位。"""
    return q2(safe_num(qty) * safe_num(factor))


def to_co2(qty, factor):
    """物理量 → 吨 CO2。"""
    return q4(safe_num(qty) * safe_num(factor))


def tce_total(rows):
    """rows: [{qty, tceFactor}] → 合计折标煤。"""
    return q2(sum(safe_num(r.get("qty")) * safe_num(r.get("tceFactor")) for r in rows))


def co2_total(rows):
    """rows: [{qty, co2Factor, scope}] → 合计碳排，并按范围一/二拆分。
    scope 缺失时按 energy 编码回退到 SCOPE_MAP。
    """
    s1 = s2 = 0.0
    for r in rows:
        scope = r.get("scope") or SCOPE_MAP.get(r.get("energy"), "范围二")
        v = safe_num(r.get("qty")) * safe_num(r.get("co2Factor"))
        if scope == "范围一":
            s1 += v
        else:
            s2 += v
    return {"scope1": q4(s1), "scope2": q4(s2), "total": q4(s1 + s2),
            "checkDiff": 0.0}


def carbon_intensity(co2, value_wan):
    """碳强度 tCO2 / 万元产值。"""
    return q4(div(co2, value_wan))


# ---------- 能耗强度 ----------

def unit_energy(tce, qty):
    """单位产品能耗 tce/单位（6 位，小量级不失真）。"""
    return q6(div(tce, qty))


def value_energy(tce, value_wan):
    """单位产值能耗 tce/万元。"""
    return q6(div(tce, value_wan))


def intensity_pack(tce, qty, value_wan):
    return {"tce": q2(tce), "qty": q2(qty), "valueWan": q2(value_wan),
            "unitEnergy": unit_energy(tce, qty),
            "valueEnergy": value_energy(tce, value_wan),
            "carbon": None}


def yoy(cur, prev):
    """同比/环比：返回 {cur, prev, diff, rate}。"""
    c, p = safe_num(cur), safe_num(prev)
    diff = q2(c - p)
    rate = q4(div(diff, p))
    return {"cur": q2(c), "prev": q2(p), "diff": diff, "rate": rate}


# ---------- 分时电费 ----------

PERIODS = ("尖峰", "峰", "平", "谷")


def tou_fee(intervals, tariff):
    """分时电费。
    intervals: [{period, kwh}]；tariff: {尖峰: 1.2, 峰: 1.0, 平: 0.65, 谷: 0.32}
    返回 {byPeriod, energyFee, kwhTotal, checkDiff}
    """
    by = {}
    total_kwh = 0.0
    fee = 0.0
    for p in PERIODS:
        kwh = 0.0
        for it in intervals:
            if (it.get("period") or "") == p:
                kwh += safe_num(it.get("kwh"))
        price = safe_num(tariff.get(p))
        amt = q2(kwh * price)
        by[p] = {"kwh": q2(kwh), "price": q2(price), "amount": amt}
        total_kwh += kwh
        fee += amt
    return {"byPeriod": by, "energyFee": q2(fee), "kwhTotal": q2(total_kwh),
            "avgPrice": q4(div(fee, total_kwh)),
            "checkDiff": q2(fee - sum(v["amount"] for v in by.values()))}


def capacity_fee(max_demand_kw, demand_price, basic_kva=None, basic_price=None):
    """容量/需量电费。两种计费方式取其一。"""
    by_demand = q2(safe_num(max_demand_kw) * safe_num(demand_price))
    by_capacity = q2(safe_num(basic_kva) * safe_num(basic_price)) if basic_kva is not None else None
    return {"byDemand": by_demand, "byCapacity": by_capacity,
            "chosen": by_capacity if by_capacity is not None else by_demand,
            "mode": "按容量" if by_capacity is not None else "按需量"}


def power_factor_fee(energy_fee, pf, standard=0.90):
    """力调电费（简化）：功率因数低于标准按比例加收，高于按比例奖励。
    规则：每低于标准 0.01，加收 0.5%；每高于标准 0.01，减免 0.15%（上限 ±15%）。
    """
    pf = safe_num(pf)
    if pf <= 0:
        return {"rate": 0.0, "amount": 0.0, "note": "无功率因数数据"}
    delta = pf - safe_num(standard, 0.90)
    # delta 以「0.01 为一档」计：低于标准每档加收 0.5%，高于标准每档减免 0.15%
    steps = abs(delta) * 100.0
    if delta < 0:
        rate = steps * 0.005      # 加收（正值）
    else:
        rate = -steps * 0.0015    # 减免（负值）
    rate = max(-0.15, min(0.15, rate))
    return {"rate": q4(rate), "amount": q2(safe_num(energy_fee) * rate),
            "note": "加收" if rate > 0 else ("减免" if rate < 0 else "不奖不罚")}


# ---------- 需量 ----------

def demand_15min(kwh_in_15min):
    """15 分钟电能 → 需量 kW。"""
    return q2(safe_num(kwh_in_15min) / 0.25)


def demand_from_hourly(kwh):
    """仅有小时电量时的近似需量。"""
    return q2(safe_num(kwh) / 1.0)


def demand_status(demand_kw, capacity_kw, warn=0.85, urgent=0.95):
    """需量状态：正常/预警/紧急/超容。"""
    r = div(demand_kw, capacity_kw)
    if r >= 1.0:
        st = "超容"
    elif r >= urgent:
        st = "紧急"
    elif r >= warn:
        st = "预警"
    else:
        st = "正常"
    return {"demandKw": q2(demand_kw), "capacityKw": q2(capacity_kw),
            "rate": q4(r), "status": st, "overKw": q2(max(0.0, safe_num(demand_kw) - safe_num(capacity_kw)))}


def max_demand(records):
    """records: [{demandKw, ts}] → 最大需量及发生时间。"""
    best = None
    for r in records:
        v = safe_num(r.get("demandKw"))
        if best is None or v > best["demandKw"]:
            best = {"demandKw": q2(v), "ts": r.get("ts") or r.get("time") or ""}
    return best or {"demandKw": 0.0, "ts": ""}


# ---------- 设备能效 ----------

EFF_SPEC = {
    "空压机": {"metric": "比功率 kW/(m³/min)", "unit": "kW/(m³/min)",
             "good": 6.3, "fair": 7.2, "lower_better": True},
    "水泵": {"metric": "运行效率 %", "unit": "%", "good": 75.0, "fair": 65.0, "lower_better": False},
    "锅炉": {"metric": "热效率 %", "unit": "%", "good": 92.0, "fair": 88.0, "lower_better": False},
    "制冷机": {"metric": "COP", "unit": "", "good": 5.0, "fair": 4.0, "lower_better": False},
}


def eff_grade(value, etype):
    """按设备类型评级：优 / 良 / 差。"""
    spec = EFF_SPEC.get(etype)
    if not spec:
        return "未知"
    v = safe_num(value)
    if spec["lower_better"]:
        if v <= spec["good"]:
            return "优"
        if v <= spec["fair"]:
            return "良"
        return "差"
    if v >= spec["good"]:
        return "优"
    if v >= spec["fair"]:
        return "良"
    return "差"


def eff_calc(etype, input_power=0, output_qty=0, output_kw=0, hours=1, heat_in=0, heat_out=0):
    """设备能效计算。
    空压机：比功率 = 输入功率 kW ÷ 排气量 (m³/min)
    水泵：效率 = 有效功率 ÷ 轴功率；有效功率 = ρgQH/1000（可用 output_kw 直接给）
    锅炉：热效率 = 有效吸热 ÷ 输入热量
    制冷机：COP = 制冷量 kW ÷ 输入功率 kW
    """
    ip = safe_num(input_power)
    if etype == "空压机":
        val = q2(div(ip, safe_num(output_qty)))
        return {"etype": etype, "metric": "比功率", "value": val, "unit": "kW/(m³/min)",
                "grade": eff_grade(val, etype)}
    if etype == "水泵":
        val = q2(div(safe_num(output_kw), ip) * 100)
        return {"etype": etype, "metric": "运行效率", "value": val, "unit": "%",
                "grade": eff_grade(val, etype)}
    if etype == "锅炉":
        val = q2(div(safe_num(heat_out), safe_num(heat_in)) * 100)
        return {"etype": etype, "metric": "热效率", "value": val, "unit": "%",
                "grade": eff_grade(val, etype)}
    if etype == "制冷机":
        val = q2(div(safe_num(output_kw), ip))
        return {"etype": etype, "metric": "COP", "value": val, "unit": "",
                "grade": eff_grade(val, etype)}
    return {"etype": etype, "metric": "未知", "value": 0.0, "unit": "", "grade": "未知"}


def eff_delta(cur_value, last_value, etype):
    """能效劣化判定：返回 {delta, degraded}。"""
    spec = EFF_SPEC.get(etype) or {}
    d = q2(safe_num(cur_value) - safe_num(last_value))
    if spec.get("lower_better"):
        degraded = d > 0 and abs(d) / max(safe_num(last_value), 1e-9) > 0.05
    else:
        degraded = d < 0 and abs(d) / max(safe_num(last_value), 1e-9) > 0.05
    return {"delta": d, "degraded": degraded}


# ---------- 节能量与项目收益 ----------

def saving(base_unit, report_unit, qty):
    """节能量 =（基线单耗 − 报告期单耗）× 产量。"""
    b, r, q = safe_num(base_unit), safe_num(report_unit), safe_num(qty)
    s = q2((b - r) * q)
    rate = q4(div(b - r, b))
    return {"baseUnit": q4(b), "reportUnit": q4(r), "qty": q2(q),
            "savingTce": s, "savingRate": rate, "achieved": s > 0}


def saving_fee(saving_tce, price_per_tce):
    """节能费 = 节能量 × 单位标煤价格。"""
    return q2(safe_num(saving_tce) * safe_num(price_per_tce))


def payback(invest, annual_fee):
    """投资回收期（年）。"""
    return q2(div(safe_num(invest), safe_num(annual_fee)))


def project_verify(base_unit, report_unit, qty, invest, price_per_tce, months=12):
    """项目验证打包：节能量、节能率、年节费、回收期。"""
    s = saving(base_unit, report_unit, qty)
    fee_year = saving_fee(s["savingTce"] * (12.0 / max(months, 1)), price_per_tce)
    pb = payback(invest, fee_year)
    return {"baseUnit": s["baseUnit"], "reportUnit": s["reportUnit"], "qty": s["qty"],
            "savingTce": s["savingTce"], "savingRate": s["savingRate"],
            "savingFeeYear": fee_year, "invest": q2(invest), "paybackYear": pb,
            "achieved": s["achieved"],
            "verdict": "达标" if s["achieved"] else "未达标"}


def baseline_unit(total_tce, qty):
    """基线单位能耗（保留 6 位，避免小量级单耗被取整失真）。"""
    return q6(div(total_tce, qty))


def q6(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return float("%.6f" % (x + (1e-13 if x >= 0 else -1e-13)))


# ---------- 告警 ----------

ALARM_LEVELS = ("紧急", "严重", "警告", "提示")


def alarm_level(value, threshold, warn_ratio=0.85, urgent_ratio=0.95):
    """按阈值比例分级（用于需量这类"越高越糟"的指标）。"""
    r = div(value, threshold)
    if r >= 1.0:
        return "紧急"
    if r >= urgent_ratio:
        return "紧急"
    if r >= warn_ratio:
        return "严重"
    return "正常"


def intensity_alarm(unit_energy, base_unit):
    """单耗偏离基线分级：>30% 紧急，>15% 严重，>8% 警告。"""
    if safe_num(base_unit) <= 0:
        return None
    dev = div(safe_num(unit_energy) - safe_num(base_unit), safe_num(base_unit))
    if dev > 0.30:
        return "紧急"
    if dev > 0.15:
        return "严重"
    if dev > 0.08:
        return "警告"
    return None


def level_rank(level):
    return {"紧急": 1, "严重": 2, "警告": 3, "提示": 4}.get(level, 9)


def alarm_summary(rows):
    out = {k: 0 for k in ALARM_LEVELS}
    out["未处置"] = 0
    for r in rows:
        lv = r.get("level")
        if lv in out:
            out[lv] += 1
        if (r.get("status") or "") in ("待处置", "未处置", ""):
            out["未处置"] += 1
    out["合计"] = len(rows)
    return out


# ---------- 抄表数据质量 ----------

JUMP_RATIO = 3.0
JUMP_MIN = 100.0


def reading_usage(last_reading, cur_reading, ratio=1.0):
    """表底差 → 用量（乘倍率）。返回 {usage, reverse, delta}。"""
    a, b = safe_num(last_reading), safe_num(cur_reading)
    delta = b - a
    return {"delta": q2(delta), "ratio": q2(ratio),
            "usage": q2(delta * safe_num(ratio, 1.0)), "reverse": delta < 0}


def reading_check(last_usage, cur_usage, ratio=JUMP_RATIO, floor=JUMP_MIN):
    """量级跳变校验。返回 {jump, factor, level}。"""
    lu, cu = safe_num(last_usage), safe_num(cur_usage)
    if lu <= 0:
        return {"jump": False, "factor": 0.0, "level": None}
    f = cu / lu
    if cu > lu * safe_num(ratio, 3.0) and cu >= safe_num(floor, 100.0):
        return {"jump": True, "factor": q2(f), "level": "警告"}
    if cu < lu / safe_num(ratio, 3.0) and lu >= safe_num(floor, 100.0):
        return {"jump": True, "factor": q2(f), "level": "警告"}
    return {"jump": False, "factor": q2(f), "level": None}


def meter_change_usage(old_last, old_at_change, new_first):
    """换表用量：(换表时旧表底 − 上期表底) + (新表首底 − 0)。"""
    return q2((safe_num(old_at_change) - safe_num(old_last)) + safe_num(new_first))


def coverage(meters_total, meters_reported):
    """抄表覆盖率。"""
    return q4(div(meters_reported, meters_total))


def fill_gap(usages, idx):
    """缺口补值：取同位置前后有效值的均值，都没有则取整体均值。"""
    n = len(usages)
    if n == 0:
        return 0.0
    fwd = None
    for i in range(idx + 1, n):
        if usages[i] is not None:
            fwd = safe_num(usages[i])
            break
    bwd = None
    for i in range(idx - 1, -1, -1):
        if usages[i] is not None:
            bwd = safe_num(usages[i])
            break
    if fwd is not None and bwd is not None:
        return q2((fwd + bwd) / 2.0)
    if fwd is not None:
        return q2(fwd)
    if bwd is not None:
        return q2(bwd)
    vals = [safe_num(u) for u in usages if u is not None]
    return q2(div(sum(vals), len(vals)))


# ---------- 能源平衡 ----------

def energy_balance(total_in, items):
    """能源平衡表：items 为 [{name, qty, tce}]，返回合计、损耗与校验差。"""
    used = q2(sum(safe_num(i.get("tce")) for i in items))
    total = q2(total_in)
    loss = q2(total - used)
    rate = q4(div(loss, total))
    return {"totalIn": total, "usedTce": used, "lossTce": loss,
            "lossRate": rate, "checkDiff": q2(total - used - loss)}


def budget_state(budget, used, warn=0.90, over=1.0, block=1.10):
    """能源预算闸口。"""
    b, u = safe_num(budget), safe_num(used)
    rate = div(u, b)
    if rate > block:
        st = "阻断"
    elif rate > over:
        st = "超支"
    elif rate >= warn:
        st = "预警"
    else:
        st = "正常"
    return {"budget": q2(b), "used": q2(u), "left": q2(b - u),
            "rate": q4(rate), "status": st, "blocked": rate > block}


# ---------- 角色与权限 ----------

ROLES = {
    "admin": "系统管理员",
    "manager": "能源主管",
    "staff": "能源专员",
    "reader": "抄表员",
    "engineer": "设备工程师",
    "prod": "生产经理",
    "finance": "财务",
}

PERMS = [
    "energy.read", "energy.write",
    "center.read", "center.write",
    "meter.read", "meter.write",
    "read.read", "read.write", "read.check",
    "equip.read", "equip.write",
    "base.read", "base.write",
    "proj.read", "proj.write", "proj.verify",
    "alarm.read", "alarm.write",
    "report.read",
    "budget.read", "budget.write",
    "sync.read",
    "sys.user", "sys.rule", "sys.key", "sys.hook", "sys.log",
]

ROLE_PERMS = {
    "admin": set(PERMS),
    "manager": {"energy.read", "energy.write", "center.read", "meter.read", "meter.write",
                "read.read", "read.write", "read.check", "equip.read", "equip.write",
                "base.read", "base.write", "proj.read", "proj.write", "proj.verify",
                "alarm.read", "alarm.write", "report.read", "budget.read", "budget.write",
                "sync.read", "sys.rule", "sys.key", "sys.hook", "sys.log"},
    "staff": {"energy.read", "energy.write", "center.read", "meter.read", "meter.write",
              "read.read", "read.write", "read.check", "equip.read", "base.read",
              "proj.read", "alarm.read", "alarm.write", "report.read", "budget.read",
              "sync.read"},
    "reader": {"energy.read", "center.read", "meter.read", "read.read", "read.write",
               "read.check", "alarm.read"},
    "engineer": {"energy.read", "center.read", "meter.read", "equip.read", "equip.write",
                 "base.read", "proj.read", "proj.write", "alarm.read", "alarm.write",
                 "report.read"},
    "prod": {"energy.read", "center.read", "meter.read", "read.read", "base.read",
             "proj.read", "alarm.read", "report.read", "budget.read"},
    "finance": {"energy.read", "center.read", "base.read", "proj.read", "report.read",
                "budget.read"},
}


def can(role, perm):
    if role == "admin":
        return True
    return perm in ROLE_PERMS.get(role, set())


def perms_of(role):
    return sorted(ROLE_PERMS.get(role, set()))


# ---------- 默认业务规则 ----------

DEFAULT_RULES = {
    "demand_warn_ratio": 0.85,
    "demand_urgent_ratio": 0.95,
    "jump_ratio": 3.0,
    "jump_floor": 100.0,
    "intensity_warn": 0.08,
    "intensity_serious": 0.15,
    "intensity_urgent": 0.30,
    "budget_warn": 0.90,
    "budget_over": 1.00,
    "budget_block": 1.10,
    "pf_standard": 0.90,
    "demand_price": 42.0,
    "tce_price": 620.0,
    "eff_degrade_ratio": 0.05,
}
