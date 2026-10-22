/* 主数据：能源介质 / 成本中心 / 计量点 */

/* ---------- 能源介质 ---------- */
App.page({
  id: 'energy', t: '能源介质',
  async render() {
    const d = await App.GET('/energy-types');
    const canWrite = App.hasPerm('energy.write');
    let h = canWrite ? '<div class="bar-actions"><button class="btn pri" onclick="Energy.add()">+ 新增介质</button></div>' : '';
    h += App.table([
      { t: '编码', k: 'code' },
      { t: '名称', k: 'name' },
      { t: '计量单位', k: 'unit' },
      { t: '折标煤系数', r: 1, f: r => `<span title="${r.tceFactor}">${Number(r.tceFactor).toFixed(6)}</span>` },
      { t: '碳排因子', r: 1, f: r => Number(r.co2Factor).toFixed(6) },
      { t: '排放范围', f: r => App.tag(r.scope, r.scope === '范围一' ? 'p' : 'i') },
      { t: '单价(元)', r: 1, f: r => App.money(r.price) },
      { t: '计价', f: r => App.tag(r.price_mode, 't') },
      { t: '状态', f: r => App.tag(r.status, r.status === '启用' ? 'ok' : 'g') },
      ...(canWrite ? [{ t: '操作', c: 1, f: r => `<button class="btn sm" onclick="Energy.edit('${r.code}')">编辑</button>` }] : []),
    ], d.list);
    h += `<div class="note"><b>系数说明</b>：折标煤系数 = 每计量单位折算吨标煤；碳排因子 = 每计量单位排放吨 CO₂。
      电力 1 kWh ≈ 0.0001229 tce、0.000581 tCO₂（区域电网因子）；天然气按范围一计，电力/蒸汽按范围二计。
      修改系数会影响历史报表重算口径，建议按年度版本化管理。</div>`;
    window.__energyTypes = d.list;
    window.__etTypes = d.list;
    return h;
  }
});

const Energy = {
  add() {
    App.modal('新增能源介质', `
      <div class="frow">
        <div class="f"><label>编码 *</label><input id="e_code" placeholder="如 HYDROGEN"></div>
        <div class="f"><label>名称 *</label><input id="e_name" placeholder="如 氢气"></div>
        <div class="f"><label>计量单位</label><input id="e_unit" placeholder="如 Nm³"></div>
        <div class="f"><label>折标煤系数</label><input id="e_tce" type="number" step="0.0000001" value="0"></div>
        <div class="f"><label>碳排因子</label><input id="e_co2" type="number" step="0.0000001" value="0"></div>
        <div class="f"><label>排放范围</label><select id="e_scope"><option>范围二</option><option>范围一</option></select></div>
        <div class="f"><label>单价(元)</label><input id="e_price" type="number" step="0.01" value="0"></div>
        <div class="f"><label>计价方式</label><select id="e_mode"><option>单一</option><option>分时</option></select></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Energy.save()">保存</button>`);
  },
  edit(code) {
    const r = (window.__energyTypes || []).find(x => x.code === code);
    App.modal('编辑能源介质 · ' + code, `
      <div class="frow">
        <div class="f"><label>名称</label><input id="e_name" value="${App.esc(r.name)}"></div>
        <div class="f"><label>计量单位</label><input id="e_unit" value="${App.esc(r.unit)}"></div>
        <div class="f"><label>折标煤系数</label><input id="e_tce" type="number" step="0.0000001" value="${r.tceFactor}"></div>
        <div class="f"><label>碳排因子</label><input id="e_co2" type="number" step="0.0000001" value="${r.co2Factor}"></div>
        <div class="f"><label>排放范围</label><select id="e_scope"><option ${r.scope === '范围一' ? 'selected' : ''}>范围一</option><option ${r.scope === '范围二' ? 'selected' : ''}>范围二</option></select></div>
        <div class="f"><label>单价(元)</label><input id="e_price" type="number" step="0.01" value="${r.price}"></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Energy.save('${code}')">保存</button>`);
  },
  async save(code) {
    const b = {
      code: (document.getElementById('e_code') || {}).value,
      name: document.getElementById('e_name').value,
      unit: document.getElementById('e_unit').value,
      tceFactor: Number(document.getElementById('e_tce').value),
      co2Factor: Number(document.getElementById('e_co2').value),
      scope: document.getElementById('e_scope').value,
      price: Number(document.getElementById('e_price').value),
      priceMode: (document.getElementById('e_mode') || {}).value || '单一',
    };
    try {
      if (code) await App.PUT('/energy-types/' + code, b);
      else await App.POST('/energy-types', b);
      App.closeModal(); App.ok('已保存'); App.route();
    } catch (e) { App.err(e.message); }
  },
};

