/* 能耗分析 / 单耗与基线 / 碳排放 / 报表 */

/* ---------- 能耗分析 ---------- */
App.page({
  id: 'consumption', t: '能耗分析',
  async render() {
    const p = App.S.period;
    const d = await App.GET('/analysis/consumption', { period: p });
    const rank = await App.GET('/analysis/rank', { period: p });

    let h = `<div class="grid g3">
      <div class="card kpi"><div class="k">综合能耗</div><div class="v">${App.num(d.totalTce, 2)}<small>tce</small></div><div class="d">期间 ${p}</div></div>
      <div class="card kpi i"><div class="k">归集组合</div><div class="v">${d.list.length}<small>条</small></div><div class="d">中心 × 介质</div></div>
      <div class="card kpi o"><div class="k">占比最高中心</div><div class="v" style="font-size:17px">${App.esc((rank.list[0] || {}).centerName || '—')}</div><div class="d">${App.num((rank.list[0] || {}).tce, 2)} tce · ${App.pct((rank.list[0] || {}).share)}</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>按能源介质</div>';
    h += App.table([
      { t: '介质', k: 'energyName' },
      { t: '用量', r: 1, f: r => App.num(r.qty, 1) },
      { t: '单位', k: 'unit' },
      { t: '折标煤(tce)', r: 1, f: r => App.num(r.tce, 2) },
      { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
      { t: '占能耗比', r: 1, f: r => App.pct(r.tce / (d.totalTce || 1)) },
      { t: '占比', f: r => `<div class="pbar" style="width:130px"><i style="width:${Math.max(2, r.tce / (d.totalTce || 1) * 100)}%"></i></div>` },
    ], d.list);

    h += '<div class="ptitle"><span class="bar"></span>成本中心 × 介质 明细</div>';
    h += App.table([
      { t: '成本中心', f: r => (r.center || '') + ' ' + (r.centerName || '') },
      { t: '介质', k: 'energyName' },
      { t: '用量', r: 1, f: r => App.num(r.qty, 1) },
      { t: '单位', k: 'unit' },
      { t: '折标煤(tce)', r: 1, f: r => App.num(r.tce, 2) },
      { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
      { t: '计量点数', r: 1, k: 'meters' },
    ], d.list, { scroll: true });

    h += `<div class="note"><b>归集口径</b>：每个计量点的用量 × 该介质的折标煤系数，再按成本中心与介质聚合。
      综合能耗 = Σ 各介质折标煤。跨介质对比只用 tce，同介质对比才用物理量（kWh / t / Nm³）。</div>`;
    return h;
  }
});

/* ---------- 单耗与基线 ---------- */
App.page({
  id: 'intensity', t: '单耗与基线',
  async render() {
    const p = App.S.period;
    const [it, bl] = await Promise.all([
      App.GET('/analysis/intensity', { period: p }),
      App.GET('/baselines'),
    ]);
    const canWrite = App.hasPerm('base.write');

    let h = `<div class="bar-actions">
      ${canWrite ? '<button class="btn pri" onclick="Intensity.addBaseline()">+ 新建基线</button>' : ''}
      <span style="margin-left:auto;font-size:12.5px;color:#6b8299">单耗超基线 8% 警告 / 15% 严重 / 30% 紧急</span>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>产线单位产品能耗 vs 基线</div>';
    h += App.table([
      { t: '产线', k: 'line' },
      { t: '产品', k: 'product' },
      { t: '产量', r: 1, f: r => App.num(r.qty) },
      { t: '能耗(tce)', r: 1, f: r => App.num(r.tce, 2) },
      { t: '本期单耗', r: 1, f: r => App.q6(r.unitEnergy) },
      { t: '基线单耗', r: 1, f: r => App.q6(r.baseUnit) },
      { t: '偏差', r: 1, f: r => `<span class="${r.deviation > 0 ? 'up' : 'down'}">${App.dev(r.deviation)}</span>` },
      { t: '判定', f: r => App.stTag(r.level) },
      { t: '偏差条', f: r => {
          const w = Math.min(Math.abs(r.deviation) * 100 * 3, 100);
          return `<div class="pbar" style="width:110px"><i class="${r.deviation > 0.15 ? 'b' : (r.deviation > 0.08 ? 'w' : '')}" style="width:${Math.max(2, w)}%"></i></div>`;
        } },
    ], it.list);

    h += '<div class="ptitle"><span class="bar"></span>能耗基线台账<span class="r">基线一经生效即为节能量验证依据</span></div>';
    h += App.table([
      { t: '基线编码', k: 'code' },
      { t: '产线', f: r => r.line || '—' },
      { t: '产品', f: r => r.product || '—' },
      { t: '基线区间', f: r => r.period_from + ' ~ ' + r.period_to },
      { t: '基线单耗', r: 1, f: r => App.q6(r.base_unit) },
      { t: '方法', f: r => App.tag(r.method, 't') },
      { t: '状态', f: r => App.tag(r.status, 'ok') },
    ], bl.list);

    h += `<div class="note"><b>基线怎么定</b>：选取一段运行稳定、数据完整的月份（建议连续 3 个月），
      用该区间总能耗 ÷ 总产量得到单位产品能耗基线。基线一旦用于节能项目立项即锁定，
      验证时只能用锁定基线，改动需审批留痕，防止事后调基线"制造节能量"。</div>`;
    return h;
  }
});

