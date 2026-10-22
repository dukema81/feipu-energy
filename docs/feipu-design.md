# 飞瀑能源管理系统 · 建设方案

- 版本：V1.0
- 日期：2026-10-22
- 定位：面向制造企业的能源全流程管控平台，覆盖「计量 → 抄表 → 能耗分析 → 能效诊断 → 节能项目 → 碳排核算」闭环

---

## 第一章 建设背景与目标

### 1.1 背景

制造企业的能源成本通常占制造费用的 8%–20%，但管理方式普遍粗放：

1. **计量孤岛**：电、水、蒸汽、压缩空气、天然气各自由不同部门管理，表计数据散落在纸质台账、Excel、甚至班组口头记录里，月底靠人汇总。
2. **算不清单耗**：只有总表读数，无法把能耗归集到产线、工单、产品，单位产品能耗、单位产值能耗说不清楚，节能考核无从下手。
3. **峰值失控**：变压器容量电费按最大需量计收，若不盯住 15 分钟需量，一次冲压线集中启动就可能把当月基本电费抬高数万元。
4. **节能量说不明**：节能项目立项靠拍脑袋，节能量没有基线、没有验证方法，投资回收期算不准，第二年预算过不了会。
5. **碳排被动报送**：客户与监管开始要求碳足迹数据，靠临时翻电费单倒推，口径不一致、无法追溯。

### 1.2 建设目标

| 目标 | 度量 |
|---|---|
| 能源数据全口径在线 | 一、二级计量点覆盖率 ≥ 95%，数据自动采集或日抄，月结不再人工汇总 |
| 单耗可归集 | 能耗可归集到成本中心 / 产线 / 产品，形成单位产品能耗与单位产值能耗 |
| 峰值可控 | 实时 15 分钟需量跟踪，超阈值提前预警，容量电费可核算 |
| 节能量可验证 | 每个节能项目有基线与验证口径，节能量与投资回收期自动计算 |
| 碳排可核算 | 按能源介质折标煤与碳排因子自动核算，支持范围一/范围二拆分 |
| 对外可集成 | 完整的 REST 接口契约与 Webhook 事件，可与 MES / ERP / 财务 / 碳平台对接 |

### 1.3 建设原则

- **零第三方运行时依赖**：Python 标准库 `http.server` + `sqlite3`（WAL），前端原生 JS，一套代码在任何装了 Python 3.8+ 的机器上都能跑起来。
- **口径即代码**：所有能源计算（折标煤、需量、能效比、节能量、碳排）都实现为纯函数，可单元测试，杜绝"两套 Excel 算出两个数"。
- **闸口优先**：数据可疑就不让过——抄表倒走、量级跳变、区间重叠、无基线不允许立项、超需量不允许确认为正常，全部在服务端硬拦截。

---

## 第二章 业务范围

### 2.1 模块清单（12 个）

| # | 模块 | 说明 |
|---|---|---|
| 1 | 能源介质 | 电、水、蒸汽、压缩空气、天然气、柴油等介质定义，含热值、折标煤系数、碳排因子、计价方式 |
| 2 | 计量点 | 一/二/三级计量点台账，挂在成本中心与产线下，含倍率、量程、通讯方式 |
| 3 | 抄表与采集 | 手工抄表、批量抄表、接口上报；含表底倒走、量级跳变、区间重叠校验 |
| 4 | 分时能耗 | 峰/平/谷/尖峰四时段电量归集，支持分时电价与电费核算 |
| 5 | 需量管理 | 15 分钟滑动需量、最大需量、容量电费、超容预警 |
| 6 | 能耗分析 | 按中心/产线/介质/时段多维分析，同比环比、单位产品能耗、单位产值能耗 |
| 7 | 能耗基线 | 按产线/产品建立基线模型（单位产品能耗基线），作为节能量验证依据 |
| 8 | 设备能效 | 空压机比功率、水泵效率、锅炉热效率、制冷 COP 等能效指标计算与评级 |
| 9 | 节能项目 | 立项（基线+措施+投资）→ 实施 → 验证（节能量、节费、投资回收期）全流程 |
| 10 | 告警中心 | 需量超限、单耗异常、抄表异常、能效劣化四级告警与处置闭环 |
| 11 | 碳排放 | 折标煤、碳排量、范围一/二拆分、碳强度（吨 CO₂/万元产值） |
| 12 | 报表与集成 | 日报月报、能源平衡表、CSV 导出、API Key / Webhook / 增量同步 |