/* ---------- 成本中心 ---------- */
App.page({
  id: 'center', t: '成本中心',
  async render() {
    const [d, lines] = await Promise.all([App.GET('/cost-centers'), App.GET('/lines')]);
    let h = '<div class="ptitle"><span class="bar"></span>成本中心</div>';
    h += App.table([
      { t: '编码', k: 'code' },
      { t: '名称', k: 'name' },
      { t: '类型', f: r => App.tag(r.ctype, { 生产: 'ok', 辅助: 'i', 管理: 'w', 研发: 'p', 办公: 'g' }[r.ctype] || 'g') },
      { t: '负责人', k: 'manager' },
      { t: '本期能耗(tce)', r: 1, f: r => App.num(r.tce, 2) },
    ], d.list);

    h += '<div class="ptitle"><span class="bar"></span>产线</div>';
    h += App.table([
      { t: '编码', k: 'code' },
      { t: '名称', k: 'name' },
      { t: '所属中心', f: r => (r.center || '') + ' ' + (d.list.find(x => x.code === r.center) || {}).name },
      { t: '产出产品', k: 'product' },
      { t: '设计产能', r: 1, f: r => App.num(r.capacity) + ' ' + (r.unit || '') },
      { t: '状态', f: r => App.tag(r.status, 'ok') },
    ], lines.list);

    h += `<div class="note">产线是单耗归集的最小单位：<b>单位产品能耗 = 该产线计量点能耗合计 ÷ 该产线产量</b>。
      能耗基线按产线建立，节能项目的节能量验证也必须绑定产线基线。</div>`;
    return h;
  }
});

/* ---------- 计量点 ---------- */
App.page({
  id: 'meter', t: '计量点',
  async render() {
    const p = App.S.period;
    const [d, et] = await Promise.all([App.GET('/meters', { period: p }), App.GET('/energy-types')]);
    window.__meters = d.list;
    const canWrite = App.hasPerm('meter.write');
    const cnt = { 1: 0, 2: 0, 3: 0 };
    d.list.forEach(x => { cnt[x.level] = (cnt[x.level] || 0) + 1; });

    let h = `<div class="grid g4">
      <div class="card kpi"><div class="k">计量点总数</div><div class="v">${d.list.length}<small>个</small></div><div class="d">期间 ${p}</div></div>
      <div class="card kpi i"><div class="k">一级（总表）</div><div class="v">${cnt[1] || 0}<small>个</small></div></div>
      <div class="card kpi o"><div class="k">二级（车间）</div><div class="v">${cnt[2] || 0}<small>个</small></div></div>
      <div class="card kpi p"><div class="k">三级（产线）</div><div class="v">${cnt[3] || 0}<small>个</small></div></div>
    </div>`;

    h += `<div class="bar-actions" style="margin-top:16px">
      <select id="fltLevel" onchange="Meter.filter()"><option value="">全部层级</option><option value="1">一级</option><option value="2">二级</option><option value="3">三级</option></select>
      <select id="fltEnergy" onchange="Meter.filter()"><option value="">全部介质</option>${et.list.map(x => `<option value="${x.code}">${x.name}</option>`).join('')}</select>
      ${canWrite ? '<button class="btn pri" style="margin-left:auto" onclick="Meter.add()">+ 新增计量点</button>' : ''}
    </div>`;

    h += '<div id="meterTable">' + Meter.table(d.list, d.list) + '</div>';
    h += `<div class="note"><b>层级说明</b>：一级为全厂总表（用于总量核对），二级为车间汇总表，三级为产线/设备表（用于单耗归集）。
      倍率用于互感器变比换算，用量 =（本期表底 − 上期表底）× 倍率。容量填写变压器容量，用于需量超容判定。</div>`;
    return h;
  }
});

