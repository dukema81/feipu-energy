# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 文档批量上传知识库（分类 33 企业管理系统）"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = r"C:/Users/maxl/WorkBuddy/Claw/feipu-energy"
BASE = "http://42.193.158.63"
CAT = 33
PASSWORD = "YCSpyVwt@J2UByom3#n6gb"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
REPLACE = "--replace" in sys.argv

DOCS = [
    ("docs/feipu-design.md", "飞瀑能源管理系统建设方案",
     "「飞瀑能源管理系统」完整建设方案 V1.0：建设背景与目标（对标 GB/T 23331 / ISO 50001）、"
     "12 模块业务范围、核心能源口径（折标煤系数 电力 0.0001229 tce/kWh / 天然气 1.33 tce/千m³、"
     "单位产品能耗 6 位精度、分时电费四时段尖峰/峰/平/谷、15 分钟需量与容量电费 42 元/kW·月、"
     "力调电费 ±15% 封顶、设备能效四类评级 空压机比功率/水泵效率/锅炉热效率/制冷机 COP、"
     "节能量 =（基线单耗−报告期单耗）×产量 与回收期、碳排范围一/二拆分、抄表三闸口校验、"
     "预算三段闸口 90%/100%/110%）、25 表数据模型、69 路由 API 契约、7 角色 × 27 权限矩阵、"
     "零依赖技术架构（标准库 http.server + sqlite3 WAL）、6 阶段实施里程碑、验收标准与风险应对。",
     "飞瀑能源,能源管理,折标煤,分时电费,需量,设备能效,节能量,碳排放,建设方案"),
    ("docs/api.md", "飞瀑能源管理系统 REST 接口契约",
     "51 端点分组契约：统一响应包、多通道鉴权（Bearer / X-Fp-Token / Cookie / ?token= / X-Fp-Key "
     "长期密钥 SHA-256 存储）、Idempotency-Key 幂等、限流 300 次每分钟、"
     "认证与看板、主数据（能源介质/成本中心/产线/计量点/设备）、抄表三接口（手工/批量/网关上报）、"
     "分时与需量、分析报表 11 个（看板/能耗分析/单耗基线/同比/排名/能源平衡/日报/碳排/CSV 导出 UTF-8 BOM）、"
     "基线、设备能效计算器、节能项目与验证三闸口、告警处置（重复 409）、预算闸口、"
     "系统管理（用户/规则动态生效/API Key/Webhook HMAC-SHA256 签名 13 种事件/增量同步 6 实体/审计日志）、"
     "权限矩阵与对接实施建议。",
     "飞瀑能源,API,接口契约,REST,Webhook,增量同步,能源管理,对接"),
    ("docs/test-report.md", "飞瀑能源管理系统测试报告",
     "三层自动化测试 315 项全部通过：pytest 267 条（业务内核单测 120：折标煤/碳排/强度/分时电费/"
     "容量与力调/需量四级/设备能效四类/节能量年化/告警分级/抄表质量/能源平衡/预算闸口/权限矩阵；"
     "接口测试 147：鉴权五通道/7 角色权限边界/主数据/抄表三闸口实测/需量动态规则/11 报表含守恒断言/"
     "基线与项目验证三闸口/告警/预算/系统/幂等/CORS）、冒烟 31 项（部署后端到端含数据断言）、"
     "UI 巡检 17 项（15 页 0 控制台错误 + 弹层交互 + 移动端 390px 无溢出 + 18 张截图）。"
     "测试中发现并修复 11 项缺陷（力调电费公式符号错误、login.html 静态 404、路由参数名不匹配 500、"
     "同步列名错误 500、需量阈值硬编码、auth/me 权限过高、reader 缺质检权限、编号生成冲突风险等）。",
     "飞瀑能源,测试报告,质量门禁,自动化测试,Playwright,pytest"),
    ("docs/user-guide.md", "飞瀑能源管理系统操作手册",
     "面向全部 7 角色的操作手册：系统定位（GB/T 23331 / ISO 50001）、登录与账号表、"
     "16 页面逐页说明（仪表盘 8 KPI 卡、抄表三闸口规则、分时需量口径、能耗分析筛选导出、"
     "单耗基线对标、设备能效计算器、节能项目验证、告警处置、预算闸口、碳排放范围一二、"
     "报表中心 CSV、系统管理五 tab）、7 条常见问题（区间重叠/规则生效/口径核对/对接方式）、"
     "操作技巧。",
     "飞瀑能源,操作手册,用户指南,能源管理"),
    ("demo/feipu-energy-demo.zip", "飞瀑能源管理系统离线演示（DEMO）",
     "单文件离线演示：解压后双击 HTML 即可用浏览器打开，无需服务与网络。数据取自演示实例"
     "2026-10 期间真实快照：6 介质 / 10 成本中心 / 6 产线 / 31 计量点 / 360 抄表 / "
     "四时段分时电费 45.95 万元 / 最大需量 6500kW / 综合能耗 591.32 tce / 碳排 1906.71 tCO₂ / "
     "41 条告警 / 12 条预算。14 个页签覆盖仪表盘（12 期趋势+介质结构环形图）、主数据、"
     "抄表、分时需量、能耗分析、单耗基线、设备能效、节能项目、告警中心、预算、碳排放、能源平衡。",
     "飞瀑能源,DEMO,离线演示,能源管理,碳排放"),
]


