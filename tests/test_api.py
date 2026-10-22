# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 接口测试（真实 HTTP + 真实 SQLite）

覆盖：健康检查、鉴权五通道、7 角色权限、主数据 CRUD、抄表三闸口、
分时/需量、11 个分析报表、基线、设备能效、项目验证、告警、预算、
系统管理（用户/规则/API Key/Webhook/审计）、增量同步、幂等、OpenAPI、CSV 导出。
"""
import json
import time

import pytest

import conftest as C
import energy as E
from conftest import Client


# ============ 1. 健康检查与静态资源 ============

class TestHealth:
    def test_health_no_auth(self, cli):
        r = cli.get("/api/health")
        assert r.status == 200
        assert r.data["brand"] == "飞瀑能源管理系统"
        assert r.data["routes"] >= 69
        assert r.data["events"] == 13
        assert r.data["meters"] == 30

    def test_index_served(self, cli):
        r = cli.get("/")
        assert r.status == 200
        assert "飞瀑" in r.body.decode("utf-8")

    def test_static_css(self, cli):
        r = cli.get("/style.css")
        assert r.status == 200

    def test_404_unknown_route(self, cli):
        r = cli.get("/api/not-exists")
        assert r.status == 404
        assert "不存在" in r.message

    def test_openapi_json(self, cli):
        r = cli.get("/api/openapi.json")
        assert r.status == 200
        spec = r.data
        assert spec["info"]["title"]
        assert len(spec["paths"]) >= 45
        # 每条 path 至少有一个 method
        for p, methods in spec["paths"].items():
            assert isinstance(methods, dict) and methods

    def test_apidoc_html(self, cli):
        r = cli.get("/apidoc")
        assert r.status == 200
        assert "text/html" in r.headers.get("Content-Type", "")
        assert "/api/board" in r.body.decode("utf-8")


# ============ 2. 鉴权与令牌 ============

class TestAuth:
    def test_login_ok(self, cli):
        c = Client(cli.base)
        d = c.login("admin")
        assert d["token"] and len(d["token"]) == 64
        assert d["user"]["role"] == "admin"
        assert len(d["user"]["perms"]) == 27
        assert d["user"]["roleName"] == "系统管理员"

    def test_login_wrong_password(self, cli):
        r = cli.post("/api/auth/login", {"username": "admin", "password": "wrong"})
        assert r.status == 401

    def test_login_unknown_user(self, cli):
        r = cli.post("/api/auth/login", {"username": "ghost", "password": "x"})
        assert r.status == 401

    def test_no_token_401(self, cli):
        r = cli.get("/api/meters")
        assert r.status == 401

    def test_bad_token_401(self, cli):
        r = cli.get("/api/meters", headers={"Authorization": "Bearer deadbeef"})
        assert r.status == 401

    def test_x_fp_token_header(self, cli, admin):
        r = cli.get("/api/meters", headers={"X-Fp-Token": admin.token})
        assert r.status == 200

    def test_cookie_token(self, cli, admin):
        r = cli.get("/api/meters", headers={"Cookie": "fp_token=" + admin.token})
        assert r.status == 200

    def test_query_token(self, cli, admin):
        r = cli.get("/api/meters?token=" + admin.token)
        assert r.status == 200

    def test_me(self, admin):
        r = admin.get("/api/auth/me")
        assert r.status == 200
        assert r.data["username"] == "admin"
        assert "perms" in r.data

    def test_change_password_and_restore(self, cli):
        """在独立客户端里改，避免污染全局 admin 会话。"""
        c = Client(cli.base)
        c.login("admin")
        r = c.post("/api/auth/change-password",
                   {"oldPassword": "energy@2026", "newPassword": "energy@2026new"})
        assert r.status == 200
        c2 = Client(cli.base)
        assert c2.post("/api/auth/login",
                       {"username": "admin", "password": "energy@2026"}).status == 401
        assert c2.post("/api/auth/login",
                       {"username": "admin", "password": "energy@2026new"}).status == 200
        # 改回，保证后续用例仍可用原口令
        r = c2.post("/api/auth/change-password",
                    {"oldPassword": "energy@2026new", "newPassword": "energy@2026"})
        assert r.status == 200

    def test_change_password_wrong_old(self, cli):
        c = Client(cli.base)
        c.login("admin")
        r = c.post("/api/auth/change-password",
                   {"oldPassword": "nope", "newPassword": "whatever1"})
        assert r.status in (400, 401, 403)

    def test_logout_invalidates_token(self, cli):
        c = Client(cli.base)
        c.login("reader")
        assert c.get("/api/meters").status == 200
        assert c.post("/api/auth/logout").status == 200
        # no_retry：登出后不许自动重登，否则测不到失效
        assert c.get("/api/meters", no_retry=True).status == 401


# ============ 3. 权限矩阵（每角色一条） ============

class TestPermissions:
    def test_reader_can_read_meters(self, tokens):
        assert tokens["reader"].get("/api/meters").status == 200

    def test_reader_cannot_create_meter(self, tokens):
        r = tokens["reader"].post("/api/meters", {"code": "EMTEST-R", "energyCode": "ELEC"})
        assert r.status == 403

    def test_reader_cannot_read_users(self, tokens):
        assert tokens["reader"].get("/api/users").status == 403

    def test_finance_readonly(self, tokens):
        assert tokens["finance"].get("/api/budgets").status == 200
        assert tokens["finance"].post("/api/budgets", {"items": []}).status == 403
        assert tokens["finance"].get("/api/meters").status == 403   # 无 meter.read

    def test_prod_no_read_write(self, tokens):
        assert tokens["prod"].get("/api/readings").status == 200
        r = tokens["prod"].post("/api/readings", {"meter": "EM601", "reading": 1})
        assert r.status == 403

    def test_engineer_can_calc_eff(self, tokens):
        r = tokens["engineer"].post("/api/eff-tests/calc",
                                    {"etype": "水泵", "inputPower": 45, "outputKw": 36})
        assert r.status == 200

    def test_engineer_cannot_verify_project(self, tokens):
        r = tokens["engineer"].post("/api/projects/SP2026-005/verify", {"period": "2026-10"})
        assert r.status == 403

    def test_staff_cannot_manage_users(self, tokens):
        assert tokens["staff"].get("/api/users").status == 403

    def test_manager_can_see_rules(self, tokens):
        assert tokens["manager"].get("/api/rules").status == 200

    def test_staff_cannot_write_rules(self, tokens):
        assert tokens["staff"].put("/api/rules", {"key": "tce_price", "value": 1}).status == 403

    def test_only_admin_sees_logs(self, tokens):
        assert tokens["admin"].get("/api/logs").status == 200
        assert tokens["manager"].get("/api/logs").status == 200   # 主管有 sys.log
        assert tokens["staff"].get("/api/logs").status == 403

    def test_perms_endpoint_matches_matrix(self, tokens):
        for role, c in tokens.items():
            r = c.get("/api/auth/me")
            assert r.status == 200, role
            assert sorted(r.data["perms"]) == E.perms_of(role), role


# ============ 4. 主数据 ============

class TestMasterData:
    def test_energy_types(self, admin):
        r = admin.get("/api/energy-types")
        assert r.status == 200
        codes = {e["code"] for e in r.data["list"]}
        assert codes == {"ELEC", "WATER", "STEAM", "AIR", "GAS", "DIESEL"}
        elec = next(e for e in r.data["list"] if e["code"] == "ELEC")
        assert elec["tceFactor"] == 0.0001229
        assert elec["unit"] == "kWh"

    def test_tariffs(self, admin):
        r = admin.get("/api/tariffs")
        assert r.status == 200
        assert len(r.data["list"]) >= 4    # 电力的尖峰/峰/平/谷

    def test_cost_centers(self, admin):
        r = admin.get("/api/cost-centers")
        assert r.status == 200
        assert len(r.data["list"]) == 10
        assert any(c["code"] == "CC202" for c in r.data["list"])

    def test_lines(self, admin):
        r = admin.get("/api/lines")
        assert r.status == 200
        assert len(r.data["list"]) >= 5

    def test_meters_all(self, admin):
        r = admin.get("/api/meters")
        assert r.status == 200
        assert len(r.data["list"]) == 30
        lv1 = [m for m in r.data["list"] if m["level"] == 1]
        assert len(lv1) == 6   # 六个介质各一个总表

    def test_meters_filter_by_center(self, admin):
        r = admin.get("/api/meters?center=CC101")
        assert r.status == 200
        assert all(m["center"] == "CC101" for m in r.data["list"])
        assert len(r.data["list"]) >= 3   # 电/气/水多介质合计

    def test_meters_filter_by_energy(self, admin):
        r = admin.get("/api/meters?energy=WATER")
        assert all(m["energy_code"] == "WATER" for m in r.data["list"])

    def test_meters_filter_by_level(self, admin):
        r = admin.get("/api/meters?level=3")
        assert all(m["level"] == 3 for m in r.data["list"])

    def test_meter_crud_cycle(self, admin):
        code = "EMTEST01"
        r = admin.post("/api/meters", {"code": code, "name": "测试表", "energyCode": "ELEC",
                                       "center": "CC101", "line": "L1", "level": 3,
                                       "ratio": 1, "capacity": 100})
        assert r.status == 200
        r = admin.post("/api/meters", {"code": code, "energyCode": "ELEC"})
        assert r.status == 409   # 重复

        r = admin.put("/api/meters/" + code, {"name": "测试表改", "center": "CC102",
                                              "line": "", "ratio": 2, "capacity": 120,
                                              "gateway": "网关", "status": "运行"})
        assert r.status == 200
        m = next(x for x in admin.get("/api/meters").data["list"] if x["code"] == code)
        assert m["name"] == "测试表改" and m["ratio"] == 2.0

    def test_meter_bad_energy(self, admin):
        r = admin.post("/api/meters", {"code": "EMTEST02", "energyCode": "NOPE"})
        assert r.status == 400

    def test_equipments(self, admin):
        r = admin.get("/api/equipments")
        assert r.status == 200
        assert len(r.data["list"]) == 8
        assert set(r.data["spec"]) == {"空压机", "水泵", "锅炉", "制冷机"}

    def test_equipment_save(self, admin):
        r = admin.post("/api/equipments", {"code": "EQ-T01", "name": "测试泵", "etype": "水泵",
                                           "center": "CC201", "ratedPower": 30})
        assert r.status == 200
        r = admin.post("/api/equipments", {"code": "EQ-T02", "name": "非法", "etype": "风机"})
        assert r.status == 400


# ============ 5. 抄表三闸口 ============

class TestReadingGates:
    """闸口用例各用独立计量点，避免相互污染。"""

    @staticmethod
    def _meter(admin, code):
        admin.post("/api/meters", {"code": code, "name": "闸口测试表-" + code,
                                   "energyCode": "ELEC", "center": "CC101",
                                   "level": 3, "ratio": 1})
        return code

    def test_normal_reading(self, admin):
        m = self._meter(admin, "EMGATE1")
        r = admin.post("/api/readings", {"meter": m, "period": "2026-08", "reading": 1000})
        assert r.status == 200
        assert r.data["quality"] == "正常"
        assert r.data["jump"] is False

    def test_gate_reverse(self, admin):
        """表底倒走 → 409。"""
        m = self._meter(admin, "EMGATE2")
        admin.post("/api/readings", {"meter": m, "period": "2026-08", "reading": 1000})
        r = admin.post("/api/readings", {"meter": m, "period": "2026-09", "reading": 500})
        assert r.status == 409
        assert "倒走" in r.message

    def test_gate_overlap(self, admin):
        """同点同期重复 → 409 区间重叠。"""
        m = self._meter(admin, "EMGATE3")
        assert admin.post("/api/readings",
                          {"meter": m, "period": "2026-08", "reading": 1000}).status == 200
        r = admin.post("/api/readings", {"meter": m, "period": "2026-08", "reading": 1500})
        assert r.status == 409
        assert "重叠" in r.message

    def test_gate_jump_up(self, admin):
        """用量放大 7 倍 → 入库标记跳变并自动告警。"""
        m = self._meter(admin, "EMGATE4")
        admin.post("/api/readings", {"meter": m, "period": "2026-08", "reading": 1000})
        admin.post("/api/readings", {"meter": m, "period": "2026-09", "reading": 1500})
        r = admin.post("/api/readings", {"meter": m, "period": "2026-10", "reading": 5000})
        assert r.status == 200
        assert r.data["jump"] is True
        assert r.data["quality"] == "跳变"
        assert r.data["alarm"], "跳变必须自动生成告警"

    def test_gate_jump_alarm_level(self, admin):
        rs = admin.get("/api/alarms?type=抄表异常").data["list"]
        assert rs, "跳变应留下抄表异常告警"
        assert any(a["level"] == "警告" for a in rs)
        # 告警字段完整，前端可直接渲染
        a = rs[0]
        assert {"no", "level", "atype", "target", "message", "status"} <= set(a)

    def test_meter_not_found(self, admin):
        r = admin.post("/api/readings", {"meter": "EM-NOPE", "period": "2026-10", "reading": 1})
        assert r.status == 404

    def test_meter_missing_field(self, admin):
        assert admin.post("/api/readings", {"period": "2026-10"}).status == 400

    def test_stopped_meter_rejected(self, admin):
        admin.post("/api/meters", {"code": "EMSTOP01", "name": "停用表", "energyCode": "ELEC",
                                   "center": "CC101", "level": 3})
        admin.put("/api/meters/EMSTOP01", {"name": "停用表", "center": "CC101", "status": "停用",
                                           "ratio": 1})
        r = admin.post("/api/readings", {"meter": "EMSTOP01", "period": "2026-10", "reading": 10})
        assert r.status == 409
        assert "停用" in r.message

    def test_batch_partial_success(self, admin):
        r = admin.post("/api/readings/batch", {
            "period": "2026-11",
            "items": [{"meter": "EMGATE1", "reading": 6000},
                      {"meter": "EMGATE1", "reading": 7000},   # 同期重复 → 失败
                      {"meter": "EM-NOPE", "reading": 1}],     # 不存在 → 失败
        })
        assert r.status == 200
        assert r.data["success"] == 1
        assert r.data["failed"] == 2

    def test_batch_empty(self, admin):
        assert admin.post("/api/readings/batch", {"items": []}).status == 400

    def test_gateway_report(self, admin):
        r = admin.post("/api/readings/report", {"meter": "EMGATE1",
                                                "ts": "2026-12-05 10:15:00", "value": 6600})
        assert r.status == 200
        assert r.data["period"] == "2026-12"

    def test_gateway_missing_value(self, admin):
        r = admin.post("/api/readings/report", {"meter": "EMGATE1", "ts": "2026-12-06 10:00:00"})
        assert r.status == 400

    def test_readings_query_filters(self, admin):
        r = admin.get("/api/readings?period=2026-10&center=CC101")
        assert r.status == 200
        assert all(x["period"] == "2026-10" for x in r.data["list"])
        assert all(x["center"] == "CC101" for x in r.data["list"])

    def test_readings_by_meter(self, admin):
        r = admin.get("/api/readings?meter=EMGATE1")
        assert r.status == 200
        assert len(r.data["list"]) >= 3
        assert all(x["meter_code"] == "EMGATE1" for x in r.data["list"])


# ============ 6. 抄表质量巡检 ============

class TestReadingCheck:
    def test_check_shape(self, admin):
        r = admin.get("/api/readings/check?period=2026-10")
        assert r.status == 200
        d = r.data
        for k in ("period", "metersTotal", "metersReported", "coverage",
                  "missing", "estimate", "jump", "reverse", "qualityScore"):
            assert k in d
        assert d["metersTotal"] >= 30
        assert 0 <= d["coverage"] <= 1

    def test_check_finds_reverse(self, admin):
        d = admin.get("/api/readings/check?period=2026-10").data
        assert isinstance(d["reverse"], list)

    def test_check_requires_perm(self, tokens):
        # 抄表员要做数据质检，故有 read.check；财务无
        assert tokens["reader"].get("/api/readings/check").status == 200
        assert tokens["finance"].get("/api/readings/check").status == 403
        assert tokens["prod"].get("/api/readings/check").status == 403


# ============ 7. 分时与需量 ============

class TestTouAndDemand:
    def test_intervals(self, admin):
        r = admin.get("/api/intervals?meter=EM1011")
        assert r.status == 200

    def test_tou_summary(self, admin):
        r = admin.get("/api/tou-summary?period=2026-10")
        assert r.status == 200
        sm = r.data["summary"]
        assert set(sm["byPeriod"]) == {"尖峰", "峰", "平", "谷"}
        assert sm["energyFee"] > 0
        # 四时段电量之和 == 总电量
        assert abs(sum(v["kwh"] for v in sm["byPeriod"].values()) - sm["kwhTotal"]) < 0.05
        # 各时段金额之和 == 总电费
        assert abs(sum(v["amount"] for v in sm["byPeriod"].values()) - sm["energyFee"]) < 0.05

    def test_demands_list(self, admin):
        r = admin.get("/api/demands?period=2026-10")
        assert r.status == 200
        assert r.data["list"]

    def test_demand_summary(self, admin):
        r = admin.get("/api/demands/summary?period=2026-10")
        assert r.status == 200
        d = r.data
        assert "maxDemand" in d or "list" in d or "capacityKw" in d

    def test_demand_normal(self, admin):
        r = admin.post("/api/demands", {"center": "CC201", "ts": "2026-10-15 10:00:00",
                                        "demandKw": 2000, "capacityKw": 6300})
        assert r.status == 200
        assert r.data["status"] == "正常"
        assert r.data["alarm"] is None

    def test_demand_warning(self, admin):
        r = admin.post("/api/demands", {"center": "CC201", "ts": "2026-10-15 11:00:00",
                                        "demandKw": 5500, "capacityKw": 6300})
        assert r.data["status"] == "预警"
        assert r.data["alarm"] is not None
        assert r.data["alarm"]["level"] == "严重"
        assert r.data["alarm"]["no"].startswith("AL")

    def test_demand_over_capacity(self, admin):
        r = admin.post("/api/demands", {"center": "CC201", "ts": "2026-10-15 12:00:00",
                                        "demandKw": 6800, "capacityKw": 6300})
        assert r.data["status"] == "超容"
        assert r.data["rate"] > 1
        assert r.data["alarm"]["level"] == "紧急"
        assert r.data["alarm"]["atype"] == "需量超限"

    def test_demand_alarm_no_unique_collision(self, admin):
        """连续上报超容不得因告警编号冲突而 500。"""
        for i in range(3):
            r = admin.post("/api/demands", {"center": "CC201",
                                            "ts": "2026-10-16 %02d:00:00" % (10 + i),
                                            "demandKw": 6900 + i, "capacityKw": 6300})
            assert r.status == 200, r.body
            assert r.data["alarm"]

    def test_demand_upsert_same_ts(self, admin):
        ts = "2026-10-17 09:00:00"
        admin.post("/api/demands", {"center": "CC201", "ts": ts, "demandKw": 1000,
                                    "capacityKw": 6300})
        r = admin.post("/api/demands", {"center": "CC201", "ts": ts, "demandKw": 1200,
                                        "capacityKw": 6300})
        assert r.status == 200 and r.data["demandKw"] == 1200.0


# ============ 8. 分析报表（11 个） ============

BOARD_KEYS = {"tce", "tcePrev", "tceRate", "co2", "scope1", "scope2", "elecQty", "elecTce",
              "qty", "valueWan", "unitEnergy", "valueEnergy", "carbonIntensity",
              "alarms", "maxDemand", "capacityKw", "budget"}


class TestAnalytics:
    def test_board(self, admin):
        r = admin.get("/api/board?period=2026-10")
        assert r.status == 200
        assert BOARD_KEYS <= set(r.data["kpi"])
        assert r.data["kpi"]["tce"] > 0
        assert r.data["kpi"]["co2"] > 0
        assert r.data["byEnergy"]
        assert r.data["period"] == "2026-10"

    def test_board_co2_scope_sum_consistent(self, admin):
        k = admin.get("/api/board?period=2026-10").data["kpi"]
        assert abs(k["scope1"] + k["scope2"] - k["co2"]) < 0.02

    def test_board_elec_dominant(self, admin):
        """电力应是第一大能耗介质。"""
        d = admin.get("/api/board?period=2026-10").data
        top = max(d["byEnergy"], key=lambda x: x["tce"])
        assert top["energy"] == "ELEC"

    def test_consumption(self, admin):
        r = admin.get("/api/analysis/consumption?period=2026-10")
        assert r.status == 200
        assert r.data["list"]
        assert r.data["totalTce"] > 0
        first = r.data["list"][0]
        assert "center" in first and "energyName" in first and "tce" in first

    def test_consumption_sorted_desc(self, admin):
        lst = admin.get("/api/analysis/consumption?period=2026-10").data["list"]
        assert all(lst[i]["tce"] >= lst[i + 1]["tce"] for i in range(len(lst) - 1))

    def test_consumption_filter_center(self, admin):
        lst = admin.get("/api/analysis/consumption?period=2026-10&center=CC101").data["list"]
        assert all(x["center"] == "CC101" for x in lst)

    def test_consumption_filter_energy(self, admin):
        lst = admin.get("/api/analysis/consumption?period=2026-10&energy=WATER").data["list"]
        assert all(x["energy"] == "WATER" for x in lst)

    def test_intensity_baseline(self, admin):
        r = admin.get("/api/analysis/intensity?period=2026-10")
        assert r.status == 200
        assert len(r.data["list"]) >= 5
        for x in r.data["list"]:
            assert x["baseUnit"] > 0
            assert x["level"] in ("紧急", "严重", "警告", "正常")

    def test_yoy(self, admin):
        r = admin.get("/api/analysis/yoy?period=2026-10&months=6")
        assert r.status == 200
        assert len(r.data["list"]) >= 5
        assert r.data["list"][-1]["period"] == "2026-10"
        for x in r.data["list"]:
            assert x["tce"] >= 0

    def test_rank(self, admin):
        r = admin.get("/api/analysis/rank?period=2026-10")
        assert r.status == 200
        assert isinstance(r.data, dict)

    def test_energy_balance(self, admin):
        r = admin.get("/api/reports/energy-balance?period=2026-10")
        assert r.status == 200
        d = r.data
        bal = d["balance"]
        assert bal["totalIn"] > 0
        assert bal["usedTce"] >= 0
        assert abs(bal["totalIn"] - bal["usedTce"] - bal["lossTce"]) < 0.02
        assert d["byEnergy"] and d["byCenter"]

    def test_daily_report(self, admin):
        r = admin.get("/api/reports/daily?period=2026-10")
        assert r.status == 200

    def test_carbon_report(self, admin):
        r = admin.get("/api/reports/carbon?period=2026-10")
        assert r.status == 200
        d = r.data
        assert d["total"]["total"] > 0
        assert d["total"]["scope1"] + d["total"]["scope2"] == pytest.approx(d["total"]["total"], abs=0.01)
        assert d["byEnergy"]

    def test_export_csv_has_bom(self, admin):
        r = admin.get("/api/reports/export?type=consumption&period=2026-10")
        assert r.status == 200
        assert "text/csv" in r.headers.get("Content-Type", "")
        assert r.body.startswith(b"\xef\xbb\xbf")   # UTF-8 BOM，Excel 友好

    def test_export_csv_all_types(self, admin):
        for t in ("consumption", "balance", "daily", "carbon"):
            r = admin.get("/api/reports/export?type=%s&period=2026-10" % t)
            assert r.status == 200, t
            assert len(r.body) > 50

    def test_reports_need_perm(self, tokens):
        assert tokens["reader"].get("/api/board").status == 403
        assert tokens["prod"].get("/api/board").status == 200


# ============ 9. 基线 ============

class TestBaseline:
    def test_list(self, admin):
        r = admin.get("/api/baselines")
        assert r.status == 200
        assert len(r.data["list"]) >= 6

    def test_create(self, admin):
        r = admin.post("/api/baselines", {"line": "L2", "periodFrom": "2025-11",
                                          "periodTo": "2026-04", "code": "BL-TEST-L2"})
        assert r.status == 200
        assert r.data["baseUnit"] > 0
        assert len(r.data["periods"]) == 6

    def test_create_duplicate_code(self, admin):
        r = admin.post("/api/baselines", {"line": "L2", "periodFrom": "2025-11",
                                          "periodTo": "2026-04", "code": "BL-TEST-L2"})
        assert r.status == 409

    def test_create_missing_line(self, admin):
        assert admin.post("/api/baselines", {}).status == 400

    def test_create_no_output(self, admin):
        r = admin.post("/api/baselines", {"line": "L9", "periodFrom": "2026-01",
                                          "periodTo": "2026-02"})
        assert r.status == 409

    def test_reader_cannot_create(self, tokens):
        assert tokens["reader"].post("/api/baselines", {"line": "L1"}).status == 403


# ============ 10. 设备能效 ============

class TestEfficiencyApi:
    def test_eff_tests_list(self, admin):
        r = admin.get("/api/eff-tests")
        assert r.status == 200
        assert len(r.data["list"]) >= 20

    def test_eff_tests_by_equipment(self, admin):
        r = admin.get("/api/eff-tests?equipment=EQ-A01")
        assert all(x["equipment_code"] == "EQ-A01" for x in r.data["list"])

    def test_calc_air_compressor(self, admin):
        r = admin.post("/api/eff-tests/calc", {"etype": "空压机", "inputPower": 118,
                                               "outputQty": 20.5})
        assert r.status == 200
        assert r.data["value"] == 5.76 and r.data["grade"] == "优"

    def test_calc_chiller(self, admin):
        r = admin.post("/api/eff-tests/calc", {"etype": "制冷机", "inputPower": 185,
                                               "outputKw": 1017})
        assert r.data["value"] == 5.5

    def test_calc_bad_type(self, admin):
        assert admin.post("/api/eff-tests/calc", {"etype": "风机"}).status == 400

    def test_save_test(self, admin):
        r = admin.post("/api/eff-tests", {"equipment": "EQ-A01", "date": "2026-10-20",
                                          "etype": "空压机", "inputPower": 120,
                                          "outputQty": 20.0})
        assert r.status == 200
        assert r.data["value"] == 6.0
        assert r.data["grade"] == "优"

    def test_saved_test_visible(self, admin):
        lst = admin.get("/api/eff-tests?equipment=EQ-A01").data["list"]
        assert any(x["date"] == "2026-10-20" and x["value"] == 6.0 for x in lst)

    def test_reader_cannot_calc(self, tokens):
        assert tokens["reader"].post("/api/eff-tests/calc",
                                     {"etype": "水泵", "inputPower": 1}).status == 403


# ============ 11. 节能项目与验证 ============

class TestProjects:
    def test_list(self, admin):
        r = admin.get("/api/projects")
        assert r.status == 200
        assert len(r.data["list"]) >= 6

    def test_detail(self, admin):
        r = admin.get("/api/projects/SP2026-005/detail")
        assert r.status == 200
        assert r.data["no"] == "SP2026-005"
        assert "baseline" in r.data
        assert isinstance(r.data["verifies"], list)

    def test_detail_404(self, admin):
        assert admin.get("/api/projects/SP9999/detail").status == 404

    def test_create(self, admin):
        r = admin.post("/api/projects", {"no": "SP-TEST-01", "name": "测试节能项目",
                                         "center": "CC101", "line": "L1",
                                         "baselineCode": "BL-L1", "invest": 100000,
                                         "measure": "测试"})
        assert r.status == 200
        assert r.data["no"] == "SP-TEST-01"

    def test_create_duplicate(self, admin):
        r = admin.post("/api/projects", {"no": "SP-TEST-01", "name": "重复",
                                         "baselineCode": "BL-L1"})
        assert r.status == 409

    def test_create_missing_name(self, admin):
        assert admin.post("/api/projects", {"baselineCode": "BL-L1"}).status == 400

    def test_create_without_baseline(self, admin):
        r = admin.post("/api/projects", {"no": "SP-TEST-02", "name": "无基线"})
        assert r.status == 409
        assert "基线" in r.message

    def test_verify_success(self, admin):
        r = admin.post("/api/projects/SP2026-005/verify", {"period": "2026-10"})
        assert r.status == 200
        d = r.data
        for k in ("baseUnit", "reportUnit", "qty", "savingTce", "savingRate",
                  "savingFeeYear", "paybackYear", "verdict"):
            assert k in d
        assert d["verdict"] in ("达标", "未达标")
        assert d["paybackYear"] >= 0

    def test_verify_persisted(self, admin):
        d = admin.get("/api/projects/SP2026-005/detail").data
        assert any(v["period"] == "2026-10" for v in d["verifies"])
        assert d["status"] in ("已验证", "未达标")

    def test_verify_no_baseline_project(self, admin):
        admin.post("/api/projects", {"no": "SP-TEST-03", "name": "无基线项目",
                                     "requireBaseline": False})
        r = admin.post("/api/projects/SP-TEST-03/verify", {"period": "2026-10"})
        assert r.status == 409
        assert "基线" in r.message

    def test_verify_no_readings(self, admin):
        r = admin.post("/api/projects/SP2026-005/verify", {"period": "2019-01"})
        assert r.status == 409

    def test_verify_404(self, admin):
        assert admin.post("/api/projects/SP-NONE/verify", {"period": "2026-10"}).status == 404

    def test_verify_requires_perm(self, tokens):
        assert tokens["staff"].post("/api/projects/SP2026-005/verify",
                                    {"period": "2026-10"}).status == 403


# ============ 12. 告警 ============

class TestAlarms:
    def test_list(self, admin):
        r = admin.get("/api/alarms")
        assert r.status == 200
        assert len(r.data["list"]) >= 40
        assert "summary" in r.data

    def test_filter_by_level(self, admin):
        lst = admin.get("/api/alarms?level=紧急").data["list"]
        assert all(a["level"] == "紧急" for a in lst)

    def test_filter_by_status(self, admin):
        lst = admin.get("/api/alarms?status=待处置").data["list"]
        assert all(a["status"] == "待处置" for a in lst)

    def test_filter_by_period(self, admin):
        lst = admin.get("/api/alarms?period=2026-10").data["list"]
        assert all(a["period"] == "2026-10" for a in lst)

    def test_order_urgent_first(self, admin):
        lst = admin.get("/api/alarms").data["list"]
        ranks = [E.level_rank(a["level"]) for a in lst]
        assert ranks == sorted(ranks)

    def test_summary(self, admin):
        r = admin.get("/api/alarms/summary")
        assert r.status == 200
        s = r.data["summary"]
        assert s["合计"] >= 40
        assert "byType" in r.data and r.data["byType"]

    def test_handle_flow(self, admin):
        target = admin.get("/api/alarms?status=待处置&level=警告").data["list"][0]
        r = admin.post("/api/alarms/%s/handle" % target["no"], {"remark": "已现场处理"})
        assert r.status == 200
        assert r.data["status"] == "已处置"
        again = admin.post("/api/alarms/%s/handle" % target["no"], {})
        assert again.status == 409
        assert "已处置" in again.message

    def test_handle_404(self, admin):
        assert admin.post("/api/alarms/AL-NONE/handle", {}).status == 404

    def test_prod_cannot_handle(self, tokens):
        no = tokens["prod"].get("/api/alarms?status=待处置").data["list"][0]["no"]
        assert tokens["prod"].post("/api/alarms/%s/handle" % no, {}).status == 403


# ============ 13. 预算 ============

class TestBudgets:
    def test_list(self, admin):
        r = admin.get("/api/budgets?period=2026-10")
        assert r.status == 200
        assert r.data["list"]
        assert "totals" in r.data
        for b in r.data["list"]:
            assert b["status"] in ("正常", "预警", "超支", "阻断")

    def test_save_and_state(self, admin):
        r = admin.post("/api/budgets", {"period": "2026-12",
                                        "items": [{"center": "CC101", "energyCode": "ELEC",
                                                   "amount": 100000, "used": 95000}]})
        assert r.status == 200
        lst = admin.get("/api/budgets?period=2026-12").data["list"]
        b = next(x for x in lst if x["center"] == "CC101")
        assert b["status"] == "预警"
        assert b["rate"] == 0.95

    def test_save_blocked_state(self, admin):
        admin.post("/api/budgets", {"period": "2026-12",
                                    "items": [{"center": "CC102", "energyCode": "ELEC",
                                               "amount": 1000, "used": 1200}]})
        lst = admin.get("/api/budgets?period=2026-12").data["list"]
        b = next(x for x in lst if x["center"] == "CC102")
        assert b["status"] == "阻断" and b["blocked"] is True

    def test_upsert(self, admin):
        admin.post("/api/budgets", {"period": "2026-12",
                                    "items": [{"center": "CC102", "energyCode": "ELEC",
                                               "amount": 5000, "used": 100}]})
        lst = admin.get("/api/budgets?period=2026-12").data["list"]
        b = next(x for x in lst if x["center"] == "CC102")
        assert b["amount"] == 5000.0

    def test_reader_cannot_read_budget(self, tokens):
        assert tokens["reader"].get("/api/budgets").status == 403


# ============ 14. 系统管理 ============

class TestSystem:
    def test_users(self, admin):
        r = admin.get("/api/users")
        assert r.status == 200
        assert len(r.data["list"]) == 7
        assert len(r.data["roles"]) == 7

    def test_user_create_and_update(self, admin):
        r = admin.post("/api/users", {"username": "testuser", "name": "测试员",
                                      "role": "staff", "password": "test@2026"})
        assert r.status == 200
        r = admin.post("/api/users", {"username": "testuser", "name": "测试员改",
                                      "role": "reader", "status": "停用"})
        assert r.status == 200
        u = next(x for x in admin.get("/api/users").data["list"] if x["username"] == "testuser")
        assert u["role"] == "reader" and u["status"] == "停用"

    def test_disabled_user_cannot_login(self, cli):
        r = cli.post("/api/auth/login", {"username": "testuser", "password": "test@2026"})
        assert r.status == 403
        assert "停用" in r.message

    def test_bad_role(self, admin):
        assert admin.post("/api/users", {"username": "x1", "role": "god"}).status == 400

    def test_rules_get(self, admin):
        r = admin.get("/api/rules")
        assert r.status == 200
        keys = {x["key"] for x in r.data["list"]}
        assert {"tce_price", "demand_warn_ratio", "budget_block"} <= keys
        assert len(r.data["events"]) == 13

    def test_rules_update_takes_effect(self, admin):
        """改 demand_warn_ratio 后需量预警点应随之移动。"""
        admin.put("/api/rules", {"key": "demand_warn_ratio", "value": 0.50})
        r = admin.post("/api/demands", {"center": "CC202", "ts": "2026-10-18 09:00:00",
                                        "demandKw": 3400, "capacityKw": 6300})  # 54%
        assert r.data["status"] == "预警", r.data
        admin.put("/api/rules", {"key": "demand_warn_ratio", "value": 0.85})

    def test_api_key_lifecycle(self, admin):
        r = admin.post("/api/api-keys", {"name": "测试对接", "role": "staff"})
        assert r.status == 200
        key = r.data["key"]
        assert key.startswith("fpk_")
        # 用长期密钥访问：必须清掉 Bearer，否则会走令牌通道
        kc = Client(admin.base)
        r2 = kc.get("/api/meters", headers={"X-Fp-Key": key})
        assert r2.status == 200
        # 越权应被拒（staff 无 sys.user）
        r3 = kc.get("/api/users", headers={"X-Fp-Key": key})
        assert r3.status == 403
        # 列表不回显明文
        lst = admin.get("/api/api-keys").data["list"]
        assert all("key" not in x for x in lst)

    def test_api_key_wrong(self, admin):
        kc = Client(admin.base)
        assert kc.get("/api/meters", headers={"X-Fp-Key": "fpk_bogus"}).status == 401

    def test_api_key_delete(self, admin):
        name = "待删-%d" % int(time.time() * 1000)
        r = admin.post("/api/api-keys", {"name": name, "role": "reader"})
        key = r.data["key"]
        # 按名字精确定位，避免依赖列表顺序
        kid = next(x["id"] for x in admin.get("/api/api-keys").data["list"]
                   if x["name"] == name)
        assert admin.delete("/api/api-keys/%s" % kid).status == 200
        kc = Client(admin.base)
        assert kc.get("/api/meters", headers={"X-Fp-Key": key}).status == 401
        assert all(x["name"] != name for x in admin.get("/api/api-keys").data["list"])

    def test_webhook_lifecycle(self, admin):
        r = admin.post("/api/webhooks", {"name": "本地测试", "url": "http://127.0.0.1:1/hook",
                                         "events": "reading.created,demand.over", "secret": "s3cr3t"})
        assert r.status == 200
        lst = admin.get("/api/webhooks").data["list"]
        assert any(w["name"] == "本地测试" for w in lst)
        wid = lst[-1]["id"]
        assert admin.delete("/api/webhooks/%s" % wid).status == 200

    def test_webhook_bad_url(self, admin):
        r = admin.post("/api/webhooks", {"name": "bad", "url": "not-a-url"})
        assert r.status == 400

    def test_logs(self, admin):
        r = admin.get("/api/logs")
        assert r.status == 200
        assert r.data["list"]
        assert all("action" in x for x in r.data["list"])

    def test_logs_order_desc(self, admin):
        lst = admin.get("/api/logs").data["list"]
        assert len(lst) <= 300
        ids = [x["id"] for x in lst]
        assert ids == sorted(ids, reverse=True)


# ============ 15. 增量同步 / 幂等 / 限流 ============

class TestIntegration:
    def test_sync_meters(self, admin):
        r = admin.get("/api/sync/changes?entity=meters")
        assert r.status == 200
        assert r.data["entity"] == "meters"
        assert r.data["count"] >= 30
        assert r.data["version"] >= 1
        assert "serverTime" in r.data

    def test_sync_all_entities(self, admin):
        for e in ("meters", "energy_types", "readings", "alarms", "projects", "demands"):
            r = admin.get("/api/sync/changes?entity=%s" % e)
            assert r.status == 200, e
            assert isinstance(r.data["list"], list)

    def test_sync_bad_entity(self, admin):
        assert admin.get("/api/sync/changes?entity=users").status == 400

    def test_sync_since_filter(self, admin):
        r1 = admin.get("/api/sync/changes?entity=readings&since=2026-10-01")
        r2 = admin.get("/api/sync/changes?entity=readings")
        assert r1.data["count"] <= r2.data["count"]

    def test_sync_requires_perm(self, tokens):
        # 只有 admin/manager/staff 有 sync.read（对接方用长期密钥）
        assert tokens["staff"].get("/api/sync/changes?entity=meters").status == 200
        for role in ("reader", "finance", "engineer", "prod"):
            assert tokens[role].get("/api/sync/changes?entity=meters").status == 403, role

    def test_idempotency_key(self, admin):
        key = "idem-test-%d" % int(time.time() * 1000)
        body = {"meter": "EMGATE1", "period": "2027-01", "reading": 999999}
        r1 = admin.post("/api/readings", body, headers={"Idempotency-Key": key})
        assert r1.status == 200
        r2 = admin.post("/api/readings", body, headers={"Idempotency-Key": key})
        assert r2.status == 200
        assert r2.body == r1.body    # 第二次直接回放缓存

    def test_cors_headers(self, admin):
        r = admin.get("/api/health")
        assert r.headers.get("Access-Control-Allow-Origin") == "*"

    def test_options_preflight(self, cli):
        r = cli._req("OPTIONS", "/api/meters")
        assert r.status == 204
        assert "Idempotency-Key" in r.headers.get("Access-Control-Allow-Headers", "")

    def test_rate_limit_allows_normal_traffic(self, admin):
        """300 次/分钟阈值下，连续 20 次应全部放行。"""
        for _ in range(20):
            assert admin.get("/api/health").status == 200