const Meter = {
  table(rows, all) {
    const canWrite = App.hasPerm('meter.write');
    return App.table([
      { t: '编码', k: 'code' },
      { t: '名称', k: 'name' },
      { t: '层级', c: 1, f: r => App.tag(['', '一级', '二级', '三级'][r.level] || r.level, ['', 'b', 'i', 'p'][r.level] || 'g') },
      { t: '介质', k: 'energyName' },
      { t: '中心', f: r => r.center + ' ' + (r.centerName || '') },
      { t: '产线', f: r => r.line || '—' },
      { t: '倍率', r: 1, f: r => r.ratio },
      { t: '本期用量', r: 1, f: r => r.lastUsage == null ? '<span class="tg g">未抄</span>' : App.num(r.lastUsage, 1) },
      { t: '折标煤', r: 1, f: r => App.num(r.tce, 2) },
      { t: '采集方式', f: r => App.tag(r.gateway, r.gateway === '采集网关' ? 't' : 'g') },
      { t: '状态', f: r => App.stTag(r.status) },
      ...(canWrite ? [{ t: '操作', c: 1, f: r => `<button class="btn sm" onclick="Meter.edit('${r.code}')">编辑</button>` }] : []),
    ], rows);
  },
  filter() {
    const lv = document.getElementById('fltLevel').value;
    const en = document.getElementById('fltEnergy').value;
    const rows = (window.__meters || []).filter(x =>
      (!lv || String(x.level) === lv) && (!en || x.energy_code === en));
    document.getElementById('meterTable').innerHTML = Meter.table(rows, window.__meters);
  },
  add() {
    App.modal('新增计量点', `
      <div class="frow">
        <div class="f"><label>编码 *</label><input id="m_code" placeholder="如 EM105"></div>
        <div class="f"><label>名称 *</label><input id="m_name" placeholder="如 装配三线表"></div>
        <div class="f"><label>能源介质</label><select id="m_energy">${(window.__etTypes || []).map(x => `<option value="${x.code}">${x.name}</option>`).join('')}</select></div>
        <div class="f"><label>成本中心</label><input id="m_center" placeholder="如 CC103"></div>
        <div class="f"><label>产线</label><input id="m_line" placeholder="如 L4（可空）"></div>
        <div class="f"><label>层级</label><select id="m_level"><option value="1">一级</option><option value="2" selected>二级</option><option value="3">三级</option></select></div>
        <div class="f"><label>倍率</label><input id="m_ratio" type="number" value="1"></div>
        <div class="f"><label>容量(kW)</label><input id="m_cap" type="number" value="0"></div>
        <div class="f"><label>采集方式</label><select id="m_gw"><option>人工抄表</option><option>采集网关</option></select></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Meter.save()">保存</button>`);
  },
  edit(code) {
    const r = (window.__meters || []).find(x => x.code === code);
    App.modal('编辑计量点 · ' + code, `
      <div class="frow">
        <div class="f"><label>名称</label><input id="m_name" value="${App.esc(r.name)}"></div>
        <div class="f"><label>成本中心</label><input id="m_center" value="${r.center}"></div>
        <div class="f"><label>产线</label><input id="m_line" value="${r.line || ''}"></div>
        <div class="f"><label>倍率</label><input id="m_ratio" type="number" value="${r.ratio}"></div>
        <div class="f"><label>容量(kW)</label><input id="m_cap" type="number" value="${r.capacity}"></div>
        <div class="f"><label>状态</label><select id="m_status"><option ${r.status === '运行' ? 'selected' : ''}>运行</option><option ${r.status === '停用' ? 'selected' : ''}>停用</option></select></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Meter.save('${code}')">保存</button>`);
  },
  async save(code) {
    const b = {
      code: (document.getElementById('m_code') || {}).value,
      name: document.getElementById('m_name').value,
      energyCode: (document.getElementById('m_energy') || {}).value,
      center: document.getElementById('m_center').value,
      line: document.getElementById('m_line').value,
      level: (document.getElementById('m_level') || {}).value || 2,
      ratio: Number(document.getElementById('m_ratio').value) || 1,
      capacity: Number(document.getElementById('m_cap').value) || 0,
      gateway: (document.getElementById('m_gw') || {}).value || '人工抄表',
      status: (document.getElementById('m_status') || {}).value || '运行',
    };
    try {
      if (code) await App.PUT('/meters/' + code, b);
      else await App.POST('/meters', b);
      App.closeModal(); App.ok('已保存'); App.route();
    } catch (e) { App.err(e.message); }
  },
};