def req(path, method="GET", data=None, token=None):
    r = urllib.request.Request(BASE + path, method=method)
    if data is not None:
        r.data = json.dumps(data).encode("utf-8")
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with OP.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:                                     # noqa: BLE001
            return e.code, {}


def curl_upload(path, title, desc, tags):
    full = os.path.join(ROOT, path)
    mime = "application/zip" if full.endswith(".zip") else "text/markdown"
    cmd = ["curl", "-s", "--noproxy", "*",
           "-H", "Authorization: Bearer " + TOKEN,
           "-F", "file=@%s;type=%s" % (full, mime),
           "-F", "title=" + title,
           "-F", "description=" + desc,
           "-F", "categoryId=%d" % CAT,
           "-F", "tags=" + tags,
           BASE + "/api/documents/upload"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8", "ignore"))
    except Exception:                                         # noqa: BLE001
        return {"code": -1, "raw": out.stdout.decode("utf-8", "ignore")[:400],
                "err": out.stderr.decode("utf-8", "ignore")[:200]}


def existing(cat=CAT):
    st, j = req("/api/documents?categoryId=%d&pageNum=1&pageSize=200" % cat, token=TOKEN)
    data = j.get("data") or {}
    if isinstance(data, list):
        return data
    return data.get("records") or data.get("list") or []


def delete_doc(doc_id):
    return req("/api/documents/%s" % doc_id, "DELETE", token=TOKEN)


def build_demo_zip():
    src = os.path.join(ROOT, "demo", "feipu-energy-demo.html")
    out = os.path.join(ROOT, "demo", "feipu-energy-demo.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, "飞瀑能源管理系统Demo.html")
        z.writestr("使用说明.txt",
                   "飞瀑能源管理系统 · 离线演示\r\n"
                   "1. 解压后双击「飞瀑能源管理系统Demo.html」，用浏览器打开即可，无需安装、无需联网。\r\n"
                   "2. 数据为演示实例 2026-10 期间真实快照：6 介质 / 10 成本中心 / 6 产线 / 31 计量点 /\r\n"
                   "   360 条抄表 / 综合能耗 591.32 tce / 碳排 1906.71 tCO2 / 41 条告警。\r\n"
                   "3. 14 个页签：仪表盘 / 能源介质 / 成本中心 / 计量点 / 抄表与采集 / 分时与需量 /\r\n"
                   "   能耗分析 / 单耗与基线 / 设备能效 / 节能项目 / 告警中心 / 能源预算 / 碳排放 / 能源平衡。\r\n"
                   "4. 本页为静态展示，不含写操作；范围一+范围二=总碳排、能源平衡校验差=0 可直接核对。\r\n"
                   "5. 完整版本请部署源码包（backend/ + frontend/，Python 标准库即可运行）。\r\n")
    print("DEMO zip 重建：%.1f KB" % (os.path.getsize(out) / 1024.0))


def main():
    global TOKEN
    st, j = req("/api/auth/login", "POST", {"username": "admin", "password": PASSWORD})
    assert j.get("code") == 200, j
    TOKEN = j["data"]["token"]
    st, j = req("/api/users/whoami", token=TOKEN)
    print("whoami:", j.get("code"))

    build_demo_zip()

    if REPLACE:
        want = {t for _, t, _, _ in DOCS}
        for r in existing():
            if r.get("title") in want:
                st, j = delete_doc(r.get("id"))
                print("删除旧文档 %s id=%s -> %s" % (r.get("title"), r.get("id"), st))
                time.sleep(0.4)

    results = []
    for path, title, desc, tags in DOCS:
        j = curl_upload(path, title, desc, tags)
        code = j.get("code")
        doc_id = (j.get("data") or {}).get("id") if isinstance(j.get("data"), dict) else j.get("data")
        size = os.path.getsize(os.path.join(ROOT, path))
        print("%-28s code=%s id=%s %.1fKB" % (os.path.basename(path), code, doc_id, size / 1024.0))
        if code != 200:
            print("   !!", str(j)[:300])
        results.append((path, title, code, doc_id))
        time.sleep(1.2)

    ok = [r for r in results if r[2] == 200]
    print("\n上传成功 %d / %d" % (len(ok), len(results)))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "kb_upload_result.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": r[0], "title": r[1], "code": r[2], "id": r[3]} for r in results],
                  f, ensure_ascii=False, indent=2)
    st, j = req("/api/document-categories", token=TOKEN)
    for c in (j.get("data") or []):
        if isinstance(c, dict) and c.get("id") == CAT:
            print("cat%d docCount:" % CAT, c.get("docCount"))


if __name__ == "__main__":
    main()