const Intensity = {
  addBaseline() {
    App.modal('新建能耗基线', `
      <div class="note">系统会按所选区间自动汇总该产线的能耗与产量，算出基线单耗。</div>
      <div class="frow">
        <div class="f"><label>产线编码 *</label><input id="bl_line" placeholder="如 L1"></div>
        <div class="f"><label>产品</label><input id="bl_product" placeholder="如 P1001"></div>
        <div class="f"><label>起始期间</label><input id="bl_from" value="2025-11"></div>
        <div class="f"><label>结束期间</label><input id="bl_to" value="2026-01"></div>
        <div class="f"><label>方法</label><select id="bl_method"><option>单位产品能耗</option><option>综合能耗</option></select></div>
        <div class="f"><label>基线编码（可空自动生成）</label><input id="bl_code"></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Intensity.saveBaseline()">计算并保存</button>`);
  },
  async saveBaseline() {
    const b = {
      line: document.getElementById('bl_line').value.trim().toUpperCase(),
      product: document.getElementById('bl_product').value,
      periodFrom: document.getElementById('bl_from').value,
      periodTo: document.getElementById('bl_to').value,
      method: document.getElementById('bl_method').value,
      code: document.getElementById('bl_code').value || undefined,
    };
    try {
      const r = await App.POST('/baselines', b);
      App.closeModal();
      App.ok(`基线 ${r.code} 已建立，单耗 ${App.q6(r.baseUnit)}`);
      App.route();
    } catch (e) { App.err(e.message); }
  },
};

