# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · 测试夹具

每个测试会话：
  1. 建临时库（FP_DB 指到 tmp），初始化 21 表并播种演示数据
  2. 在空闲端口起真实的 ThreadingHTTPServer（PREFIX 置空，便于直接打 /api/*）
  3. 提供 http 客户端与各角色令牌
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

# 必须在 import server 之前定好环境
_TMP = tempfile.mkdtemp(prefix="feipu-test-")
os.environ["FP_DB"] = os.path.join(_TMP, "test.db")
os.environ["FP_PREFIX"] = ""
os.environ.setdefault("FP_TEST", "1")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = _free_port()
os.environ["FP_PORT"] = str(PORT)
BASE = "http://localhost:%d" % PORT

import db          # noqa: E402
import energy as E  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def server():
    import seed as seed_mod
    import server as srv_mod

    db.init()
    if not db.val("SELECT COUNT(*) FROM users"):
        seed_mod.seed()
    db.close_thread_conns()
    srv_mod._warmup()

    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), srv_mod.Handler)
    httpd.daemon_threads = True
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()

    # 等端口就绪
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/api/health", timeout=1).read()
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    else:
        raise RuntimeError("测试服务启动失败")

    yield {"base": BASE, "port": PORT, "server": srv_mod}

    httpd.shutdown()
    db.close_thread_conns()


# ---------------- HTTP 客户端 ----------------

class Resp:
    def __init__(self, status, body, headers):
        self.status = status
        self.body = body
        self.headers = headers
        try:
            self.json = json.loads(body.decode("utf-8")) if body else {}
        except Exception:  # noqa: BLE001
            self.json = {}
        self.data = self.json.get("data") if isinstance(self.json, dict) else None
        self.code = self.json.get("code") if isinstance(self.json, dict) else None
        self.message = self.json.get("message") if isinstance(self.json, dict) else ""

    def __repr__(self):
        return "<Resp %s %s>" % (self.status, self.message)


class Client:
    def __init__(self, base, user=None, password="energy@2026"):
        self.base = base
        self.token = ""
        self.extra = {}
        self.user = user
        self.password = password
        self._logins = 0

    def relogin(self):
        """令牌失效（改密/登出会清空该用户全部令牌）后重新登录。"""
        self._logins += 1
        self.token = ""
        self.login(self.user, self.password)
        return self

    def call(self, method, path, body=None, no_retry=False, **kw):
        r = self._req(method, path, body=body, **kw)
        # 登录成功即自动接管令牌，方便直接 post('/api/auth/login') 的写法
        if path == "/api/auth/login" and r.status == 200 and isinstance(r.data, dict):
            self.token = r.data.get("token", "")
            self.extra = {}
            if body and body.get("username"):
                self.user = body["username"]
                self.password = body.get("password", self.password)
        if r.status == 401 and self.user and not no_retry and self._logins < 3:
            self.relogin()
            r = self._req(method, path, body=body, **kw)
        return r

    def _req(self, method, path, body=None, headers=None, raw=False, key=None):
        # 中文查询参数需百分号编码，urlopen 只接受 ASCII
        safe = "/?:=&%+,"
        url = self.base + urllib.parse.quote(path, safe=safe)
        data = None
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        h.update(self.extra)
        h.update(headers or {})
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
                return Resp(r.status, b, dict(r.headers))
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read(), dict(e.headers or {}))

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body=body, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, body=body, **kw)

    def delete(self, path, **kw):
        return self.call("DELETE", path, **kw)

    def login(self, username, password="energy@2026"):
        r = self._req("POST", "/api/auth/login", body={"username": username, "password": password})
        assert r.status == 200, "登录 %s 失败: %r" % (username, r.body)
        self.token = r.data["token"]
        self.user = username
        self.password = password
        self.extra = {}
        return r.data


@pytest.fixture(scope="session")
def cli(server):
    return Client(server["base"])


@pytest.fixture(scope="session")
def admin(cli):
    c = Client(cli.base, "admin")
    c.login("admin")
    return c


@pytest.fixture(scope="session")
def tokens(cli):
    """7 个角色的独立客户端（各自登录一次，复用会话）。"""
    out = {}
    for name in E.ROLES:
        c = Client(cli.base, name)
        c.login(name)
        out[name] = c
    return out


# ---------------- 数据辅助 ----------------

@pytest.fixture(scope="session")
def periods():
    """演示数据覆盖的 12 个期间，返回 dict。"""
    rs = db.rows("SELECT DISTINCT period FROM readings ORDER BY period")
    return {"all": [r["period"] for r in rs],
            "cur": rs[-1]["period"], "prev": rs[-2]["period"] if len(rs) > 1 else rs[-1]["period"]}


def db_rows(sql, args=()):
    return db.rows(sql, args)


def db_one(sql, args=()):
    return db.one(sql, args)


def db_val(sql, args=(), default=0):
    return db.val(sql, args, default)
