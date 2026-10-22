/* 飞瀑能源管理系统 · 前端框架（原生 JS，无依赖） */
const App = (() => {
  const S = { token: '', user: null, period: '', periods: [] };

  /* ---------- 请求 ---------- */
  function qs(o) {
    const a = [];
    for (const k in o) {
      const v = o[k];
      if (v === undefined || v === null || v === '') continue;
      a.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    }
    return a.length ? '?' + a.join('&') : '';
  }

  async function req(path, method = 'GET', body = null) {
    const opt = { method, headers: {} };
    if (S.token) opt.headers['Authorization'] = 'Bearer ' + S.token;
    if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const r = await fetch('api' + path, opt);
    if (r.status === 401) { localStorage.removeItem('fp_token'); location.href = 'login.html'; throw new Error('未登录'); }
    const j = await r.json();
    if (j.code !== 200) throw new Error(j.message || '请求失败');
    return j.data;
  }
  const GET = (p, q) => req(p + qs(q || {}), 'GET');
  const POST = (p, b) => req(p, 'POST', b || {});
  const PUT = (p, b) => req(p, 'PUT', b || {});
  const DEL = p => req(p, 'DELETE');

  /* ---------- 格式化 ---------- */
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (v, d = 0) => (v == null || v === '') ? '—' :
    Number(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
  const money = v => (v == null || v === '') ? '—' : Number(v).toLocaleString('zh-CN',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const wan = v => (v == null) ? '—' : (Math.abs(v) >= 10000 ? (v / 10000).toFixed(2) + ' 万' : num(v, 2));
  const pct = (v, d = 1) => (v == null) ? '—' : (Number(v) * 100).toFixed(d) + '%';
  const pctp = (v, d = 1) => (v == null) ? '—' : v.toFixed(d) + '%';
  const q6 = v => (v == null) ? '—' : Number(v).toFixed(6);
  const dev = v => (v == null) ? '—' : (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%';
  const dt = s => (s ? String(s).slice(0, 16) : '—');

  /* ---------- 提示 ---------- */
  function toast(msg, type = 'ok') {
    const d = document.createElement('div');
    d.className = 'toast ' + type;
    d.textContent = msg;
    document.body.appendChild(d);
    setTimeout(() => { d.style.opacity = '0'; d.style.transition = '.3s'; }, 2200);
    setTimeout(() => d.remove(), 2600);
  }
  const ok = m => toast(m, 'ok');
  const err = m => toast(m, 'err');
  const info = m => toast(m, 'info');

  /* ---------- 标签 ---------- */
  function tag(text, cls) {
    return `<span class="tg ${cls || 'g'}">${esc(text)}</span>`;
  }

  const ST = {
    '紧急': 'b', '严重': 'w', '警告': 'i', '提示': 'g',
    '待处置': 'w', '已处置': 'ok',
    '优': 'ok', '良': 't', '差': 'b', '未知': 'g',
    '正常': 'ok', '预警': 'w', '超支': 'b', '阻断': 'b',
    '超容': 'b', '运行': 'ok', '停用': 'g',
    '达标': 'ok', '未达标': 'b',
    '待实施': 'g', '实施中': 'i', '待验证': 'w', '已验证': 'ok',
    '范围一': 'p', '范围二': 'i',
    '正常': 'ok', '估算': 'w', '跳变': 'w',
    '生产中': 'ok', '已下达': 'i',
  };
  const stTag = v => tag(v, ST[v] || 'g');

  /* ---------- 表格 ---------- */
  /* cols: [{t, k, f, r, c, w}]  rows: array */
  function table(cols, rows, opt) {
    opt = opt || {};
    if (!rows || !rows.length) return `<div class="tbwrap"><div class="empty">${opt.empty || '暂无数据'}</div></div>`;
    let h = '<div class="tbwrap' + (opt.scroll ? ' scroll' : '') + '"><table class="tb"><thead><tr>';
    h += cols.map(c => `<th class="${c.r ? 'r' : (c.c ? 'c' : '')}">${c.t}</th>`).join('');
    h += '</tr></thead><tbody>';
    rows.forEach((r, i) => {
      h += '<tr>' + cols.map(c => {
        const cls = (c.r ? 'r' : (c.c ? 'c' : '')) + (c.click ? ' cli' : '');
        const v = c.f ? c.f(r, i) : (r[c.k] == null ? '—' : esc(r[c.k]));
        return `<td class="${cls}"${c.click ? ` onclick="${c.click}(${i})"` : ''}>${v}</td>`;
      }).join('') + '</tr>';
    });
    return h + '</tbody></table></div>';
  }

  /* ---------- 弹层 ---------- */
  function modal(title, bodyHtml, footHtml, wide) {
    const m = document.createElement('div');
    m.className = 'mask';
    m.innerHTML = `<div class="modal${wide ? ' wide' : ''}">
      <div class="mh">${esc(title)}<span class="x" onclick="this.closest('.mask').remove()">×</span></div>
      <div class="mb">${bodyHtml}</div>
      <div class="mf">${footHtml || '<button class="btn" onclick="this.closest(\'.mask\').remove()">关闭</button>'}</div>
    </div>`;
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
    document.body.appendChild(m);
    return m;
  }
  const closeModal = () => { const m = document.querySelector('.mask'); if (m) m.remove(); };

  function confirmBox(msg, onYes, danger) {
    const m = modal('确认操作', `<div style="padding:6px 0;line-height:1.8">${msg}</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn ${danger ? 'dan' : 'pri'}" id="yesBtn">确定</button>`);
    m.querySelector('#yesBtn').onclick = () => { closeModal(); onYes(); };
  }

  /* ---------- 图表 ---------- */
  function lineChart(data, opt) {
    opt = opt || {};
    const W = 100, H = opt.h || 46;
    if (!data || !data.length) return '<div class="empty">暂无数据</div>';
    const vals = data.map(d => d.v);
    const mx = Math.max(...vals, 1) * 1.12;
    const mn = Math.min(...vals, 0) * 0.92;
    const span = mx - mn || 1;
    const step = W / Math.max(data.length - 1, 1);
    const pts = data.map((d, i) => [i * step, H - ((d.v - mn) / span) * H]);
    const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(2) + ' ' + p[1].toFixed(2)).join(' ');
    const area = path + ` L${W} ${H} L0 ${H} Z`;
    const gid = 'g' + Math.random().toString(36).slice(2, 8);
    let h = `<svg class="chart" viewBox="0 0 ${W} ${H + 9}" preserveAspectRatio="none" style="height:${(H + 9) * 4}px">
      <defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${opt.color || '#1fa3a5'}" stop-opacity=".22"/>
        <stop offset="100%" stop-color="${opt.color || '#1fa3a5'}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${gid})"/>
      <path d="${path}" fill="none" stroke="${opt.color || '#1fa3a5'}" stroke-width=".5" vector-effect="non-scaling-stroke"/>
      ${pts.map((p, i) => `<circle cx="${p[0].toFixed(2)}" cy="${p[1].toFixed(2)}" r=".9" fill="#fff" stroke="${opt.color || '#1fa3a5'}" stroke-width=".45"/>`).join('')}
    </svg>`;
    if (opt.labels) {
      h += `<div style="display:flex;justify-content:space-between;font-size:11px;color:#8ba0b8;margin-top:2px">
        ${data.map((d, i) => (i % Math.ceil(data.length / 6) === 0 || i === data.length - 1) ? `<span>${esc(d.k)}</span>` : '<span></span>').join('')}
      </div>`;
    }
    return h;
  }

  function bars(data, opt) {
    opt = opt || {};
    if (!data || !data.length) return '<div class="empty">暂无数据</div>';
    const mx = Math.max(...data.map(d => Math.abs(d.v)), 1);
    return '<div>' + data.map(d => `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:9px">
        <span style="width:130px;font-size:12.5px;color:#4a6274;flex-shrink:0;text-align:right">${esc(d.k)}</span>
        <div class="pbar" style="flex:1"><i class="${d.c || ''}" style="width:${Math.max(2, Math.abs(d.v) / mx * 100)}%"></i></div>
        <span style="width:92px;font-size:12.5px;text-align:right;font-variant-numeric:tabular-nums;flex-shrink:0">${d.label || num(d.v, 2)}</span>
      </div>`).join('') + '</div>';
  }

  function donut(data, opt) {
    opt = opt || {};
    if (!data || !data.length) return '<div class="empty">暂无数据</div>';
    const total = data.reduce((a, d) => a + d.v, 0) || 1;
    const C = ['#12787a', '#1fa3a5', '#4fb8b0', '#7cc9bf', '#a8dbd2', '#c9e8e2', '#2563eb', '#7c3aed'];
    let acc = 0;
    const R = 42, r0 = 26, cx = 50, cy = 50;
    let paths = '';
    data.forEach((d, i) => {
      const a0 = acc / total * Math.PI * 2 - Math.PI / 2;
      acc += d.v;
      const a1 = acc / total * Math.PI * 2 - Math.PI / 2;
      const lg = (a1 - a0) > Math.PI ? 1 : 0;
      const x0 = cx + R * Math.cos(a0), y0 = cy + R * Math.sin(a0);
      const x1 = cx + R * Math.cos(a1), y1 = cy + R * Math.sin(a1);
      const xi0 = cx + r0 * Math.cos(a1), yi0 = cy + r0 * Math.sin(a1);
      const xi1 = cx + r0 * Math.cos(a0), yi1 = cy + r0 * Math.sin(a0);
      paths += `<path d="M${x0.toFixed(2)} ${y0.toFixed(2)} A${R} ${R} 0 ${lg} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} L${xi0.toFixed(2)} ${yi0.toFixed(2)} A${r0} ${r0} 0 ${lg} 0 ${xi1.toFixed(2)} ${yi1.toFixed(2)} Z" fill="${C[i % C.length]}"/>`;
    });
    return `<div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap">
      <svg viewBox="0 0 100 100" style="width:150px;height:150px;flex-shrink:0">${paths}</svg>
      <div style="flex:1;min-width:160px">
        ${data.map((d, i) => `<div style="display:flex;align-items:center;gap:7px;font-size:12.5px;margin-bottom:6px">
          <i style="width:9px;height:9px;border-radius:2px;background:${C[i % C.length]};flex-shrink:0"></i>
          <span style="flex:1;color:#4a6274">${esc(d.k)}</span>
          <span style="font-variant-numeric:tabular-nums;color:#1c2b36">${d.label || num(d.v, 2)}</span>
          <span style="width:46px;text-align:right;color:#8ba0b8">${(d.v / total * 100).toFixed(1)}%</span>
        </div>`).join('')}
      </div></div>`;
  }

  /* ---------- 页面注册 ---------- */
  const PAGES = [];
  function page(o) { PAGES.push(o); }
  const find = id => PAGES.find(p => p.id === id);

  const NAV = [
    { g: '总览' },
    { id: 'dashboard', t: '仪表盘', i: '◉' },
    { g: '主数据' },
    { id: 'energy', t: '能源介质', i: '⬢' },
    { id: 'center', t: '成本中心', i: '⬣' },
    { id: 'meter', t: '计量点', i: '◎' },
    { g: '运行' },
    { id: 'reading', t: '抄表与采集', i: '✎' },
    { id: 'tou', t: '分时与需量', i: '⏱' },
    { g: '分析' },
    { id: 'consumption', t: '能耗分析', i: '▤' },
    { id: 'intensity', t: '单耗与基线', i: '▥' },
    { id: 'equipment', t: '设备能效', i: '⚙' },
    { id: 'project', t: '节能项目', i: '◈' },
    { g: '管控' },
    { id: 'alarm', t: '告警中心', i: '⚠' },
    { id: 'budget', t: '能源预算', i: '◧' },
    { id: 'carbon', t: '碳排放', i: '☁' },
    { id: 'report', t: '报表中心', i: '▦' },
    { g: '系统' },
    { id: 'system', t: '系统管理', i: '⚒' },
  ];

  function renderNav() {
    const u = S.user || {};
    const hide = {
      system: !hasPerm('sys.user') && !hasPerm('sys.rule') && !hasPerm('sys.key'),
      budget: !hasPerm('budget.read'),
      project: !hasPerm('proj.read'),
      equipment: !hasPerm('equip.read'),
    };
    let h = '';
    let lastG = '';
    NAV.forEach(n => {
      if (n.g) { h += `<div class="grp">${n.g}</div>`; return; }
      if (hide[n.id]) return;
      h += `<a data-id="${n.id}" onclick="App.go('${n.id}')"><span class="ic">${n.i}</span>${n.t}</a>`;
    });
    document.getElementById('nav').innerHTML = h;
  }

  function hasPerm(p) {
    if (!S.user) return false;
    if (S.user.role === 'admin') return true;
    return (S.user.perms || []).indexOf(p) >= 0;
  }

  /* ---------- 路由 ---------- */
  function go(id) {
    if (!find(id)) id = 'dashboard';
    location.hash = '#/' + id;
  }

  async function route() {
    const id = (location.hash.replace('#/', '') || 'dashboard');
    const p = find(id) || find('dashboard');
    document.getElementById('pageTitle').textContent = p.t;
    document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('on', a.dataset.id === p.id));
    document.getElementById('side').classList.remove('open');
    const main = document.getElementById('main');
    main.innerHTML = '<div class="empty">加载中…</div>';
    try {
      main.innerHTML = await p.render();
    } catch (e) {
      main.innerHTML = `<div class="note warnbox">加载失败：${esc(e.message)}</div>`;
    }
  }

  /* ---------- 期间 ---------- */
  function setPeriod(v) {
    S.period = v;
    localStorage.setItem('fp_period', v);
    route();
  }

  function buildPeriods() {
    const list = [];
    const d = new Date();
    // 固定到演示期间 2026-10 为当前月
    let y = 2026, m = 10;
    for (let i = 0; i < 14; i++) {
      list.push(`${y}-${String(m).padStart(2, '0')}`);
      m--; if (m < 1) { m = 12; y--; }
    }
    S.periods = list;
    const sel = document.getElementById('periodSel');
    sel.innerHTML = list.map(p => `<option value="${p}">${p}</option>`).join('');
    const saved = localStorage.getItem('fp_period');
    S.period = list.indexOf(saved) >= 0 ? saved : list[0];
    sel.value = S.period;
  }

  /* ---------- 用户菜单 ---------- */
  function userMenu() {
    const u = S.user || {};
    modal('账号信息', `
      <div class="frow">
        <div class="f"><label>账号</label><div>${esc(u.username)}</div></div>
        <div class="f"><label>姓名</label><div>${esc(u.name)}</div></div>
        <div class="f"><label>角色</label><div>${esc(u.roleName || u.role)}</div></div>
        <div class="f"><label>权限数</label><div>${(u.perms || []).length} 项</div></div>
      </div>
      <div class="ptitle" style="margin-top:18px"><span class="bar"></span>修改口令</div>
      <div class="frow">
        <div class="f"><label>原口令</label><input type="password" id="oldPwd"></div>
        <div class="f"><label>新口令</label><input type="password" id="newPwd" placeholder="至少 6 位"></div>
      </div>`,
      `<button class="btn" onclick="App.closeModal()">关闭</button>
       <button class="btn" onclick="App.logout()">退出登录</button>
       <button class="btn pri" onclick="App.changePwd()">修改口令</button>`);
  }

  async function changePwd() {
    const o = document.getElementById('oldPwd').value;
    const n = document.getElementById('newPwd').value;
    if (!o || !n) return err('请填写原口令与新口令');
    try {
      await POST('/auth/change-password', { oldPassword: o, newPassword: n });
      closeModal();
      ok('口令已修改，请重新登录');
      setTimeout(logout, 900);
    } catch (e) { err(e.message); }
  }

  function logout() {
    localStorage.removeItem('fp_token');
    localStorage.removeItem('fp_user');
    location.href = 'login.html';
  }

  /* ---------- 启动 ---------- */
  async function start() {
    S.token = localStorage.getItem('fp_token') || '';
    if (!S.token) { location.href = 'login.html'; return; }
    try {
      S.user = JSON.parse(localStorage.getItem('fp_user') || '{}');
      const me = await GET('/auth/me');
      S.user = Object.assign(S.user, { perms: me.perms, role: me.role, roleName: me.roleName, name: me.name });
      localStorage.setItem('fp_user', JSON.stringify(S.user));
    } catch (e) { return; }
    document.getElementById('userName').textContent = S.user.name || S.user.username || '-';
    document.getElementById('avatar').textContent = (S.user.name || 'U').slice(0, 1);
    buildPeriods();
    renderNav();
    window.addEventListener('hashchange', route);
    route();
  }

  /* ---------- 导出 ---------- */
  function exportCsv(type) {
    const url = 'api/reports/export?type=' + type + '&period=' + S.period + '&token=' + S.token;
    window.open(url, '_blank');
  }

  return {
    S, GET, POST, PUT, DEL, qs,
    esc, num, money, wan, pct, pctp, q6, dev, dt,
    toast, ok, err, info, tag, stTag,
    table, modal, closeModal, confirmBox,
    lineChart, bars, donut,
    page, go, route, setPeriod, userMenu, changePwd, logout,
    start, hasPerm, exportCsv, PAGES,
  };
})();