### 2.2 明确不做（V1.0 边界）

- 不做 SCADA 实时数采驱动（提供标准上报接口，由采集网关对接）
- 不做电力市场交易与需求响应竞价
- 不做设备台账全生命周期（与 EAM/设备系统对接）
- 不做碳配额履约与 CCER 交易

---

## 第三章 核心能源口径

本章所有公式均实现为 `backend/energy.py` 中的纯函数，并有单元测试覆盖。

### 3.1 折标煤

```
折标煤(吨标煤) = 物理量 × 折标煤系数
电：1 kWh = 0.1229 kgce  → 系数 0.0001229 tce/kWh（等价值口径可按企业实际调整）
蒸汽：1 t = 0.09286 tce（按焓值可调）
天然气：1 万 m³ ≈ 13.3 tce
```

系统内介质表字段 `tce_factor` 存每计量单位折标煤系数，`co2_factor` 存碳排因子（tCO₂/单位）。

### 3.2 能耗强度

```
单位产品能耗 = 期间综合能耗(折标煤) ÷ 期间合格产出量
单位产值能耗 = 期间综合能耗(折标煤) ÷ 期间工业总产值(万元)
```

两个指标同时给出，前者用于生产考核，后者用于行业对标。

### 3.3 分时电费

```
电费 = Σ(时段电量 × 时段电价) + 基本电费(容量电费) + 力调电费
容量电费 = 最大需量(kW) × 需量单价(元/kW·月)
```

时段划分：尖峰 / 峰 / 平 / 谷，各时段电价由能源介质下的电价方案维护。

### 3.4 需量（15 分钟滑动）

```
需量(kW) = 15 分钟内电能增量(kWh) ÷ 0.25 h
```

采集到 1 分钟粒度功率曲线时按滑动窗口取最大值；仅抄到小时电量时按"小时电量 ÷ 1h"作为该小时需量近似，并在数据质量标记中说明口径。

### 3.5 设备能效

| 设备类型 | 指标 | 公式 | 优/良/差分界 |
|---|---|---|---|
| 空压机 | 比功率 kW/(m³/min) | 输入功率 ÷ 排气量 | ≤6.3 优，≤7.2 良，>7.2 差 |
| 水泵 | 运行效率 % | 有效功率 ÷ 轴功率 | ≥75 优，≥65 良，<65 差 |
| 锅炉 | 热效率 % | 有效吸热 ÷ 输入热量 | ≥92 优，≥88 良，<88 差 |
| 制冷机 | COP | 制冷量 ÷ 输入功率 | ≥5.0 优，≥4.0 良，<4.0 差 |

### 3.6 节能量与项目收益

```
节能量 = (基线单位能耗 − 报告期单位能耗) × 报告期产量
节能率 = (基线单位能耗 − 报告期单位能耗) ÷ 基线单位能耗
年节费 = 节能量(折标煤) × 能源单价换算系数  或按介质分别计算
投资回收期(年) = 投资额 ÷ 年节费
```

**闸口**：无基线不允许立项；报告期产量为 0 不允许验证；节能量为负（项目反而更耗能）必须标记为"未达标"并强制填写原因。

### 3.7 碳排放

```
碳排量(tCO₂) = Σ(各介质物理量 × 该介质 co2_factor)
范围一：天然气、柴油等直接燃烧
范围二：外购电力、外购蒸汽
碳强度 = 碳排量 ÷ 工业总产值(万元)
```

### 3.8 告警分级

| 级别 | 触发条件（默认，可按规则表调整） |
|---|---|
| 紧急 | 需量 ≥ 变压器容量 × 95%，或单耗超基线 30% |
| 严重 | 需量 ≥ 容量 × 85%，或单耗超基线 15% |
| 警告 | 单耗超基线 8%，或抄表量级跳变超 50% |
| 提示 | 抄表逾期、能效等级下滑一档 |

### 3.9 抄表数据质量校验

