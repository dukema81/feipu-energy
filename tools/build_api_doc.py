# -*- coding: utf-8 -*-
"""从运行中实例的 /api/openapi.json 自动生成 docs/api.md。"""
import json
import os
import urllib.request

BASE = "http://localhost:8931"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

req = urllib.request.Request(BASE + "/api/openapi.json")
with urllib.request.urlopen(req, timeout=15) as r:
    js = json.loads(r.read())
spec = js.get("data", js)   # 兼容 {code,message,data} 包裹

PERM_CN = {
    "energy.read": "介质查看", "energy.write": "介质维护",
    "center.read": "中心查看", "center.write": "中心维护",
    "meter.read": "计量点查看", "meter.write": "计量点维护",
    "read.read": "抄表查看", "read.write": "抄表录入", "read.check": "抄表质检",
    "equip.read": "设备查看", "equip.write": "设备维护",
    "base.read": "基线查看", "base.write": "基线维护",
    "proj.read": "项目查看", "proj.write": "项目维护", "proj.verify": "项目验证",
    "alarm.read": "告警查看", "alarm.write": "告警处置",
    "report.read": "报表查看",
    "budget.read": "预算查看", "budget.write": "预算维护",
    "sync.read": "增量同步",
    "sys.user": "用户管理", "sys.rule": "规则维护", "sys.key": "密钥管理",
    "sys.hook": "Webhook 管理", "sys.log": "审计日志",
}

lines = ["# 飞瀑能源管理系统 · API 接口文档",
         "",
         "- 版本：%s" % spec["info"].get("version", "1.0.0"),
         "- 基础地址：`http://<host>:8021/pu`（nginx 子路径部署）",
         "- 响应包：`{\"code\": 200, \"message\": \"ok\", \"data\": …}`；非 200 时 code 为 HTTP 状态码",
         "- 端点总数：%d" % len(spec["paths"]),
         "",
         "## 鉴权",
         "",
         "| 方式 | 头部/参数 | 适用场景 |",
         "|---|---|---|",
         "| 会话令牌 | `Authorization: Bearer <token>` | 浏览器 / 脚本 |",
         "| 令牌头 | `X-Fp-Token: <token>` | 不便改 Authorization 的客户端 |",
         "| Cookie | `Cookie: fp_token=<token>` | 同域页面 |",
         "| 查询参数 | `?token=<token>` | 仅限 GET、低敏接口 |",
         "| 长期密钥 | `X-Fp-Key: fpk_xxx` | 系统对接（SHA-256 存储，可配角色） |",
         "",
         "令牌经 `POST /api/auth/login` 获取，有效期 7 天；改密后全部令牌作废。",
         "长期密钥经 `POST /api/api-keys` 创建，**明文仅返回一次**。",
         "",
         "## 对接约定",
         "",
         "- 限流：300 次/分钟/IP，超出返回 429",
         "- 幂等：写接口带 `Idempotency-Key` 头，重复请求回放首次响应",
         "- 增量同步：`GET /api/sync/changes?entity=<实体>&since=<时间>`，实体 meters / energy_types / readings / alarms / projects / demands",
         "- Webhook：管理端订阅 13 种事件，推送 `X-Fp-Signature: sha256=hex(hmac_sha256(secret, timestamp + '.' + body))`，失败按 0/30/60/120s 退避重试",
         "- CORS：全放行（`Access-Control-Allow-Origin: *`），支持 OPTIONS 预检",
         "",
         "## Webhook 事件",
         "",
         "reading.created · reading.abnormal · demand.over · alarm.raised · alarm.handled · "
         "project.verified · baseline.created · eff.degraded · meter.changed · budget.warning · "
         "sync.ready · user.changed · period.closed",
         "",
         "## 接口清单",
         ""]

# 按前缀分组
groups = {}
for path, methods in spec["paths"].items():
    for m, op in methods.items():
        pre = "/" + "/".join(path.strip("/").split("/")[:2])
        groups.setdefault(pre, []).append((m.upper(), path, op))

for pre in sorted(groups):
    lines.append("### %s" % pre)
    lines.append("")
    lines.append("| 方法 | 路径 | 说明 | 权限 |")
    lines.append("|---|---|---|---|")
    for m, path, op in groups[pre]:
        perm = op.get("permission", "登录")
        perm_cn = PERM_CN.get(perm, perm or "公开")
        summary = op.get("summary", "")
        lines.append("| %s | `%s` | %s | %s |" % (m, path, summary, perm_cn))
    lines.append("")

lines.append("## 响应示例")
lines.append("")
lines.append("```json")
lines.append("// GET /api/board?period=2026-10")
example = {
    "code": 200, "message": "ok",
    "data": {"period": "2026-10",
             "kpi": {"tce": 591.32, "tcePrev": 598.81, "tceRate": -0.0125,
                     "co2": 1906.71, "scope1": 198.33, "scope2": 1708.38,
                     "unitEnergy": 0.00206, "valueEnergy": 0.505091,
                     "maxDemand": 6500.0, "capacityKw": 6300.0,
                     "alarms": {"紧急": 1, "严重": 12, "警告": 5, "提示": 23, "未处置": 34},
                     "budget": {"rate": 0.978, "status": "预警"}},
             "byEnergy": [{"energy": "ELEC", "qty": 1883515.5, "tce": 231.5}]}}
lines.append(json.dumps(example, ensure_ascii=False, indent=1))
lines.append("```")
lines.append("")

out = os.path.join(ROOT, "docs", "api.md")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print("api.md: %d 端点 -> %s" % (len(spec["paths"]), out))
