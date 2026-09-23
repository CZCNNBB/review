/* 界面冒烟测试：用最小 DOM 桩逐页渲染 app.js，检查渲染和按钮处理函数是否有运行时错误。
   用法：node smoke-test.js
   依赖 demo.js 提供示例数据，不连接后端。 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function makeElement(tag) {
  const el = {
    tagName: String(tag || 'div').toUpperCase(),
    className: '', id: '', value: '', textContent: '', hidden: false,
    style: {}, dataset: {}, elements: {}, children: [],
    _html: '',
    _listeners: {},
    addEventListener(type, handler) { (el._listeners[type] = el._listeners[type] || []).push(handler); },
    removeEventListener() {},
    dispatch(type, event) { (el._listeners[type] || []).forEach((handler) => handler(event || {})); },
    appendChild(child) { el.children.push(child); return child; },
    remove() {}, select() {}, focus() {},
    setPointerCapture() {}, releasePointerCapture() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 1000, height: 600, right: 1000, bottom: 600 }; },
    setAttribute(name, value) { el[name] = value; },
    querySelector() { return makeElement('div'); },
    // 测试可以往 _queryAll 里塞假的连线元素，用来驱动拖动时的重绘逻辑
    querySelectorAll() { return el._queryAll || []; },
    closest() { return null; },
    classList: { add() {}, remove() {}, contains() { return false; } },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(v) {
      el._html = String(v);
      // 真实页面上重设 innerHTML 会把旧子树连同监听一起丢掉，
      // 这里也要丢，否则画布每渲染一次就多挂一份指针监听
      if (el.id === 'view') dropRenderedListeners();
    },
  });
  return el;
}

const elements = {};
for (const id of ['view', 'cfg-base', 'cfg-admin', 'cfg-apikey', 'cfg-person', 'cfg-check', 'cfg-state', 'rail-nav', 'overlay-host', 'toast-host', 'demo-banner']) {
  const el = makeElement('div');
  el.id = id;
  elements[id] = el;
}

// 页面骨架之外的元素都是渲染时按 id 现取的，重渲染后等于新元素、没有监听
const skeletonIds = new Set(Object.keys(elements));
function dropRenderedListeners() {
  Object.keys(elements).forEach((id) => {
    if (!skeletonIds.has(id)) elements[id]._listeners = {};
  });
}

const sandbox = {
  console,
  setTimeout: (fn) => setTimeout(fn, 0),
  clearTimeout,
  JSON, Math, Date, Object, Array, String, Number, Boolean, Error, Set, Map, Promise,
  URL, URLSearchParams,
  localStorage: {
    _data: { 'approval-console.demo': '1' },
    getItem(k) { return this._data[k] === undefined ? null : this._data[k]; },
    setItem(k, v) { this._data[k] = String(v); },
    removeItem(k) { delete this._data[k]; },
  },
  navigator: { clipboard: { writeText: async () => {} } },
  location: { hash: '#/overview', href: 'file:///web/index.html' },
  document: {
    getElementById: (id) => elements[id] || (elements[id] = makeElement('div')),
    createElement: makeElement,
    createElementNS: (namespace, tag) => makeElement(tag),
    querySelector: (selector) => elements[selector] || (elements[selector] = makeElement('div')),
    addEventListener() {}, removeEventListener() {},
    body: makeElement('body'),
    head: makeElement('head'),
    // 拉线的 pointerup 用它判断落在哪个节点上，测试往 elements.__hovered 里塞桩
    elementFromPoint: () => elements.__hovered || null,
  },
  fetch: async () => { throw new Error('真实网络不可用'); },
  addEventListener() {}, removeEventListener() {},
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);

const web = __dirname;
vm.runInContext(fs.readFileSync(path.join(web, 'demo.js'), 'utf8'), sandbox, { filename: 'demo.js' });
sandbox.ApprovalDemo.enable();
vm.runInContext(fs.readFileSync(path.join(web, 'app.js'), 'utf8'), sandbox, { filename: 'app.js' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitRendered() {
  for (let i = 0; i < 60; i += 1) {
    await sleep(5);
    const html = elements.view.innerHTML;
    if (html && !html.includes('正在读取数据')) return html;
  }
  return elements.view.innerHTML;
}

const ROUTES = [
  ['#/overview', '闭环进度'],
  ['#/tenants', '租户'],
  ['#/tenants/10000000-0000-4000-8000-000000000001', 'API Key'],
  ['#/people', '全局人员'],
  ['#/processes', '审批流'],
  ['#/processes/40000000-0000-4000-8000-000000000001', '版本历史'],
  ['#/versions/41000000-0000-4000-8000-000000000002', '已发布版本永久只读'],
  ['#/actions', '业务动作'],
  ['#/grants', '审批流授权'],
  ['#/tasks', '审批任务'],
  ['#/start', '发起审批'],
  ['#/executions', '执行记录'],
  ['#/executions/90000000-0000-4000-8000-000000000001', '调用结果'],
  ['#/usages', '使用记录'],
];

(async () => {
  let failed = 0;

  async function check(hash, marker) {
    sandbox.location.hash = hash;
    vm.runInContext('route()', sandbox);
    const html = await waitRendered();
    const error = html.includes('读取失败') ? html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').match(/读取失败：(.{0,90})/) : null;
    const ok = !error && html.includes(marker);
    if (!ok) failed += 1;
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${hash.padEnd(58)} ${error ? `渲染失败 → ${error[1]}` : ok ? '' : `缺少标记「${marker}」`}`);
  }

  for (const [hash, marker] of ROUTES) await check(hash, marker);

  // 审批详情与任务视图：管理台自动借用租户密钥，不需要额外配置
  vm.runInContext(
    `config.adminKey='demo';config.base='http://127.0.0.1:8090';`,
    sandbox
  );

  for (const [hash, marker] of [
    ['#/tasks', '审批任务'],
    ['#/tasks?status=ALL', '全部状态'],
    ['#/instances/70000000-0000-4000-8000-000000000001', '会签时间线'],
    ['#/instances/70000000-0000-4000-8000-000000000002', '业务执行'],
    ['#/start', ''], // 重新渲染，确认自动借用密钥后不再要求手填
  ]) {
    await check(hash, marker);
  }

  // 页面上的关键动作：打开弹窗、保存草稿、校验、发起审批等
  const TENANT = '10000000-0000-4000-8000-000000000001';
  const TASK = '80000000-0000-4000-8000-000000000001';
  const ACTIONS = [
    ['#/tenants', ['new-tenant']],
    [`#/tenants/${TENANT}`, ['new-key', 'new-credential']],
    ['#/people', ['new-person', 'new-department', ['edit-person', '20000000-0000-4000-8000-000000000001']]],
    ['#/processes', ['new-process']],
    ['#/versions/41000000-0000-4000-8000-000000000002', [
      ['palette-add', '00000000-0000-0000-0000-000000000102'],
      ['edit-node', '50000000-0000-4000-8000-000000000002'],
      ['edit-branch', '50000000-0000-4000-8000-000000000006'],
      'flow-layout', 'save-graph', 'validate',
    ]],
    ['#/actions', ['new-action', ['edit-action', '60000000-0000-4000-8000-000000000001']]],
    ['#/grants', ['bind-process', 'bind-action']],
    ['#/executions', ['filter']],
    ['#/start', ['sample-form', 'gen-curl', 'use-manual-key']],
    ['#/tasks', [['approve', TASK]]],
    ['#/instances/70000000-0000-4000-8000-000000000001', [['approve', TASK]]],
  ];

  for (const [hash, entries] of ACTIONS) {
    sandbox.location.hash = hash;
    vm.runInContext('route()', sandbox);
    await waitRendered();
    for (const entry of entries) {
      const [name, id] = Array.isArray(entry) ? entry : [entry, null];
      sandbox.arguments0 = {
        dataset: { id, definitionId: id, index: '0', tenant: TENANT, next: 'DISABLED', tab: 'departments' },
        value: '', checked: false, tagName: 'BUTTON', selectedOptions: [], closest: () => null,
      };
      try {
        await vm.runInContext(`Promise.resolve().then(() => actions['${name}'](arguments0))`, sandbox);
        console.log(`PASS  动作 ${name.padEnd(22)} @ ${hash}`);
      } catch (err) {
        failed += 1;
        console.log(`FAIL  动作 ${name.padEnd(22)} @ ${hash} → ${err.message}`);
      }
    }
  }

  // 版本编辑器：本地编辑状态在重新渲染后必须保留（新增节点、拖动坐标都不能被接口数据覆盖）
  const VERSION = '41000000-0000-4000-8000-000000000002';
  sandbox.location.hash = `#/versions/${VERSION}`;
  vm.runInContext('route()', sandbox);
  await waitRendered();

  const before = vm.runInContext('versionEditorState.nodes.length', sandbox);
  vm.runInContext(
    `versionEditorState.nodes.push({ id: '99999999-0000-4000-8000-000000000001', node_definition_id: '${'00000000-0000-0000-0000-000000000102'}', node_type: 'APPROVAL', name: '新增的测试节点', config: { approval_mode: 'AND', approvers: [] }, position: { x: 900, y: 400 } });
     versionEditorState.dirty = true;`,
    sandbox
  );
  // 切换页签会重新渲染整个编辑器，这一步以前会把未保存的改动冲掉
  vm.runInContext(`actions['version-tab']({ dataset: { tab: 'list' } })`, sandbox);
  await sleep(150);
  const after = vm.runInContext('versionEditorState.nodes.length', sandbox);
  const kept = after === before + 1;
  if (!kept) failed += 1;
  console.log(`${kept ? 'PASS' : 'FAIL'}  重新渲染保留未保存的节点（${before} → ${after}）`);

  vm.runInContext(`actions['version-tab']({ dataset: { tab: 'canvas' } })`, sandbox);
  await sleep(150);
  const canvasHtml = elements.view.innerHTML;
  const inCanvas = canvasHtml.includes('新增的测试节点') && canvasHtml.includes('flow__node');
  if (!inCanvas) failed += 1;
  console.log(`${inCanvas ? 'PASS' : 'FAIL'}  画布渲染出新节点`);

  // 自动排版：所有节点坐标必须互不相同
  vm.runInContext(`actions['flow-layout']()`, sandbox);
  await sleep(200);
  const distinct = vm.runInContext(
    `new Set(versionEditorState.nodes.map((node) => node.position.x + ':' + node.position.y)).size === versionEditorState.nodes.length`,
    sandbox
  );
  if (!distinct) failed += 1;
  console.log(`${distinct ? 'PASS' : 'FAIL'}  自动排版后节点坐标互不重叠`);

  // 节点面板（由节点定义渲染）与按 Schema 生成的配置表单
  sandbox.location.hash = '#/versions/41000000-0000-4000-8000-000000000003';
  vm.runInContext('route()', sandbox);
  await waitRendered();

  const paletteHtml = elements.view.innerHTML;
  const paletteOk =
    (paletteHtml.match(/flow-palette__item/g) || []).length >= 3 &&
    paletteHtml.includes('人工审批') &&
    paletteHtml.includes('拖到画布上新增节点');
  if (!paletteOk) failed += 1;
  console.log(`${paletteOk ? 'PASS' : 'FAIL'}  节点面板按定义渲染出全部节点`);

  const nodesBefore = vm.runInContext('versionEditorState.nodes.length', sandbox);
  sandbox.arguments0 = { dataset: { definitionId: '00000000-0000-0000-0000-000000000102' }, value: '', checked: false, tagName: 'DIV' };
  vm.runInContext(`actions['palette-add'](arguments0)`, sandbox);
  await sleep(120);
  const nodesAfter = vm.runInContext('versionEditorState.nodes.length', sandbox);
  const newNode = vm.runInContext(
    `(() => { const list = versionEditorState.nodes; const node = list[list.length - 1];
      return { def: node.node_definition_id, type: node.node_type, mode: node.config.approval_mode, approvers: node.config.approvers }; })()`,
    sandbox
  );
  const added = nodesAfter === nodesBefore + 1
    && newNode.def === '00000000-0000-0000-0000-000000000102'
    && newNode.type === 'APPROVAL'
    && newNode.mode === 'AND'
    && Array.isArray(newNode.approvers);
  if (!added) failed += 1;
  console.log(`${added ? 'PASS' : 'FAIL'}  面板新增节点带上定义与 Schema 默认值（${JSON.stringify(newNode)}）`);

  const overlayHtml = elements['overlay-host'].innerHTML;
  const formOk = overlayHtml.includes('审批模式') && overlayHtml.includes('审批人') && overlayHtml.includes('审批表单') === false;
  if (!formOk) failed += 1;
  console.log(`${formOk ? 'PASS' : 'FAIL'}  配置弹窗按 Schema 生成「审批模式」「审批人」字段`);

  // 回归：编辑已有节点必须回填当前取值。曾经漏传 values，导致下拉停在第一个选项上，
  // 打开配置直接保存会把「任意一人同意」改成「全部同意」、把审批人清空。
  const bossId = vm.runInContext(
    `versionEditorState.nodes.find((node) => node.name === '总经理审批').id`,
    sandbox
  );
  sandbox.arguments0 = { dataset: { id: bossId }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-node'](arguments0)`, sandbox);
  await sleep(150);
  const editHtml = elements['overlay-host'].innerHTML;
  const modeSelect = (editHtml.match(/<select class="select" name="approval_mode">[\s\S]{0,200}?<\/select>/) || [''])[0];
  const approversSelect = (editHtml.match(/<select[^>]*name="approvers"[^>]*>[\s\S]{0,600}?<\/select>/) || [''])[0];
  const prefillOk = modeSelect.includes('value="OR" selected')
    && (approversSelect.match(/selected/g) || []).length === 1
    && editHtml.includes('name="name" value="总经理审批"')
    && editHtml.includes('留空就用定义名');
  if (!prefillOk) failed += 1;
  console.log(`${prefillOk ? 'PASS' : 'FAIL'}  编辑节点时回填当前配置和名称`);

  // 不命名就保持定义名：节点名称不是必填项
  elements['#dialog-form'].elements = { name: { value: '' } };
  await vm.runInContext(`dialogActions['dialog-submit']()`, sandbox);
  await sleep(150);
  const renamed = vm.runInContext(
    `(() => { const node = versionEditorState.nodes.find((item) => item.id === '${bossId}');
       return { name: node.name, mode: node.config.approval_mode, approvers: node.config.approvers.length }; })()`,
    sandbox
  );
  const fallbackOk = renamed.name === '人工审批' && renamed.mode === 'OR' && renamed.approvers === 1;
  if (!fallbackOk) failed += 1;
  console.log(`${fallbackOk ? 'PASS' : 'FAIL'}  名称留空保持定义名，配置不被改掉（${JSON.stringify(renamed)}）`);

  // 分支阶梯：前面每条要配条件，最后一条是"其余情况"不能带条件
  const ladder = vm.runInContext(
    `(() => {
       const nodes = [{ id: 'b', node_type: 'CONDITION', name: '条件分支' }];
       const condition = { field: 'approval_form.amount', operator: 'GT', value: 10000 };
       const first = { source_node_id: 'b', target_node_id: 'x', condition };
       const last = { source_node_id: 'b', target_node_id: 'y' };
       const good = [first, last];
       const badLast = [first, { source_node_id: 'b', target_node_id: 'y', condition }];
       const badFirst = [{ source_node_id: 'b', target_node_id: 'x' }, last];
       return {
         goodFirst: branchRowState(first, nodes, good).problem,
         goodLast: branchRowState(last, nodes, good).problem,
         lastMarked: branchRowState(last, nodes, good).isLast,
         badLastProblem: branchRowState(badLast[1], nodes, badLast).problem,
         badFirstProblem: branchRowState(badFirst[0], nodes, badFirst).problem,
       };
     })()`,
    sandbox
  );
  const orderOk = ladder.goodFirst === null && ladder.goodLast === null && ladder.lastMarked === true
    && Boolean(ladder.badLastProblem) && Boolean(ladder.badFirstProblem);
  if (!orderOk) failed += 1;
  console.log(`${orderOk ? 'PASS' : 'FAIL'}  分支阶梯规则（${JSON.stringify(ladder)}）`);

  // 审批表单：Schema 与字段表的互转
  const formSchemaDemo = {
    type: 'object',
    title: '付款申请',
    required: ['amount', 'supplier_name'],
    additionalProperties: false,
    properties: {
      amount: { type: 'number', title: '付款金额', exclusiveMinimum: 0 },
      supplier_name: { type: 'string', title: '供应商名称' },
      pay_date: { type: 'string', format: 'date', title: '期望付款日期' },
      remark: { type: 'string', title: '备注' },
    },
  };
  sandbox.formSchemaDemo = formSchemaDemo;

  const parsedForm = vm.runInContext(
    `(() => {
       const parsed = formFieldsFromSchema(formSchemaDemo);
       const roundTrip = applyFormFields(formSchemaDemo, parsed.fields);
       return {
         simple: parsed.simple,
         types: parsed.fields.map((field) => field.key + ':' + field.type + (field.required ? '*' : '')),
         keepsConstraint: roundTrip.properties.amount.exclusiveMinimum === 0,
         keepsRequired: JSON.stringify(roundTrip.required) === JSON.stringify(['amount', 'supplier_name']),
         keepsExtra: roundTrip.additionalProperties === false,
       };
     })()`,
    sandbox
  );
  const parseOk = parsedForm.simple
    && parsedForm.types.join(',') === 'amount:number*,supplier_name:string*,pay_date:date,remark:string'
    && parsedForm.keepsConstraint && parsedForm.keepsRequired && parsedForm.keepsExtra;
  if (!parseOk) failed += 1;
  console.log(`${parseOk ? 'PASS' : 'FAIL'}  表单 Schema 解析与回写（${parsedForm.types.join(' / ')}）`);

  const operatorFilter = vm.runInContext(
    `({
       number: operatorOptionsForField({ type: 'number' }).map((item) => item.value),
       string: operatorOptionsForField({ type: 'string' }).map((item) => item.value),
       boolean: operatorOptionsForField({ type: 'boolean' }).map((item) => item.value),
     })`,
    sandbox
  );
  const operatorOk = operatorFilter.number.includes('GT')
    && !operatorFilter.string.includes('GT')
    && operatorFilter.string.includes('EQ')
    && operatorFilter.boolean.includes('EQ')
    && !operatorFilter.boolean.includes('IN');
  if (!operatorOk) failed += 1;
  console.log(`${operatorOk ? 'PASS' : 'FAIL'}  比较方式按字段类型过滤（数字 ${operatorFilter.number.length} 项，文本 ${operatorFilter.string.length} 项）`);

  const typed = vm.runInContext(
    `({
       num: typedConditionValue({ type: 'number' }, 'GT', '10000'),
       text: typedConditionValue({ type: 'string' }, 'EQ', '宁波精工'),
       pick: typedConditionValue({ type: 'enum' }, 'EQ', '差旅'),
       list: typedConditionValue({ type: 'string' }, 'IN', '["A","B"]'),
       sentence: conditionText({ field: 'approval_form.amount', operator: 'GT', value: 10000 }, { 'approval_form.amount': '付款金额' }),
       empty: conditionText({ field: 'approval_form.remark', operator: 'IS_EMPTY' }, { 'approval_form.remark': '备注' }),
     })`,
    sandbox
  );
  const typedOk = typed.num === 10000 && typed.text === '宁波精工' && typed.pick === '差旅'
    && JSON.stringify(typed.list) === '["A","B"]'
    && typed.sentence === '付款金额 > 10000'
    && typed.empty === '备注 为空';
  if (!typedOk) failed += 1;
  console.log(`${typedOk ? 'PASS' : 'FAIL'}  比较值按类型转换与人话措辞（${typed.sentence} / ${typed.empty}）`);

  // 条件分支节点：卡片上按 if/elif/else 列出分支，每条分支有自己的出口
  const orderedCanvas = elements.view.innerHTML;
  const branchCardOk = orderedCanvas.includes('flow__node--CONDITION')
    && orderedCanvas.includes('flow__row-mark')
    && orderedCanvas.includes('其余情况')
    && orderedCanvas.includes('按金额分流')
    && (orderedCanvas.match(/flow__row-port/g) || []).length >= 3; // 两条分支 + 新增分支各一个出口
  if (!branchCardOk) failed += 1;
  console.log(`${branchCardOk ? 'PASS' : 'FAIL'}  条件分支卡片列出分支，每条分支带自己的出口`);

  // 分支节点的每条分支从自己那一行出发：节点在 (520,150)，卡片宽 232，
  // 第一条分支的出口在 520+232=752、150+42+14=206
  const rowAnchorOk = orderedCanvas.includes('M 752 206 C') && orderedCanvas.includes('M 752 234 C');
  if (!rowAnchorOk) failed += 1;
  console.log(`${rowAnchorOk ? 'PASS' : 'FAIL'}  分支线从各自那一行的出口引出`);

  // 分支节点里没配条件的行要高亮，并在卡片上提示"分支未配完"
  vm.runInContext(
    `versionEditorState.connections.push({
       source_node_id: '50000000-0000-4000-8000-000000000006',
       target_node_id: '50000000-0000-4000-8000-000000000002',
     });
     versionEditorState.dirty = true;`,
    sandbox
  );
  vm.runInContext('route()', sandbox);
  await waitRendered();
  const multiOut = elements.view.innerHTML;
  const incomplete = (multiOut.match(/flow__row is-incomplete/g) || []).length;
  const knobOk = incomplete === 1 && multiOut.includes('分支未配完');
  if (!knobOk) failed += 1;
  console.log(`${knobOk ? 'PASS' : 'FAIL'}  没配条件的分支行高亮并在卡片上提示（${incomplete} 行）`);

  // 只定义了分支还没拉线时，行上显示"未接去向"，卡片上提示"分支未接去向"
  vm.runInContext(
    `versionEditorState.connections.push({
       source_node_id: '50000000-0000-4000-8000-000000000006',
       target_node_id: null,
     });
     versionEditorState.dirty = true;`,
    sandbox
  );
  vm.runInContext('route()', sandbox);
  await waitRendered();
  const unlinkedHtml = elements.view.innerHTML;
  const unlinkedOk = unlinkedHtml.includes('flow__row-target is-unlinked')
    && unlinkedHtml.includes('未接去向')
    && unlinkedHtml.includes('分支未接去向');
  if (!unlinkedOk) failed += 1;
  console.log(`${unlinkedOk ? 'PASS' : 'FAIL'}  定义了但没拉线的分支显示"未接去向"`);
  vm.runInContext('versionEditorState.connections.pop(); route();', sandbox);
  await waitRendered();

  // 回归：连线的条件只能从分支节点里配，不该再有第二个入口
  const noEdgeDialog = !vm.runInContext('Object.keys(actions)', sandbox).includes('edit-connection');
  if (!noEdgeDialog) failed += 1;
  console.log(`${noEdgeDialog ? 'PASS' : 'FAIL'}  单条连线没有独立的条件弹窗，条件统一在分支节点里配`);

  // 交互：拖动节点时连线要跟着重画（这一段只在指针事件里执行，渲染测试覆盖不到）
  const flowEl = elements['flow'];
  const stageEl = elements['flow-stage'];
  const draggedNode = '50000000-0000-4000-8000-000000000002'; // 财务审批
  const before300 = vm.runInContext(
    `versionEditorState.nodes.find((node) => node.id === '${draggedNode}').position.x`,
    sandbox
  );
  // 假的连线元素：拖动时 updateEdges 会遍历它并按新坐标重画
  const drawn = [];
  stageEl._queryAll = [{ dataset: { conn: '0' }, setAttribute(name, value) { drawn.push(value); } }];
  const nodeStub = {
    dataset: { id: draggedNode },
    style: {},
    classList: { add() {}, remove() {} },
  };
  const dragEvent = (type, clientX) => ({
    type,
    button: 0,
    pointerId: 1,
    clientX,
    clientY: 100,
    preventDefault() {},
    target: {
      closest: (selector) => (selector === '.flow__node' ? nodeStub : null),
    },
  });
  let dragError = null;
  try {
    flowEl.dispatch('pointerdown', dragEvent('pointerdown', 400));
    flowEl.dispatch('pointermove', dragEvent('pointermove', 520));
  } catch (err) {
    dragError = err;
  }
  const movedOk = !dragError
    && drawn.length > 0
    && vm.runInContext(
      `versionEditorState.nodes.find((node) => node.id === '${draggedNode}').position.x`,
      sandbox
    ) !== before300;
  if (!movedOk) failed += 1;
  console.log(`${movedOk ? 'PASS' : 'FAIL'}  拖动节点时坐标更新且连线跟着重画${dragError ? ` → ${dragError.message}` : ''}`);

  // 分支编辑器：一个窗口里把 if/elif/else 阶梯配完，保存后按列表重建出线
  const BRANCH_NODE = '50000000-0000-4000-8000-000000000006';
  // 这几段会改动编排，跑完恢复原样，后面的用例还依赖原来那份数据
  const connSnapshot = vm.runInContext('JSON.stringify(versionEditorState.connections)', sandbox);
  sandbox.arguments0 = { dataset: { id: BRANCH_NODE }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-branch'](arguments0)`, sandbox);
  await sleep(120);
  const branchDialog = elements['overlay-host'].innerHTML;
  const rowCount = (branchDialog.match(/class="branch-row"/g) || []).length;
  // 弹窗里只配条件，去向是只读的：去哪由画布上拉的那条线决定
  const branchDialogOk = rowCount === 3
    && branchDialog.includes('其余情况')
    && branchDialog.includes('新增条件')
    && branchDialog.includes('branch-row__target')
    && !branchDialog.includes('branch-0-target')
    && !branchDialog.includes('<option value=""');
  if (!branchDialogOk) failed += 1;
  console.log(`${branchDialogOk ? 'PASS' : 'FAIL'}  分支编辑器只配条件，去向只读（${rowCount} 条）`);

  // 新增条件插在"其余情况"之前，最后一行不会被顶掉
  vm.runInContext(`dialogActions['branch-add']()`, sandbox);
  await sleep(60);
  const afterAdd = (elements['branch-host'].innerHTML.match(/class="branch-row"/g) || []).length;
  const addOk = afterAdd === 4;
  if (!addOk) failed += 1;
  console.log(`${addOk ? 'PASS' : 'FAIL'}  新增条件插在其余情况之前（${rowCount} → ${afterAdd} 条）`);

  // 填好条件再保存：出线按列表顺序重建，去向原样保留，最后一条不带条件
  const TARGET_FINANCE = '50000000-0000-4000-8000-000000000002';
  const TARGET_APPROVED = '50000000-0000-4000-8000-000000000004';
  vm.runInContext(
    `(() => {
       const set = (id, value) => { document.getElementById(id).value = value; };
       for (let index = 0; index < 3; index += 1) {
         set('branch-' + index + '-field', 'approval_form.amount');
         set('branch-' + index + '-operator', 'GT');
         set('branch-' + index + '-value', String(1000 * (index + 1)));
       }
     })()`,
    sandbox
  );
  await vm.runInContext(`dialogActions['branch-submit']()`, sandbox);
  await sleep(120);
  const rebuilt = vm.runInContext(
    `versionEditorState.connections
       .filter((connection) => connection.source_node_id === '${BRANCH_NODE}')
       .map((connection) => ({
         target: connection.target_node_id,
         hasCondition: Boolean(connection.condition),
         value: connection.condition ? connection.condition.value : null,
       }))`,
    sandbox
  );
  const rebuildOk = rebuilt.length === 4
    && rebuilt.slice(0, 3).every((item) => item.hasCondition)
    && rebuilt[3].hasCondition === false
    // 新增的那条还没拉线，去向留空；原来的兜底行去向不动
    && rebuilt[2].target === null
    && rebuilt[3].target === TARGET_FINANCE
    && rebuilt[0].value === 1000;
  if (!rebuildOk) failed += 1;
  console.log(`${rebuildOk ? 'PASS' : 'FAIL'}  保存后按阶梯重建出线并保留去向（${JSON.stringify(rebuilt)}）`);

  // 从某一行的圆点拉线：改的是这条分支的去向，不是新增一条线
  vm.runInContext(`route()`, sandbox);
  await waitRendered();
  const branchTargets = () => vm.runInContext(
    `versionEditorState.connections
       .filter((connection) => connection.source_node_id === '${BRANCH_NODE}')
       .map((connection) => connection.target_node_id)`,
    sandbox
  );
  const beforeLink = branchTargets();
  const linkStub = (branch) => ({
    dataset: { branch },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 10, height: 10, right: 10, bottom: 10 }),
  });
  const connectEvent = (type, branch, targetId) => ({
    type,
    button: 0,
    pointerId: 1,
    clientX: 300,
    clientY: 200,
    preventDefault() {},
    target: {
      closest: (selector) => {
        if (selector === '.flow__node') return { dataset: { id: BRANCH_NODE }, style: {}, classList: { add() {}, remove() {} } };
        if (selector === '.flow__port--out, .flow__row-port') return linkStub(branch);
        // 端口画在带 data-act="edit-branch" 的分支行里面，真实 DOM 里这两个会同时命中
        if (selector === '[data-act]') return { dataset: { id: BRANCH_NODE } };
        return null;
      },
    },
    // pointerup 时 elementFromPoint 决定落到哪个节点上
    hovered: { closest: (selector) => (selector === '.flow__node' ? { dataset: { id: targetId } } : null) },
  });
  elements.__hovered = null;
  flowEl.dispatch('pointerdown', connectEvent('pointerdown', '2'));
  elements.__hovered = connectEvent('pointerup', '2', TARGET_APPROVED).hovered;
  flowEl.dispatch('pointerup', connectEvent('pointerup', '2', TARGET_APPROVED));
  await sleep(80);
  const afterLink = branchTargets();
  const linkOk = afterLink.length === beforeLink.length
    && afterLink[2] === TARGET_APPROVED
    && afterLink[3] === beforeLink[3];
  if (!linkOk) failed += 1;
  console.log(`${linkOk ? 'PASS' : 'FAIL'}  从分支行的圆点拉线只改这条分支的去向（${JSON.stringify(afterLink)}）`);

  // 从"＋ 新增分支"的圆点拉线：新开一条分支，插在其余情况之前，并弹出配置窗口补条件
  const beforeAddBranch = branchTargets();
  flowEl.dispatch('pointerdown', connectEvent('pointerdown', 'new'));
  elements.__hovered = connectEvent('pointerup', 'new', TARGET_APPROVED).hovered;
  flowEl.dispatch('pointerup', connectEvent('pointerup', 'new', TARGET_APPROVED));
  await sleep(80);
  const afterAddBranch = branchTargets();
  const newBranchOk = afterAddBranch.length === beforeAddBranch.length + 1
    && afterAddBranch[afterAddBranch.length - 2] === TARGET_APPROVED
    && afterAddBranch[afterAddBranch.length - 1] === beforeAddBranch[beforeAddBranch.length - 1]
    && elements['overlay-host'].innerHTML.includes('条件分支');
  if (!newBranchOk) failed += 1;
  console.log(`${newBranchOk ? 'PASS' : 'FAIL'}  从"新增分支"圆点拉线新开一条分支并打开配置（${JSON.stringify(afterAddBranch)}）`);
  vm.runInContext(`dialogActions['close-dialog']()`, sandbox);
  vm.runInContext(`versionEditorState.connections = JSON.parse(${JSON.stringify(connSnapshot)});`, sandbox);
  vm.runInContext('route()', sandbox);
  await waitRendered();

  // 条件分支的出口只挂在分支行上：卡片本身不模拟普通节点的"边缘出口"
  const conditionCard = elements.view.innerHTML;
  const cardStart = conditionCard.indexOf('flow__node--CONDITION');
  // 只截这一张卡片：到下一张卡片为止，否则会把后面节点的端口也算进来
  const nextCard = conditionCard.indexOf('flow__node--', cardStart + 1);
  const cardPortHtml = conditionCard.slice(cardStart, nextCard === -1 ? undefined : nextCard);
  const branchRowPorts = (cardPortHtml.match(/class="flow__row-port"/g) || []).length;
  const branchNodeRows = vm.runInContext(
    `versionEditorState.connections.filter((connection) => connection.source_node_id === '${BRANCH_NODE}').length`,
    sandbox
  );
  const cardPortOk = cardStart >= 0
    && !cardPortHtml.includes('flow__port--out')
    && branchRowPorts === branchNodeRows;
  if (!cardPortOk) failed += 1;
  console.log(`${cardPortOk ? 'PASS' : 'FAIL'}  条件分支的出口只在分支行上，卡片不挂悬停出口（行出口 ${branchRowPorts}/${branchNodeRows}）`);

  // 每条线中点都要有删线入口
  const connCount = vm.runInContext('versionEditorState.connections.length', sandbox);
  const delButtons = (elements.view.innerHTML.match(/data-act="drop-connection"/g) || []).length;
  const delOk = delButtons === connCount;
  if (!delOk) failed += 1;
  console.log(`${delOk ? 'PASS' : 'FAIL'}  每条连线中点都有断开入口（${delButtons}/${connCount}）`);

  // 断开分支的一条线：只清去向，分支和条件都留着
  const branchEdgeIndex = vm.runInContext(
    `versionEditorState.connections.findIndex((connection) => connection.source_node_id === '${BRANCH_NODE}')`,
    sandbox
  );
  const beforeBreak = vm.runInContext('JSON.stringify(versionEditorState.connections)', sandbox);
  // 这条线在"该节点的第几条分支"里的位置，用它去读过滤后的列表
  const branchPosition = vm.runInContext(
    `versionEditorState.connections
       .slice(0, ${branchEdgeIndex})
       .filter((connection) => connection.source_node_id === '${BRANCH_NODE}').length`,
    sandbox
  );
  vm.runInContext(`actions['drop-connection']({ dataset: { conn: '${branchEdgeIndex}' } })`, sandbox);
  await sleep(80);
  const afterBreak = vm.runInContext(
    `versionEditorState.connections
       .filter((connection) => connection.source_node_id === '${BRANCH_NODE}')
       .map((connection) => [connection.target_node_id, Boolean(connection.condition)])`,
    sandbox
  );
  const breakOk = vm.runInContext('versionEditorState.connections.length', sandbox)
      === JSON.parse(beforeBreak).length
    && afterBreak[branchPosition][0] === null
    && afterBreak[branchPosition][1] === true;
  if (!breakOk) failed += 1;
  console.log(`${breakOk ? 'PASS' : 'FAIL'}  断开分支去向只清空目标，分支和条件保留（${JSON.stringify(afterBreak)}）`);

  // 断开普通连线：整条线删掉，来源节点提示"还没有去向"
  const plainEdgeIndex = vm.runInContext(
    `versionEditorState.connections.findIndex((connection) => connection.source_node_id === '50000000-0000-4000-8000-000000000002')`,
    sandbox
  );
  vm.runInContext(`actions['drop-connection']({ dataset: { conn: '${plainEdgeIndex}' } })`, sandbox);
  await sleep(80);
  const afterDeleteOk = vm.runInContext('versionEditorState.connections.length', sandbox) === connCount - 1
    && elements.view.innerHTML.includes('还没有去向');
  if (!afterDeleteOk) failed += 1;
  console.log(`${afterDeleteOk ? 'PASS' : 'FAIL'}  删除普通连线后来源节点提示"还没有去向"`);

  vm.runInContext(`versionEditorState.connections = JSON.parse(${JSON.stringify(connSnapshot)});`, sandbox);
  vm.runInContext('route()', sandbox);
  await waitRendered();

  // 回归：流程还没有表单字段时，条件无从选起，要给出解释和入口而不是一句"不能为空"
  const savedSchema = vm.runInContext('JSON.stringify(versionEditorState.formSchema)', sandbox);
  vm.runInContext('versionEditorState.formSchema = {};', sandbox);
  vm.runInContext('route()', sandbox);
  await waitRendered();
  sandbox.arguments0 = { dataset: { id: BRANCH_NODE }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-branch'](arguments0)`, sandbox);
  await sleep(120);
  const emptyForm = elements['overlay-host'].innerHTML;
  const emptyOk = emptyForm.includes('还没有定义表单字段')
    && emptyForm.includes('去配置表单字段')
    && !emptyForm.includes('name="field"');
  if (!emptyOk) failed += 1;
  console.log(`${emptyOk ? 'PASS' : 'FAIL'}  没有表单字段时给出解释和入口，而不是空下拉`);
  vm.runInContext(`dialogActions['close-dialog']()`, sandbox);
  vm.runInContext(`versionEditorState.formSchema = JSON.parse(${JSON.stringify(savedSchema)});`, sandbox);

  // 开始节点的配置弹窗：不该出现裸 JSON 输入框，应该把人引到审批表单
  sandbox.location.hash = '#/versions/41000000-0000-4000-8000-000000000003';
  vm.runInContext('route()', sandbox);
  await waitRendered();
  sandbox.arguments0 = { dataset: { id: '50000000-0000-4000-8000-000000000001' }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-node'](arguments0)`, sandbox);
  await sleep(120);
  const startDialog = elements['overlay-host'].innerHTML;
  const startOk = startDialog.includes('去配置表单字段')
    && startDialog.includes('审批表单')
    && !startDialog.includes('节点配置')
    && !startDialog.includes('textarea');
  if (!startOk) failed += 1;
  console.log(`${startOk ? 'PASS' : 'FAIL'}  开始节点弹窗引导到审批表单而不是裸 JSON`);
  vm.runInContext(`dialogActions['close-dialog']()`, sandbox);

  // 结束节点没有配置项：弹窗只解释语义，不问结束状态
  const endNodeId = vm.runInContext(
    `(() => { const node = versionEditorState.nodes.find((item) => item.node_type === 'END'); return node ? node.id : null; })()`,
    sandbox
  );
  sandbox.arguments0 = { dataset: { id: endNodeId }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-node'](arguments0)`, sandbox);
  await sleep(120);
  const endDialog = elements['overlay-host'].innerHTML;
  const endDialogOk = endDialog.includes('结束节点没有配置项')
    && endDialog.includes('走到这里就是审批通过')
    && !endDialog.includes('结束状态')
    && !endDialog.includes('name="result_status"');
  if (!endDialogOk) failed += 1;
  console.log(`${endDialogOk ? 'PASS' : 'FAIL'}  结束节点弹窗不要求选结束状态，只说明语义`);
  vm.runInContext(`dialogActions['close-dialog']()`, sandbox);

  // 老草稿里结束节点还带着下线过的 result_status：进编辑器时按定义清理掉，
  // 否则保存会被后端校验拦下，而界面上根本没有地方去删这个字段。
  const prune = vm.runInContext(
    `(() => {
       const definition = { config_schema_json: { properties: { keep: { type: 'string' } } } };
       const result = pruneNodeConfig({ config: { keep: 'A', result_status: 'APPROVED' } }, definition);
       // 包一层计数，确认重载版本编辑器时真的走了清理这一步
       const original = pruneNodeConfig;
       window.__pruneCalls = 0;
       pruneNodeConfig = function (...args) { window.__pruneCalls += 1; return original.apply(null, args); };
       return { config: result.config, dropped: result.dropped };
     })()`,
    sandbox
  );
  vm.runInContext(`versionEditorState = null; route();`, sandbox);
  await waitRendered();
  const pruneCalls = vm.runInContext('window.__pruneCalls', sandbox);
  const pruneOk = prune.config.keep === 'A'
    && prune.config.result_status === undefined
    && JSON.stringify(prune.dropped) === '["result_status"]'
    && pruneCalls > 0;
  if (!pruneOk) failed += 1;
  console.log(`${pruneOk ? 'PASS' : 'FAIL'}  旧草稿里下线的配置项按定义清理（丢 ${JSON.stringify(prune.dropped)}，重载时调用 ${pruneCalls} 次）`);

  // 节点定义：config_schema + ui_schema 与配置项表的互转，以及编辑弹窗的呈现
  const definitionParsed = vm.runInContext(
    `(() => {
       const config = {
         type: 'object',
         required: ['approval_mode', 'approvers'],
         properties: {
           approval_mode: { type: 'string', title: '审批模式', enum: ['AND', 'OR'] },
           approvers: {
             type: 'array', title: '审批人', minItems: 1,
             items: { type: 'object', required: ['person_id'],
                      properties: { person_id: { type: 'string', format: 'uuid' } } },
           },
         },
       };
       const ui = { approval_mode: { 'ui:widget': 'select' }, approvers: { 'ui:widget': 'person-select' } };
       const fields = configFieldsFromSchema(config, ui).fields;
       const back = applyConfigFields(config, ui, fields);
       return {
         types: fields.map((field) => field.key + ':' + field.type + (field.required ? '*' : '')),
         keepsMinItems: back.schema.properties.approvers.minItems === 1,
         keepsWidget: back.uiSchema.approvers['ui:widget'] === 'person-select'
           && back.uiSchema.approval_mode['ui:widget'] === 'select',
         keepsRequired: JSON.stringify(back.schema.required) === JSON.stringify(['approval_mode', 'approvers']),
       };
     })()`,
    sandbox
  );
  const definitionOk = definitionParsed.types.join(',') === 'approval_mode:enum*,approvers:person-select*'
    && definitionParsed.keepsMinItems && definitionParsed.keepsWidget && definitionParsed.keepsRequired;
  if (!definitionOk) failed += 1;
  console.log(`${definitionOk ? 'PASS' : 'FAIL'}  节点配置项解析与回写（${definitionParsed.types.join(' / ')}）`);

  sandbox.location.hash = '#/definitions';
  vm.runInContext('route()', sandbox);
  await waitRendered();
  sandbox.arguments0 = { dataset: { id: '00000000-0000-0000-0000-000000000102' }, value: '', checked: false, closest: () => null };
  vm.runInContext(`actions['edit-definition'](arguments0)`, sandbox);
  await sleep(120);
  const definitionDialog = elements['overlay-host'].innerHTML;
  const dialogOk = definitionDialog.includes('配置键')
    && (definitionDialog.match(/data-prop="key"/g) || []).length === 2
    && definitionDialog.includes('人员选择器')
    && !definitionDialog.includes('id="def-schema"');
  if (!dialogOk) failed += 1;
  console.log(`${dialogOk ? 'PASS' : 'FAIL'}  编辑节点定义弹窗渲染成配置项表而非 JSON`);

  vm.runInContext(`dialogActions['cfg-mode']()`, sandbox);
  await sleep(60);
  const advancedHost = elements['cfg-host'] ? elements['cfg-host'].innerHTML : '';
  vm.runInContext(`document.getElementById('def-schema').value = '{}'; document.getElementById('def-ui').value = '{}'`, sandbox);
  vm.runInContext(`dialogActions['cfg-mode']()`, sandbox);
  await sleep(60);
  const backHost = elements['cfg-host'] ? elements['cfg-host'].innerHTML : '';
  const modeOk = advancedHost.includes('id="def-schema"') && !advancedHost.includes('data-prop="key"')
    && backHost.includes('cfg-field-add') && !backHost.includes('id="def-schema"');
  if (!modeOk) failed += 1;
  console.log(`${modeOk ? 'PASS' : 'FAIL'}  节点定义的字段模式与高级模式来回切换`);
  vm.runInContext('dialogActions["close-dialog"]()', sandbox);

  // 拖拽预览的组成：默认配置、卡片摘要、边框配色三者要和落地后的节点一致
  const ghost = vm.runInContext(
    `(() => {
       const definition = { id: 'd1', node_type: 'APPROVAL', name: '人工审批', config_schema_json: {
         type: 'object', required: ['approval_mode', 'approvers'],
         properties: { approval_mode: { type: 'string', enum: ['AND', 'OR'] },
                       approvers: { type: 'array', items: { type: 'object', required: ['person_id'] } } } } };
       const config = defaultConfigFor(definition);
       const preview = { node_type: definition.node_type, config };
       // 结束节点没有配置项：不管 config 里有什么，卡片形态都是"流程完成"
       return { config, summary: nodeConfigSummary(preview), variant: flowNodeVariant(preview),
                endVariant: flowNodeVariant({ node_type: 'END', config: { result_status: 'REJECTED' } }),
                endSummary: nodeConfigSummary({ node_type: 'END', config: {} }) };
     })()`,
    sandbox
  );
  const ghostOk = ghost.config.approval_mode === 'AND'
    && Array.isArray(ghost.config.approvers)
    && ghost.summary === '全部同意 · 0 位审批人'
    && ghost.variant === 'APPROVAL'
    && ghost.endVariant === 'END-APPROVED'
    && ghost.endSummary === '流程完成';
  if (!ghostOk) failed += 1;
  console.log(`${ghostOk ? 'PASS' : 'FAIL'}  拖拽预览与落地配置一致（${JSON.stringify(ghost)}）`);

  // 回归：拖拽/点击新增节点会先触发页面重渲染再打开弹窗，
  // 重渲染不能把弹窗的处理函数一起冲掉，否则按钮全部失灵。
  sandbox.location.hash = '#/versions/41000000-0000-4000-8000-000000000003';
  vm.runInContext('route()', sandbox);
  await waitRendered();
  sandbox.arguments0 = { dataset: { definitionId: '00000000-0000-0000-0000-000000000102' }, value: '', checked: false, tagName: 'DIV' };
  vm.runInContext(`actions['palette-add'](arguments0)`, sandbox);
  await sleep(80);
  const openedAfterAdd = elements['overlay-host'].innerHTML.includes('dialog');
  vm.runInContext('route()', sandbox); // 模拟异步重渲染落地
  await sleep(200);
  // 用和点击处理完全相同的解析顺序判断按钮是否还能找到处理函数
  const dialogAlive = vm.runInContext(
    `[GLOBAL_ACTIONS, dialogActions, actions].some((map) =>
       typeof map['close-dialog'] === 'function' && typeof map['dialog-submit'] === 'function')`,
    sandbox
  );
  if (!openedAfterAdd || !dialogAlive) failed += 1;
  console.log(`${openedAfterAdd && dialogAlive ? 'PASS' : 'FAIL'}  重渲染后弹窗按钮仍然可用（打开=${openedAfterAdd} 可用=${dialogAlive}）`);

  vm.runInContext(`dialogActions['close-dialog']()`, sandbox);
  const closed = elements['overlay-host'].innerHTML === '';
  if (!closed) failed += 1;
  console.log(`${closed ? 'PASS' : 'FAIL'}  取消能关闭弹窗`);

  // 弹窗：表单 / 节点 / 连线 / 校验结果
  const dialogChecks = [
    ['formDialog', `formDialog({title:'测试表单',fields:[{name:'a',label:'甲',type:'text',required:true},{name:'b',label:'乙',type:'code'}],values:{},onSubmit:async()=>{}})`],
    ['confirmDialog', `confirmDialog({title:'确认',message:'内容',submitText:'确定'})`],
    ['showIssues', `showIssues('校验未通过',[{code:'RULE_APPROVER_REQUIRED',message:'审批节点必须配置审批人',node_id:null,field:'config.approvers',connection_index:null}])`],
  ];
  for (const [name, code] of dialogChecks) {
    try {
      vm.runInContext(code, sandbox);
      console.log(`PASS  ${name}`);
    } catch (err) {
      failed += 1;
      console.log(`FAIL  ${name}: ${err.message}`);
    }
  }

  console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
  process.exit(failed ? 1 : 0);
})();
