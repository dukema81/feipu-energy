/* 设备能效 / 节能项目 / 能源预算 */

/* ---------- 设备能效 ---------- */
App.page({
  id: 'equipment', t: '设备能效',
  async render() {
    const [eq, tests] = await Promise.all([App.GET('/equipments'), App.GET('/eff-tests')]);
    const canWrite = App.hasPerm('equip.write');

    const gradeCnt = { 优: 0, 良: 0, 差: 0, 未知: 0 };
    eq.list.forEach(x => { gradeCnt[x.lastGrade || '未知'] = (gradeCnt[x.lastGrade || '未知'] || 0) + 1; });

    let h = `<div class="grid g4">
      <div class="card kpi"><div class="k">在册设备</div><div class="v">${eq.list.length}<small>台</small></div><div class="d">${Object.keys(eq.spec).length} 类能效模型</div></div>
      <div class="card kpi o"><div class="k">能效 优</div><div class="v">${gradeCnt['优']}<small>台</small></div></div>
      <div class="card kpi w"><div class="k">能效 良</div><div class="v">${gradeCnt['良']}<small>台</small></div></div>
      <div class="card kpi b"><div class="k">能效 差</div><div class="v">${gradeCnt['差']}<small>台</small></div><div class="d">建议安排检修或改造</div></div>
    </div>`;

    h += `<div class="bar-actions" style="margin-top:16px">
      ${canWrite ? '<button class="btn pri" onclick="Equip.calc()">能效计算器</button>' : ''}
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>设备能效台账</div>';
    h += App.table([
      { t: '设备编码', k: 'code' },
      { t: '名称', k: 'name' },
      { t: '类型', f: r => App.tag(r.etype, 't') },
      { t: '所属中心', f: r => r.center },
      { t: '铭牌参数', f: r => r.spec || '—' },
      { t: '指标', f: r => r.metric || '—' },
      { t: '最近测试值', r: 1, f: r => r.lastValue == null ? '—' : App.num(r.lastValue, 2) },
      { t: '评级', f: r => App.stTag(r.lastGrade || '未知') },
      { t: '测试日期', f: r => r.lastAt || '—' },
      ...(canWrite ? [{ t: '操作', c: 1, f: r => `<button class="btn sm" onclick="Equip.test('${r.code}','${r.etype}')">录入测试</button>` }] : []),
    ], eq.list);

    h += '<div class="ptitle"><span class="bar"></span>评级标准</div>';
    h += App.table([
      { t: '设备类型', k: 'type' },
      { t: '指标', k: 'metric' },
      { t: '优', r: 1, k: 'good' },
      { t: '良', r: 1, k: 'fair' },
      { t: '差', r: 1, k: 'bad' },
    ], Object.keys(eq.spec).map(k => {
      const s = eq.spec[k];
      return { type: k, metric: s.metric,
        good: s.lower_better ? '≤ ' + s.good : '≥ ' + s.good,
        fair: s.lower_better ? '≤ ' + s.fair : '≥ ' + s.fair,
        bad: s.lower_better ? '> ' + s.fair : '< ' + s.fair };
    }));

    h += '<div class="ptitle"><span class="bar"></span>测试记录</div>';
    h += App.table([
      { t: '日期', k: 'date' },
      { t: '设备', f: r => r.equipment_code + ' ' + (r.equipmentName || '') },
      { t: '类型', k: 'etype' },
      { t: '输入功率(kW)', r: 1, f: r => r.input_power ? App.num(r.input_power, 1) : '—' },
      { t: '输出量', r: 1, f: r => r.output_qty ? App.num(r.output_qty, 2) : (r.output_kw ? r.output_kw + ' kW' : (r.heat_out ? r.heat_out + ' MJ' : '—')) },
      { t: '指标值', r: 1, f: r => App.num(r.value, 2) + ' ' + (r.metric || '') },
      { t: '评级', f: r => App.stTag(r.grade) },
      { t: '测试人', k: 'tester' },
    ], tests.list, { scroll: true });

    h += `<div class="note"><b>能效口径</b>：空压机看比功率（输入功率 ÷ 排气量），越低越好；
      水泵看运行效率（有效功率 ÷ 轴功率）；锅炉看热效率（有效吸热 ÷ 输入热量）；制冷机看 COP（制冷量 ÷ 输入功率）。
      连续两次测试劣化超 5% 自动生成「能效劣化」提示告警，提示安排保养。</div>`;
    return h;
  }
});

const Equip = {
  calc() {
    App.modal('能效计算器', `
      <div class="frow">
        <div class="f"><label>设备类型</label><select id="c_type" onchange="Equip.fields()">
          <option>空压机</option><option>水泵</option><option>锅炉</option><option>制冷机</option></select></div>
        <div class="f"><label>输入功率 (kW)</label><input id="c_ip" type="number" step="0.1" value="118"></div>
        <div class="f" id="c_f1"><label>排气量 (m³/min)</label><input id="c_oq" type="number" step="0.1" value="20.5"></div>
        <div class="f" id="c_f2" style="display:none"><label>有效功率 (kW)</label><input id="c_okw" type="number" step="0.1" value="32"></div>
        <div class="f" id="c_f3" style="display:none"><label>输入热量 (MJ/h)</label><input id="c_hi" type="number" value="2840"></div>
        <div class="f" id="c_f4" style="display:none"><label>有效吸热 (MJ/h)</label><input id="c_ho" type="number" value="2620"></div>
      </div>
      <div id="c_result" style="margin-top:16px"></div>`,
      `<button class="btn" onclick="App.closeModal()">关闭</button>
       <button class="btn pri" onclick="Equip.doCalc()">计算</button>`);
    Equip.fields();
  },
  fields() {
    const t = document.getElementById('c_type').value;
    document.getElementById('c_f1').style.display = t === '空压机' ? '' : 'none';
    document.getElementById('c_f2').style.display = (t === '水泵' || t === '制冷机') ? '' : 'none';
    document.getElementById('c_f3').style.display = t === '锅炉' ? '' : 'none';
    document.getElementById('c_f4').style.display = t === '锅炉' ? '' : 'none';
  },
  async doCalc() {
    const t = document.getElementById('c_type').value;
    const b = {
      etype: t,
      inputPower: Number(document.getElementById('c_ip').value) || 0,
      outputQty: Number((document.getElementById('c_oq') || {}).value) || 0,
      outputKw: Number((document.getElementById('c_okw') || {}).value) || 0,
      heatIn: Number((document.getElementById('c_hi') || {}).value) || 0,
      heatOut: Number((document.getElementById('c_ho') || {}).value) || 0,
    };
    try {
      const r = await App.POST('/eff-tests/calc', b);
      document.getElementById('c_result').innerHTML = `
        <div class="card kpi ${r.grade === '优' ? 'o' : (r.grade === '差' ? 'b' : 'w')}">
          <div class="k">${r.metric}</div>
          <div class="v">${App.num(r.value, 2)}<small>${r.unit}</small></div>
          <div class="d">评级 ${r.grade}</div>
        </div>`;
    } catch (e) { App.err(e.message); }
  },
  test(code, etype) {
    const map = { 空压机: '排气量 (m³/min)', 水泵: '有效功率 (kW)', 锅炉: '输入/有效吸热 (MJ/h)', 制冷机: '制冷量 (kW)' };
    App.modal(`录入能效测试 · ${code}`, `
      <div class="note">类型 ${etype}，指标：${map[etype]}</div>
      <div class="frow">
        <div class="f"><label>测试日期</label><input id="t_date" value="${App.S.period}-15"></div>
        <div class="f"><label>输入功率 (kW)</label><input id="t_ip" type="number" step="0.1" value="${etype === '锅炉' ? 2840 : 110}"></div>
        <div class="f"><label>排气量 (m³/min，空压机)</label><input id="t_oq" type="number" step="0.1" value="20"></div>
        <div class="f"><label>有效功率/制冷量 (kW)</label><input id="t_okw" type="number" step="0.1" value="880"></div>
        <div class="f"><label>输入热量 (MJ/h，锅炉)</label><input id="t_hi" type="number" value="2840"></div>
        <div class="f"><label>有效吸热 (MJ/h，锅炉)</label><input id="t_ho" type="number" value="2620"></div>
      </div>`, `<button class="btn" onclick="App.closeModal()">取消</button>
      <button class="btn pri" onclick="Equip.doSave('${code}')">保存测试</button>`);
  },
  async doSave(code) {
    const b = {
      equipment: code,
      date: document.getElementById('t_date').value,
      inputPower: Number(document.getElementById('t_ip').value) || 0,
      outputQty: Number(document.getElementById('t_oq').value) || 0,
      outputKw: Number(document.getElementById('t_okw').value) || 0,
      heatIn: Number(document.getElementById('t_hi').value) || 0,
      heatOut: Number(document.getElementById('t_ho').value) || 0,
    };
    try {
      const r = await App.POST('/eff-tests', b);
      App.closeModal();
      if (r.degraded) App.err(`已保存，能效较上次劣化（${r.result.value}）`);
      else App.ok(`已保存，${r.result.metric} ${r.result.value}（${r.result.grade}）`);
      App.route();
    } catch (e) { App.err(e.message); }
  },
};

/* ---------- 节能项目 ---------- */
App.page({
  id: 'project', t: '节能项目',
  async render() {
    const d = await App.GET('/projects');
    const canWrite = App.hasPerm('proj.write');
    const canVerify = App.hasPerm('proj.verify');

    const cnt = { 待实施: 0, 实施中: 0, 待验证: 0, 已验证: 0, 未达标: 0 };
    d.list.forEach(x => { cnt[x.status] = (cnt[x.status] || 0) + 1; });

    let h = `<div class="grid g5">
      <div class="card kpi"><div class="k">项目总数</div><div class="v">${d.list.length}<small>个</small></div></div>
      <div class="card kpi i"><div class="k">实施中</div><div class="v">${cnt['实施中'] || 0}</div></div>
      <div class="card kpi w"><div class="k">待验证</div><div class="v">${cnt['待验证'] || 0}</div></div>
      <div class="card kpi o"><div class="k">已验证</div><div class="v">${cnt['已验证'] || 0}</div></div>
      <div class="card kpi b"><div class="k">未达标</div><div class="v">${cnt['未达标'] || 0}</div></div>
    </div>`;

    h += `<div class="bar-actions" style="margin-top:16px">
      ${canWrite ? '<button class="btn pri" onclick="Project.add()">+ 立项</button>' : ''}
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>项目台账</div>';
    h += App.table([
      { t: '项目编号', k: 'no' },
      { t: '名称', k: 'name' },
      { t: '投资(元)', r: 1, f: r => App.num(r.invest) },
      { t: '基线', f: r => r.baseline_code || App.tag('无基线', 'b') },
      { t: '周期', f: r => (r.start_period || '') + ' ~ ' + (r.end_period || '') },
      { t: '负责人', k: 'owner' },
      { t: '状态', f: r => App.stTag(r.status) },
      { t: '节能量(tce)', r: 1, f: r => r.lastVerify ? App.num(r.lastVerify.saving_tce, 2) : '—' },
      { t: '回收期(年)', r: 1, f: r => r.lastVerify ? App.num(r.lastVerify.payback, 2) : '—' },
      { t: '操作', c: 1, f: r => `<button class="btn sm" onclick="Project.detail('${r.no}')">详情</button>`
          + (canVerify && r.status !== '已验证' ? ` <button class="btn sm pri" onclick="Project.verify('${r.no}')">验证</button>` : '') },
    ], d.list);

    h += `<div class="note"><b>验证三闸口</b>：① 项目必须绑定锁定基线，无基线不允许验证；
      ② 报告期该产线必须有用量数据，否则无法计算单耗；
      ③ 报告期产量为 0 不允许验证（避免"分母为零算出天文节能量"）。
      节能量 =（基线单耗 − 报告期单耗）× 报告期产量；回收期 = 投资 ÷ 年节费。节能量为负判为「未达标」，强制标注原因。</div>`;
    return h;
  }
});

