# 飞瀑能源管理系统 · API 接口文档

- 版本：1.0.0
- 基础地址：`http://<host>:8021/pu`（nginx 子路径部署）
- 响应包：`{"code": 200, "message": "ok", "data": …}`；非 200 时 code 为 HTTP 状态码
- 端点总数：51

## 鉴权

| 方式 | 头部/参数 | 适用场景 |
|---|---|---|
| 会话令牌 | `Authorization: Bearer <token>` | 浏览器 / 脚本 |
| 令牌头 | `X-Fp-Token: <token>` | 不便改 Authorization 的客户端 |
| Cookie | `Cookie: fp_token=<token>` | 同域页面 |
| 查询参数 | `?token=<token>` | 仅限 GET、低敏接口 |
| 长期密钥 | `X-Fp-Key: fpk_xxx` | 系统对接（SHA-256 存储，可配角色） |

令牌经 `POST /api/auth/login` 获取，有效期 7 天；改密后全部令牌作废。
长期密钥经 `POST /api/api-keys` 创建，**明文仅返回一次**。

## 对接约定

- 限流：300 次/分钟/IP，超出返回 429
- 幂等：写接口带 `Idempotency-Key` 头，重复请求回放首次响应
- 增量同步：`GET /api/sync/changes?entity=<实体>&since=<时间>`，实体 meters / energy_types / readings / alarms / projects / demands
- Webhook：管理端订阅 13 种事件，推送 `X-Fp-Signature: sha256=hex(hmac_sha256(secret, timestamp + '.' + body))`，失败按 0/30/60/120s 退避重试
- CORS：全放行（`Access-Control-Allow-Origin: *`），支持 OPTIONS 预检

## Webhook 事件

reading.created · reading.abnormal · demand.over · alarm.raised · alarm.handled · project.verified · baseline.created · eff.degraded · meter.changed · budget.warning · sync.ready · user.changed · period.closed

## 接口清单

### /api/alarms

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/alarms` | alarms | 告警查看 |
| GET | `/api/alarms/summary` | alarm summary | 告警查看 |
| POST | `/api/alarms/{no}/handle` | alarm handle | 告警处置 |

### /api/analysis

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/analysis/consumption` | analysis consumption | 报表查看 |
| GET | `/api/analysis/intensity` | analysis intensity | 报表查看 |
| GET | `/api/analysis/yoy` | analysis yoy | 报表查看 |
| GET | `/api/analysis/rank` | analysis rank | 报表查看 |

### /api/api-keys

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/api-keys` | keys | 密钥管理 |
| POST | `/api/api-keys` | key create | 密钥管理 |
| DELETE | `/api/api-keys/{kid}` | key del | 密钥管理 |

### /api/auth

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/api/auth/login` | login | 登录 |
| POST | `/api/auth/logout` | logout | 登录 |
| GET | `/api/auth/me` | me | 登录 |
| POST | `/api/auth/change-password` | change pwd | 登录 |

### /api/baselines

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/baselines` | baselines | 基线查看 |
| POST | `/api/baselines` | baseline create | 基线维护 |

### /api/board

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/board` | board | 报表查看 |

### /api/budgets

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/budgets` | budgets | 预算查看 |
| POST | `/api/budgets` | budget save | 预算维护 |

### /api/cost-centers

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/cost-centers` | centers | 中心查看 |
| POST | `/api/cost-centers` | <lambda> | 中心维护 |
| PUT | `/api/cost-centers/{code}` | <lambda> | 中心维护 |

### /api/demands

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/demands` | demands | 介质查看 |
| POST | `/api/demands` | demand create | 介质维护 |
| GET | `/api/demands/summary` | demand summary | 介质查看 |

### /api/eff-tests

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/eff-tests` | eff tests | 设备查看 |
| POST | `/api/eff-tests` | eff save | 设备维护 |
| POST | `/api/eff-tests/calc` | eff calc | 设备维护 |

### /api/energy-types

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/energy-types` | energy types | 介质查看 |
| POST | `/api/energy-types` | <lambda> | 介质维护 |
| PUT | `/api/energy-types/{code}` | <lambda> | 介质维护 |
| DELETE | `/api/energy-types/{code}` | energy type del | 介质维护 |

### /api/equipments

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/equipments` | equipments | 设备查看 |
| POST | `/api/equipments` | equipment save | 设备维护 |

### /api/health

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/health` | health | 登录 |

### /api/intervals

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/intervals` | intervals | 介质查看 |
| POST | `/api/intervals` | interval save | 介质维护 |

### /api/lines

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/lines` | lines | 中心查看 |
| POST | `/api/lines` | line save | 中心维护 |

### /api/logs

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/logs` | logs | 审计日志 |

### /api/meters

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/meters` | meters | 计量点查看 |
| POST | `/api/meters` | <lambda> | 计量点维护 |
| PUT | `/api/meters/{code}` | <lambda> | 计量点维护 |

### /api/openapi.json

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/openapi.json` | openapi | 登录 |

### /api/projects

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/projects` | projects | 项目查看 |
| POST | `/api/projects` | project create | 项目维护 |
| GET | `/api/projects/{no}/detail` | project detail | 项目查看 |
| POST | `/api/projects/{no}/verify` | project verify | 项目验证 |

### /api/readings

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/readings` | readings | 抄表查看 |
| POST | `/api/readings` | reading create | 抄表录入 |
| POST | `/api/readings/batch` | reading batch | 抄表录入 |
| POST | `/api/readings/report` | reading report | 抄表录入 |
| GET | `/api/readings/check` | reading check | 抄表质检 |

### /api/reports

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/reports/energy-balance` | report balance | 报表查看 |
| GET | `/api/reports/daily` | report daily | 报表查看 |
| GET | `/api/reports/carbon` | report carbon | 报表查看 |
| GET | `/api/reports/export` | report export | 报表查看 |

### /api/rules

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/rules` | rules | 报表查看 |
| PUT | `/api/rules` | rule save | 规则维护 |

### /api/sync

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/sync/changes` | sync changes | 增量同步 |

### /api/tariffs

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/tariffs` | tariffs | 介质查看 |
| POST | `/api/tariffs` | tariff save | 介质维护 |

### /api/tou-summary

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/tou-summary` | tou summary | 介质查看 |

### /api/users

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/users` | users | 用户管理 |
| POST | `/api/users` | user save | 用户管理 |

### /api/webhooks

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/webhooks` | webhooks | Webhook 管理 |
| POST | `/api/webhooks` | webhook create | Webhook 管理 |
| DELETE | `/api/webhooks/{wid}` | webhook del | Webhook 管理 |

### /apidoc

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/apidoc` | openhtml | 登录 |

## 响应示例

```json
// GET /api/board?period=2026-10
{
 "code": 200,
 "message": "ok",
 "data": {
  "period": "2026-10",
  "kpi": {
   "tce": 591.32,
   "tcePrev": 598.81,
   "tceRate": -0.0125,
   "co2": 1906.71,
   "scope1": 198.33,
   "scope2": 1708.38,
   "unitEnergy": 0.00206,
   "valueEnergy": 0.505091,
   "maxDemand": 6500.0,
   "capacityKw": 6300.0,
   "alarms": {
    "紧急": 1,
    "严重": 12,
    "警告": 5,
    "提示": 23,
    "未处置": 34
   },
   "budget": {
    "rate": 0.978,
    "status": "预警"
   }
  },
  "byEnergy": [
   {
    "energy": "ELEC",
    "qty": 1883515.5,
    "tce": 231.5
   }
  ]
 }
}
```