/* ---------- 碳排放 ---------- */
App.page({
  id: 'carbon', t: '碳排放',
  async render() {
    const p = App.S.period;
    const d = await App.GET('/reports/carbon', { period: p });

    let h = `<div class="grid g4">
      <div class="card kpi p"><div class="k">本期碳排放</div><div class="v">${App.num(d.total.total, 2)}<small>tCO₂</small></div><div class="d">期间 ${p}</div></div>
      <div class="card kpi b"><div class="k">范围一（直接燃烧）</div><div class="v">${App.num(d.total.scope1, 2)}<small>tCO₂</small></div><div class="d">天然气、柴油</div></div>
      <div class="card kpi i"><div class="k">范围二（外购能源）</div><div class="v">${App.num(d.total.scope2, 2)}<small>tCO₂</small></div><div class="d">电力、蒸汽、水</div></div>
      <div class="card kpi w"><div class="k">碳强度</div><div class="v">${App.num(d.intensity, 4)}<small>tCO₂/万元</small></div><div class="d">产值 ${App.num(d.valueWan, 2)} 万元</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>介质碳排构成</div>';
    h += `<div class="grid g2">
      <div class="card">${App.donut(d.byEnergy.map(x => ({ k: x.name, v: x.co2, label: App.num(x.co2, 1) + ' t' })))}</div>
      <div class="card">${App.table([
        { t: '介质', k: 'name' },
        { t: '用量', r: 1, f: r => App.num(r.qty, 1) },
        { t: '单位', k: 'unit' },
        { t: '碳排因子', r: 1, f: r => Number(r.factor).toFixed(6) },
        { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
        { t: '范围', f: r => App.tag(r.scope, r.scope === '范围一' ? 'p' : 'i') },
      ], d.byEnergy)}</div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>近 3 期碳排趋势</div>';
    h += `<div class="card">${App.lineChart(d.months.map(x => ({ k: x.period, v: x.co2 })), { labels: true, h: 42, color: '#7c3aed' })}
      <div class="lg"><span><i style="background:#7c3aed"></i>碳排放 tCO₂</span></div></div>`;

    h += `<div class="note"><b>核算口径</b>：碳排量 = Σ（各介质物理量 × 碳排因子）。范围一为厂内直接燃烧（天然气、柴油），
      范围二为外购电力、蒸汽、水的间接排放。校验差 ${App.num(d.total.checkDiff, 4)}（应为 0）。
      该口径可直接用于客户碳足迹问询与集团 ESG 报表，但正式对外披露需第三方核查并确认因子版本。</div>`;
    return h;
  }
});

/* ---------- 报表中心 ---------- */
App.page({
  id: 'report', t: '报表中心',
  async render() {
    const p = App.S.period;
    const [bal, daily] = await Promise.all([
      App.GET('/reports/energy-balance', { period: p }),
      App.GET('/reports/daily', {}),
    ]);
    const b = bal.balance;

    let h = `<div class="bar-actions">
      <button class="btn" onclick="App.exportCsv('consumption')">导出能耗明细</button>
      <button class="btn" onclick="App.exportCsv('balance')">导出能源平衡</button>
      <button class="btn" onclick="App.exportCsv('daily')">导出日电量</button>
      <button class="btn" onclick="App.exportCsv('carbon')">导出碳排</button>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>能源平衡表</div>';
    h += `<div class="grid g4">
      <div class="card kpi"><div class="k">输入能源</div><div class="v">${App.num(b.totalIn, 2)}<small>tce</small></div></div>
      <div class="card kpi o"><div class="k">各中心消耗</div><div class="v">${App.num(b.usedTce, 2)}<small>tce</small></div></div>
      <div class="card kpi w"><div class="k">损耗/未计量</div><div class="v">${App.num(b.lossTce, 2)}<small>tce</small></div><div class="d">损耗率 ${App.pct(b.lossRate)}</div></div>
      <div class="card kpi ${Math.abs(b.checkDiff) < 0.01 ? 'o' : 'b'}"><div class="k">平衡校验</div><div class="v">${App.num(b.checkDiff, 2)}</div><div class="d">输入 − 消耗 − 损耗</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>介质汇总</div>';
    h += App.table([
      { t: '介质', k: 'name' },
      { t: '用量', r: 1, f: r => App.num(r.qty, 1) },
      { t: '单位', k: 'unit' },
      { t: '折标煤(tce)', r: 1, f: r => App.num(r.tce, 2) },
      { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
    ], bal.byEnergy);

    h += '<div class="ptitle"><span class="bar"></span>中心消耗明细</div>';
    h += App.table([
      { t: '成本中心', f: r => r.center + ' ' + r.centerName },
      { t: '折标煤(tce)', r: 1, f: r => App.num(r.tce, 2) },
      { t: '占总量', r: 1, f: r => App.pct(r.tce / (b.totalIn || 1)) },
      { t: '碳排(tCO₂)', r: 1, f: r => App.num(r.co2, 2) },
      { t: '估算点数', r: 1, k: 'estimate' },
    ], bal.byCenter);

    h += '<div class="ptitle"><span class="bar"></span>日电量与需量</div>';
    h += App.table([
      { t: '日期', k: 'date' },
      { t: '电量(kWh)', r: 1, f: r => App.num(r.kwh, 1) },
      { t: '电费(元)', r: 1, f: r => App.money(r.fee) },
      { t: '最大需量(kW)', r: 1, f: r => App.num(r.maxDemand, 1) },
      { t: '日均电价', r: 1, f: r => App.num(r.kwh ? r.fee / r.kwh : 0, 4) },
    ], daily.list.slice().reverse(), { scroll: true });

    h += `<div class="note">合计电量 ${App.wan(daily.totalKwh)} kWh、电费 ${App.wan(daily.totalFee)} 元。
      CSV 导出为 UTF-8 BOM 编码，Excel 双击打开不乱码。</div>`;
    return h;
  }
});
