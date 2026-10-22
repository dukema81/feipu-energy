# -*- coding: utf-8 -*-
"""飞瀑能源管理系统 · UI 巡检（Playwright）

对 16 个页面逐页巡检：
  1. 控制台 error / pageerror 收集
  2. 关键元素存在性（侧边栏、主区、KPI/表格）
  3. 页面文字长度下限（防白屏）
  4. 逐页截图到 reports/screenshots/

用法：
    python tools/ui_check.py --base http://localhost:8931
    python tools/ui_check.py --base https://example.com/pu --shots reports/screenshots
"""
import argparse
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (hash 路由, 名称, 期望出现的文案片段)
PAGES = [
    ("#/dashboard", "仪表盘", ["综合能耗", "碳排放"]),
    ("#/energy", "能源介质", ["能源介质"]),
    ("#/center", "成本中心", ["成本中心"]),
    ("#/meter", "计量点", ["计量点"]),
    ("#/reading", "抄表与采集", ["抄表"]),
    ("#/tou", "分时与需量", ["需量"]),
    ("#/consumption", "能耗分析", ["能耗"]),
    ("#/intensity", "单耗与基线", ["基线"]),
    ("#/efficiency", "设备能效", ["能效"]),
    ("#/project", "节能项目", ["项目"]),
    ("#/alarm", "告警中心", ["告警"]),
    ("#/budget", "能源预算", ["预算"]),
    ("#/carbon", "碳排放", ["碳"]),
    ("#/report", "报表中心", ["报表"]),
    ("#/system", "系统管理", ["用户"]),
]

results = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8021/pu")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--pwd", default="energy@2026")
    ap.add_argument("--shots", default=os.path.join(ROOT, "reports", "screenshots"))
    ap.add_argument("--headless", default="1")
    a = ap.parse_args()
    os.makedirs(a.shots, exist_ok=True)
    base = a.base.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=a.headless != "0")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  device_scale_factor=1)
        page = ctx.new_page()

        errors = []
        page.on("console", lambda m: errors.append("console.%s: %s" % (m.type, m.text))
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))

        # ---------- 登录 ----------
        print("打开登录页 …")
        page.goto(base + "/login.html", wait_until="networkidle")
        page.fill("#username", a.user)
        page.fill("#password", a.pwd)
        page.click("button[type=submit]")
        try:
            page.wait_for_url(lambda u: "login" not in u, timeout=15000)
        except Exception:  # noqa: BLE001
            page.screenshot(path=os.path.join(a.shots, "00-login-fail.png"))
            print("登录失败，已截图 00-login-fail.png")
            print("控制台：", errors)
            browser.close()
            return 1
        page.wait_for_timeout(1200)
        print("登录成功 →", page.url)

        # ---------- 逐页巡检 ----------
        for i, (route, name, expect) in enumerate(PAGES, 1):
            errors.clear()
            row = {"name": name, "route": route, "ok": True, "why": []}
            try:
                page.goto(base + "/index.html" + route, wait_until="networkidle")
                page.wait_for_timeout(900)

                # 等主区渲染
                page.wait_for_selector("#main", timeout=8000)
                body_len = len((page.inner_text("#main") or "").strip())
                if body_len < 40:
                    row["ok"] = False
                    row["why"].append("主区内容过少(%d 字)，疑似白屏" % body_len)

                # 关键文案
                text = page.inner_text("body")
                for kw in expect:
                    if kw not in text:
                        row["ok"] = False
                        row["why"].append("缺少关键文案「%s」" % kw)

                # 侧边栏导航
                if page.locator("aside .nav a, .sidebar a").count() == 0:
                    row["ok"] = False
                    row["why"].append("侧边栏无导航项")

                # 表格/卡片至少有一
                cards = page.locator(".kpi, .card, table").count()
                if cards == 0:
                    row["ok"] = False
                    row["why"].append("页面无任何卡片或表格")

                shot = os.path.join(a.shots, "%02d-%s.png" % (i, name))
                page.screenshot(path=shot, full_page=True)
                row["shot"] = shot
            except Exception as e:  # noqa: BLE001
                row["ok"] = False
                row["why"].append("异常 %s: %s" % (type(e).__name__, str(e)[:120]))
                try:
                    page.screenshot(path=os.path.join(a.shots, "%02d-%s-fail.png" % (i, name)))
                except Exception:  # noqa: BLE001
                    pass

            real_err = [e for e in errors if "favicon" not in e.lower()]
            if real_err:
                row["ok"] = False
                row["why"].append("控制台报错: " + " | ".join(real_err[:2]))

            results.append(row)
            print("%s %-12s %s" % ("[通过]" if row["ok"] else "[失败]", name,
                                   "" if row["ok"] else "→ " + "; ".join(row["why"])))

        # ---------- 弹层交互抽查 ----------
        print("\n抽查交互：打开手工抄表弹层 …")
        try:
            page.goto(base + "/index.html#/reading", wait_until="networkidle")
            page.wait_for_timeout(800)
            btn = page.locator("button:has-text('手工抄表')").first
            if btn.count():
                btn.click()
                page.wait_for_timeout(600)
                ok = page.locator(".modal, .dialog, .mask").count() > 0
                page.screenshot(path=os.path.join(a.shots, "90-modal-reading.png"))
                print(("[通过] " if ok else "[失败] ") + "抄表弹层可打开")
                results.append({"name": "抄表弹层", "route": "#/reading", "ok": ok,
                                "why": [] if ok else ["弹层未出现"]})
                page.keyboard.press("Escape")
            else:
                print("[跳过] 未找到「手工抄表」按钮")
        except Exception as e:  # noqa: BLE001
            print("[失败] 弹层抽查异常:", e)

        # ---------- 移动端 ----------
        print("\n抽查移动端 390x844 …")
        try:
            mob = ctx.new_page()
            mob.set_viewport_size({"width": 390, "height": 844})
            mob.goto(base + "/index.html#/dashboard", wait_until="networkidle")
            mob.wait_for_timeout(1000)
            mob.screenshot(path=os.path.join(a.shots, "91-mobile-dashboard.png"), full_page=True)
            w = mob.evaluate("document.documentElement.scrollWidth")
            ok = w <= 400
            print(("[通过] " if ok else "[失败] ") + "移动端无横向溢出 (scrollWidth=%d)" % w)
            results.append({"name": "移动端", "route": "#/dashboard", "ok": ok,
                            "why": [] if ok else ["横向溢出 %dpx" % w]})
            mob.close()
        except Exception as e:  # noqa: BLE001
            print("[失败] 移动端抽查异常:", e)

        browser.close()

    # ---------- 汇总 ----------
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print("\n" + "=" * 62)
    print("UI 巡检：%d/%d 通过" % (passed, total))
    if passed < total:
        for r in results:
            if not r["ok"]:
                print("  [失败] %s %s — %s" % (r["name"], r["route"], "; ".join(r["why"])))
    print("截图目录：%s" % a.shots)
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