const Project = {
  add() {
    App.modal('节能项目立项', `
      <div class="frow">
        <div class="f"><label>项目名称 *</label><input id="p_name" placeholder="如 空压机变频改造"></div>
        <div class="f"><label>成本中心</label><input id="p_center" placeholder="如 CC202"></div>
        <div class="f"><label>产线</label><input id="p_line" placeholder="如 L6（可空）"></div>
        <div class="f"><label>基线编码 *</label><input id="p_bl" placeholder="如 BL-L6"></div>
        <div class="f"><label>投资额(元)</label><input id="p_invest" type="number" value="0"></div>
        <div class="f"><label>负责人</label><input id="p_owner"></div>
        <div class="f"><label>开始期间</label><input id="p_start" value="${App.S.period}"></div>
        <div class="f"><label>结束期间</label><input id="p_end"></div>
      </div>
      <div class="frow one"><div class="f"><label>技术措施</label><textarea id="p_measure" placeholder="描述改造内容与预期效果"></textarea></div></div>
      <div class="note">立项必须绑定能耗基线，否则节能量无法验证，系统会拒绝创建。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Project.save()">提交立项</button>`);
  },
  async save() {
    const b = {
      name: document.getElementById('p_name').value,
      center: document.getElementById('p_center').value,
      line: document.getElementById('p_line').value,
      baselineCode: document.getElementById('p_bl').value,
      invest: Number(document.getElementById('p_invest').value) || 0,
      owner: document.getElementById('p_owner').value,
      startPeriod: document.getElementById('p_start').value,
      endPeriod: document.getElementById('p_end').value,
      measure: document.getElementById('p_measure').value,
    };
    try {
      const r = await App.POST('/projects', b);
      App.closeModal(); App.ok('立项成功 ' + r.no); App.route();
    } catch (e) { App.err(e.message); }
  },
  async detail(no) {
    try {
      const p = await App.GET('/projects/' + no + '/detail');
      let h = `<div class="grid g3">
        <div class="card kpi"><div class="k">投资额</div><div class="v">${App.wan(p.invest)}<small>元</small></div></div>
        <div class="card kpi i"><div class="k">状态</div><div class="v" style="font-size:18px">${p.status}</div></div>
        <div class="card kpi o"><div class="k">基线</div><div class="v" style="font-size:18px">${p.baseline_code || '无'}</div>
          <div class="d">${p.baseline ? '基线单耗 ' + App.q6(p.baseline.base_unit) : ''}</div></div>
      </div>`;
      h += `<div class="note" style="margin-top:14px"><b>${App.esc(p.name)}</b><br>${App.esc(p.measure || '')}</div>`;
      if (p.verifies && p.verifies.length) {
        h += '<div class="ptitle"><span class="bar"></span>验证记录</div>';
        h += App.table([
          { t: '期间', k: 'period' },
          { t: '基线单耗', r: 1, f: r => App.q6(r.base_unit) },
          { t: '报告期单耗', r: 1, f: r => App.q6(r.report_unit) },
          { t: '产量', r: 1, f: r => App.num(r.qty) },
          { t: '节能量(tce)', r: 1, f: r => App.num(r.saving_tce, 2) },
          { t: '节能率', r: 1, f: r => App.pct(r.saving_rate) },
          { t: '年节费(元)', r: 1, f: r => App.num(r.saving_fee) },
          { t: '回收期(年)', r: 1, f: r => App.num(r.payback, 2) },
          { t: '结论', f: r => App.stTag(r.verdict) },
        ], p.verifies);
      } else {
        h += '<div class="note">该项目尚无验证记录。完成实施后在列表点「验证」按报告期自动核算节能量。</div>';
      }
      App.modal('项目详情 · ' + no, h, null, true);
    } catch (e) { App.err(e.message); }
  },
  verify(no) {
    App.modal('节能量验证 · ' + no, `
      <div class="frow">
        <div class="f"><label>报告期</label><input id="v_period" value="${App.S.period}"></div>
        <div class="f"><label>年化月数</label><input id="v_months" type="number" value="12"></div>
      </div>
      <div class="note">系统按报告期实际用量与产量计算单耗，与锁定基线对比得出节能量、节能率、年节费与投资回收期。
        若报告期产量为 0 或无非计量数据，将拒绝验证。</div>`,
      `<button class="btn" onclick="App.closeModal()">取消</button>
       <button class="btn pri" onclick="Project.doVerify('${no}')">执行验证</button>`);
  },
  async doVerify(no) {
    const b = {
      period: document.getElementById('v_period').value,
      months: Number(document.getElementById('v_months').value) || 12,
    };
    try {
      const r = await App.POST('/projects/' + no + '/verify', b);
      App.closeModal();
      App.modal('验证结果 · ' + no, `
        <div class="grid g2">
          <div class="card kpi"><div class="k">节能量</div><div class="v">${App.num(r.savingTce, 2)}<small>tce</small></div>
            <div class="d">节能率 ${App.pct(r.savingRate)}</div></div>
          <div class="card kpi ${r.achieved ? 'o' : 'b'}"><div class="k">结论</div>
            <div class="v" style="font-size:20px">${r.verdict}</div></div>
          <div class="card kpi i"><div class="k">年节费</div><div class="v">${App.wan(r.savingFeeYear)}<small>元</small></div></div>
          <div class="card kpi w"><div class="k">投资回收期</div><div class="v">${App.num(r.paybackYear, 2)}<small>年</small></div></div>
        </div>
        <div class="note" style="margin-top:14px">基线单耗 ${App.q6(r.baseUnit)} → 报告期单耗 ${App.q6(r.reportUnit)}，
          产量 ${App.num(r.qty)}，投资 ${App.num(r.invest)} 元。${r.achieved ? '' : '节能量为负，项目未达预期，需填写原因并复评技术方案。'}</div>`);
      if (!r.achieved) setTimeout(() => App.err('节能量为负，项目判为未达标'), 300);
    } catch (e) { App.err(e.message); }
  },
};