| 校验 | 规则 | 处理 |
|---|---|---|
| 倒走 | 本期表底 < 上期表底 | 拒绝（409） |
| 区间重叠 | 同一计量点同期间已有读数 | 拒绝（409） |
| 量级跳变 | 本期用量 > 上期用量 × 3 且上期用量 > 0 | 允许但标记 `跳变`，进告警 |
| 换表 | 换表时填写新表底与表底差值 | 用量 = (新表底 − 0) + (上期终底 − 换表时旧表底) |

---

## 第四章 数据模型（21 张表）

| 表 | 说明 | 关键字段 |
|---|---|---|
| `users` | 用户 | username, password_hash, name, role |
| `tokens` | 会话令牌 | token, username, expire_at |
| `api_keys` | 接口密钥 | key_prefix, key_hash, name, role |
| `energy_types` | 能源介质 | code, name, unit, tce_factor, co2_factor, scope, price, price_mode |
| `tariffs` | 分时电价方案 | energy_code, period, price, month |
| `cost_centers` | 成本中心 | code, name, ctype, parent |
| `lines` | 产线 | code, name, center, product, capacity |
| `meters` | 计量点 | code, name, energy_code, center, line, level, ratio, capacity, status, gateway |
| `readings` | 抄表记录 | meter_code, period, date, reading, usage, is_estimate, quality, source |
| `intervals` | 分时电量 | meter_code, date, period, kwh, price |
| `demands` | 需量记录 | center, date, time, demand_kw, capacity_kw, over |
| `outputs` | 产量/产值 | center, line, period, product, qty, value |
| `baselines` | 能耗基线 | line, product, period_from, period_to, base_unit, method |
| `equipments` | 用能设备 | code, name, etype, center, rated_power, rated_output, spec |
| `eff_tests` | 能效测试 | equipment_code, date, input_power, output_qty, efficiency, grade |
| `projects` | 节能项目 | no, name, line, baseline_id, invest, measure, status, verify_period |
| `project_verify` | 项目验证 | project_no, period, base_unit, report_unit, qty, saving_tce, saving_fee, payback |
| `alarms` | 告警 | no, level, atype, target, message, value, threshold, status, handled_by |
| `budgets` | 能源预算 | period, center, energy_code, amount, used |
| `rules` | 业务规则 | key, value, remark |
| `logs` | 审计日志 | at, user, action, target, detail, ip |
| `webhooks` / `webhook_deliveries` | 事件订阅 | url, secret, events, status |
| `idem_keys` | 幂等键 | key, endpoint, response |
| `sync_state` | 增量同步游标 | entity, version |

---

## 第五章 API 契约（对外对接重点章节）

### 5.1 通用约定

**基础路径**：`/api`（部署在子路径时对外为 `http://host/pu/api`，服务端同时兼容带/不带前缀）

**响应包**：

```json
{ "code": 200, "message": "ok", "data": {...} }
```

错误码：`400` 参数错误、`401` 未认证、`403` 权限不足、`404` 不存在、`409` 业务闸口拦截、`429` 限流。

**鉴权（多通道，任选一种）**：

| 通道 | 用法 | 适用 |
|---|---|---|
| `Authorization: Bearer <token>` | 登录后获得 | 前端、脚本 |
| `X-Fp-Token: <token>` | 同上 | 不方便改 header 的网关 |
| `Cookie: fp_token=<token>` | 同上 | 浏览器直连 |
| `?token=<token>` | 同上 | Webhook 回调、临时链接 |
| `X-Fp-Key: <api_key>` | 长期密钥 | 系统对接（MES/ERP/采集网关） |

API Key 明文形如 `fpk_xxxxxxxxxxxx`，服务端只存 SHA-256 前 16 位用于检索 + 哈希校验，创建时一次性返回明文。

**幂等**：写接口支持 `Idempotency-Key: <uuid>`，同 key 同 endpoint 24 小时内重复请求直接返回首次结果。

**限流**：单 IP 每分钟 300 次，超限 429。

**时间与期间**：期间统一 `YYYY-MM`；时间 `YYYY-MM-DD HH:MM:SS`（服务器本地时区）。

### 5.2 认证

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | `{username, password}` → `{token, user}` |
| POST | `/api/auth/logout` | 登录 | 注销当前令牌 |
| POST | `/api/auth/change-password` | 登录 | `{oldPassword, newPassword}` |
| GET | `/api/auth/me` | 登录 | 当前用户与权限列表 |

