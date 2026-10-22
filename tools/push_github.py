# -*- coding: utf-8 -*-
"""把飞瀑能源管理系统推送到 GitHub（gh api contents 逐文件 PUT）。

为什么不用 git push：本机出口代理对 github.com:443 的 CONNECT 返回 502，
而 api.github.com 可用（gh 走 API）。逐文件 PUT 支持二进制（base64）。

用法：python tools/push_github.py [OWNER/REPO] [BRANCH]
"""
import base64
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = sys.argv[1] if len(sys.argv) > 1 else "dukema81/feipu-energy"
BRANCH = sys.argv[2] if len(sys.argv) > 2 else "main"
MSG = "feat: 飞瀑能源管理系统 V1.0（折标煤+分时电费+15分钟需量+设备能效+节能量验证+碳排核算+预算闸口+7角色27权限）"

SKIP_DIRS = {"__pycache__", ".git", "db", "screenshots", "node_modules"}
SKIP_EXT = {".db", ".db-wal", ".db-shm", ".zip", ".log", ".pyc"}
# reports/ 全排除，demo/ 只保留 html


def walk():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        if rel_dir.split("/")[0] in SKIP_DIRS or os.path.basename(dirpath) in SKIP_DIRS:
            dirnames[:] = []
            continue
        if rel_dir == "reports":
            continue
        if rel_dir == "demo":
            dirnames[:] = []
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXT:
                continue
            if rel_dir == "demo" and ext != ".html":
                continue
            files.append(os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/"))
    return sorted(files)


def gh(args, data=None):
    cmd = ["gh"] + args
    if data is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(cmd, cwd=ROOT, input=(json.dumps(data).encode() if data is not None else None),
                          capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8", "ignore"), proc.stderr.decode("utf-8", "ignore")


def remote_sha(path):
    code, out, _ = gh(["api", "repos/%s/contents/%s?ref=%s" % (REPO, path, BRANCH)])
    if code != 0:
        return None
    try:
        return json.loads(out).get("sha")
    except Exception:
        return None


def ensure_repo():
    code, out, err = gh(["api", "repos/%s" % REPO])
    if code == 0:
        print("仓库已存在：", json.loads(out)["full_name"])
        return True
    owner, name = REPO.split("/", 1)
    code, out, err = gh(["api", "--method", "POST", "user/repos"], data={
        "name": name,
        "description": "飞瀑能源管理系统 — 折标煤、分时电费、需量、设备能效、节能量验证、碳排核算、预算闸口",
        "private": False, "auto_init": True})
    if code == 0:
        print("仓库已创建：", REPO)
        return True
    print("创建仓库失败：", err[:300])
    return False


def main():
    if not ensure_repo():
        return 1
    files = walk()
    print("待推送文件：%d" % len(files))
    ok = fail = 0
    for i, rel in enumerate(files, 1):
        with open(os.path.join(ROOT, rel), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        body = {"message": "%s\n\n%s" % (MSG, rel), "content": content, "branch": BRANCH}
        sha = remote_sha(rel)
        if sha:
            body["sha"] = sha
        code, out, err = gh(["api", "--method", "PUT", "repos/%s/contents/%s" % (REPO, rel)], data=body)
        if code == 0:
            ok += 1
            print("  [%2d/%2d] OK   %s" % (i, len(files), rel))
        else:
            fail += 1
            print("  [%2d/%2d] FAIL %s :: %s" % (i, len(files), rel, (err or out).strip()[:160]))
    print("\n成功 %d，失败 %d" % (ok, fail))
    print("仓库地址：https://github.com/%s" % REPO)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