/* ---------- 能源预算 ---------- */
App.page({
  id: 'budget', t: '能源预算',
  async render() {
    const d = await App.GET('/budgets', { period: App.S.period });
    const t = d.totals;
    const rate = t.amount ? t.used / t.amount : 0;

    let h = `<div class="grid g4">
      <div class="card kpi"><div class="k">预算总额</div><div class="v">${App.wan(t.amount)}<small>元</small></div><div class="d">期间 ${d.period}</div></div>
      <div class="card kpi i"><div class="k">已执行</div><div class="v">${App.wan(t.used)}<small>元</small></div></div>
      <div class="card kpi w"><div class="k">剩余</div><div class="v">${App.wan(t.amount - t.used)}<small>元</small></div></div>
      <div class="card kpi ${rate > 1 ? 'b' : (rate >= 0.9 ? 'w' : 'o')}"><div class="k">执行率</div>
        <div class="v">${App.pct(rate)}</div><div class="d">≥90% 预警 · >100% 超支 · >110% 阻断</div></div>
    </div>`;

    h += '<div class="ptitle"><span class="bar"></span>预算执行明细</div>';
    h += App.table([
      { t: '成本中心', f: r => r.center + ' ' + (r.centerName || '') },
      { t: '介质', f: r => (r.energy_code || '') + ' ' + (r.energyName || '') },
      { t: '预算(元)', r: 1, f: r => App.num(r.amount) },
      { t: '已用(元)', r: 1, f: r => App.num(r.used) },
      { t: '剩余(元)', r: 1, f: r => App.num(r.left) },
      { t: '执行率', r: 1, f: r => App.pct(r.rate) },
      { t: '进度', f: r => `<div class="pbar" style="width:120px"><i class="${r.rate > 1 ? 'b' : (r.rate >= 0.9 ? 'w' : '')}" style="width:${Math.min(r.rate * 100, 100)}%"></i></div>` },
      { t: '状态', f: r => App.stTag(r.status) },
    ], d.list);

    h += `<div class="note"><b>预算闸口</b>：执行率进入 90% 触发预警（不进预算中心主动推送，只在看板与列表标红），
      超 100% 判为超支并生成告警，超 110% 阻断新的能源费用入账。
      预算按「成本中心 × 能源介质」双维度控制，避免只盯总量导致某个车间偷偷超用。</div>`;
    return h;
  }
});