### 5.3 主数据

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET/POST | `/api/energy-types` | `energy.read` / `energy.write` | 介质列表 / 新建 |
| PUT/DELETE | `/api/energy-types/{code}` | `energy.write` | 修改 / 删除（有计量点则拒绝） |
| GET/POST | `/api/tariffs` | `energy.read` / `energy.write` | 分时电价 |
| GET/POST | `/api/cost-centers` | `center.read` / `center.write` | 成本中心 |
| GET/POST | `/api/lines` | `center.read` / `center.write` | 产线 |
| GET/POST | `/api/meters` | `meter.read` / `meter.write` | 计量点 |
| PUT | `/api/meters/{code}` | `meter.write` | 修改（倍率、容量、状态） |
| GET/POST | `/api/equipments` | `equip.read` / `equip.write` | 用能设备 |

### 5.4 抄表与采集（对接重点）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/readings?meter=&period=&from=&to=` | `read.read` | 抄表记录 |
| POST | `/api/readings` | `read.write` | 单条抄表 `{meter, date, reading, isEstimate}` |
| POST | `/api/readings/batch` | `read.write` | 批量抄表 `{period, items:[{meter, reading}]}`，逐条返回成功/失败原因 |
| POST | `/api/readings/report` | `read.write`（或 API Key） | **采集网关上报**：`{meter, ts, value, quality}`，自动算用量 |
| GET | `/api/readings/check?period=` | `read.read` | 数据质量报告：缺失、跳变、倒走 |

**采集网关上报示例**：

```http
POST /api/readings/report
X-Fp-Key: fpk_9f2c1a7b3e6d4c5f
Content-Type: application/json

{ "meter": "EM101", "ts": "2026-10-22 10:15:00", "value": 128456.7, "quality": "good" }
```

返回：

```json
{ "code": 200, "data": { "meter": "EM101", "usage": 42.7, "quality": "good", "alarm": null } }
```

### 5.5 分时与需量

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/intervals?meter=&date=` | `energy.read` | 分时电量 |
| POST | `/api/intervals` | `energy.write` | 写入分时电量 |
| GET | `/api/demands?center=&period=` | `energy.read` | 需量记录 |
| POST | `/api/demands` | `energy.write` | 上报需量 `{center, ts, demandKw}`，超容自动生成告警 |
| GET | `/api/demands/summary?period=` | `energy.read` | 最大需量与容量电费汇总 |

### 5.6 分析与报表

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/board?period=` | `report.read` | 看板 KPI |
| GET | `/api/analysis/consumption?period=&center=&line=&energy=` | `report.read` | 多维能耗 |
| GET | `/api/analysis/intensity?period=` | `report.read` | 单位产品/单位产值能耗 |
| GET | `/api/analysis/yoy?period=` | `report.read` | 同比环比 |
| GET | `/api/reports/energy-balance?period=` | `report.read` | 能源平衡表 |
| GET | `/api/reports/daily?from=&to=` | `report.read` | 日报 |
| GET | `/api/reports/carbon?period=` | `report.read` | 碳排 |
| GET | `/api/reports/export?type=&period=` | `report.read` | CSV 导出（UTF-8 BOM） |

### 5.7 基线、能效、项目

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET/POST | `/api/baselines` | `base.read` / `base.write` | 能耗基线 |
| POST | `/api/eff-tests/calc` | `equip.write` | 能效计算（传实测参数，返回指标与评级） |
| GET/POST | `/api/projects` | `proj.read` / `proj.write` | 节能项目 |
| POST | `/api/projects/{no}/verify` | `proj.write` | 项目节能量验证 |
| GET | `/api/projects/{no}/detail` | `proj.read` | 项目详情含验证记录 |

### 5.8 告警

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/alarms?level=&status=&period=` | `alarm.read` | 告警列表 |
| POST | `/api/alarms/{no}/handle` | `alarm.write` | 处置 `{action, remark}` |
| GET | `/api/alarms/summary` | `alarm.read` | 按级别统计 |

### 5.9 同步与管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/sync/changes?entity=meters&since=2026-10-01` | `sync.read` | 增量同步 |
| GET | `/api/openapi.json` | 登录 | 自动生成 OpenAPI |
| GET | `/api/health` | 公开 | 健康检查 |
| GET/POST | `/api/users` | `sys.user` | 用户管理 |
| GET/PUT | `/api/rules` | `sys.rule` | 业务规则 |
| GET/POST/DELETE | `/api/api-keys` | `sys.key` | 接口密钥 |
| GET/POST/DELETE | `/api/webhooks` | `sys.hook` | 事件订阅 |
| GET | `/api/logs` | `sys.log` | 审计日志 |

