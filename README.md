# 飞瀑能源管理系统 (FeiPu Energy)

面向制造企业的能源管理系统（EnMS），对标 GB/T 23331 / ISO 50001。
**零第三方依赖**：Python 3.8+ 标准库（`http.server` + `sqlite3`）即可运行，前端为原生 JS。

## 功能全景

| 模块 | 能力 |
|---|---|
| 计量抄表 | 三级计量体系、手工/批量/网关上报、倒走·重叠·跳变三闸口校验 |
| 分时与需量 | 四时段电费（尖峰/峰/平/谷）、15 分钟需量、容量电费、力调电费 |
| 能耗分析 | 中心×介质归集、折标煤、单位产品/产值能耗、同比环比、排名 |
| 单耗与基线 | 基线锁定、单耗对标、8%/15%/30% 三级偏离告警 |
| 设备能效 | 空压机比功率/水泵效率/锅炉热效率/制冷机 COP、劣化 5% 告警 |
| 节能项目 | 立项绑基线、节能量验证三闸口、年节费与回收期 |
| 告警中心 | 四级分级、类型分布、处置留痕、重复处置 409 |
| 能源预算 | 中心×介质×期间限额、90%/100%/110% 闸口 |
| 碳排放 | 范围一/二拆分、分介质因子、碳强度 |
| 报表 | 能源平衡表、日报、CSV 导出（UTF-8 BOM） |
| 系统管理 | 7 角色×27 权限、14 项业务规则、API Key、Webhook、审计日志 |

## 快速启动

```bash
cd backend
python server.py            # 默认 0.0.0.0:8021，前缀 /pu
# 自定义：
FP_PORT=9000 FP_PREFIX="" python server.py
```

- 首次启动自动建库（25 表）并播种 12 个月演示数据
- 登录 `admin / energy@2026`（另有 manager/staff/reader/engineer/prod/finance 同口令）
- 界面：`http://localhost:8021/pu/` · 接口文档：`/pu/apidoc`

## 生产部署（nginx + systemd）

```nginx
location /pu/ {
    proxy_pass http://127.0.0.1:8021/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

```ini
# /etc/systemd/system/feipu-energy.service
[Unit]
Description=FeiPu Energy Management System
After=network.target

[Service]
WorkingDirectory=/opt/feipu-energy/backend
Environment=FP_PORT=8021
Environment=FP_PREFIX=/pu
ExecStart=/usr/bin/python3 server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 与外部系统对接

- **多通道鉴权**：Bearer / X-Fp-Token / Cookie / ?token= / X-Fp-Key（长期密钥，SHA-256 存储）
- **增量同步**：`GET /api/sync/changes?entity=meters|readings|alarms|…&since=<ts>`
- **Webhook**：13 种事件（reading.created、demand.over、project.verified…），HMAC-SHA256 签名 + 0/30/60/120s 退避
- **幂等**：写接口支持 `Idempotency-Key`
- **限流**：300 req/min/IP
- 完整契约见 [docs/api.md](docs/api.md) 与运行时 `/apidoc`（自动生成的 OpenAPI 3.0）

## 目录结构

```
backend/
  server.py      # HTTP 服务（69 路由）
  energy.py      # 业务内核（纯函数：折标煤/电费/需量/能效/节能量/碳排…）
  db.py          # 25 表 schema + 助手
  seed.py        # 12 个月演示数据
frontend/        # 原生 JS 单页应用（16 页面）
tests/           # pytest 单测 + 接口测试（267 条）
tools/
  smoke_api.py   # 部署后冒烟（31 项）
  ui_check.py    # Playwright UI 巡检（17 项）
  build_demo.py  # 离线 DEMO 生成
  build_api_doc.py
demo/            # 单文件离线演示（双击即开）
docs/            # 设计文档 / API 手册 / 用户手册 / 测试报告
```

## 测试

```bash
python -m pytest tests/ -q          # 267 条
python tools/smoke_api.py --base http://localhost:8021/pu
python tools/ui_check.py --base http://localhost:8021/pu
```

## 许可

内部交付物，未授权不得公开分发。
