# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 业务内核单测（纯函数，不依赖数据库）

覆盖：折标煤、碳排、能耗强度、分时电费、容量/力调电费、需量、设备能效、
节能量与项目收益、告警分级、抄表质量校验、能源平衡、预算闸口、权限矩阵。
"""
import math

import pytest

import conftest  # noqa: F401  确保 sys.path 就绪
import energy as E


# ============ 工具函数 ============

class TestHelpers:
    def test_q2_half_up(self):
        assert E.q2(1.005) == 1.01
        assert E.q2(2.675) == 2.68
        assert E.q2(-1.005) == -1.01

    def test_q0_bankers_avoided(self):
        assert E.q0("3.6") == 4
        assert E.q0(3.4) == 3
        assert E.q0(None) == 0

    def test_safe_num(self):
        assert E.safe_num("12.5") == 12.5
        assert E.safe_num("") == 0.0
        assert E.safe_num(None) == 0.0
        assert E.safe_num("-") == 0.0
        assert E.safe_num("abc", 9.9) == 9.9

    def test_div_zero_guard(self):
        assert E.div(10, 0) == 0.0
        assert E.div(10, 0, -1) == -1
        assert E.div(10, 4) == 2.5

    def test_prev_period_cross_year(self):
        assert E.prev_period("2026-01") == "2025-12"
        assert E.prev_period("2026-10") == "2026-09"

    def test_period_range_inclusive(self):
        assert E.period_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
        assert E.period_range("2026-03", "2026-03") == ["2026-03"]

    def test_period_days(self):
        assert E.period_days("2026-02") == 28
        assert E.period_days("2024-02") == 29
        assert E.period_days("2026-10") == 31


# ============ 折标煤与碳排 ============

class TestTce:
    def test_to_tce_elec(self):
        # 10000 kWh × 0.0001229 tce/kWh
        assert E.to_tce(10000, 0.0001229) == 1.23

    def test_to_tce_gas_thousand_m3(self):
        # 46 千m³ 天然气 × 1.33
        assert E.to_tce(46, 1.33) == 61.18

    def test_to_tce_zero_and_bad(self):
        assert E.to_tce(0, 1.33) == 0.0
        assert E.to_tce(None, None) == 0.0

    def test_tce_total_multi_energy(self):
        rows = [
            {"qty": 100000, "tceFactor": 0.0001229},   # 12.29
            {"qty": 1000, "tceFactor": 0.09286},       # 92.86
            {"qty": 40, "tceFactor": 1.33},            # 53.20
        ]
        assert E.tce_total(rows) == 158.35

    def test_tce_total_empty(self):
        assert E.tce_total([]) == 0.0


class TestCarbon:
    def test_to_co2(self):
        assert E.to_co2(10000, 0.000581) == 5.81

    def test_co2_scope_split_by_field(self):
        rows = [
            {"qty": 100000, "co2Factor": 0.000581, "scope": "范围二"},   # 58.1
            {"qty": 40, "co2Factor": 2.1622, "scope": "范围一"},          # 86.488
        ]
        r = E.co2_total(rows)
        assert r["scope1"] == 86.488
        assert r["scope2"] == 58.1
        assert r["total"] == 144.588

    def test_co2_scope_fallback_by_energy(self):
        """scope 缺失时按 energy 编码回退 SCOPE_MAP。"""
        rows = [
            {"qty": 40, "co2Factor": 2.1622, "energy": "GAS"},     # 范围一
            {"qty": 1000, "co2Factor": 0.2620, "energy": "STEAM"},  # 范围二
        ]
        r = E.co2_total(rows)
        assert r["scope1"] == 86.488
        assert r["scope2"] == 262.0

    def test_co2_default_scope_two(self):
        r = E.co2_total([{"qty": 100, "co2Factor": 0.5}])
        assert r["scope2"] == 50.0 and r["scope1"] == 0.0

    def test_co2_empty(self):
        r = E.co2_total([])
        assert r["total"] == 0.0 and r["scope1"] == 0.0

    def test_carbon_intensity(self):
        # 1906.71 tCO2 ÷ 1170 万元
        assert E.carbon_intensity(1906.71, 1170) == 1.6297
        assert E.carbon_intensity(100, 0) == 0.0


# ============ 能耗强度 ============

class TestIntensity:
    def test_unit_energy_six_decimals(self):
        """小量级单耗必须是 6 位，不能失真。"""
        v = E.unit_energy(0.0125, 6000)
        assert v == 0.000002
        assert isinstance(v, float)

    def test_unit_energy_normal(self):
        assert E.unit_energy(591.32, 21000) == 0.028158
        assert E.unit_energy(100, 0) == 0.0

    def test_value_energy(self):
        assert E.value_energy(591.32, 1170) == 0.505402
        assert E.value_energy(100, 0) == 0.0

    def test_intensity_pack_shape(self):
        p = E.intensity_pack(591.32, 21000, 1170)
        assert set(p) == {"tce", "qty", "valueWan", "unitEnergy", "valueEnergy", "carbon"}
        assert p["tce"] == 591.32
        assert p["unitEnergy"] == E.unit_energy(591.32, 21000)

    def test_yoy_positive(self):
        r = E.yoy(120, 100)
        assert r["diff"] == 20.0 and r["rate"] == 0.2

    def test_yoy_negative(self):
        r = E.yoy(90, 100)
        assert r["diff"] == -10.0 and r["rate"] == -0.1

    def test_yoy_prev_zero(self):
        r = E.yoy(50, 0)
        assert r["rate"] == 0.0 and r["diff"] == 50.0


# ============ 分时电费 ============

TARIFF = {"尖峰": 1.28, "峰": 1.02, "平": 0.68, "谷": 0.34}


class TestTouFee:
    def test_four_period_fee(self):
        ivs = [
            {"period": "尖峰", "kwh": 1000},
            {"period": "峰", "kwh": 2000},
            {"period": "平", "kwh": 3000},
            {"period": "谷", "kwh": 4000},
        ]
        r = E.tou_fee(ivs, TARIFF)
        assert r["byPeriod"]["尖峰"]["amount"] == 1280.0
        assert r["byPeriod"]["峰"]["amount"] == 2040.0
        assert r["byPeriod"]["平"]["amount"] == 2040.0
        assert r["byPeriod"]["谷"]["amount"] == 1360.0
        assert r["energyFee"] == 6720.0
        assert r["kwhTotal"] == 10000.0
        assert r["avgPrice"] == 0.672

    def test_merge_duplicate_periods(self):
        ivs = [{"period": "峰", "kwh": 100}, {"period": "峰", "kwh": 200}]
        r = E.tou_fee(ivs, TARIFF)
        assert r["byPeriod"]["峰"]["kwh"] == 300.0
        assert r["byPeriod"]["峰"]["amount"] == 306.0

    def test_unknown_period_ignored(self):
        r = E.tou_fee([{"period": "自定义", "kwh": 999}], TARIFF)
        assert r["kwhTotal"] == 0.0 and r["energyFee"] == 0.0

    def test_check_diff_always_zero(self):
        r = E.tou_fee([{"period": "谷", "kwh": 333}], TARIFF)
        assert r["checkDiff"] == 0.0

    def test_empty(self):
        r = E.tou_fee([], TARIFF)
        assert r["energyFee"] == 0.0 and r["avgPrice"] == 0.0


class TestCapacityAndPf:
    def test_capacity_fee_by_demand(self):
        r = E.capacity_fee(1200, 42)
        assert r["byDemand"] == 50400.0
        assert r["byCapacity"] is None
        assert r["chosen"] == 50400.0
        assert r["mode"] == "按需量"

    def test_capacity_fee_by_capacity(self):
        r = E.capacity_fee(1200, 42, basic_kva=1600, basic_price=30)
        assert r["byCapacity"] == 48000.0
        assert r["chosen"] == 48000.0
        assert r["mode"] == "按容量"

    def test_pf_below_standard_surcharge(self):
        # pf=0.85，低于 0.90 0.05 → 加收 0.05×50% = 2.5%
        r = E.power_factor_fee(10000, 0.85)
        assert r["rate"] == 0.025
        assert r["amount"] == 250.0
        assert r["note"] == "加收"

    def test_pf_above_standard_reward(self):
        # pf=0.95，高于 0.05 → 减免 0.05×15% = 0.75%
        r = E.power_factor_fee(10000, 0.95)
        assert r["rate"] == -0.0075
        assert r["amount"] == -75.0
        assert r["note"] == "减免"

    def test_pf_cap_15pct(self):
        r = E.power_factor_fee(10000, 0.50)   # 理论加收 20%，被压到 15%
        assert r["rate"] == 0.15
        assert r["amount"] == 1500.0

    def test_pf_exact_standard(self):
        r = E.power_factor_fee(10000, 0.90)
        assert r["rate"] == 0.0 and r["note"] == "不奖不罚"

    def test_pf_missing(self):
        r = E.power_factor_fee(10000, 0)
        assert r["rate"] == 0.0 and r["note"] == "无功率因数数据"


# ============ 需量 ============

class TestDemand:
    def test_demand_15min(self):
        # 15 分钟用 25 kWh → 25/0.25 = 100 kW
        assert E.demand_15min(25) == 100.0
        assert E.demand_15min(0) == 0.0

    def test_demand_from_hourly(self):
        assert E.demand_from_hourly(1500) == 1500.0

    @pytest.mark.parametrize("kw,status", [
        (5000, "正常"),   # 79.4%
        (5400, "预警"),   # 85.7%
        (6000, "紧急"),   # 95.2%
        (6300, "超容"),   # 100%
        (6900, "超容"),   # 109.5%
    ])
    def test_demand_status_levels(self, kw, status):
        r = E.demand_status(kw, 6300)
        assert r["status"] == status

    def test_demand_status_over_kw(self):
        r = E.demand_status(6900, 6300)
        assert r["overKw"] == 600.0
        assert r["rate"] == 1.0952

    def test_demand_status_capacity_zero(self):
        """容量未配置时 div 回落 0，状态为正常 —— 所以容量字段必须录入。"""
        r = E.demand_status(100, 0)
        assert r["status"] == "正常"
        assert r["rate"] == 0.0

    def test_max_demand(self):
        recs = [{"demandKw": 1200, "ts": "2026-10-01 08:00"},
                {"demandKw": 3450, "ts": "2026-10-12 14:15"},
                {"demandKw": 2900, "ts": "2026-10-20 09:30"}]
        r = E.max_demand(recs)
        assert r["demandKw"] == 3450.0
        assert r["ts"] == "2026-10-12 14:15"

    def test_max_demand_empty(self):
        assert E.max_demand([])["demandKw"] == 0.0


# ============ 设备能效 ============

class TestEfficiency:
    def test_air_compressor_calc(self):
        r = E.eff_calc("空压机", input_power=118, output_qty=20.5)
        assert r["value"] == 5.76
        assert r["grade"] == "优"
        assert r["unit"] == "kW/(m³/min)"

    def test_air_compressor_fair(self):
        r = E.eff_calc("空压机", input_power=140, output_qty=20)   # 7.0
        assert r["grade"] == "良"

    def test_air_compressor_poor(self):
        r = E.eff_calc("空压机", input_power=160, output_qty=20)   # 8.0
        assert r["grade"] == "差"

    def test_pump_efficiency(self):
        r = E.eff_calc("水泵", input_power=45, output_kw=36)
        assert r["value"] == 80.0 and r["grade"] == "优"

    def test_pump_low(self):
        r = E.eff_calc("水泵", input_power=50, output_kw=30)       # 60%
        assert r["grade"] == "差"

    def test_boiler_heat_efficiency(self):
        r = E.eff_calc("锅炉", heat_in=1000, heat_out=930)
        assert r["value"] == 93.0 and r["grade"] == "优"

    def test_chiller_cop(self):
        r = E.eff_calc("制冷机", input_power=185, output_kw=1017)
        assert r["value"] == 5.5 and r["grade"] == "优"

    def test_unknown_etype(self):
        r = E.eff_calc("风机", input_power=10, output_qty=5)
        assert r["grade"] == "未知" and r["metric"] == "未知"

    def test_grade_boundaries(self):
        assert E.eff_grade(6.3, "空压机") == "优"    # 小于等于 good
        assert E.eff_grade(6.31, "空压机") == "良"
        assert E.eff_grade(7.2, "空压机") == "良"
        assert E.eff_grade(7.21, "空压机") == "差"
        assert E.eff_grade(75.0, "水泵") == "优"
        assert E.eff_grade(65.0, "水泵") == "良"
        assert E.eff_grade(5.0, "制冷机") == "优"

    def test_degrade_air_compressor(self):
        # 比功率从 5.5 升到 6.0，劣化 9% > 5%
        r = E.eff_delta(6.0, 5.5, "空压机")
        assert r["degraded"] is True and r["delta"] == 0.5

    def test_degrade_within_5pct(self):
        r = E.eff_delta(5.7, 5.5, "空压机")   # 3.6%
        assert r["degraded"] is False

    def test_degrade_pump_drop(self):
        # 效率从 80 降到 74，降幅 7.5% > 5%
        r = E.eff_delta(74.0, 80.0, "水泵")
        assert r["degraded"] is True and r["delta"] == -6.0

    def test_improvement_not_degraded(self):
        r = E.eff_delta(5.2, 5.5, "空压机")
        assert r["degraded"] is False


# ============ 节能量与项目收益 ============

class TestSaving:
    def test_saving_basic(self):
        # 基线 0.028000，报告期 0.026000，产量 21000
        r = E.saving(0.028000, 0.026000, 21000)
        assert r["savingTce"] == 42.0
        assert r["savingRate"] == 0.0714
        assert r["achieved"] is True

    def test_saving_negative(self):
        r = E.saving(0.026, 0.028, 21000)
        assert r["savingTce"] == -42.0
        assert r["achieved"] is False

    def test_saving_rate(self):
        r = E.saving(0.03, 0.024, 1000)
        assert r["savingRate"] == 0.2
        assert r["savingTce"] == 6.0

    def test_saving_fee(self):
        assert E.saving_fee(42.0, 620) == 26040.0
        assert E.saving_fee(0, 620) == 0.0

    def test_payback(self):
        assert E.payback(310000, 26040) == 11.9
        assert E.payback(310000, 0) == 0.0

    def test_payback_zero_invest(self):
        assert E.payback(0, 1000) == 0.0

    def test_project_verify_achieved(self):
        r = E.project_verify(0.028, 0.026, 21000, 310000, 620, months=12)
        assert r["savingTce"] == 42.0
        assert r["savingFeeYear"] == 26040.0
        assert r["paybackYear"] == 11.9
        assert r["verdict"] == "达标"

    def test_project_verify_annualize_by_months(self):
        """6 个月数据 → 年化翻倍，回收期减半。"""
        full = E.project_verify(0.028, 0.026, 21000, 310000, 620, months=12)
        half = E.project_verify(0.028, 0.026, 21000, 310000, 620, months=6)
        assert half["savingFeeYear"] == pytest.approx(full["savingFeeYear"] * 2, rel=1e-6)
        assert half["paybackYear"] == pytest.approx(full["paybackYear"] / 2, rel=1e-6)

    def test_project_verify_not_achieved(self):
        r = E.project_verify(0.026, 0.028, 21000, 100000, 620)
        assert r["verdict"] == "未达标"
        assert r["savingTce"] < 0

    def test_baseline_unit_six_decimals(self):
        v = E.baseline_unit(158.35, 6000)
        assert v == 0.026392
        assert E.baseline_unit(100, 0) == 0.0


# ============ 告警分级 ============

class TestAlarm:
    def test_alarm_level_levels(self):
        assert E.alarm_level(5000, 6300) == "正常"     # 79%
        assert E.alarm_level(5400, 6300) == "严重"     # 86%
        assert E.alarm_level(6000, 6300) == "紧急"     # 95%
        assert E.alarm_level(7000, 6300) == "紧急"     # 111%

    def test_intensity_alarm_thresholds(self):
        assert E.intensity_alarm(0.0300, 0.0280) is None       # +7.1%，未破 8%
        assert E.intensity_alarm(0.0305, 0.0280) == "警告"      # +8.9%
        assert E.intensity_alarm(0.0330, 0.0280) == "严重"      # +17.9%
        assert E.intensity_alarm(0.0370, 0.0280) == "紧急"      # +32.1%

    def test_intensity_alarm_normal(self):
        assert E.intensity_alarm(0.0250, 0.0280) is None

    def test_intensity_alarm_no_baseline(self):
        assert E.intensity_alarm(0.03, 0) is None

    def test_level_rank_order(self):
        assert E.level_rank("紧急") < E.level_rank("严重") < E.level_rank("警告")
        assert E.level_rank("未知级别") == 9

    def test_alarm_summary(self):
        rows = [
            {"level": "紧急", "status": "待处置"},
            {"level": "严重", "status": "待处置"},
            {"level": "警告", "status": "已处置"},
            {"level": "提示", "status": "已处置"},
            {"level": "警告", "status": "已处置"},
        ]
        s = E.alarm_summary(rows)
        assert s["紧急"] == 1 and s["严重"] == 1 and s["警告"] == 2 and s["提示"] == 1
        assert s["未处置"] == 2
        assert s["合计"] == 5

    def test_alarm_summary_empty(self):
        s = E.alarm_summary([])
        assert s["合计"] == 0 and s["未处置"] == 0


# ============ 抄表质量校验 ============

class TestReading:
    def test_usage_with_ratio(self):
        r = E.reading_usage(1000, 1200, ratio=60)
        assert r["delta"] == 200.0
        assert r["usage"] == 12000.0
        assert r["reverse"] is False

    def test_usage_reverse(self):
        r = E.reading_usage(1000, 900, ratio=1)
        assert r["reverse"] is True
        assert r["delta"] == -100.0

    def test_usage_equal(self):
        r = E.reading_usage(500, 500)
        assert r["usage"] == 0.0 and r["reverse"] is False

    def test_jump_up(self):
        # 上期 100，本期 400 → 4 倍且 >100
        r = E.reading_check(100, 400)
        assert r["jump"] is True
        assert r["factor"] == 4.0
        assert r["level"] == "警告"

    def test_jump_within_ratio(self):
        r = E.reading_check(100, 250)     # 2.5 倍
        assert r["jump"] is False

    def test_jump_below_floor(self):
        # 30 → 200 是 6.7 倍，但本期 200 ≥ 100，仍判跳变
        assert E.reading_check(30, 200)["jump"] is True
        # 10 → 90，本期 90 < 100 门槛 → 不判
        assert E.reading_check(10, 90)["jump"] is False

    def test_jump_down(self):
        # 上期 1000，本期 200 → 1/5，跌幅超 3 倍
        r = E.reading_check(1000, 200)
        assert r["jump"] is True

    def test_no_prev_usage(self):
        r = E.reading_check(0, 500)
        assert r["jump"] is False

    def test_meter_change_usage(self):
        # 旧表上期 1000，换表时 1300；新表首底 50
        assert E.meter_change_usage(1000, 1300, 50) == 350.0

    def test_coverage(self):
        assert E.coverage(30, 27) == 0.9
        assert E.coverage(0, 0) == 0.0
        assert E.coverage(30, 30) == 1.0

    def test_fill_gap_both_sides(self):
        assert E.fill_gap([100, None, 200], 1) == 150.0

    def test_fill_gap_forward_only(self):
        assert E.fill_gap([None, None, 300], 0) == 300.0

    def test_fill_gap_backward_only(self):
        assert E.fill_gap([120, None, None], 2) == 120.0

    def test_fill_gap_all_none(self):
        assert E.fill_gap([None, None], 0) == 0.0

    def test_fill_gap_empty(self):
        assert E.fill_gap([], 0) == 0.0


# ============ 能源平衡 ============

class TestBalance:
    def test_balance_exact(self):
        items = [{"name": "注塑", "qty": 1, "tce": 60.0},
                 {"name": "冲压", "qty": 1, "tce": 40.0}]
        r = E.energy_balance(100.0, items)
        assert r["usedTce"] == 100.0
        assert r["lossTce"] == 0.0
        assert r["lossRate"] == 0.0
        assert r["checkDiff"] == 0.0

    def test_balance_with_loss(self):
        items = [{"tce": 95.0}]
        r = E.energy_balance(100.0, items)
        assert r["lossTce"] == 5.0
        assert r["lossRate"] == 0.05

    def test_balance_empty_items(self):
        r = E.energy_balance(100.0, [])
        assert r["lossTce"] == 100.0 and r["lossRate"] == 1.0

    def test_balance_zero_total(self):
        r = E.energy_balance(0, [])
        assert r["lossRate"] == 0.0 and r["lossTce"] == 0.0


# ============ 预算闸口 ============

class TestBudget:
    @pytest.mark.parametrize("used,status,blocked", [
        (50000, "正常", False),     # 50%
        (89999, "正常", False),     # 89.9%
        (90000, "预警", False),     # 90%
        (99999, "预警", False),
        (100001, "超支", False),    # 100.01%
        (110000, "超支", False),    # 110%
        (110001, "阻断", True),     # 110.01%
    ])
    def test_budget_states(self, used, status, blocked):
        r = E.budget_state(100000, used)
        assert r["status"] == status
        assert r["blocked"] is blocked

    def test_budget_left(self):
        r = E.budget_state(100000, 60000)
        assert r["left"] == 40000.0 and r["rate"] == 0.6

    def test_budget_zero(self):
        r = E.budget_state(0, 0)
        assert r["rate"] == 0.0 and r["status"] == "正常"

    def test_budget_overdraw_left_negative(self):
        r = E.budget_state(100, 150)
        assert r["left"] == -50.0


# ============ 角色权限 ============

class TestPerms:
    def test_seven_roles(self):
        assert len(E.ROLES) == 7
        assert set(E.ROLES) == {"admin", "manager", "staff", "reader", "engineer", "prod", "finance"}

    def test_perm_count(self):
        assert len(E.PERMS) == 27
        assert len(set(E.PERMS)) == 27   # 无重复

    def test_admin_has_all(self):
        for p in E.PERMS:
            assert E.can("admin", p) is True
        assert len(E.perms_of("admin")) == 27

    def test_reader_no_write_perm(self):
        assert E.can("reader", "read.write") is True
        assert E.can("reader", "meter.write") is False
        assert E.can("reader", "sys.user") is False
        assert E.can("reader", "budget.write") is False

    def test_finance_read_only(self):
        assert E.can("finance", "budget.read") is True
        assert E.can("finance", "budget.write") is False
        assert E.can("finance", "read.write") is False

    def test_engineer_eff_perms(self):
        assert E.can("engineer", "equip.write") is True
        assert E.can("engineer", "proj.write") is True
        assert E.can("engineer", "proj.verify") is False   # 仅主管/管理员可验证

    def test_manager_can_verify(self):
        assert E.can("manager", "proj.verify") is True
        assert E.can("manager", "budget.write") is True

    def test_prod_no_write(self):
        assert E.can("prod", "read.read") is True
        assert E.can("prod", "read.write") is False

    def test_unknown_role(self):
        assert E.can("nobody", "energy.read") is False
        assert E.perms_of("nobody") == []

    def test_every_role_has_energy_read(self):
        for r in E.ROLES:
            assert E.can(r, "energy.read") is True


# ============ 默认规则 ============

class TestDefaultRules:
    def test_rule_keys(self):
        must = {"demand_warn_ratio", "demand_urgent_ratio", "jump_ratio", "jump_floor",
                "intensity_warn", "budget_warn", "budget_block", "pf_standard",
                "demand_price", "tce_price"}
        assert must <= set(E.DEFAULT_RULES)

    def test_rule_value_sanity(self):
        assert 0 < E.DEFAULT_RULES["demand_warn_ratio"] < E.DEFAULT_RULES["demand_urgent_ratio"] < 1
        assert E.DEFAULT_RULES["budget_warn"] < E.DEFAULT_RULES["budget_over"] < E.DEFAULT_RULES["budget_block"]
        assert E.DEFAULT_RULES["tce_price"] == 620.0
        assert E.DEFAULT_RULES["demand_price"] == 42.0

    def test_spec_four_types(self):
        assert set(E.EFF_SPEC) == {"空压机", "水泵", "锅炉", "制冷机"}
        for k, s in E.EFF_SPEC.items():
            assert "good" in s and "fair" in s and "lower_better" in s