### 5.10 Webhook 事件

服务端在关键动作后异步 POST 到订阅地址：

```
POST <your-url>
X-Fp-Event: reading.created
X-Fp-Timestamp: 1761187200
X-Fp-Signature: sha256=<hex(hmac_sha256(secret, timestamp + "." + rawBody))>

{ "event": "reading.created", "at": "2026-10-22 10:15:00", "data": { ... } }
```

事件清单（13 种）：`reading.created`、`reading.abnormal`、`demand.over`、`alarm.raised`、`alarm.handled`、`project.verified`、`baseline.created`、`eff.degraded`、`meter.changed`、`budget.warning`、`sync.ready`、`user.changed`、`period.closed`。

失败重试：30s / 60s / 120s 三次退避，仍失败记入 `webhook_deliveries` 并告警。

### 5.11 给对接方的实施建议

1. **采集网关**：用 API Key + `/api/readings/report` 上报，单点失败不影响批次；建议本地缓存断点续传。
2. **MES 取产量**：定时调 `/api/analysis/intensity` 拿单位产品能耗，与 MES 的产量做交叉核对。
3. **ERP / 财务**：用 `/api/reports/energy-balance` 拿月度能源成本，`/api/reports/carbon` 拿碳排数据入 ESG 报表。
4. **增量同步**：`/api/sync/changes` 按 `since` 拉变更，适合做数据仓库同步，避免全量拉取。
5. **幂等**：`POST` 一律带 `Idempotency-Key`，网络重试不会重复记账。

---

## 第六章 权限矩阵（7 角色 × 22 权限）

| 权限 | 能源主管 | 能源专员 | 抄表员 | 设备工程师 | 生产经理 | 财务 | 管理员 |
|---|---|---|---|---|---|---|---|
| energy.read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| energy.write | ✓ | ✓ | | | | | ✓ |
| center.read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| center.write | ✓ | | | | | | ✓ |
| meter.read | ✓ | ✓ | ✓ | ✓ | ✓ | | ✓ |
| meter.write | ✓ | ✓ | | | | | ✓ |
| read.read | ✓ | ✓ | ✓ | | ✓ | | ✓ |
| read.write | ✓ | ✓ | ✓ | | | | ✓ |
| read.check | ✓ | ✓ | | | | | ✓ |
| equip.read | ✓ | ✓ | | ✓ | | | ✓ |
| equip.write | ✓ | | | ✓ | | | ✓ |
| base.read | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ |
| base.write | ✓ | | | | | | ✓ |
| proj.read | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ |
| proj.write | ✓ | | | ✓ | | | ✓ |
| proj.verify | ✓ | | | | | | ✓ |
| alarm.read | ✓ | ✓ | ✓ | ✓ | ✓ | | ✓ |
| alarm.write | ✓ | ✓ | | ✓ | | | ✓ |
| report.read | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ |
| budget.read | ✓ | ✓ | | | ✓ | ✓ | ✓ |
| budget.write | ✓ | | | | | | ✓ |
| sync.read | ✓ | ✓ | | | | | ✓ |
| sys.user | | | | | | | ✓ |
| sys.rule | ✓ | | | | | | ✓ |
| sys.key | ✓ | | | | | | ✓ |
| sys.hook | ✓ | | | | | | ✓ |
| sys.log | ✓ | | | | | | ✓ |

**硬约束**：抄表员可写抄表但不可改主数据；设备工程师可做能效与项目但不能审批节能量；生产经理只读；财务只读能源与报表、可管预算。

---

## 第七章 技术架构

### 7.1 分层

```
┌──────────────────────────────────────────┐
│ 前端（原生 JS SPA，13 页，hash 路由）        │
├──────────────────────────────────────────┤
│ HTTP 层 server.py（路由表 + 鉴权 + 限流    │
│ + 幂等 + 审计 + Webhook 派发）              │
├──────────────────────────────────────────┤
│ 业务内核 energy.py（纯函数，可单测）         │
│ 折标煤 / 需量 / 分时 / 能效 / 节能量 / 碳排  │
├──────────────────────────────────────────┤
│ 数据层 db.py（sqlite3 WAL，21 表）          │
└──────────────────────────────────────────┘
```

