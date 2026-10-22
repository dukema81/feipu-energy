/* 系统管理：用户 / 业务规则 / API Key / Webhook / 审计日志 */
App.page({
  id: 'system', t: '系统管理',
  async render() {
    const tabs = [];
    if (App.hasPerm('sys.user')) tabs.push(['user', '用户']);
    if (App.hasPerm('report.read')) tabs.push(['rule', '业务规则']);
    if (App.hasPerm('sys.key')) tabs.push(['key', '接口密钥']);
    if (App.hasPerm('sys.hook')) tabs.push(['hook', 'Webhook']);
    if (App.hasPerm('sys.log')) tabs.push(['log', '审计日志']);
    if (!tabs.length) return '<div class="note warnbox">当前角色无系统管理权限。</div>';

    window.__sysTabs = tabs;
    let h = '<div class="bar-actions">' + tabs.map((t, i) =>
      `<button class="btn${i === 0 ? ' pri' : ''}" id="tab_${t[0]}" onclick="Sys.tab('${t[0]}')">${t[1]}</button>`).join('') + '</div>';
    h += '<div id="sysBody"><div class="empty">加载中…</div></div>';
    setTimeout(() => Sys.tab(tabs[0][0]), 0);
    return h;
  }
});

const Sys = {
  async tab(id) {
    document.querySelectorAll('[id^=tab_]').forEach(b => {
      b.className = 'btn' + (b.id === 'tab_' + id ? ' pri' : '');
    });
    const box = document.getElementById('sysBody');
    box.innerHTML = '<div class="empty">加载中…</div>';
    try {
      if (id === 'user') box.innerHTML = await Sys.users();
      else if (id === 'rule') box.innerHTML = await Sys.rules();
      else if (id === 'key') box.innerHTML = await Sys.keys();
      else if (id === 'hook') box.innerHTML = await Sys.hooks();
      else if (id === 'log') box.innerHTML = await Sys.logs();
    } catch (e) { box.innerHTML = `<div class="note warnbox">${App.esc(e.message)}</div>`; }
  },

  async users() {
    const d = await App.GET('/users');
    window.__users = d.list;
    let h = '<div class="bar-actions"><button class="btn pri" onclick="Sys.addUser()">+ 新增用户</button></div>';
    h += App.table([
      { t: '账号', k: 'username' },
      { t: '姓名', k: 'name' },
      { t: '角色', f: r => App.tag(r.roleName, 't') },
      { t: '角色码', f: r => App.tag(r.role, 'g') },
      { t: '电话', f: r => r.phone || '—' },
      { t: '状态', f: r => App.tag(r.status, r.status === '启用' ? 'ok' : 'g') },
      { t: '操作', c: 1, f: r => `<button class="btn sm" onclick="Sys.editUser('${r.username}')">编辑</button>` },
    ], d.list);
    h += `<div class="note"><b>7 个角色</b>：${Object.keys(d.roles).map(k => `${d.roles[k]}(${k})`).join(' · ')}
      。抄表员只能抄表与看主数据，不能改计量点；设备工程师能做能效与项目但不能验节能量；生产经理与财务只读。</div>`;
    return h;
  },

  addUser() {
    App.modal('新增用户', `
      <div class="frow">
        <div class="f"><label>账号 *</label><input id="u_name"></div>
        <div class="f"><label>姓名</label><input id="u_real"></div>
        <div class="f"><label>角色</label><select id="u_role">
          <option value="manager">能源主管</option><option value="staff">能源专员</option>
          <option value="reader">抄表员</option><option value="engineer">设备工程师</option>
          <option value="prod">生产经理</option><option value="finance">财务</option>
          <option value="admin">系统管理员</option></select></div>
        <div class="f"><label>电话</label><input id="u_phone"></div>
        <div class="f"><label>初始口令</label><input id="u_pwd" value="energy@2026"></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Sys.saveUser()">保存</button>`);
  },
  editUser(username) {
    const r = (window.__users || []).find(x => x.username === username);
    App.modal('编辑用户 · ' + username, `
      <div class="frow">
        <div class="f"><label>姓名</label><input id="u_real" value="${App.esc(r.name)}"></div>
        <div class="f"><label>角色</label><select id="u_role">${Object.keys({ manager: 1, staff: 1, reader: 1, engineer: 1, prod: 1, finance: 1, admin: 1 }).map(k => `<option value="${k}" ${r.role === k ? 'selected' : ''}>${k}</option>`).join('')}</select></div>
        <div class="f"><label>电话</label><input id="u_phone" value="${App.esc(r.phone || '')}"></div>
        <div class="f"><label>状态</label><select id="u_status"><option ${r.status === '启用' ? 'selected' : ''}>启用</option><option ${r.status === '停用' ? 'selected' : ''}>停用</option></select></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Sys.saveUser('${username}')">保存</button>`);
  },
  async saveUser(username) {
    const b = {
      username: username || document.getElementById('u_name').value.trim(),
      name: document.getElementById('u_real').value,
      role: document.getElementById('u_role').value,
      phone: document.getElementById('u_phone').value,
      status: (document.getElementById('u_status') || {}).value || '启用',
      password: (document.getElementById('u_pwd') || {}).value,
    };
    if (!b.username) return App.err('请填写账号');
    try {
      await App.POST('/users', b);
      App.closeModal(); App.ok('已保存'); Sys.tab('user');
    } catch (e) { App.err(e.message); }
  },

  async rules() {
    const d = await App.GET('/rules');
    const canWrite = App.hasPerm('sys.rule');
    const label = {
      demand_warn_ratio: '需量预警比例（容量 × 此值）',
      demand_urgent_ratio: '需量紧急比例',
      jump_ratio: '抄表跳变倍数阈值',
      jump_floor: '跳变判定绝对量下限',
      intensity_warn: '单耗偏差预警（警告）',
      intensity_serious: '单耗偏差（严重）',
      intensity_urgent: '单耗偏差（紧急）',
      budget_warn: '预算预警比例',
      budget_over: '预算超支比例',
      budget_block: '预算阻断比例',
      pf_standard: '功率因数考核标准',
      demand_price: '需量电价（元/kW·月）',
      tce_price: '标煤单价（元/tce）',
      eff_degrade_ratio: '能效劣化判定比例',
    };
    window.__ruleKeys = d.list.map(r => r.key);
    let h = '<div class="note">改动即时生效，影响告警分级、预算闸口与节能量核算。改前请确认口径已与生产、财务对齐。</div>';
    h += App.table([
      { t: '规则键', f: r => `<b>${r.key}</b><br><span style="font-size:12px;color:#8ba0b8">${label[r.key] || ''}</span>` },
      { t: '当前值', r: 1, f: r => `<input id="rule_${r.key}" value="${App.esc(r.value)}" style="border:1px solid #e2eaf1;border-radius:5px;padding:4px 8px;width:110px;text-align:right;font-family:inherit">` },
    ], d.list);
    if (canWrite) {
      h += '<div class="bar-actions" style="margin-top:14px"><button class="btn pri" onclick="Sys.saveRules()">保存规则</button></div>';
    }
    h += `<div class="note"><b>Webhook 事件（${d.events.length} 种）</b>：${d.events.map(e => `<code style="background:#f0f8f8;padding:1px 6px;border-radius:4px;font-size:12px;margin-right:6px">${e}</code>`).join('')}</div>`;
    return h;
  },
  async saveRules() {
    const b = {};
    (window.__ruleKeys || []).forEach(k => {
      const el = document.getElementById('rule_' + k);
      if (el) b[k] = el.value;
    });
    if (!Object.keys(b).length) {
      // 兜底：从 DOM 收集
      document.querySelectorAll('[id^=rule_]').forEach(el => { b[el.id.slice(5)] = el.value; });
    }
    try {
      await App.PUT('/rules', b);
      App.ok('规则已保存'); Sys.tab('rule');
    } catch (e) { App.err(e.message); }
  },

  async keys() {
    const d = await App.GET('/api-keys');
    let h = '<div class="note">API Key 用于系统对接（采集网关、MES、ERP）。明文仅在创建时返回一次，服务端只存前缀与哈希。</div>';
    h += '<div class="bar-actions"><button class="btn pri" onclick="Sys.addKey()">+ 生成密钥</button></div>';
    h += App.table([
      { t: 'ID', k: 'id' },
      { t: '名称', k: 'name' },
      { t: '前缀', f: r => `<code style="background:#f0f4f8;padding:1px 6px;border-radius:4px">${r.key_prefix}…</code>` },
      { t: '角色', f: r => App.tag(r.role, 't') },
      { t: '状态', f: r => App.tag(r.status, 'ok') },
      { t: '创建时间', f: r => App.dt(r.created_at) },
      { t: '最近使用', f: r => App.dt(r.last_used) },
      { t: '操作', c: 1, f: r => `<button class="btn sm dan" onclick="Sys.delKey(${r.id})">删除</button>` },
    ], d.list);
    h += `<div class="note"><b>用法</b>：请求头 <code>X-Fp-Key: fpk_xxx</code>，即可以该密钥所属角色的权限访问接口。
      采集网关用 reader 角色即可只写抄表。</div>`;
    return h;
  },
  addKey() {
    App.modal('生成接口密钥', `
      <div class="frow">
        <div class="f"><label>名称</label><input id="k_name" placeholder="如 采集网关-压缩空气站"></div>
        <div class="f"><label>角色权限</label><select id="k_role">
          <option value="reader">抄表员（只写抄表+读主数据）</option>
          <option value="staff">能源专员</option>
          <option value="engineer">设备工程师</option>
          <option value="manager">能源主管</option>
          <option value="prod">生产经理（只读）</option></select></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Sys.doAddKey()">生成</button>`);
  },
  async doAddKey() {
    try {
      const r = await App.POST('/api-keys', {
        name: document.getElementById('k_name').value || '对接密钥',
        role: document.getElementById('k_role').value,
      });
      App.closeModal();
      App.modal('密钥已生成（仅显示一次）', `
        <div class="note warnbox">请立即复制保存，关闭后无法再次查看。</div>
        <div style="background:#0f2a3d;color:#7ee0d8;padding:14px 16px;border-radius:8px;font-family:monospace;font-size:13.5px;word-break:break-all">${r.key}</div>
        <div class="note" style="margin-top:14px">用法：请求头 <code>X-Fp-Key: ${r.key.slice(0, 8)}…</code><br>
        示例：<code>curl -H "X-Fp-Key: 你的密钥" http://host/api/meters</code></div>`);
      Sys.tab('key');
    } catch (e) { App.err(e.message); }
  },
  async delKey(id) {
    App.confirmBox('确定删除该密钥？使用该密钥的对接方将立即无法访问。', async () => {
      try { await App.DEL('/api-keys/' + id); App.ok('已删除'); Sys.tab('key'); }
      catch (e) { App.err(e.message); }
    }, true);
  },

  async hooks() {
    const d = await App.GET('/webhooks');
    let h = '<div class="note">事件发生时向订阅地址 POST，带 HMAC-SHA256 签名，失败按 30s / 60s / 120s 退避重试三次。</div>';
    h += '<div class="bar-actions"><button class="btn pri" onclick="Sys.addHook()">+ 新建订阅</button></div>';
    h += App.table([
      { t: 'ID', k: 'id' },
      { t: '名称', k: 'name' },
      { t: '地址', f: r => `<span style="font-size:12px">${App.esc(r.url)}</span>` },
      { t: '订阅事件', f: r => (r.events || '').split(',').map(e => `<span class="tg t" style="margin-right:3px">${App.esc(e)}</span>`).join('') },
      { t: '状态', f: r => App.tag(r.status, 'ok') },
      { t: '操作', c: 1, f: r => `<button class="btn sm dan" onclick="Sys.delHook(${r.id})">删除</button>` },
    ], d.list);

    if (d.deliveries && d.deliveries.length) {
      h += '<div class="ptitle"><span class="bar"></span>最近投递</div>';
      h += App.table([
        { t: '时间', f: r => App.dt(r.at) },
        { t: '事件', k: 'event' },
        { t: '地址', f: r => `<span style="font-size:12px">${App.esc((r.url || '').slice(0, 50))}</span>` },
        { t: '状态', f: r => App.tag(r.status, r.status === '成功' ? 'ok' : 'b') },
        { t: 'HTTP', r: 1, k: 'code' },
        { t: '重试', r: 1, k: 'tries' },
      ], d.deliveries);
    }

    h += `<div class="note"><b>签名验证</b>：<code>X-Fp-Signature = "sha256=" + hex(hmac_sha256(secret, timestamp + "." + rawBody))</code>，
      <code>X-Fp-Timestamp</code> 为秒级时间戳，建议校验时间偏差不超过 5 分钟以防重放。</div>`;
    return h;
  },
  addHook() {
    App.modal('新建 Webhook 订阅', `
      <div class="frow">
        <div class="f"><label>名称</label><input id="h_name" value="对接订阅"></div>
        <div class="f"><label>回调地址 *</label><input id="h_url" placeholder="https://your-host/callback"></div>
      </div>
      <div class="frow one"><div class="f"><label>订阅事件（逗号分隔，* 表示全部）</label>
        <input id="h_events" value="alarm.raised,demand.over"></div></div>
      <div class="note">创建后会返回 secret，请保存到对接方用于验签。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Sys.doAddHook()">创建</button>`);
  },
  async doAddHook() {
    try {
      const r = await App.POST('/webhooks', {
        name: document.getElementById('h_name').value,
        url: document.getElementById('h_url').value,
        events: document.getElementById('h_events').value.split(',').map(s => s.trim()).filter(Boolean),
      });
      App.closeModal();
      App.modal('订阅已创建', `
        <div class="note warnbox">Secret 仅显示一次，请保存到对接方。</div>
        <div style="background:#0f2a3d;color:#7ee0d8;padding:14px 16px;border-radius:8px;font-family:monospace;word-break:break-all">${r.secret}</div>
        <div class="note" style="margin-top:14px">${App.esc(r.sign)}</div>`);
      Sys.tab('hook');
    } catch (e) { App.err(e.message); }
  },
  async delHook(id) {
    App.confirmBox('确定删除该订阅？', async () => {
      try { await App.DEL('/webhooks/' + id); App.ok('已删除'); Sys.tab('hook'); }
      catch (e) { App.err(e.message); }
    }, true);
  },

  async logs() {
    const d = await App.GET('/logs');
    return App.table([
      { t: '时间', f: r => App.dt(r.at) },
      { t: '用户', k: 'username' },
      { t: '动作', f: r => App.tag(r.action, 't') },
      { t: '对象', f: r => `<span style="font-size:12px">${App.esc(r.target || '')}</span>` },
      { t: '详情', f: r => `<span style="font-size:12px;color:#6b8299">${App.esc((r.detail || '').slice(0, 60))}</span>` },
      { t: 'IP', f: r => r.ip || '—' },
    ], d.list, { scroll: true });
  },
};