### 7.2 运行时

- Python 标准库：`http.server`（ThreadingHTTPServer）、`sqlite3`、`hmac`、`hashlib`、`json`、`csv`
- 端口：`FP_PORT`（默认 8021）；子路径前缀：`FP_PREFIX`（默认 `/pu`）
- 数据文件：`backend/feipu.db`（可用 `FP_DB` 覆盖）
- 首次启动自动建表 + 播种演示数据 + 预热（跑一遍分析），开箱可用

### 7.3 前端

- 单页应用，hash 路由（`#/dashboard`），13 个页面模块
- 无构建步骤，无 CDN 依赖（离线可用）
- 图表用内联 SVG 手绘（折线、条形、堆叠条），不引第三方库

---

## 第八章 实施里程碑

| 阶段 | 内容 | 交付 |
|---|---|---|
| M1 需求与口径 | 介质清单、计量点清单、口径确认 | 设计文档 |
| M2 后端内核 | energy.py + db.py + seed.py | 单测通过 |
| M3 接口层 | 路由、鉴权、幂等、Webhook | 接口测试通过 |
| M4 前端 | 13 页 SPA | UI 巡检通过 |
| M5 试运行 | 历史数据导入、口径比对、告警阈值调优 | 试运行报告 |
| M6 上线 | 部署、培训、交接 | 上线验收单 |

---

## 第九章 验收标准

1. **口径闭合**：折标煤、碳排、分时电费计算结果与手工核算一致，误差 ≤ 0.01。
2. **需量正确**：15 分钟需量计算与电表读数一致；超容必生成告警。
3. **数据质量**：倒走、重叠、跳变全部可检出并给出原因。
4. **节能量可验证**：项目验证输出基线单耗、报告期单耗、节能量、节费、回收期五项。
5. **权限隔离**：7 角色越权操作全部 403，抄表员不能改主数据。
6. **接口可用**：API Key 鉴权、Webhook 签名、增量同步、幂等重放均有测试。
7. **性能**：单表 10 万条抄表记录下，看板接口响应 < 500ms（本地 SQLite）。

---

## 第十章 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 计量点不全，二级计量缺失 | 单耗无法归集到产线 | 一期先做中心级归集，二期补装二级表；系统支持"估算值"标记 |
| 表计通讯不稳、数据缺口 | 需量失真、分析断档 | 缺口按同期均值补值并标记 `is_estimate`，需量计算排除估算点并告警 |
| 折标煤系数与行业口径不一致 | 与政府/集团报表对不上 | 系数做成介质表可配置项，支持按年度切换口径版本 |
| 节能项目基线被事后调整 | 节能量不可信 | 基线一经立项锁定，验证只能用锁定基线；改动需审批并留审计 |
| 峰值负荷受生产排程影响 | 需量告警误报 | 阈值按中心分别配置，支持计划性生产时段豁免 |
| 与 MES 产量口径不一致 | 单耗偏差 | 提供产量交叉核对接口，差异超 5% 出告警 |

---

## 附录 A 演示数据

- 6 类能源介质（电、水、蒸汽、压缩空气、天然气、柴油）
- 10 个成本中心、6 条产线、42 个计量点（一级 11、二级 20、三级 11）
- 12 个月抄表记录（2025-11 ~ 2026-10），含少量估算值与跳变样本
- 分时电价 4 段 × 12 个月、15 分钟需量曲线近 30 天
- 8 台用能设备（空压机 3、水泵 2、锅炉 1、制冷机 2）含能效测试
- 6 个节能项目（2 已验证、2 实施中、1 待验证、1 未达标）
- 40 条告警（四级分布）、12 条月度能源预算

## 附录 B 七个登录账号

| 账号 | 口令 | 角色 |
|---|---|---|
| admin | energy@2026 | 系统管理员 |
| manager | energy@2026 | 能源主管 |
| staff | energy@2026 | 能源专员 |
| reader | energy@2026 | 抄表员 |
| engineer | energy@2026 | 设备工程师 |
| prod | energy@2026 | 生产经理 |
| finance | energy@2026 | 财务 |
