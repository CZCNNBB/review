/* ==========================================================================
   审批中心配置台 · 前端逻辑
   纯静态实现：不依赖构建工具，直接调用后端 /api 接口。
   接口约定：统一返回 { code, msg, data }，HTTP 错误返回 { detail }。
   ========================================================================== */

/* --------------------------------------------------------------------------
   1. 配置：接口地址与两个密钥都保存在本机浏览器
   -------------------------------------------------------------------------- */

const CONFIG_KEY = 'approval-console.config';

const config = Object.assign(
  { base: 'http://127.0.0.1:8090', adminKey: '', apiKey: '' },
  JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}')
);

function saveConfig() {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}

const railCounts = {};
let actions = {};
/* 弹窗的处理函数和页面分开存：弹窗打开期间页面可能重新渲染，而重渲染会整体替换
   actions，如果共用一份，弹窗的按钮就会在重新渲染后集体失灵。 */
let dialogActions = {};
let peopleTab = 'persons';

/* --------------------------------------------------------------------------
   2. 基础工具
   -------------------------------------------------------------------------- */

const view = document.getElementById('view');

function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function uuid4() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function fmtTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms} 毫秒`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} 秒`;
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return `${minutes} 分 ${Math.round((ms % 60000) / 1000)} 秒`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function shortId(value) {
  if (!value) return '—';
  return String(value).slice(0, 8);
}

function parseJsonInput(text, label) {
  const trimmed = (text || '').trim();
  if (!trimmed) return {};
  try {
    return JSON.parse(trimmed);
  } catch (err) {
    throw new Error(`${label} 不是合法的 JSON：${err.message}`);
  }
}

function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    return String(value);
  }
}

/* --------------------------------------------------------------------------
   3. 接口请求层
   -------------------------------------------------------------------------- */

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function detailMessage(payload, status) {
  const detail = payload && payload.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => `${(item.loc || []).join('.')}：${item.msg}`)
      .join('；');
  }
  if (detail && typeof detail === 'object') {
    let message = detail.message || '请求未通过校验';
    if (Array.isArray(detail.issues) && detail.issues.length) {
      const parts = detail.issues.map((issue) =>
        issue.field ? `${issue.message}（${issue.field}）` : issue.message
      );
      message += `：${parts.join('；')}`;
    }
    return message;
  }
  if (status === 401) return '认证失败，请检查密钥是否正确';
  if (status === 403) return '当前身份没有访问该资源的权限';
  if (status === 404) return '目标资源不存在';
  if (status === 503) return '服务端配置不完整，接口暂不可用';
  return `请求失败（HTTP ${status}）`;
}

async function request(path, options = {}) {
  const { method = 'GET', body, auth = 'admin', key } = options;
  const headers = {};
  // 示例数据模式不校验密钥，方便在没有后端时直接浏览界面。
  if (auth === 'admin') {
    if (config.adminKey) headers['X-Admin-Key'] = config.adminKey;
    else if (!demoOn()) throw new ApiError('请先在顶部填写管理密钥（X-Admin-Key）', 0);
  }
  if (auth === 'apikey') {
    // 租户密钥由管理台自动借用，key 参数允许单个请求临时指定。
    const tenantKey = key || config.apiKey;
    if (tenantKey) headers['X-API-Key'] = tenantKey;
    else if (!demoOn()) throw new ApiError('没有找到可用的租户 API Key，请先在租户页面签发一个', 0);
  }
  if (body !== undefined && body !== null) headers['Content-Type'] = 'application/json';

  let response;
  try {
    response = await fetch(config.base.replace(/\/+$/, '') + path, {
      method,
      headers,
      body: body === undefined || body === null ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError(`无法连接 ${config.base}，请确认后端已启动`, 0);
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (err) {
      payload = text;
    }
  }

  if (!response.ok) throw new ApiError(detailMessage(payload, response.status), response.status);
  if (payload && typeof payload === 'object' && 'code' in payload) {
    if (payload.code !== 0) throw new ApiError(payload.msg || '接口返回失败', response.status);
    return payload.data;
  }
  return payload;
}

const api = {
  get: (path, auth = 'admin', key) => request(path, { auth, key }),
  post: (path, body, auth = 'admin', key) => request(path, { method: 'POST', body, auth, key }),
  patch: (path, body, auth = 'admin') => request(path, { method: 'PATCH', body, auth }),
  put: (path, body, auth = 'admin') => request(path, { method: 'PUT', body, auth }),
};

/* 页面局部失败不应阻塞整页渲染，用于概览这类聚合页。 */
async function safe(promise, fallback) {
  try {
    return await promise;
  } catch (err) {
    return fallback;
  }
}

/* --------------------------------------------------------------------------
   管理台自动借用租户密钥

   审批详情、时间线、待办任务和发起审批在租户模式下都要求 X-API-Key。管理台按
   “审批使用记录 → 租户 → 该租户的有效 API Key” 自动解析，管理员只需要一个管理
   密钥就能看到全部数据。解析结果按会话缓存，发起新审批后失效重取。
   -------------------------------------------------------------------------- */

const tenantCache = { tenants: null, apiKeys: {}, usage: {} };

function invalidateTenantCache() {
  tenantCache.tenants = null;
  tenantCache.apiKeys = {};
  tenantCache.usage = {};
}

async function loadTenantList() {
  if (!tenantCache.tenants) tenantCache.tenants = await api.get('/api/admin/tenants?limit=200');
  return tenantCache.tenants;
}

async function tenantApiKeys(tenantId) {
  if (!tenantCache.apiKeys[tenantId]) {
    tenantCache.apiKeys[tenantId] = await safe(api.get(`/api/admin/tenants/${tenantId}/api-keys`), []);
  }
  return tenantCache.apiKeys[tenantId];
}

async function tenantApiKey(tenantId) {
  const keys = await tenantApiKeys(tenantId);
  const usable = keys.find((item) => item.status === 'ENABLED');
  return usable ? usable.api_key : null;
}

/* 使用记录是管理台判断“这张审批单属于哪个租户”的唯一依据。 */
async function tenantUsageRecords(tenantId) {
  if (!tenantCache.usage[tenantId]) {
    tenantCache.usage[tenantId] = await safe(
      api.get(`/api/admin/tenants/${tenantId}/process-usage-records?limit=500`),
      []
    );
  }
  return tenantCache.usage[tenantId];
}

async function tenantOfInstance(instanceId) {
  const tenants = await loadTenantList();
  for (const tenant of tenants) {
    const records = await tenantUsageRecords(tenant.id);
    if (records.some((record) => record.approval_instance_id === instanceId)) return tenant;
  }
  return null;
}

/* 返回某个审批实例对应的租户和可借用密钥，用于查询详情和代办操作。 */
async function credentialsForInstance(instanceId) {
  const tenant = await tenantOfInstance(instanceId);
  if (!tenant) return { tenant: null, key: null };
  return { tenant, key: await tenantApiKey(tenant.id) };
}

/* --------------------------------------------------------------------------
   4. 通用展示组件
   -------------------------------------------------------------------------- */

const STATUS_TEXT = {
  ENABLED: '启用', DISABLED: '停用', DRAFT: '草稿', PUBLISHED: '已发布',
  RUNNING: '审批中', APPROVED: '已通过', REJECTED: '已拒绝', CANCELLED: '已取消',
  ERROR: '异常', PENDING: '待办', ACTIVE: '进行中', COMPLETED: '已完成',
  SUCCEEDED: '成功', FAILED: '失败',
};

const TAG_ON = ['ENABLED', 'APPROVED', 'PUBLISHED', 'SUCCEEDED', 'COMPLETED'];
const TAG_OFF = ['DISABLED', 'REJECTED', 'FAILED', 'ERROR', 'CANCELLED'];
const TAG_WAIT = ['PENDING', 'DRAFT'];

function tag(status, text) {
  const cls = TAG_ON.includes(status) ? 'on' : TAG_OFF.includes(status) ? 'off' : TAG_WAIT.includes(status) ? 'wait' : 'work';
  return `<span class="tag tag--${cls}">${esc(text || STATUS_TEXT[status] || status || '—')}</span>`;
}

function stamp(status) {
  const cls = status === 'APPROVED' ? 'approved' : status === 'REJECTED' ? 'rejected' : status === 'RUNNING' ? 'running' : 'idle';
  return `<span class="stamp stamp--lg stamp--${cls}">${esc(STATUS_TEXT[status] || status || '未知')}</span>`;
}

function tableHtml(columns, rows, empty) {
  if (!rows.length) {
    return `<div class="empty"><div class="empty__title">${esc(empty.title)}</div><div>${esc(empty.hint || '')}</div></div>`;
  }
  const head = columns.map((col) => `<th class="${col.cls || ''}">${esc(col.title)}</th>`).join('');
  const body = rows
    .map((row) => {
      const cells = columns
        .map((col) => `<td class="${col.cls || ''}">${col.render(row)}</td>`)
        .join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function kvHtml(pairs) {
  const rows = pairs
    .filter((pair) => pair)
    .map(([key, value]) => `<div class="kv__key">${esc(key)}</div><div class="kv__val">${value}</div>`)
    .join('');
  return `<div class="kv">${rows}</div>`;
}

function pageHead(title, note, actionsHtml) {
  return `<div class="page-head">
    <div>
      <h1 class="page-head__title">${esc(title)}</h1>
      ${note ? `<div class="page-head__note">${note}</div>` : ''}
    </div>
    <div class="page-head__actions">${actionsHtml || ''}</div>
  </div>`;
}

function breadcrumb(items) {
  return `<div class="breadcrumb">${items
    .map((item, index) =>
      index === items.length - 1 || !item.href
        ? `<span>${esc(item.text)}</span>`
        : `<span><a href="${esc(item.href)}">${esc(item.text)}</a></span>`
    )
    .join('')}</div>`;
}

function errorPanel(err) {
  return `<div class="panel"><div class="panel__body">
    <div class="note note--wait"><strong>读取失败：</strong>${esc(err.message)}</div>
    <p style="font-size:13px;color:var(--ink-2)">确认后端已启动（默认 http://127.0.0.1:8090）、管理密钥正确，然后刷新页面重试。</p>
    <p style="font-size:13px;color:var(--ink-2)">只是先看界面的话，可以切到示例数据模式，用一组固定的假数据浏览全部页面。</p>
    <button class="btn btn--sm" data-act="demo-on">用示例数据预览</button>
  </div></div>`;
}

/* --------------------------------------------------------------------------
   示例数据模式（可选）：用于在没有后端的环境里预览界面
   -------------------------------------------------------------------------- */

function demoOn() {
  return Boolean(window.ApprovalDemo && window.ApprovalDemo.isOn());
}

function syncDemoBanner() {
  const banner = document.getElementById('demo-banner');
  if (banner) banner.hidden = !demoOn();
}

function enableDemo() {
  const start = () => {
    window.ApprovalDemo.enable();
    syncDemoBanner();
    toast('已切换到示例数据模式，写操作不会真正保存', 'ok');
    route();
  };
  if (window.ApprovalDemo) {
    start();
    return;
  }
  const script = document.createElement('script');
  script.src = 'demo.js';
  script.onload = start;
  script.onerror = () => toast('无法加载 demo.js，请确认文件与 index.html 在同一目录', 'err');
  document.head.appendChild(script);
}

/* --------------------------------------------------------------------------
   5. 提示与弹窗
   -------------------------------------------------------------------------- */

function toast(message, kind) {
  const host = document.getElementById('toast-host');
  const node = document.createElement('div');
  node.className = `toast${kind ? ` toast--${kind}` : ''}`;
  node.textContent = message;
  host.appendChild(node);
  setTimeout(() => node.remove(), kind === 'err' ? 6000 : 3200);
}

function closeOverlay() {
  document.getElementById('overlay-host').innerHTML = '';
  dialogActions = {};
  document.removeEventListener('keydown', onOverlayKey);
}

function setDialogActions(map) {
  dialogActions = map || {};
}

function onOverlayKey(event) {
  if (event.key === 'Escape') closeOverlay();
}

function openOverlay(html, wide) {
  const host = document.getElementById('overlay-host');
  host.innerHTML = `<div class="overlay"><div class="dialog${wide ? ' dialog--wide' : ''}">${html}</div></div>`;
  dialogActions = {};
  document.addEventListener('keydown', onOverlayKey);
  host.querySelector('.overlay').addEventListener('mousedown', (event) => {
    if (event.target.classList.contains('overlay')) closeOverlay();
  });
  const first = host.querySelector('input, select, textarea');
  if (first) first.focus();
}

function dialogShell(title, bodyHtml, footHtml) {
  return `<div class="dialog__head">
      <h3 class="dialog__title">${esc(title)}</h3>
      <button class="dialog__close" data-act="close-dialog" aria-label="关闭">×</button>
    </div>
    <div class="dialog__body">${bodyHtml}</div>
    <div class="dialog__foot">${footHtml}</div>`;
}

function confirmDialog(options) {
  return new Promise((resolve) => {
    openOverlay(
      dialogShell(
        options.title,
        `<p style="margin:0;font-size:13.5px;color:var(--ink-2)">${esc(options.message)}</p>`,
        `<button class="btn" data-act="confirm-no">取消</button>
         <button class="btn ${options.danger ? 'btn--danger' : 'btn--primary'}" data-act="confirm-yes">${esc(options.submitText || '确定')}</button>`
      )
    );
    setDialogActions({
      'close-dialog': () => { closeOverlay(); resolve(false); },
      'confirm-no': () => { closeOverlay(); resolve(false); },
      'confirm-yes': () => { closeOverlay(); resolve(true); },
    });
  });
}

/* 通用表单弹窗。fields 支持 text / number / select / multiselect / textarea / code / checkbox。
   字段可以带 when(values) 条件，只在满足时出现。 */
function formDialog(options) {
  const values = Object.assign({}, options.values);

  function currentFields() {
    return options.fields.filter((field) => !field.when || field.when(values));
  }

  function renderField(field) {
    if (field.type === 'note') {
      return `<div class="note" style="grid-column:1/-1">${field.html || ''}</div>`;
    }
    const value = values[field.name];
    let control;
    if (field.type === 'select') {
      control = `<select class="select" name="${field.name}">${(field.options || [])
        .map((option) => `<option value="${esc(option.value)}"${String(option.value) === String(value) ? ' selected' : ''}>${esc(option.label)}</option>`)
        .join('')}</select>`;
    } else if (field.type === 'multiselect') {
      const picked = new Set((value || []).map(String));
      control = `<select class="select select--multi" name="${field.name}" multiple>${(field.options || [])
        .map((option) => `<option value="${esc(option.value)}"${picked.has(String(option.value)) ? ' selected' : ''}>${esc(option.label)}</option>`)
        .join('')}</select>`;
    } else if (field.type === 'textarea' || field.type === 'code') {
      control = `<textarea class="textarea${field.type === 'code' ? ' textarea--code' : ''}" name="${field.name}" placeholder="${esc(field.placeholder || '')}">${esc(value === undefined || value === null ? '' : value)}</textarea>`;
    } else if (field.type === 'checkbox') {
      control = `<label class="checkline"><input type="checkbox" name="${field.name}"${value ? ' checked' : ''}> ${esc(field.checkboxLabel || '')}</label>`;
    } else {
      control = `<input class="input" type="${field.type === 'number' ? 'number' : field.type === 'password' ? 'password' : 'text'}" name="${field.name}" value="${esc(value === undefined || value === null ? '' : value)}" placeholder="${esc(field.placeholder || '')}">`;
    }
    const hint = field.hint ? `<div class="field__hint">${esc(field.hint)}</div>` : '';
    return `<div class="field"${field.wide ? ' style="grid-column:1/-1"' : ''}>
      <label class="field__label" for="f-${field.name}">${esc(field.label)}</label>${control}${hint}
    </div>`;
  }

  function renderBody() {
    return `<div class="form__row--split">${currentFields().map(renderField).join('')}</div>`;
  }

  const extraButtons = (options.extraActions || [])
    .map((extra, index) => `<button class="btn${extra.danger ? ' btn--danger' : ''}" data-act="dialog-extra-${index}">${esc(extra.label)}</button>`)
    .join('');

  openOverlay(
    dialogShell(
      options.title,
      `<form class="form" id="dialog-form">${renderBody()}<div id="dialog-error"></div></form>`,
      `${extraButtons}
       <button class="btn" data-act="close-dialog">取消</button>
       <button class="btn btn--primary" data-act="dialog-submit">${esc(options.submitText || '保存')}</button>`
    ),
    options.wide
  );

  const form = document.querySelector('#dialog-form');

  /* 把表单上当前的取值读回 values，联动和提交都用它。 */
  function collect() {
    for (const field of currentFields()) {
      const input = form.elements[field.name];
      if (!input) continue;
      if (field.type === 'checkbox') values[field.name] = input.checked;
      else if (field.type === 'multiselect') values[field.name] = Array.from(input.selectedOptions).map((option) => option.value);
      else if (field.type === 'number') values[field.name] = input.value === '' ? null : Number(input.value);
      else values[field.name] = input.value.trim();
    }
  }

  async function submit() {
    collect();
    const result = {};
    for (const field of currentFields()) {
      result[field.name] = values[field.name];
      if (field.required && (result[field.name] === '' || result[field.name] === null || result[field.name] === undefined)) {
        document.getElementById('dialog-error').innerHTML = `<div class="note note--wait">${esc(field.label)}不能为空</div>`;
        return;
      }
    }
    try {
      await options.onSubmit(result, values);
      closeOverlay();
    } catch (err) {
      document.getElementById('dialog-error').innerHTML = `<div class="note note--wait">${esc(err.message)}</div>`;
    }
  }

  const extraHandlers = {};
  (options.extraActions || []).forEach((extra, index) => {
    extraHandlers[`dialog-extra-${index}`] = async () => {
      try {
        await extra.onClick(values);
        closeOverlay();
      } catch (err) {
        document.getElementById('dialog-error').innerHTML = `<div class="note note--wait">${esc(err.message)}</div>`;
      }
    };
  });

  setDialogActions(Object.assign({}, extraHandlers, {
    'close-dialog': closeOverlay,
    'dialog-submit': submit,
  }));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    submit();
  });
}

/* --------------------------------------------------------------------------
   6. 复制到剪贴板
   -------------------------------------------------------------------------- */

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制到剪贴板', 'ok');
  } catch (err) {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
      toast('已复制到剪贴板', 'ok');
    } catch (inner) {
      toast('复制失败，请手动选中复制', 'err');
    }
    area.remove();
  }
}

function copyButton(text, label) {
  return `<button class="btn--link btn--sm" data-act="copy" data-copy="${esc(text)}">${esc(label || '复制')}</button>`;
}

/* --------------------------------------------------------------------------
   7. 页面渲染入口
   -------------------------------------------------------------------------- */

/* 每次渲染领一个序号。异步渲染可能乱序返回，只有最后一次发起的渲染允许写入页面，
   否则快速切换页面时旧页面的结果会覆盖新页面，动作表也会跟着错位。 */
let renderGeneration = 0;
let pendingActions = null;

async function paint(builder) {
  const generation = ++renderGeneration;
  const slot = { value: null };
  const previousSlot = pendingActions;
  pendingActions = slot;

  view.innerHTML = '<div class="loading">正在读取数据…</div>';
  let html;
  let mount = null;
  try {
    const result = await builder();
    // 需要操作真实 DOM 的页面（例如拖拽画布）返回 { html, mount }，其余直接返回 HTML。
    if (result && typeof result === 'object') {
      html = result.html;
      mount = result.mount || null;
    } else {
      html = result;
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && err.message.includes('管理密钥')) {
      html = `<div class="panel"><div class="panel__body">
        <div class="note note--wait">请先在页面顶部填写管理密钥（X-Admin-Key），然后点击“测试连接”。</div>
      </div></div>`;
    } else {
      html = errorPanel(err);
    }
  } finally {
    pendingActions = previousSlot;
  }

  if (generation !== renderGeneration) return;

  actions = slot.value || actions;
  view.innerHTML = html;
  syncRail();
  if (mount) mount();
}

/* 页面在渲染过程中登记本页的按钮处理函数，由 paint 在确定写入页面时一起生效。 */
function setActions(map) {
  if (pendingActions) pendingActions.value = map || {};
  else actions = map || {};
}

/* --------------------------------------------------------------------------
   8. 概览：闭环进度 + 运行概况
   -------------------------------------------------------------------------- */

const CLOSED_LOOP_STEPS = [
  { name: '创建租户并配置接入凭据', desc: '业务系统接入审批中心的第一步，回调地址决定审批通过后请求发往哪里。', href: '#/tenants', key: 'tenants' },
  { name: '维护人员与部门', desc: '审批人、发起人都来自全局人员，审批流配置时需要选择具体人员。', href: '#/people', key: 'persons' },
  { name: '创建并发布审批流', desc: '编辑节点、审批人与分支条件，发布后才能被业务系统发起。', href: '#/processes', key: 'published' },
  { name: '配置业务动作', desc: '审批通过后要调用的业务接口，包含相对路径、参数规则和超时。', href: '#/actions', key: 'actions' },
  { name: '授权租户使用流程与动作', desc: '租户只有被授权后才能用对应流程发起审批、触发对应业务动作。', href: '#/grants', key: 'grants' },
  { name: '发起审批', desc: '业务系统用 API Key 调用发起接口，审批中心按当前发布版本创建实例。', href: '#/start', key: null },
  { name: '处理待办任务', desc: '审批人查看审批单与时间线，同意或拒绝，引擎按 AND / OR 规则推进。', href: '#/tasks', key: null },
  { name: '核对业务执行结果', desc: '审批通过后由后台 Worker 调用业务系统，执行记录保存入参、响应和失败原因。', href: '#/executions', key: 'executions' },
];

async function renderOverview() {
  await paint(async () => {
    const [tenants, persons, processes, businessActions, executions] = await Promise.all([
      safe(loadTenantList(), []),
      safe(api.get('/api/admin/persons?limit=200'), []),
      safe(api.get('/api/admin/processes?limit=200'), []),
      safe(api.get('/api/admin/business-actions?limit=200'), []),
      safe(api.get('/api/admin/execution-records?limit=200'), []),
    ]);

    // 审批运行总览：把各租户的使用记录合并起来看全局。
    const usageGroups = await Promise.all(tenants.map((tenant) => tenantUsageRecords(tenant.id)));
    const usages = usageGroups
      .flatMap((list, index) => list.map((record) => Object.assign({}, record, { tenant_name: tenants[index].name })))
      .sort((left, right) => new Date(right.created_at) - new Date(left.created_at));
    const countByStatus = (status) => usages.filter((item) => item.approval_status === status).length;

    const published = processes.filter((item) => item.current_version_id).length;

    Object.assign(railCounts, {
      tenants: tenants.length,
      persons: persons.length,
      processes: processes.length,
      actions: businessActions.length,
      executions: executions.length,
    });

    const grants = null; // 授权是租户维度数据，进入租户页面后按需加载。
    const counts = {
      tenants: tenants.length,
      persons: persons.length,
      published,
      actions: businessActions.length,
      grants,
      executions: executions.length,
    };

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
    });

    const steps = CLOSED_LOOP_STEPS.map((step, index) => {
      const count = step.key ? counts[step.key] : null;
      const done = count !== null && count > 0;
      const countText = count === null ? '' : count > 0 ? `${count} 项` : '未开始';
      return `<div class="step">
        <div class="step__no">${String(index + 1).padStart(2, '0')}</div>
        <div>
          <div class="step__name">${esc(step.name)}</div>
          <div class="step__desc">${esc(step.desc)}</div>
        </div>
        <div class="step__side">
          ${count === null ? '' : done ? tag('ENABLED', countText) : tag('DRAFT', countText)}
          <a class="btn btn--sm" href="${step.href}">进入</a>
        </div>
      </div>`;
    }).join('');

    const succeeded = executions.filter((item) => item.status === 'SUCCEEDED').length;
    const failed = executions.filter((item) => item.status === 'FAILED').length;
    const waiting = executions.filter((item) => item.status === 'PENDING' || item.status === 'RUNNING').length;
    const failedRows = executions.filter((item) => item.status === 'FAILED').slice(0, 5);

    return `${pageHead(
      '闭环进度',
      '按业务闭环的顺序排列。每一项都可以直接进入对应页面处理；计数来自当前接口返回的数据。',
      `<a class="btn" href="#/start">发起审批</a><a class="btn btn--primary" href="#/tasks">处理待办</a>`
    )}
    <div class="panel"><div class="panel__head"><h2 class="panel__title">先把这条链路走通</h2>
      <span class="panel__note">只有整条链路在同一环境跑通，当前阶段才算闭环</span></div>
      <div class="steps">${steps}</div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">审批运行总览</h2>
        <a class="btn btn--sm" href="#/usages">查看全部使用记录</a></div>
      <div class="panel__body">
        ${kvHtml([
          ['审批总数', `<span class="code">${usages.length}</span>`],
          ['审批中', `<span class="code" style="color:var(--indigo)">${countByStatus('RUNNING')}</span>`],
          ['已通过', `<span class="code" style="color:var(--pine)">${countByStatus('APPROVED')}</span>`],
          ['已拒绝', `<span class="code" style="color:var(--cinnabar)">${countByStatus('REJECTED')}</span>`],
        ])}
      </div>
      ${tableHtml(
        [
          { title: '发起时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          { title: '租户', render: (row) => esc(row.tenant_name) },
          { title: '审批单', render: (row) => `<a class="cell-title" href="#/instances/${esc(row.approval_instance_id)}">${esc(row.approval_title || '—')}</a>` },
          { title: '业务单号', render: (row) => `<span class="code">${esc(row.business_key)}</span>` },
          { title: '状态', render: (row) => tag(row.approval_status || 'ERROR') },
          { title: '当前节点', render: (row) => esc(row.current_node_name || '—') },
        ],
        usages.slice(0, 5),
        { title: '还没有审批记录', hint: '业务系统发起审批后，这里会显示最近的处理情况。' }
      )}
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">业务执行概况</h2>
        <a class="btn btn--sm" href="#/executions">查看全部执行记录</a></div>
      <div class="panel__body">
        ${kvHtml([
          ['执行记录总数', `<span class="code">${executions.length}</span>`],
          ['调用成功', `<span class="code">${succeeded}</span>`],
          ['调用失败', failed ? `<span class="code" style="color:var(--cinnabar)">${failed}</span>` : '<span class="code">0</span>'],
          ['等待执行', `<span class="code">${waiting}</span>`],
        ])}
      </div>
      ${failedRows.length
        ? `<div class="panel__head" style="border-top:1px solid var(--rule-weak)"><h3 class="panel__title">最近失败的调用</h3>
             <span class="panel__note">第一版不自动重试，需要人工核对后处理</span></div>
           ${tableHtml(
             [
               { title: '业务动作', render: (row) => `<span class="code">${esc(row.action_code)}</span>` },
               { title: '失败原因', render: (row) => `<span style="color:var(--cinnabar)">${esc((row.error_message || '').slice(0, 80))}</span>` },
               { title: '时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
               { title: '操作', cls: 'is-actions', render: (row) => `<a class="btn--link btn--sm" href="#/executions/${esc(row.id)}">查看</a>` },
             ],
             failedRows,
             { title: '暂无失败调用' }
           )}`
        : ''}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   9. 租户管理
   -------------------------------------------------------------------------- */

const TENANT_FIELDS = [
  { name: 'code', label: '租户编码', type: 'text', required: true, placeholder: 'PAYMENT', hint: '大写字母开头，只能包含字母、数字和下划线，创建后不可修改' },
  { name: 'name', label: '租户名称', type: 'text', required: true, placeholder: '付款系统' },
  { name: 'callback_base_url', label: '回调基础地址', type: 'text', required: true, placeholder: 'https://payment.example.com', hint: '业务系统站点根地址，不能带查询参数；审批通过后与业务动作相对路径拼接' },
  { name: 'description', label: '说明', type: 'text', wide: true },
];

async function renderTenants() {
  await paint(async () => {
    const tenants = await api.get('/api/admin/tenants?limit=200');
    railCounts.tenants = tenants.length;

    setActions({
      'new-tenant': () =>
        formDialog({
          title: '新建租户',
          fields: TENANT_FIELDS,
          submitText: '创建租户',
          values: {},
          onSubmit: async (values) => {
            const tenant = await api.post('/api/admin/tenants', {
              code: values.code,
              name: values.name,
              description: values.description || null,
              callback_base_url: values.callback_base_url,
            });
            toast('租户已创建', 'ok');
            location.hash = `#/tenants/${tenant.id}`;
          },
        }),
      'copy': (el) => copyText(el.dataset.copy),
    });

    return `${pageHead(
      '租户',
      '一个租户对应一个接入审批中心的业务系统。API Key 决定业务系统发起审批时的身份，回调凭据决定审批通过后请求业务系统时使用的认证方式。',
      `<button class="btn btn--primary" data-act="new-tenant">新建租户</button>`
    )}
    <div class="panel">
      ${tableHtml(
        [
          { title: '编码', render: (row) => `<span class="cell-title">${esc(row.code)}</span>` },
          { title: '名称', render: (row) => esc(row.name) },
          { title: '回调基础地址', render: (row) => `<span class="code">${esc(row.callback_base_url)}</span>` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '创建时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<a class="btn--link btn--sm" href="#/tenants/${esc(row.id)}">接入凭据</a>
               <button class="btn--link btn--sm" data-act="edit-tenant" data-id="${esc(row.id)}">编辑</button>`,
          },
        ],
        tenants,
        { title: '还没有租户', hint: '创建第一个租户，业务系统才能接入并发起审批。' }
      )}
    </div>`;
  });
}

async function renderTenantDetail(tenantId) {
  await paint(async () => {
    const [tenant, apiKeys, credentials, usages] = await Promise.all([
      api.get(`/api/admin/tenants/${tenantId}`),
      api.get(`/api/admin/tenants/${tenantId}/api-keys`),
      safe(api.get(`/api/admin/tenants/${tenantId}/callback-credentials`), []),
      safe(api.get(`/api/admin/tenants/${tenantId}/process-usage-records?limit=20`), []),
    ]);

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'edit-tenant': () =>
        formDialog({
          title: '编辑租户',
          fields: TENANT_FIELDS.map((field) => (field.name === 'code' ? Object.assign({}, field, { when: () => false }) : field))
            .concat([{ name: 'status', label: '状态', type: 'select', options: [{ value: 'ENABLED', label: '启用' }, { value: 'DISABLED', label: '停用' }], hint: '停用后该租户的 API Key 立即失效' }]),
          values: {
            code: tenant.code,
            name: tenant.name,
            description: tenant.description || '',
            callback_base_url: tenant.callback_base_url,
            status: tenant.status,
          },
          onSubmit: async (values) => {
            await api.patch(`/api/admin/tenants/${tenantId}`, {
              name: values.name,
              description: values.description || null,
              callback_base_url: values.callback_base_url,
              status: values.status,
            });
            toast('租户已更新', 'ok');
            renderTenantDetail(tenantId);
          },
        }),
      'new-key': () =>
        formDialog({
          title: '签发 API Key',
          fields: [
            { name: 'name', label: '用途名称', type: 'text', required: true, placeholder: '付款系统生产环境' },
            { name: 'expires_at', label: '过期时间', type: 'text', placeholder: '留空表示长期有效，例如 2026-12-31T00:00:00Z' },
          ],
          values: {},
          submitText: '签发',
          onSubmit: async (values) => {
            const body = { name: values.name };
            if (values.expires_at) body.expires_at = values.expires_at;
            const created = await api.post(`/api/admin/tenants/${tenantId}/api-keys`, body);
            toast('API Key 已签发，请立即复制', 'ok');
            renderTenantDetail(tenantId);
            copyText(created.api_key);
          },
        }),
      'revoke-key': async (el) => {
        if (!(await confirmDialog({ title: '撤销 API Key', message: '撤销后使用该密钥的业务系统将立即无法发起审批，且不能恢复。确认撤销？', submitText: '撤销', danger: true }))) return;
        await api.post(`/api/admin/tenants/${tenantId}/api-keys/${el.dataset.id}/revoke`);
        toast('API Key 已撤销', 'ok');
        renderTenantDetail(tenantId);
      },
      'new-credential': () =>
        formDialog({
          title: '配置回调 Service Token',
          fields: [
            { name: 'name', label: '用途名称', type: 'text', required: true, placeholder: '审批中心服务账号' },
            { name: 'token', label: 'Service Token', type: 'text', required: true, hint: '由业务系统为自己的服务账号签发，审批中心加密保存且不回显明文' },
            { name: 'header_name', label: '认证请求头', type: 'text', placeholder: 'Authorization' },
            { name: 'token_prefix', label: 'Token 前缀', type: 'text', placeholder: 'Bearer', hint: '留空表示请求头里直接放 Token 明文' },
            { name: 'expires_at', label: '过期时间', type: 'text', placeholder: '留空表示长期有效' },
          ],
          values: { header_name: 'Authorization', token_prefix: 'Bearer' },
          submitText: '保存凭据',
          onSubmit: async (values) => {
            const body = {
              name: values.name,
              token: values.token,
              header_name: values.header_name || 'Authorization',
              token_prefix: values.token_prefix === '' ? '' : values.token_prefix || 'Bearer',
            };
            if (values.expires_at) body.expires_at = values.expires_at;
            await api.post(`/api/admin/tenants/${tenantId}/callback-credentials`, body);
            toast('回调凭据已保存', 'ok');
            renderTenantDetail(tenantId);
          },
        }),
      'revoke-credential': async (el) => {
        if (!(await confirmDialog({ title: '撤销回调凭据', message: '撤销后审批通过时将无法认证到业务系统，对应执行记录会失败。确认撤销？', submitText: '撤销', danger: true }))) return;
        await api.post(`/api/admin/tenants/${tenantId}/callback-credentials/${el.dataset.id}/revoke`);
        toast('回调凭据已撤销', 'ok');
        renderTenantDetail(tenantId);
      },
    });

    return `${breadcrumb([{ text: '租户', href: '#/tenants' }, { text: tenant.name }])}
    ${pageHead(
      tenant.name,
      `租户编码 ${esc(tenant.code)}。密钥和回调凭据属于敏感信息，仅在本页展示。`,
      `<a class="btn" href="#/grants?tenant=${esc(tenant.id)}">资源授权</a>
       <button class="btn" data-act="edit-tenant">编辑租户</button>`
    )}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">基本信息</h2>${tag(tenant.status)}</div>
      <div class="panel__body">
        ${kvHtml([
          ['租户 ID', `<span class="code">${esc(tenant.id)}</span>`],
          ['回调基础地址', `<span class="code">${esc(tenant.callback_base_url)}</span>`],
          ['说明', esc(tenant.description || '—')],
          ['创建时间', esc(fmtTime(tenant.created_at))],
        ])}
      </div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">API Key</h2>
        <button class="btn btn--sm btn--primary" data-act="new-key">签发密钥</button></div>
      ${tableHtml(
        [
          { title: '用途', render: (row) => `<span class="cell-title">${esc(row.name)}</span>` },
          { title: '密钥', render: (row) => `<span class="code">${esc(row.api_key)}</span> ${copyButton(row.api_key)}` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '最近使用', render: (row) => `<span class="muted">${esc(fmtTime(row.last_used_at))}</span>` },
          { title: '过期时间', render: (row) => `<span class="muted">${esc(fmtTime(row.expires_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              row.status === 'ENABLED'
                ? `<button class="btn--link btn--sm is-danger" data-act="revoke-key" data-id="${esc(row.id)}">撤销</button>`
                : `<span class="muted">${esc(fmtTime(row.revoked_at))} 撤销</span>`,
          },
        ],
        apiKeys,
        { title: '还没有 API Key', hint: '签发一个密钥交给业务系统，用于调用发起审批接口。' }
      )}
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">回调 Service Token</h2>
        <button class="btn btn--sm" data-act="new-credential">配置凭据</button></div>
      <div class="panel__body" style="padding-bottom:0">
        <div class="note">审批通过后，审批中心用这里的 Token 以业务系统认可的方式调用回调接口。只返回元数据，不回显明文。</div>
      </div>
      ${tableHtml(
        [
          { title: '用途', render: (row) => `<span class="cell-title">${esc(row.name)}</span>` },
          { title: '认证请求头', render: (row) => `<span class="code">${esc(row.header_name)}${row.token_prefix ? `: ${esc(row.token_prefix)} ***` : ': ***'}</span>` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '过期时间', render: (row) => `<span class="muted">${esc(fmtTime(row.expires_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              row.status === 'ENABLED'
                ? `<button class="btn--link btn--sm is-danger" data-act="revoke-credential" data-id="${esc(row.id)}">撤销</button>`
                : `<span class="muted">已撤销</span>`,
          },
        ],
        credentials,
        { title: '还没有回调凭据', hint: '如果业务动作需要调用业务系统接口，必须在这里配置 Service Token。' }
      )}
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">最近使用记录</h2>
        <a class="btn btn--sm" href="#/usages?tenant=${esc(tenant.id)}">查看全部</a></div>
      ${tableHtml(
        [
          { title: '发起时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          { title: '审批单', render: (row) => esc(row.approval_title || '—') },
          { title: '业务单号', render: (row) => `<span class="code">${esc(row.business_key)}</span>` },
          { title: '业务动作', render: (row) => `<span class="code">${esc(row.action_code || '—')}</span>` },
          { title: '审批状态', render: (row) => tag(row.approval_status || 'ERROR') },
          { title: '当前节点', render: (row) => esc(row.current_node_name || '—') },
          { title: '耗时', render: (row) => `<span class="muted">${esc(fmtMs(row.duration_ms))}</span>` },
          { title: '操作', cls: 'is-actions', render: (row) => `<a class="btn--link btn--sm" href="#/instances/${esc(row.approval_instance_id)}">查看审批</a>` },
        ],
        usages,
        { title: '还没有审批记录', hint: '业务系统使用 API Key 发起审批后，这里会显示记录。' }
      )}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   10. 人员与部门
   -------------------------------------------------------------------------- */

async function renderPeople() {
  await paint(async () => {
    const [persons, departments, tenants] = await Promise.all([
      safe(api.get('/api/admin/persons?limit=200'), []),
      safe(api.get('/api/admin/departments?limit=200'), []),
      safe(api.get('/api/admin/tenants?limit=200'), []),
    ]);
    railCounts.persons = persons.length;

    const personOptions = persons.map((person) => ({ value: person.id, label: `${person.name}（${shortId(person.id)}）` }));

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'tab': (el) => {
        peopleTab = el.dataset.tab;
        renderPeople();
      },
      'new-person': () =>
        formDialog({
          title: '新建人员',
          fields: [
            { name: 'name', label: '姓名', type: 'text', required: true },
            { name: 'mobile', label: '手机号', type: 'text' },
            { name: 'email', label: '邮箱', type: 'text' },
          ],
          values: {},
          onSubmit: async (values) => {
            await api.post('/api/admin/persons', values);
            toast('人员已创建', 'ok');
            renderPeople();
          },
        }),
      'edit-person': (el) => {
        const person = persons.find((item) => item.id === el.dataset.id);
        formDialog({
          title: '编辑人员',
          fields: [
            { name: 'name', label: '姓名', type: 'text', required: true },
            { name: 'mobile', label: '手机号', type: 'text' },
            { name: 'email', label: '邮箱', type: 'text' },
            { name: 'status', label: '状态', type: 'select', options: [{ value: 'ENABLED', label: '启用' }, { value: 'DISABLED', label: '停用' }], hint: '停用后不能再作为新审批流的审批人' },
          ],
          values: { name: person.name, mobile: person.mobile || '', email: person.email || '', status: person.status },
          onSubmit: async (values) => {
            await api.patch(`/api/admin/persons/${person.id}`, values);
            toast('人员已更新', 'ok');
            renderPeople();
          },
        });
      },
      'new-department': () =>
        formDialog({
          title: '新建部门',
          fields: [
            { name: 'code', label: '部门编码', type: 'text', required: true, placeholder: 'FINANCE' },
            { name: 'name', label: '部门名称', type: 'text', required: true, placeholder: '财务部' },
          ],
          values: {},
          onSubmit: async (values) => {
            await api.post('/api/admin/departments', values);
            toast('部门已创建', 'ok');
            renderPeople();
          },
        }),
      'members': async (el) => {
        const departmentId = el.dataset.id;
        const members = await api.get(`/api/admin/departments/${departmentId}/members`);
        const department = departments.find((item) => item.id === departmentId);
        const memberIds = new Set(members.map((item) => item.person_id));
        const available = persons.filter((person) => !memberIds.has(person.id));

        openOverlay(
          dialogShell(
            `${department ? department.name : '部门'} · 成员`,
            `<div class="field"><label class="field__label">添加成员</label>
               <select class="select" id="member-pick">
                 <option value="">选择人员…</option>
                 ${available.map((person) => `<option value="${esc(person.id)}">${esc(person.name)}</option>`).join('')}
               </select>
             </div>
             <div style="margin-top:14px">
               ${members.length
                 ? members.map((member) => `<div class="step" style="padding:10px 0">
                      <div class="step__no">　</div>
                      <div><div class="step__name">${esc(member.person_name)}</div>
                        <div class="step__desc">加入时间 ${esc(fmtTime(member.created_at))}</div></div>
                      <div class="step__side">${tag(member.status)}
                        ${member.status === 'ENABLED' ? `<button class="btn--link btn--sm is-danger" data-act="drop-member" data-person="${esc(member.person_id)}">停用</button>` : ''}
                      </div>
                    </div>`).join('')
                 : '<div class="empty">该部门还没有成员</div>'}
             </div>`,
            `<button class="btn" data-act="close-dialog">关闭</button>
             <button class="btn btn--primary" data-act="add-member">添加</button>`
          )
        );

        setDialogActions({
          'close-dialog': closeOverlay,
          'add-member': async () => {
            const personId = document.getElementById('member-pick').value;
            if (!personId) return;
            await api.post(`/api/admin/departments/${departmentId}/members`, { person_id: personId });
            toast('成员已添加', 'ok');
            closeOverlay();
            renderPeople();
          },
          'drop-member': async (btn) => {
            await api.post(`/api/admin/departments/${departmentId}/members/${btn.dataset.person}/disable`);
            toast('成员关系已停用', 'ok');
            closeOverlay();
            renderPeople();
          },
        });
      },
      'bind-person': (el) => {
        const tenantId = el.dataset.tenant;
        if (!tenantId) {
          toast('请先选择租户', 'err');
          return;
        }
        formDialog({
          title: '绑定租户人员',
          fields: [
            { name: 'person_id', label: '人员', type: 'select', required: true, options: personOptions },
            { name: 'employee_no', label: '工号', type: 'text', hint: '租户内唯一，用于和业务系统的账号对齐' },
            { name: 'external_user_id', label: '外部用户标识', type: 'text', hint: '业务系统里的用户 ID，租户内唯一' },
            { name: 'display_name', label: '租户内显示名', type: 'text' },
          ],
          values: {},
          submitText: '绑定',
          onSubmit: async (values) => {
            await api.post(`/api/admin/tenants/${tenantId}/persons/bind`, {
              person_id: values.person_id,
              employee_no: values.employee_no || null,
              external_user_id: values.external_user_id || null,
              display_name: values.display_name || null,
            });
            toast('绑定成功', 'ok');
            renderPeople();
          },
        });
      },
      'toggle-binding': async (el) => {
        const next = el.dataset.status === 'ENABLED' ? 'DISABLED' : 'ENABLED';
        await api.patch(`/api/admin/tenants/${el.dataset.tenant}/persons/${el.dataset.person}/binding`, { status: next });
        toast(next === 'ENABLED' ? '已启用' : '已停用', 'ok');
        renderPeople();
      },
    });

    const bindTenantId = new URLSearchParams((location.hash.split('?')[1] || '')).get('tenant') || (tenants[0] ? tenants[0].id : '');
    let bindings = [];
    if (peopleTab === 'bindings' && bindTenantId) {
      bindings = await safe(api.get(`/api/admin/tenants/${bindTenantId}/persons`), []);
    }

    const tabs = `<div class="tabs">
      ${[['persons', '人员'], ['departments', '部门'], ['bindings', '租户人员绑定']]
        .map(([key, label]) => `<button class="tab${peopleTab === key ? ' tab--active' : ''}" data-act="tab" data-tab="${key}">${label}</button>`)
        .join('')}
    </div>`;

    let body = '';

    if (peopleTab === 'persons') {
      body = `<div class="panel">
        <div class="panel__head"><h2 class="panel__title">全局人员</h2>
          <button class="btn btn--sm btn--primary" data-act="new-person">新建人员</button></div>
        ${tableHtml(
          [
            { title: '姓名', render: (row) => `<span class="cell-title">${esc(row.name)}</span>` },
            { title: '手机号', render: (row) => esc(row.mobile || '—') },
            { title: '邮箱', render: (row) => esc(row.email || '—') },
            { title: '状态', render: (row) => tag(row.status) },
            { title: '人员 ID', render: (row) => `<span class="code">${esc(row.id)}</span> ${copyButton(row.id, '复制 ID')}` },
            { title: '操作', cls: 'is-actions', render: (row) => `<button class="btn--link btn--sm" data-act="edit-person" data-id="${esc(row.id)}">编辑</button>` },
          ],
          persons,
          { title: '还没有人员', hint: '审批人和发起人都来自这里，先创建人员再配置审批流。' }
        )}
      </div>`;
    }

    if (peopleTab === 'departments') {
      body = `<div class="panel">
        <div class="panel__head"><h2 class="panel__title">部门</h2>
          <button class="btn btn--sm btn--primary" data-act="new-department">新建部门</button></div>
        ${tableHtml(
          [
            { title: '编码', render: (row) => `<span class="cell-title">${esc(row.code)}</span>` },
            { title: '名称', render: (row) => esc(row.name) },
            { title: '状态', render: (row) => tag(row.status) },
            { title: '创建时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
            { title: '操作', cls: 'is-actions', render: (row) => `<button class="btn--link btn--sm" data-act="members" data-id="${esc(row.id)}">成员</button>` },
          ],
          departments,
          { title: '还没有部门', hint: '第一版部门为全局平铺结构，用于按部门查看和核对人员。' }
        )}
      </div>`;
    }

    if (peopleTab === 'bindings') {
      body = `<div class="panel">
        <div class="filters">
          <div class="field"><label class="field__label">租户</label>
            <select class="select" id="binding-tenant">
              ${tenants.map((tenant) => `<option value="${esc(tenant.id)}"${tenant.id === bindTenantId ? ' selected' : ''}>${esc(tenant.name)}</option>`).join('')}
            </select>
          </div>
          <button class="btn btn--sm" data-act="switch-binding-tenant">切换</button>
          <button class="btn btn--sm btn--primary" data-act="bind-person" data-tenant="${esc(bindTenantId)}">绑定人员</button>
        </div>
        ${tableHtml(
          [
            { title: '姓名', render: (row) => `<span class="cell-title">${esc(row.person_name)}</span>` },
            { title: '工号', render: (row) => esc(row.employee_no || '—') },
            { title: '外部用户标识', render: (row) => esc(row.external_user_id || '—') },
            { title: '显示名', render: (row) => esc(row.display_name || '—') },
            { title: '状态', render: (row) => tag(row.status) },
            {
              title: '操作', cls: 'is-actions', render: (row) =>
                `<button class="btn--link btn--sm" data-act="toggle-binding" data-tenant="${esc(bindTenantId)}" data-person="${esc(row.person_id)}" data-status="${esc(row.status)}">${row.status === 'ENABLED' ? '停用' : '启用'}</button>`,
            },
          ],
          bindings,
          { title: '该租户还没有绑定人员', hint: '绑定后可以把人员与租户内的工号、外部账号对应起来。' }
        )}
      </div>`;
    }

    return `${pageHead('人员与部门', '第一版由管理台手工维护；接入项目平台后改为同步平台的人员和组织数据。', '')}
      ${tabs}${body}`;
  });
}

/* --------------------------------------------------------------------------
   11. 审批流
   -------------------------------------------------------------------------- */

async function renderProcesses() {
  await paint(async () => {
    const processes = await api.get('/api/admin/processes?limit=200');
    railCounts.processes = processes.length;

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'new-process': () =>
        formDialog({
          title: '新建审批流',
          fields: [
            { name: 'name', label: '流程名称', type: 'text', required: true, placeholder: '付款审批流程' },
            { name: 'description', label: '流程说明', type: 'text', hint: '创建后会进入编排页，在那里添加节点、审批人和表单字段' },
          ],
          values: {},
          submitText: '创建并进入编排',
          onSubmit: async (values) => {
            const created = await api.post('/api/admin/processes', {
              name: values.name,
              description: values.description || null,
            });
            toast('审批流已创建，接下来编辑 V1 草稿', 'ok');
            location.hash = created.draft_version_id
              ? `#/versions/${created.draft_version_id}`
              : `#/processes/${created.id}`;
          },
        }),
      'copy-process': async (el) => {
        if (!(await confirmDialog({ title: '复制审批流', message: '将复制当前可见版本，生成一条拥有 V1 草稿的新流程。确认复制？', submitText: '复制' }))) return;
        const copied = await api.post(`/api/admin/processes/${el.dataset.id}/copy`);
        toast('审批流已复制', 'ok');
        location.hash = `#/processes/${copied.id}`;
      },
      'disable-process': async (el) => {
        if (!(await confirmDialog({ title: '停用审批流', message: '停用后业务系统不能再使用该流程发起新审批，已经运行的实例不受影响。确认停用？', submitText: '停用', danger: true }))) return;
        await api.post(`/api/admin/processes/${el.dataset.id}/disable`);
        toast('审批流已停用', 'ok');
        renderProcesses();
      },
      'draft': async (el) => {
        const version = await api.post(`/api/admin/processes/${el.dataset.id}/draft`);
        toast(`已创建 V${version.version_no} 草稿`, 'ok');
        location.hash = `#/versions/${version.id}`;
      },
    });

    return `${pageHead(
      '审批流',
      '流程的稳定身份与版本分离：已发布版本永久只读，编辑时先创建下一版草稿，发布后原子切换为新版本。',
      `<button class="btn btn--primary" data-act="new-process">新建审批流</button>`
    )}
    <div class="panel">
      ${tableHtml(
        [
          { title: '流程名称', render: (row) => `<a class="cell-title" href="#/processes/${esc(row.id)}">${esc(row.name)}</a>` },
          { title: '状态', render: (row) => tag(row.status) },
          {
            title: '当前版本', render: (row) =>
              row.current_version_id
                ? `<a class="code" href="#/versions/${esc(row.current_version_id)}">V${row.current_version_no}</a>`
                : '<span class="muted">未发布</span>',
          },
          {
            title: '草稿', render: (row) =>
              row.draft_version_id
                ? `<a class="code" href="#/versions/${esc(row.draft_version_id)}">V${row.draft_version_no} 编辑中</a>`
                : `<button class="btn--link btn--sm" data-act="draft" data-id="${esc(row.id)}">创建草稿</button>`,
          },
          { title: '节点数', cls: 'is-num', render: (row) => esc(row.node_count) },
          { title: '更新时间', render: (row) => `<span class="muted">${esc(fmtTime(row.updated_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<a class="btn--link btn--sm" href="#/processes/${esc(row.id)}">详情</a>
               <button class="btn--link btn--sm" data-act="copy-process" data-id="${esc(row.id)}">复制</button>
               ${row.status !== 'DISABLED' ? `<button class="btn--link btn--sm is-danger" data-act="disable-process" data-id="${esc(row.id)}">停用</button>` : ''}`,
          },
        ],
        processes,
        { title: '还没有审批流', hint: '新建审批流后会同步生成 V1 草稿，接着配置节点、审批人和分支条件。' }
      )}
    </div>`;
  });
}

async function renderProcessDetail(processId) {
  await paint(async () => {
    const [process, versions] = await Promise.all([
      api.get(`/api/admin/processes/${processId}`),
      api.get(`/api/admin/processes/${processId}/versions`),
    ]);

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'draft': async (el) => {
        const version = await api.post(`/api/admin/processes/${el.dataset.id}/draft`);
        toast(`已创建 V${version.version_no} 草稿`, 'ok');
        renderProcessDetail(processId);
      },
      'publish': async (el) => {
        if (!(await confirmDialog({ title: '发布版本', message: '发布会执行完整校验并把该版本切换为流程当前版本，已发布版本之后不可修改。确认发布？', submitText: '发布' }))) return;
        try {
          await api.post(`/api/admin/process-versions/${el.dataset.id}/publish`);
          toast('版本已发布', 'ok');
          renderProcessDetail(processId);
        } catch (err) {
          toast(err.message, 'err');
        }
      },
      'validate': async (el) => {
        const result = await api.post(`/api/admin/process-versions/${el.dataset.id}/validate`);
        if (result.valid) {
          toast('校验通过，可以发布', 'ok');
        } else {
          showIssues('校验未通过', result.issues);
        }
      },
      'copy-process': async () => {
        const copied = await api.post(`/api/admin/processes/${processId}/copy`);
        toast('审批流已复制', 'ok');
        location.hash = `#/processes/${copied.id}`;
      },
    });

    return `${breadcrumb([{ text: '审批流', href: '#/processes' }, { text: process.name }])}
    ${pageHead(
      process.name,
      esc(process.description || '暂无流程说明'),
      `${process.draft_version_id
        ? `<a class="btn btn--primary" href="#/versions/${esc(process.draft_version_id)}">继续编辑 V${process.draft_version_no}</a>`
        : `<button class="btn btn--primary" data-act="draft" data-id="${esc(process.id)}">创建下一版草稿</button>`}
       <button class="btn" data-act="copy-process">复制流程</button>`
    )}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">流程概况</h2>${tag(process.status)}</div>
      <div class="panel__body">
        ${kvHtml([
          ['流程 ID', `<span class="code">${esc(process.id)}</span>`],
          ['当前版本', process.current_version_id ? `V${process.current_version_no}` : '<span class="muted">未发布</span>'],
          ['编辑中草稿', process.draft_version_id ? `V${process.draft_version_no}` : '<span class="muted">无</span>'],
          ['当前版本节点数', `<span class="code">${esc(process.node_count)}</span>`],
          ['更新时间', esc(fmtTime(process.updated_at))],
        ])}
        ${process.draft_version_id ? '' : '<div class="note" style="margin-top:14px">当前没有草稿。需要修改流程时，点“创建下一版草稿”从当前发布版本复制一份。</div>'}
      </div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">版本历史</h2>
        <span class="panel__note">已发布版本只读，用于追溯和对比；新实例始终使用当前版本</span></div>
      ${tableHtml(
        [
          { title: '版本', render: (row) => `<span class="cell-title">V${row.version_no}</span>` },
          { title: '名称', render: (row) => esc(row.name) },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '节点数', cls: 'is-num', render: (row) => esc(row.node_count) },
          { title: '修订号', cls: 'is-num', render: (row) => esc(row.revision) },
          { title: '发布时间', render: (row) => `<span class="muted">${esc(fmtTime(row.published_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<a class="btn--link btn--sm" href="#/versions/${esc(row.id)}">${row.status === 'DRAFT' ? '编辑' : '查看'}</a>
               <button class="btn--link btn--sm" data-act="validate" data-id="${esc(row.id)}">校验</button>
               ${row.status === 'DRAFT' ? `<button class="btn--link btn--sm" data-act="publish" data-id="${esc(row.id)}">发布</button>` : ''}`,
          },
        ],
        versions,
        { title: '暂无版本', hint: '正常情况下新建流程时会自动创建 V1 草稿。' }
      )}
    </div>`;
  });
}

function showIssues(title, issues) {
  const body = issues.length
    ? `<div class="issues">${issues
        .map((issue) => `<div class="issue">
          <div class="issue__code">${esc(issue.code)}</div>
          <div>${esc(issue.message)}${issue.node_id ? `<span class="muted"> · 节点 ${esc(shortId(issue.node_id))}</span>` : ''}${issue.field ? `<span class="muted"> · 字段 ${esc(issue.field)}</span>` : ''}${issue.connection_index !== null && issue.connection_index !== undefined ? `<span class="muted"> · 连线 #${esc(issue.connection_index)}</span>` : ''}</div>
        </div>`)
        .join('')}</div>`
    : `<div class="issue issue--ok"><div class="issue__code">OK</div><div>没有发现问题，可以发布。</div></div>`;
  openOverlay(
    dialogShell(title, body, `<button class="btn" data-act="close-dialog">关闭</button>`),
    true
  );
  setDialogActions({ 'close-dialog': closeOverlay });
}

/* --------------------------------------------------------------------------
   12. 节点能力定义

   节点定义是"画布上能放什么节点"的清单。执行类型只有 START、APPROVAL、END
   三种（后端只注册了三个执行器），但同一种执行类型可以有多张定义，各自带自己的
   配置 Schema 和配置面板规则。流程开始前定义会随流程发布固化，改定义不影响历史版本。
   -------------------------------------------------------------------------- */

const NODE_TYPE_TEXT = { START: '开始', APPROVAL: '人工审批', END: '结束' };

const CONFIG_SCHEMA_SAMPLE = `{
  "type": "object",
  "title": "人工审批",
  "required": ["approval_mode", "approvers"],
  "properties": {
    "approval_mode": {
      "type": "string",
      "title": "审批模式",
      "enum": ["AND", "OR"]
    },
    "approvers": {
      "type": "array",
      "title": "审批人",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["person_id"],
        "properties": {
          "person_id": { "type": "string", "format": "uuid", "title": "人员 ID" }
        }
      }
    }
  }
}`;

/* 节点定义的编辑弹窗：配置项用字段表维护，JSON 只在高级模式出现。 */
function openDefinitionDialog(definition, onSaved) {
  const isNew = !definition;
  const draft = {
    schema: Object.assign({}, (definition && definition.config_schema_json) || {}),
    uiSchema: Object.assign({}, (definition && definition.ui_schema_json) || {}),
    advanced: false,
    fields: [],
  };
  const parsed = configFieldsFromSchema(draft.schema, draft.uiSchema);
  draft.fields = parsed.fields;
  if (!parsed.simple) draft.advanced = true;

  function metaHtml() {
    return `<div class="form__row--split">
      ${isNew
        ? `<div class="field"><label class="field__label">执行类型</label>
             <select class="select" id="def-type">
               ${['START', 'APPROVAL', 'END'].map((type) => `<option value="${type}">${esc(NODE_TYPE_TEXT[type])}（${type}）</option>`).join('')}
             </select>
             <div class="field__hint">决定后端用哪个执行器，创建后不可修改</div>
           </div>`
        : ''}
      <div class="field"><label class="field__label">名称</label>
        <input class="input" id="def-name" value="${esc(definition ? definition.name : '')}" placeholder="财务审批">
        <div class="field__hint">节点面板上显示的名字，全局唯一</div>
      </div>
      <div class="field"><label class="field__label">说明</label>
        <input class="input" id="def-desc" value="${esc(definition ? definition.description || '' : '')}" placeholder="金额超过 1 万元时需要财务审批">
      </div>
      <div class="field"><label class="field__label">图标标识</label>
        <input class="input" id="def-icon" value="${esc(definition ? definition.icon || '' : '')}" placeholder="user-check">
      </div>
      <div class="field"><label class="field__label">状态</label>
        <select class="select" id="def-status">
          <option value="ENABLED"${!definition || definition.status === 'ENABLED' ? ' selected' : ''}>启用</option>
          <option value="DISABLED"${definition && definition.status === 'DISABLED' ? ' selected' : ''}>停用</option>
        </select>
        <div class="field__hint">停用后不能再放新节点，已有流程不受影响</div>
      </div>
    </div>`;
  }

  function configHtml() {
    if (draft.advanced) {
      return `<div class="note" style="margin-bottom:12px">
          高级模式：直接编辑 JSON Schema 和配置面板规则，两者的根类型都必须是 object。
        </div>
        <div class="field"><label class="field__label">配置 Schema</label>
          <textarea class="textarea textarea--code" id="def-schema" placeholder="${esc(CONFIG_SCHEMA_SAMPLE)}">${esc(formatJson(draft.schema))}</textarea>
        </div>
        <div class="field" style="margin-top:12px"><label class="field__label">配置面板规则</label>
          <textarea class="textarea textarea--code" id="def-ui">${esc(formatJson(draft.uiSchema))}</textarea>
          <div class="field__hint">例如 {"approvers": {"ui:widget": "person-select"}}</div>
        </div>`;
    }

    const rows = draft.fields
      .map((field, index) => `<tr>
        <td><input class="input input--cell" data-act="cfg-field" data-index="${index}" data-prop="key" value="${esc(field.key)}"></td>
        <td><input class="input input--cell" data-act="cfg-field" data-index="${index}" data-prop="title" value="${esc(field.title)}" placeholder="显示给配置人看"></td>
        <td>
          <select class="select input--cell" data-act="cfg-field" data-index="${index}" data-prop="type">
            ${CONFIG_FIELD_TYPES.map((type) => `<option value="${type.value}"${type.value === field.type ? ' selected' : ''}>${esc(type.label)}</option>`).join('')}
          </select>
        </td>
        <td style="text-align:center">
          <input type="checkbox" data-act="cfg-field" data-index="${index}" data-prop="required"${field.required ? ' checked' : ''}>
        </td>
        <td>
          ${field.type === 'enum'
            ? `<input class="input input--cell" data-act="cfg-field" data-index="${index}" data-prop="options" value="${esc(field.options)}" placeholder="用、分隔，例如 AND、OR">`
            : '<span class="muted">—</span>'}
        </td>
        <td class="is-actions">
          <button class="btn--link btn--sm" data-act="cfg-field-up" data-index="${index}">上移</button>
          <button class="btn--link btn--sm" data-act="cfg-field-down" data-index="${index}">下移</button>
          <button class="btn--link btn--sm is-danger" data-act="cfg-field-drop" data-index="${index}">删除</button>
        </td>
      </tr>`)
      .join('');

    return `<div class="note" style="margin-bottom:12px">
        这里定义画布上放了这个节点之后，右侧弹窗里能配置哪些项。
        "人员选择器"就是让人从人员列表里挑人，不用手写 ID。
      </div>
      ${draft.fields.length
        ? `<div class="tbl-wrap"><table class="tbl field-tbl">
             <thead><tr><th>配置键</th><th>显示名</th><th>类型</th><th>必填</th><th>下拉选项</th><th></th></tr></thead>
             <tbody>${rows}</tbody>
           </table></div>`
        : '<div class="empty"><div class="empty__title">这个节点没有可配置项</div><div>例如"开始"和"结束"节点就不需要额外配置。</div></div>'}
      <div style="margin-top:12px"><button class="btn btn--sm btn--primary" data-act="cfg-field-add">新增配置项</button></div>`;
  }

  function refresh() {
    const host = document.getElementById('cfg-host');
    if (host) host.innerHTML = configHtml();
  }

  function syncFromFields() {
    const applied = applyConfigFields(draft.schema, draft.uiSchema, draft.fields);
    draft.schema = applied.schema;
    draft.uiSchema = applied.uiSchema;
  }

  function reportError(message) {
    const box = document.getElementById('dialog-error');
    if (box) box.innerHTML = `<div class="note note--wait">${esc(message)}</div>`;
  }

  async function submit() {
    const name = document.getElementById('def-name').value.trim();
    if (!name) {
      reportError('名称不能为空');
      return;
    }
    let schema = draft.schema;
    let uiSchema = draft.uiSchema;
    if (draft.advanced) {
      try {
        schema = parseJsonInput(document.getElementById('def-schema').value, '配置 Schema');
        uiSchema = parseJsonInput(document.getElementById('def-ui').value, '配置面板规则');
      } catch (err) {
        reportError(err.message);
        return;
      }
    }
    const body = {
      name,
      description: document.getElementById('def-desc').value.trim() || null,
      icon: document.getElementById('def-icon').value.trim() || null,
      status: document.getElementById('def-status').value,
      config_schema_json: schema,
      ui_schema_json: uiSchema,
    };
    try {
      if (isNew) {
        body.node_type = document.getElementById('def-type').value;
        await api.post('/api/admin/node-definitions', body);
      } else {
        await api.patch(`/api/admin/node-definitions/${definition.id}`, body);
      }
      closeOverlay();
      toast(isNew ? '节点定义已创建，回到编排页就能拖它' : '节点定义已更新', 'ok');
      onSaved();
    } catch (err) {
      reportError(err.message);
    }
  }

  openOverlay(
    dialogShell(
      isNew ? '新建节点定义' : `编辑节点定义 · ${definition.name}`,
      `<form class="form" id="def-form">${metaHtml()}</form>
       <div class="panel__head" style="padding:16px 0 8px">
         <h4 style="font-size:14px">这个节点允许配置哪些项</h4>
         <button class="btn btn--sm" data-act="cfg-mode">${draft.advanced ? '切到字段模式' : '高级模式（JSON）'}</button>
       </div>
       <div id="cfg-host">${configHtml()}</div>
       <div id="dialog-error"></div>
       <div class="dialog__foot" style="margin:18px -20px -20px;border-radius:0">
         <button class="btn" data-act="close-dialog">取消</button>
         <button class="btn btn--primary" data-act="def-submit">${isNew ? '创建定义' : '保存'}</button>
       </div>`,
      ''
    ),
    true
  );

  setDialogActions({
    'close-dialog': closeOverlay,
    'def-submit': submit,
    'cfg-mode': () => {
      if (draft.advanced) {
        // 切回字段表前先试解析，含字段表表达不了的结构就不让切，避免丢配置
        const schemaText = document.getElementById('def-schema').value.trim();
        const uiText = document.getElementById('def-ui').value.trim();
        if (!schemaText) {
          reportError('配置 Schema 不能为空：没有配置项时请填 {}');
          return;
        }
        try {
          const schema = parseJsonInput(schemaText, '配置 Schema');
          const uiSchema = parseJsonInput(uiText, '配置面板规则');
          const next = configFieldsFromSchema(schema, uiSchema);
          if (!next.simple) throw new Error('这份 Schema 含字段表表达不了的结构，不能切回字段模式');
          draft.schema = schema;
          draft.uiSchema = uiSchema;
          draft.fields = next.fields;
        } catch (err) {
          reportError(err.message);
          return;
        }
      }
      draft.advanced = !draft.advanced;
      refresh();
      const button = document.querySelector('[data-act="cfg-mode"]');
      if (button) button.textContent = draft.advanced ? '切到字段模式' : '高级模式（JSON）';
    },
    'cfg-field': (el) => {
      const field = draft.fields[Number(el.dataset.index)];
      if (!field) return;
      field[el.dataset.prop] = el.dataset.prop === 'required' ? Boolean(el.checked) : el.value;
      syncFromFields();
      if (el.dataset.prop === 'type') refresh();
    },
    'cfg-field-add': () => {
      draft.fields.push({ key: uniqueFieldKey(draft.fields), title: '新配置项', type: 'string', required: false, options: '' });
      syncFromFields();
      refresh();
    },
    'cfg-field-drop': (el) => {
      draft.fields.splice(Number(el.dataset.index), 1);
      syncFromFields();
      refresh();
    },
    'cfg-field-up': (el) => {
      const index = Number(el.dataset.index);
      if (index <= 0) return;
      const moved = draft.fields.splice(index, 1)[0];
      draft.fields.splice(index - 1, 0, moved);
      syncFromFields();
      refresh();
    },
    'cfg-field-down': (el) => {
      const index = Number(el.dataset.index);
      if (index >= draft.fields.length - 1) return;
      const moved = draft.fields.splice(index, 1)[0];
      draft.fields.splice(index + 1, 0, moved);
      syncFromFields();
      refresh();
    },
  });
}

async function renderNodeDefinitions() {
  await paint(async () => {
    const definitions = await api.get('/api/admin/node-definitions?limit=100');
    railCounts.definitions = definitions.length;

    setActions({
      'new-definition': () => openDefinitionDialog(null, renderNodeDefinitions),
      'edit-definition': (el) =>
        openDefinitionDialog(definitions.find((item) => item.id === el.dataset.id), renderNodeDefinitions),
      'copy': (el) => copyText(el.dataset.copy),
    });

    const configSummary = (definition) => {
      const schema = definition.config_schema_json || {};
      const properties = schema.properties || {};
      const required = new Set(schema.required || []);
      const names = Object.keys(properties);
      if (!names.length) return '<span class="muted">无配置项</span>';
      return names
        .map((name) => {
          const title = (properties[name] || {}).title || name;
          return `<span class="tag">${esc(title)}${required.has(name) ? ' *' : ''}</span>`;
        })
        .join(' ');
    };

    return `${pageHead(
      '节点定义',
      `这是系统支持的节点能力清单，一般不需要日常维护。<br>
       画布上能放哪些节点由它决定；而"这条流程用谁审批、怎么审批"是在审批流里填的，这里只管"这类节点允许配什么"。<br>
       执行类型只有开始、人工审批、结束三种，因为后端只有三个执行器；要加第四种执行语义需要后端开发。<br>
       同一种类型可以建多张定义（比如"财务审批"和"总经理审批"各自带不同规矩），也可以只用一张通用的。`,
      `<button class="btn" data-act="new-definition">新建节点定义</button>`
    )}
    <div class="panel">
      <div class="panel__body" style="padding-bottom:0">
        <div class="note note--work">
          什么时候需要来这里：系统新增了节点能力（例如人工审批多了"按部门选人"），或者要把某个能力停用。
          改配置规则会影响所有还在编辑中的草稿——<strong>给已有定义加必填项，会让老草稿在下次保存时报错</strong>，所以补新能力时建议加成选填。
        </div>
      </div>
      ${tableHtml(
        [
          { title: '名称', render: (row) => `<span class="cell-title">${esc(row.name)}</span>` },
          { title: '执行类型', render: (row) => `<span class="tag">${esc(NODE_TYPE_TEXT[row.node_type] || row.node_type)}</span>` },
          { title: '配置项', render: (row) => configSummary(row) },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '说明', render: (row) => `<span class="muted">${esc(row.description || '—')}</span>` },
          { title: '操作', cls: 'is-actions', render: (row) => `<button class="btn--link btn--sm" data-act="edit-definition" data-id="${esc(row.id)}">编辑</button>` },
        ],
        definitions,
        { title: '还没有节点定义', hint: '全新库执行 init.sql 会带入开始、人工审批、结束三个种子定义。' }
      )}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   13. 流程画布

   节点坐标保存在版本节点的 position_json 中，随整图保存一起提交。画布只负责
   交互和呈现，节点配置仍然复用弹窗，避免两套编辑逻辑。
   -------------------------------------------------------------------------- */

/* --- 画布几何 ---
   普通节点是固定尺寸的卡片；条件分支节点按分支数变高，每条分支在卡片右侧有自己
   的出口，线从那个出口引出，形态和 Dify 的 IF/ELSE 节点一致。 */

const FLOW_NODE_WIDTH = 184;
const FLOW_NODE_HEIGHT = 70;
const CONDITION_NODE_WIDTH = 232;
const CONDITION_HEADER_HEIGHT = 42;
const CONDITION_ROW_HEIGHT = 28;
const FLOW_PADDING = 64;
let flowScale = 1;

const ORDER_MARKS = '①②③④⑤⑥⑦⑧⑨⑩';

function orderMark(position) {
  return ORDER_MARKS[position - 1] || `${position}.`;
}

function nodeBox(node) {
  const position = node.position || {};
  const x = typeof position.x === 'number' ? position.x : 0;
  const y = typeof position.y === 'number' ? position.y : 0;
  return { x, y };
}

function flowNodeVariant(node) {
  if (node.node_type === 'START') return 'START';
  if (node.node_type === 'CONDITION') return 'CONDITION';
  if (node.node_type === 'END') return 'END-APPROVED';
  return 'APPROVAL';
}

function flowTypeLabel(node) {
  if (node.node_type === 'START') return '开始';
  if (node.node_type === 'CONDITION') return '条件分支';
  if (node.node_type === 'END') return '结束';
  return '审批';
}

/* 按节点定义的配置 Schema 生成初始配置：优先用 Schema 里的 default，枚举取第一项。
   画布上拖入新节点、以及拖拽预览都用它，保证预览和落地的配置一致。 */
function defaultConfigFor(definition) {
  const properties = ((definition.config_schema_json || {}).properties) || {};
  const config = {};
  for (const [name, rule] of Object.entries(properties)) {
    if (rule.default !== undefined) config[name] = rule.default;
    else if (Array.isArray(rule.enum) && rule.enum.length) config[name] = rule.enum[0];
    else if (rule.type === 'array') config[name] = [];
    else if (rule.type === 'object') config[name] = {};
    else if (rule.type === 'boolean') config[name] = false;
  }
  return config;
}

/* 节点定义是配置项的唯一来源：定义里已经删掉的配置项（例如下线过的「结束状态」）
   不再留在编辑器里，否则保存会被校验拦下，而用户在界面上根本找不到地方删。
   返回被清理掉的字段名，调用方可以据此提示一次。 */
function pruneNodeConfig(node, definition) {
  const config = Object.assign({}, node.config || {});
  const properties = ((definition || {}).config_schema_json || {}).properties || {};
  const dropped = [];
  Object.keys(config).forEach((name) => {
    if (!(name in properties)) {
      delete config[name];
      dropped.push(name);
    }
  });
  return { config, dropped };
}

/* 节点尺寸、出口位置和连线路径统一在这里算，渲染和交互共用同一套结果。 */
function flowGeometry(nodes, connections) {
  const byId = (id) => nodes.find((node) => node.id === id);
  const outgoingOf = (nodeId) =>
    connections.filter((connection) => connection.source_node_id === nodeId);

  function sizeOf(node) {
    if (!node || node.node_type !== 'CONDITION') {
      return { width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT };
    }
    const rows = Math.max(1, outgoingOf(node.id).length) + 1; // 多一行"新增分支"
    return {
      width: CONDITION_NODE_WIDTH,
      height: CONDITION_HEADER_HEIGHT + rows * CONDITION_ROW_HEIGHT,
    };
  }

  /* 条件分支节点每条分支从自己那一行的出口出发，其余节点从右侧中点出发。 */
  function startOf(connection) {
    const node = byId(connection.source_node_id);
    if (!node) return null;
    const box = nodeBox(node);
    const size = sizeOf(node);
    if (node.node_type === 'CONDITION') {
      const position = outgoingOf(node.id).indexOf(connection);
      return {
        x: box.x + size.width,
        y: box.y + CONDITION_HEADER_HEIGHT + position * CONDITION_ROW_HEIGHT + CONDITION_ROW_HEIGHT / 2,
      };
    }
    return { x: box.x + size.width, y: box.y + size.height / 2 };
  }

  function endOf(node) {
    const box = nodeBox(node);
    return { x: box.x, y: box.y + sizeOf(node).height / 2 };
  }

  function edgeOf(connection) {
    const start = startOf(connection);
    const target = byId(connection.target_node_id);
    if (!start || !target) return null;
    const end = endOf(target);
    const handle = Math.max(48, Math.abs(end.x - start.x) * 0.45);
    return {
      d: `M ${start.x} ${start.y} C ${start.x + handle} ${start.y}, ${end.x - handle} ${end.y}, ${end.x} ${end.y}`,
      // 三次贝塞尔在 t=0.5 处正好落在两端的中点，标签直接用这个位置。
      mid: { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 },
      start,
      end,
    };
  }

  return { byId, outgoingOf, sizeOf, startOf, endOf, edgeOf };
}

function flowStageSize(nodes, connections) {
  const geo = flowGeometry(nodes, connections);
  let right = 0;
  let bottom = 0;
  nodes.forEach((node) => {
    const box = nodeBox(node);
    const size = geo.sizeOf(node);
    right = Math.max(right, box.x + size.width);
    bottom = Math.max(bottom, box.y + size.height);
  });
  return {
    width: Math.max(980, right + FLOW_PADDING),
    height: Math.max(520, bottom + FLOW_PADDING),
  };
}

/* 分支节点的每一行：前面每条都要有条件，最后一条是"其余情况"不能带条件。 */
function branchRowState(connection, nodes, connections) {
  const node = nodes.find((item) => item.id === connection.source_node_id);
  if (!node || node.node_type !== 'CONDITION') return { isLast: false, problem: null };
  const siblings = connections.filter((item) => item.source_node_id === node.id);
  const isLast = siblings.indexOf(connection) === siblings.length - 1;
  if (isLast && connection.condition) {
    return { isLast, problem: '最后一条是「其余情况」，不能配条件' };
  }
  if (!isLast && !connection.condition) {
    return { isLast, problem: '这条分支还没有配条件' };
  }
  return { isLast, problem: null };
}

/* 从条件分支某一行的圆点拉线：这一步只定这条分支的去向，不改条件。
   branch 为 "new" 时新开一条分支（条件待配），插在"其余情况"之前。
   返回 null 表示这次拖拽没有产生变化。 */
function connectBranchTo(connections, nodeId, branch, targetId) {
  const siblings = connections.filter((item) => item.source_node_id === nodeId);
  if (branch === 'new') {
    const connection = { source_node_id: nodeId, target_node_id: targetId };
    const last = siblings[siblings.length - 1];
    if (last) connections.splice(connections.indexOf(last), 0, connection);
    else connections.push(connection);
    // 只有插在"其余情况"之前的那条才需要配条件
    return { created: true, needsCondition: Boolean(last) };
  }
  const connection = siblings[Number(branch)];
  if (!connection || connection.target_node_id === targetId) return null;
  connection.target_node_id = targetId;
  return { created: false, needsCondition: false };
}

/* 卡片上的提醒：普通节点多条去向、分支节点有分支没配完。 */
function flowNodeWarning(node, nodes, connections) {
  const outgoing = connections.filter((item) => item.source_node_id === node.id);
  if (node.node_type === 'CONDITION') {
    if (!outgoing.length) return '还没有分支';
    if (outgoing.some((item) => !item.target_node_id)) return '分支未接去向';
    return outgoing.some((item) => branchRowState(item, nodes, connections).problem)
      ? '分支未配完'
      : null;
  }
  if (node.node_type === 'END') return null;
  if (!outgoing.length) return '还没有去向';
  if (outgoing.length > 1) return '只能有一条去向';
  if (outgoing.some((item) => item.condition)) return '去向不能带条件';
  return null;
}

function hasConnection(connections, sourceId, targetId) {
  return connections.some((item) => item.source_node_id === sourceId && item.target_node_id === targetId);
}

function flowPaletteHtml(definitions, nodes, editable) {
  if (!editable) {
    return `<div class="flow-palette" id="flow-palette"><div class="flow-palette__hint">已发布版本只读，不能新增节点。需要修改请创建下一版草稿。</div></div>`;
  }
  const hasStart = nodes.some((node) => node.node_type === 'START');
  const usable = definitions.filter((definition) => definition.status === 'ENABLED');
  if (!usable.length) {
    return `<div class="flow-palette" id="flow-palette"><div class="flow-palette__hint">没有可用的节点定义。先去“节点定义”页面创建，或执行 init.sql 带入种子定义。</div></div>`;
  }
  // 分组按接口返回的定义动态生成，以后新增节点类型不用改这里
  const types = [];
  usable.forEach((definition) => {
    if (!types.includes(definition.node_type)) types.push(definition.node_type);
  });
  const groups = types
    .map((type) => {
      const items = usable.filter((definition) => definition.node_type === type);
      return `<div class="flow-palette__group">${esc(NODE_TYPE_TEXT[type] || type)}</div>
        ${items
          .map((definition) => {
            const blocked = type === 'START' && hasStart;
            return `<div class="flow-palette__item${blocked ? ' is-disabled' : ''}"
              ${blocked
                ? 'title="每条流程只能有一个开始节点"'
                : `draggable="true" data-act="palette-add" data-definition-id="${esc(definition.id)}" title="拖到画布上，或点击直接新增"`}>
              <span class="flow-palette__dot flow-palette__dot--${esc(type)}"></span>${esc(definition.name)}
            </div>`;
          })
          .join('')}`;
    })
    .join('');
  return `<div class="flow-palette" id="flow-palette">
    <div class="flow-palette__title">拖到画布上新增节点</div>
    ${groups}
  </div>`;
}

/* 条件分支节点卡片里的分支行：序号 + 条件 + 去向 + 自己的出口。 */
function conditionRowsHtml(node, nodes, connections, editable, fieldLabels) {
  const outgoing = connections.filter((item) => item.source_node_id === node.id);
  const rows = outgoing
    .map((connection, position) => {
      const state = branchRowState(connection, nodes, connections);
      const target = nodes.find((item) => item.id === connection.target_node_id);
      const mark = state.isLast ? '—' : orderMark(position + 1);
      // 文字按位置判断：只有最后一行才是"其余情况"，中间的没配条件要显出来
      const text = state.isLast
        ? '其余情况'
        : connection.condition
          ? conditionText(connection.condition, fieldLabels)
          : '未配条件';
      // 去向由这一行右侧的圆点拉线决定，行本身只管条件
      const linked = Boolean(connection.target_node_id);
      return `<div class="flow__row${state.problem ? ' is-incomplete' : ''}"
        ${editable ? `data-act="edit-branch" data-id="${esc(node.id)}" title="${esc(state.problem || '点这里改条件')}"` : ''}>
        <span class="flow__row-mark">${esc(mark)}</span>
        <span class="flow__row-text">${esc(text)}</span>
        <span class="flow__row-target${linked ? '' : ' is-unlinked'}">→ ${esc(linked ? (target || {}).name || '未知节点' : '未接去向')}</span>
        <span class="flow__row-port" data-branch="${position}" title="从这里拉一条线到目标节点"></span>
      </div>`;
    })
    .join('');
  const addRow = editable
    ? `<div class="flow__row flow__row--add" data-act="edit-branch" data-id="${esc(node.id)}" title="新增一条分支">
         <span class="flow__row-text">＋ 新增分支</span>
         <span class="flow__row-port flow__row-port--add" data-branch="new" title="从这里拉一条线，直接连到新分支的目标节点"></span>
       </div>`
    : '';
  return rows + addRow;
}

function flowCanvasHtml(nodes, connections, editable, fieldLabels) {
  const geo = flowGeometry(nodes, connections);
  const size = flowStageSize(nodes, connections);

  const edges = connections
    .map((connection, index) => {
      const geometry = geo.edgeOf(connection);
      if (!geometry) return '';
      const kind = connection.condition ? 'condition' : 'plain';
      const marker = connection.condition ? 'flow-arrow-condition' : 'flow-arrow';
      return `<path class="flow__edge flow__edge--${kind}" data-conn="${index}" d="${geometry.d}" marker-end="url(#${marker})" />`;
    })
    .join('');

  const hits = connections
    .map((connection, index) => {
      const geometry = geo.edgeOf(connection);
      return geometry ? `<path class="flow__edge-hit" data-conn="${index}" d="${geometry.d}" />` : '';
    })
    .join('');

  // 线中点挂两样东西：条件摘要（便于线交叉时对上是哪条）和删线按钮。
  // 条件本身写在节点的分支行里，这里只是复述一句。
  const labels = connections
    .map((connection, index) => {
      const geometry = geo.edgeOf(connection);
      if (!geometry) return '';
      const node = nodes.find((item) => item.id === connection.source_node_id);
      const conditionLabel = connection.condition
        ? `<span class="flow__edge-label flow__edge-label--condition">${esc(conditionText(connection.condition, fieldLabels))}</span>`
        : '';
      // 分支节点的一条线就是一条分支的去向：断开它等于把去向留空，分支和条件都还在
      const action = node && node.node_type === 'CONDITION' ? '断开这条分支的去向' : '删除这条连线';
      return `<div class="flow__edge-tools" data-conn="${index}" style="left:${geometry.mid.x}px;top:${geometry.mid.y}px">
        ${conditionLabel}
        ${editable
          ? `<button class="flow__edge-del" data-act="drop-connection" data-conn="${index}" title="${esc(action)}" aria-label="${esc(action)}">×</button>`
          : ''}
      </div>`;
    })
    .join('');

  const nodeCards = nodes
    .map((node) => {
      const box = nodeBox(node);
      const warning = flowNodeWarning(node, nodes, connections);
      const isCondition = node.node_type === 'CONDITION';
      const body = isCondition
        ? `<div class="flow__rows">${conditionRowsHtml(node, nodes, connections, editable, fieldLabels)}</div>`
        : `<div class="flow__node-desc">${esc(nodeConfigSummary(node))}</div>`;
      // 条件分支的出口全在分支行上（一条分支一个圆点），卡片本身不挂出口圆点：
      // 卡片边缘那个"悬停才出现"的圆点在这里没有对应物，一并去掉，免得两套手感打架。
      const ports = isCondition
        ? ''
        : `${editable && node.node_type !== 'START' ? '<div class="flow__port flow__port--in"></div>' : ''}
           ${editable && node.node_type !== 'END' ? '<div class="flow__port flow__port--out" data-out="1"></div>' : ''}`;
      return `<div class="flow__node flow__node--${flowNodeVariant(node)}" data-id="${esc(node.id)}"
        style="left:${box.x}px;top:${box.y}px${isCondition ? `;width:${CONDITION_NODE_WIDTH}px` : ''}">
        <div class="flow__node-head">
          <span class="flow__node-type">${esc(node.node_definition_name || flowTypeLabel(node))}</span>
          <span class="flow__node-name">${esc(node.name)}</span>
          ${warning ? `<span class="flow__node-warn">${esc(warning)}</span>` : ''}
        </div>
        ${body}
        ${ports}
        ${editable
          ? `<div class="flow__node-tools">
               <button data-act="edit-node" data-id="${esc(node.id)}">${isCondition ? '改名' : '配置'}</button>
               ${node.node_type === 'START' ? '' : `<button class="is-danger" data-act="drop-node" data-id="${esc(node.id)}">删除</button>`}
             </div>`
          : ''}
      </div>`;
    })
    .join('');

  return `<div class="flow" id="flow">
    <div class="flow__sizer" id="flow-sizer">
      <div class="flow__stage" id="flow-stage" data-width="${size.width}" data-height="${size.height}"
           style="width:${size.width}px;height:${size.height}px">
        <svg class="flow__edges" id="flow-edges" width="${size.width}" height="${size.height}">
          <defs>
            <marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#7c8894" />
            </marker>
            <marker id="flow-arrow-condition" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#2c4a73" />
            </marker>
          </defs>
          ${edges}${hits}
        </svg>
        ${nodeCards}
        ${labels}
        ${nodes.length ? '' : `<div class="flow__empty">
          <div>这条流程还没有节点</div>
          <div>从左边把节点拖进来开始编排。</div>
        </div>`}
      </div>
    </div>
  </div>`;
}
/* 画布交互：拖动节点、拖动连线、空白平移、缩放。结构变化通过回调交给页面重渲染。 */
function mountFlowCanvas(options) {
  const flow = document.getElementById('flow');
  const stage = document.getElementById('flow-stage');
  const sizer = document.getElementById('flow-sizer');
  if (!flow || !stage || !sizer || !flow.addEventListener) return;

  const { nodes, connections, editable } = options;
  const stageWidth = Number(stage.dataset.width) || 980;
  const stageHeight = Number(stage.dataset.height) || 520;
  const byId = (id) => nodes.find((node) => node.id === id);
  const scaleLabel = document.getElementById('flow-zoom-value');

  let mode = null;
  let dragState = null;
  let tempPath = null;

  function applyScale(next, focus) {
    const before = focus
      ? { x: (flow.scrollLeft + focus.x) / flowScale, y: (flow.scrollTop + focus.y) / flowScale }
      : null;
    flowScale = Math.min(1.8, Math.max(0.4, next));
    sizer.style.width = `${stageWidth * flowScale}px`;
    sizer.style.height = `${stageHeight * flowScale}px`;
    stage.style.transform = `scale(${flowScale})`;
    if (before) {
      flow.scrollLeft = before.x * flowScale - focus.x;
      flow.scrollTop = before.y * flowScale - focus.y;
    }
    if (scaleLabel) scaleLabel.textContent = `${Math.round(flowScale * 100)}%`;
  }

  /* 拖动节点时按当前坐标重画所有连线，几何口径和渲染完全一致。 */
  function updateEdges() {
    const geo = flowGeometry(nodes, connections);
    stage.querySelectorAll('path[data-conn]').forEach((pathElement) => {
      const connection = connections[Number(pathElement.dataset.conn)];
      if (!connection) return;
      const geometry = geo.edgeOf(connection);
      if (!geometry) return;
      pathElement.setAttribute('d', geometry.d);
      const tools = stage.querySelector(`.flow__edge-tools[data-conn="${pathElement.dataset.conn}"]`);
      if (tools) {
        tools.style.left = `${geometry.mid.x}px`;
        tools.style.top = `${geometry.mid.y}px`;
      }
    });
  }

  /* 把屏幕坐标换算成画布坐标（考虑滚动和缩放）。 */
  function pointerToStage(clientX, clientY) {
    const rect = flow.getBoundingClientRect();
    return {
      x: (flow.scrollLeft + clientX - rect.left) / flowScale,
      y: (flow.scrollTop + clientY - rect.top) / flowScale,
    };
  }

  function showTempEdge(portElement) {
    const svg = document.getElementById('flow-edges');
    if (!svg) return null;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'flow__edge flow__edge--condition');
    svg.appendChild(path);
    // 起点取被按住的那个端口中心，缩放后依然对得上
    if (portElement && portElement.getBoundingClientRect) {
      const portRect = portElement.getBoundingClientRect();
      dragState.startPoint = pointerToStage(
        portRect.left + portRect.width / 2,
        portRect.top + portRect.height / 2
      );
    } else {
      const node = byId(dragState.nodeId);
      const box = nodeBox(node);
      const size = flowGeometry(nodes, connections).sizeOf(node);
      dragState.startPoint = { x: box.x + size.width, y: box.y + size.height / 2 };
    }
    return path;
  }

  function moveTempEdge(event) {
    if (!tempPath || !dragState || !dragState.startPoint) return;
    const target = pointerToStage(event.clientX, event.clientY);
    const start = dragState.startPoint;
    tempPath.setAttribute('d', `M ${start.x} ${start.y} L ${target.x} ${target.y}`);
  }

  function clearTempEdge() {
    if (tempPath && tempPath.parentNode) tempPath.parentNode.removeChild(tempPath);
    tempPath = null;
  }

  flow.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    // 一次只处理一个手势：拖动或拉线还没结束时，不要再起一个
    if (mode) return;
    const nodeElement = event.target.closest ? event.target.closest('.flow__node') : null;

    // 出口有两种：普通节点右侧的圆点，以及条件分支每一行（含"新增分支"）的圆点。
    // 这个判断要排在 data-act 前面：分支行的圆点画在带 data-act 的行里面，
    // 先判 data-act 会把"按住圆点拖线"误当成"点这一行"。
    const portElement = event.target.closest
      ? event.target.closest('.flow__port--out, .flow__row-port')
      : null;
    const target = portElement && nodeElement
      ? null
      : (event.target.closest ? event.target.closest('[data-act]') : null);
    if (target) return;

    if (editable && nodeElement && portElement) {
      mode = 'connect';
      // 条件分支的行端口带 data-branch：数字是分支序号，"new" 表示新开一条分支
      const rawBranch = portElement.dataset ? portElement.dataset.branch : undefined;
      dragState = {
        nodeId: nodeElement.dataset.id,
        branch: rawBranch === undefined ? null : rawBranch,
      };
      tempPath = showTempEdge(portElement);
      flow.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }

    if (editable && nodeElement) {
      const node = byId(nodeElement.dataset.id);
      const box = nodeBox(node);
      mode = 'drag';
      dragState = { node, nodeElement, startX: event.clientX, startY: event.clientY, originX: box.x, originY: box.y, moved: false };
      nodeElement.classList.add('is-dragging');
      flow.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }

    if (event.target.closest && event.target.closest('.flow__edge-label, .flow__edge-hit')) return;
    mode = 'pan';
    dragState = { startX: event.clientX, startY: event.clientY, scrollLeft: flow.scrollLeft, scrollTop: flow.scrollTop };
    flow.classList.add('is-panning');
    flow.setPointerCapture(event.pointerId);
  });

  flow.addEventListener('pointermove', (event) => {
    if (!mode || !dragState) return;
    if (mode === 'drag') {
      const dx = (event.clientX - dragState.startX) / flowScale;
      const dy = (event.clientY - dragState.startY) / flowScale;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) dragState.moved = true;
      const position = { x: Math.round(dragState.originX + dx), y: Math.round(dragState.originY + dy) };
      dragState.node.position = position;
      dragState.nodeElement.style.left = `${position.x}px`;
      dragState.nodeElement.style.top = `${position.y}px`;
      updateEdges();
    } else if (mode === 'pan') {
      flow.scrollLeft = dragState.scrollLeft - (event.clientX - dragState.startX);
      flow.scrollTop = dragState.scrollTop - (event.clientY - dragState.startY);
    } else if (mode === 'connect') {
      moveTempEdge(event);
    }
  });

  function finishPointer(event) {
    if (!mode) return;
    // 回调里可能会重画画布（画布元素是复用的，会再挂一个 pointerup），
    // 所以先把这一次的状态收走，重复进来时直接返回
    const finishedMode = mode;
    const finishedDrag = dragState;
    mode = null;
    dragState = null;
    flow.classList.remove('is-panning');
    if (finishedMode === 'drag' && finishedDrag) {
      finishedDrag.nodeElement.classList.remove('is-dragging');
      if (finishedDrag.moved) options.onMoved && options.onMoved();
      else options.onSelect && options.onSelect(finishedDrag.node.id);
    } else if (finishedMode === 'connect' && finishedDrag) {
      const hovered = document.elementFromPoint(event.clientX, event.clientY);
      const targetElement = hovered && hovered.closest ? hovered.closest('.flow__node') : null;
      clearTempEdge();
      if (targetElement && targetElement.dataset.id !== finishedDrag.nodeId) {
        options.onConnect && options.onConnect(
          finishedDrag.nodeId,
          targetElement.dataset.id,
          finishedDrag.branch === undefined ? null : finishedDrag.branch
        );
      }
    }
  }

  flow.addEventListener('pointerup', finishPointer);
  flow.addEventListener('pointercancel', finishPointer);

  flow.addEventListener('wheel', (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const rect = flow.getBoundingClientRect();
    applyScale(flowScale * (event.deltaY < 0 ? 1.1 : 0.9), {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    });
  }, { passive: false });

  /* 从左侧节点面板拖到画布上新增节点。
     拖拽影像是节点卡本身（所见即所得），画布上再用一个虚线框标出落点。 */
  const palette = document.getElementById('flow-palette');
  let draggingDefinitionId = null;
  let draggingItem = null;
  let dropHint = null;

  function positionForPointer(clientX, clientY) {
    const rect = flow.getBoundingClientRect();
    return {
      x: Math.max(0, Math.round((flow.scrollLeft + clientX - rect.left) / flowScale - FLOW_NODE_WIDTH / 2)),
      y: Math.max(0, Math.round((flow.scrollTop + clientY - rect.top) / flowScale - FLOW_NODE_HEIGHT / 2)),
    };
  }

  function moveDropHint(clientX, clientY) {
    if (!dropHint) {
      dropHint = document.createElement('div');
      dropHint.className = 'flow__drop-hint';
      dropHint.style.width = `${FLOW_NODE_WIDTH}px`;
      dropHint.style.height = `${FLOW_NODE_HEIGHT}px`;
      stage.appendChild(dropHint);
    }
    const position = positionForPointer(clientX, clientY);
    dropHint.style.left = `${position.x}px`;
    dropHint.style.top = `${position.y}px`;
  }

  function clearDropHint() {
    if (dropHint && dropHint.parentNode) dropHint.parentNode.removeChild(dropHint);
    dropHint = null;
    flow.classList.remove('is-dropping');
  }

  if (palette && editable) {
    palette.addEventListener('dragstart', (event) => {
      const item = event.target.closest ? event.target.closest('[data-definition-id]') : null;
      if (!item) return;
      draggingDefinitionId = item.dataset.definitionId;
      draggingItem = item;
      item.classList.add('is-dragging');
      if (event.dataTransfer) {
        event.dataTransfer.setData('text/plain', draggingDefinitionId);
        event.dataTransfer.effectAllowed = 'copy';
        // 用节点卡本身做拖拽预览，而不是把面板这一行复制一份
        const ghostHtml = options.renderGhost ? options.renderGhost(draggingDefinitionId) : null;
        if (ghostHtml && event.dataTransfer.setDragImage) {
          const holder = document.createElement('div');
          holder.className = 'flow-drag-ghost';
          holder.innerHTML = ghostHtml;
          document.body.appendChild(holder);
          event.dataTransfer.setDragImage(holder, 26, 30);
          // 个别浏览器要等一帧才取快照，给足时间再移除离屏元素
          setTimeout(() => holder.remove(), 200);
        }
      }
    });
    palette.addEventListener('dragend', () => {
      draggingDefinitionId = null;
      if (draggingItem) draggingItem.classList.remove('is-dragging');
      draggingItem = null;
      clearDropHint();
    });
  }

  if (editable) {
    flow.addEventListener('dragover', (event) => {
      if (!draggingDefinitionId) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
      flow.classList.add('is-dropping');
      moveDropHint(event.clientX, event.clientY);
    });
    flow.addEventListener('dragleave', (event) => {
      if (event.target === flow) clearDropHint();
    });
    flow.addEventListener('drop', (event) => {
      event.preventDefault();
      const definitionId = (event.dataTransfer && event.dataTransfer.getData('text/plain')) || draggingDefinitionId;
      const position = positionForPointer(event.clientX, event.clientY);
      draggingDefinitionId = null;
      clearDropHint();
      if (!definitionId || !options.onCreateNode) return;
      options.onCreateNode(definitionId, position);
    });
  }

  const zoomIn = document.getElementById('flow-zoom-in');
  const zoomOut = document.getElementById('flow-zoom-out');
  const zoomFit = document.getElementById('flow-zoom-fit');
  if (zoomIn) zoomIn.addEventListener('click', () => applyScale(flowScale * 1.15));
  if (zoomOut) zoomOut.addEventListener('click', () => applyScale(flowScale / 1.15));
  if (zoomFit) {
    zoomFit.addEventListener('click', () => {
      const fit = Math.min(1, (flow.clientWidth - 32) / stageWidth, (flow.clientHeight - 32) / stageHeight);
      applyScale(fit);
      flow.scrollLeft = 0;
      flow.scrollTop = 0;
    });
  }

  applyScale(flowScale);
}

/* 从开始节点做一次广度优先分层，把节点摆成从左到右的流程图。 */
function autoLayoutNodes(nodes, connections) {
  const known = new Set(nodes.map((node) => node.id));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));
  connections.forEach((connection) => {
    const list = outgoing.get(connection.source_node_id);
    if (list && known.has(connection.target_node_id)) list.push(connection.target_node_id);
  });

  const start = nodes.find((node) => node.node_type === 'START');
  const layerOf = new Map();
  if (start) {
    layerOf.set(start.id, 0);
    const queue = [start.id];
    while (queue.length) {
      const current = queue.shift();
      for (const next of outgoing.get(current) || []) {
        if (layerOf.has(next)) continue;
        layerOf.set(next, layerOf.get(current) + 1);
        queue.push(next);
      }
    }
  }
  const maxLayer = Math.max(0, ...Array.from(layerOf.values()));
  nodes.forEach((node) => {
    if (!layerOf.has(node.id)) layerOf.set(node.id, maxLayer + 1);
  });

  const rowByLayer = new Map();
  nodes.forEach((node) => {
    const layer = layerOf.get(node.id);
    const row = rowByLayer.get(layer) || 0;
    rowByLayer.set(layer, row + 1);
    node.position = { x: FLOW_PADDING + layer * (FLOW_NODE_WIDTH + 88), y: FLOW_PADDING + row * (FLOW_NODE_HEIGHT + 42) };
  });
}

function flowNeedsLayout(nodes) {
  if (nodes.length < 2) return false;
  const seen = new Set();
  return nodes.some((node) => {
    const box = nodeBox(node);
    if (!box.x && !box.y) return true;
    const key = `${box.x}:${box.y}`;
    if (seen.has(key)) return true;
    seen.add(key);
    return false;
  });
}

/* --------------------------------------------------------------------------
   条件分支编辑弹窗

   一个窗口里把这条分支阶梯配完：前面每条是"如果……"，最后一条是"其余情况"。
   保存时按列表重建这个节点的全部出线，顺序就是运行时的匹配顺序。
   -------------------------------------------------------------------------- */

function conditionValueHtml(index, field, operator, value) {
  if (!field || operator === 'IS_EMPTY' || operator === 'NOT_EMPTY') return '';
  const current = value === undefined || value === null ? '' : String(value);
  if (operator === 'IN' || operator === 'NOT_IN') {
    const text = value === undefined ? '' : formatJson(value);
    return `<input class="input input--cell" id="branch-${index}-value" value="${esc(text)}" placeholder='["A","B"]' title="多个取值写成 JSON 数组">`;
  }
  if (field.type === 'enum') {
    return `<select class="select input--cell" id="branch-${index}-value">${splitOptions(field.options)
      .map((item) => `<option value="${esc(item)}"${item === current ? ' selected' : ''}>${esc(item)}</option>`)
      .join('')}</select>`;
  }
  if (field.type === 'boolean') {
    return `<select class="select input--cell" id="branch-${index}-value">
      <option value="true"${current === 'true' ? ' selected' : ''}>是</option>
      <option value="false"${current === 'false' ? ' selected' : ''}>否</option>
    </select>`;
  }
  if (field.type === 'number' || field.type === 'integer') {
    return `<input class="input input--cell" type="number" id="branch-${index}-value" value="${esc(current)}">`;
  }
  return `<input class="input input--cell" id="branch-${index}-value" value="${esc(current)}" placeholder="要比较的内容">`;
}

function openBranchDialog(node, nodes, connections, formSchema, onSave) {
  const formFields = formFieldsFromSchema(formSchema).fields.filter((field) => field.type !== 'unsupported');
  const fieldOptions = formFields.map((field) => ({
    value: `approval_form.${field.key}`,
    label: `${field.title}（${FORM_FIELD_TYPE_LABEL(field.type)}）`,
  }));
  const fieldOf = (path) =>
    formFields.find((field) => `approval_form.${field.key}` === path) || null;
  // 去向不在这里选：从卡片上每一行右侧的圆点拉线到目标节点
  const targetNameOf = (targetId) => {
    const target = nodes.find((item) => item.id === targetId);
    return target ? target.name : '未接去向';
  };
  const hasTarget = (targetId) =>
    nodes.some((item) => item.id === targetId && item.node_type !== 'START');

  // 分支列表来自这个节点的出线，顺序就是运行时从上往下匹配的顺序
  const branches = connections
    .filter((connection) => connection.source_node_id === node.id)
    .map((connection) => ({
      target_node_id: connection.target_node_id,
      condition: connection.condition ? Object.assign({}, connection.condition) : null,
    }));
  if (!branches.length) branches.push({ target_node_id: '', condition: null });

  function rowsHtml() {
    if (!formFields.length) {
      return `<div class="note note--wait">这条流程还没有定义表单字段，条件无从选起。`
        + '先在下面的「审批表单」里加上要判断的字段（比如金额、类别），再回来配条件。'
        + ' <button class="btn--link btn--sm" data-act="goto-form">去配置表单字段</button></div>';
    }
    return branches
      .map((branch, index) => {
        const isLast = index === branches.length - 1;
        const condition = branch.condition || {};
        const field = fieldOf(condition.field);
        const operator = condition.operator || 'EQ';
        const linked = hasTarget(branch.target_node_id);
        return `<div class="branch-row">
          <div class="branch-row__head">
            <span class="branch-row__mark">${isLast ? '—' : esc(orderMark(index + 1))}</span>
            <span class="branch-row__label">${isLast ? '其余情况' : `条件 ${index + 1}`}</span>
            ${branches.length > 1
              ? `<button class="btn--link btn--sm is-danger" data-act="branch-drop" data-index="${index}">删除</button>`
              : ''}
          </div>
          <div class="branch-row__body">
            ${isLast
              ? '<span class="branch-row__hint">上面的条件都不满足时走这条</span>'
              : `<select class="select input--cell" data-act="branch-change" data-index="${index}" id="branch-${index}-field" title="条件字段">
                   ${fieldOptions
                     .map((option) => `<option value="${esc(option.value)}"${option.value === condition.field ? ' selected' : ''}>${esc(option.label)}</option>`)
                     .join('')}
                 </select>
                 <select class="select input--cell" data-act="branch-change" data-index="${index}" id="branch-${index}-operator" title="比较方式">
                   ${operatorOptionsForField(field)
                     .map((option) => `<option value="${esc(option.value)}"${option.value === operator ? ' selected' : ''}>${esc(option.label)}</option>`)
                     .join('')}
                 </select>
                 ${conditionValueHtml(index, field, operator, condition.value)}`}
            <span class="branch-row__arrow">去</span>
            <span class="branch-row__target${linked ? '' : ' is-unlinked'}">${esc(targetNameOf(branch.target_node_id))}</span>
          </div>
        </div>`;
      })
      .join('');
  }

  function refresh() {
    const host = document.getElementById('branch-host');
    if (host) host.innerHTML = rowsHtml();
  }

  function reportError(message) {
    const box = document.getElementById('dialog-error');
    if (box) box.innerHTML = message ? `<div class="note note--wait">${esc(message)}</div>` : '';
  }

  /* 改动后把整个列表读回内存，再决定要不要重画（换字段要换比较方式和取值控件）。 */
  function collect() {
    branches.forEach((branch, index) => {
      // 去向不在这里改，拉线的时候才动它，这里原样带回去
      const isLast = index === branches.length - 1;
      if (isLast) {
        branch.condition = null;
        return;
      }
      const fieldSelect = document.getElementById(`branch-${index}-field`);
      const operatorSelect = document.getElementById(`branch-${index}-operator`);
      const valueInput = document.getElementById(`branch-${index}-value`);
      if (!fieldSelect || !operatorSelect) return;
      const condition = { field: fieldSelect.value, operator: operatorSelect.value };
      if (operatorSelect.value !== 'IS_EMPTY' && operatorSelect.value !== 'NOT_EMPTY' && valueInput) {
        condition.value = valueInput.value;
      }
      branch.condition = condition;
    });
  }

  function submit() {
    collect();
    // 最后一条永远当"其余情况"处理，即使前面配过条件
    const last = branches[branches.length - 1];
    if (last) last.condition = null;

    const missingCondition = branches.findIndex(
      (branch, index) => index < branches.length - 1 && (!branch.condition || !branch.condition.field)
    );
    if (missingCondition >= 0) {
      reportError(`条件 ${missingCondition + 1} 还没有配完，只有最后一条才是“其余情况”`);
      return;
    }
    const built = branches.map((branch) => {
      // 还没拉线的分支把去向留空，画布上会显示"未接去向"，发布前校验会拦下来
      const target = hasTarget(branch.target_node_id) ? branch.target_node_id : null;
      if (!branch.condition) return { target_node_id: target, condition: null };
      const field = fieldOf(branch.condition.field);
      const condition = { field: branch.condition.field, operator: branch.condition.operator };
      if (branch.condition.operator !== 'IS_EMPTY' && branch.condition.operator !== 'NOT_EMPTY') {
        try {
          condition.value = typedConditionValue(field, branch.condition.operator, branch.condition.value);
        } catch (err) {
          reportError(err.message);
          return null;
        }
      }
      return { target_node_id: target, condition };
    });
    if (built.some((item) => item === null)) return;

    onSave(built);
    closeOverlay();
  }

  openOverlay(
    dialogShell(
      `条件分支 · ${node.name}`,
      `<div class="note" style="margin-bottom:14px">
         这里只定条件：按顺序从上往下判断，命中哪条走哪条；最后一条是"其余情况"，兜住上面的条件都不满足的时候。
         每条走哪里，关掉这个窗口后从卡片上对应一行右侧的圆点拉一条线到目标节点。
       </div>
       <div id="branch-host">${rowsHtml()}</div>
       <div style="margin-top:14px">
         <button class="btn btn--sm" data-act="branch-add">＋ 新增条件</button>
       </div>
       <div id="dialog-error"></div>
       <div class="dialog__foot" style="margin:18px -20px -20px;border-radius:0">
         <button class="btn" data-act="close-dialog">取消</button>
         <button class="btn btn--primary" data-act="branch-submit">保存</button>
       </div>`,
      ''
    ),
    true
  );

  setDialogActions({
    'close-dialog': closeOverlay,
    'branch-submit': submit,
    'branch-add': () => {
      collect();
      // 新条件插在"其余情况"之前，最后一行的位置不会被打乱
      branches.splice(Math.max(0, branches.length - 1), 0, {
        target_node_id: null,
        condition: { field: (fieldOptions[0] || {}).value || '', operator: 'EQ', value: '' },
      });
      reportError('');
      refresh();
    },
    'branch-drop': (el) => {
      collect();
      branches.splice(Number(el.dataset.index), 1);
      reportError('');
      refresh();
    },
    'branch-change': (el) => {
      collect();
      // 换了条件字段，比较方式和取值控件要跟着换
      if (el.id.endsWith('-field')) refresh();
    },
  });
}

/* --------------------------------------------------------------------------
   14. 版本编排编辑器
   -------------------------------------------------------------------------- */

/* 版本编辑器的本地工作副本，保存成功后丢弃，离开页面时清空。 */
let versionEditorState = null;
let versionTab = 'form';

const OPERATORS = [
  { value: 'EQ', label: '等于', symbol: '=' },
  { value: 'NE', label: '不等于', symbol: '≠' },
  { value: 'GT', label: '大于', symbol: '>' },
  { value: 'GTE', label: '大于等于', symbol: '≥' },
  { value: 'LT', label: '小于', symbol: '<' },
  { value: 'LTE', label: '小于等于', symbol: '≤' },
  { value: 'IN', label: '属于', symbol: '属于' },
  { value: 'NOT_IN', label: '不属于', symbol: '不属于' },
  { value: 'IS_EMPTY', label: '为空', symbol: '为空' },
  { value: 'NOT_EMPTY', label: '不为空', symbol: '不为空' },
];

const OPERATOR_BY_VALUE = (value) => OPERATORS.find((item) => item.value === value);

/* --------------------------------------------------------------------------
   审批表单：JSON Schema 与"字段列表"之间的转换

   面向非专业用户时表单以字段表维护，Schema 只在高级模式出现。转换时保留原属性
   上没被字段表管理的约束（例如 minimum、pattern），避免来回切换丢失配置。
   -------------------------------------------------------------------------- */

const FORM_FIELD_TYPES = [
  { value: 'string', label: '文本' },
  { value: 'number', label: '数字' },
  { value: 'integer', label: '整数' },
  { value: 'boolean', label: '是 / 否' },
  { value: 'date', label: '日期' },
  { value: 'enum', label: '单选' },
  { value: 'multiselect', label: '多选' },
];

const FORM_FIELD_TYPE_LABEL = (type) => (FORM_FIELD_TYPES.find((item) => item.value === type) || {}).label || type;

const DATE_FORMATS = ['date', 'date-time', 'time'];

/* 只有数字、整数和日期时间字段能参与大小比较，和后端校验保持一致。 */
const ORDERABLE_FIELD_TYPES = ['number', 'integer', 'date'];

function uniqueFieldKey(fields) {
  const taken = new Set(fields.map((field) => field.key));
  let index = fields.length + 1;
  while (taken.has(`field${index}`)) index += 1;
  return `field${index}`;
}

function splitOptions(text) {
  return String(text || '')
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formFieldsFromSchema(schema) {
  const properties = ((schema || {}).properties) || {};
  const required = new Set((schema || {}).required || []);
  const fields = [];
  for (const [key, rule] of Object.entries(properties)) {
    const field = { key, title: rule.title || key, required: required.has(key), type: 'string', options: '' };
    if (rule.type === 'string' && Array.isArray(rule.enum)) {
      field.type = 'enum';
      field.options = rule.enum.join('、');
    } else if (rule.type === 'array' && rule.items && Array.isArray(rule.items.enum)) {
      field.type = 'multiselect';
      field.options = rule.items.enum.join('、');
    } else if (rule.type === 'string' && DATE_FORMATS.includes(rule.format)) {
      field.type = 'date';
      field.options = rule.format;
    } else if (['string', 'number', 'integer', 'boolean'].includes(rule.type)) {
      field.type = rule.type;
    } else {
      // 字段表表达不了的结构（嵌套对象、对象数组等），保留原样并提示走高级模式
      field.type = 'unsupported';
    }
    fields.push(field);
  }
  const simple = fields.every((field) => field.type !== 'unsupported');
  return { fields, simple };
}

function applyFormFields(schema, fields) {
  const originals = (schema || {}).properties || {};
  const properties = {};
  const required = [];
  fields.forEach((field) => {
    if (!field.key) return;
    const rule = Object.assign({}, originals[field.key] || {});
    if (field.type === 'unsupported') {
      properties[field.key] = rule;
      return;
    }
    delete rule.enum;
    delete rule.format;
    delete rule.items;
    if (field.type === 'enum') {
      rule.type = 'string';
      rule.enum = splitOptions(field.options);
    } else if (field.type === 'multiselect') {
      rule.type = 'array';
      rule.items = { type: 'string', enum: splitOptions(field.options) };
    } else if (field.type === 'date') {
      rule.type = 'string';
      rule.format = field.options && DATE_FORMATS.includes(field.options) ? field.options : 'date';
    } else {
      rule.type = field.type;
    }
    rule.title = field.title || field.key;
    properties[field.key] = rule;
    if (field.required) required.push(field.key);
  });
  const next = Object.assign({}, schema || {});
  next.type = 'object';
  next.properties = properties;
  if (required.length) next.required = required;
  else delete next.required;
  return next;
}

/* 条件字段 → 表单里的显示名，用来在画布和弹窗里写成人话。 */
function formFieldLabels(schema) {
  const labels = {};
  formFieldsFromSchema(schema).fields.forEach((field) => {
    labels[`approval_form.${field.key}`] = field.title || field.key;
  });
  return labels;
}

function operatorOptionsForField(field) {
  const orderable = field && ORDERABLE_FIELD_TYPES.includes(field.type);
  const names = field && field.type === 'boolean'
    ? ['EQ', 'NE', 'IS_EMPTY', 'NOT_EMPTY']
    : orderable
      ? ['EQ', 'NE', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'NOT_IN', 'IS_EMPTY', 'NOT_EMPTY']
      : ['EQ', 'NE', 'IN', 'NOT_IN', 'IS_EMPTY', 'NOT_EMPTY'];
  return names.map((name) => {
    const operator = OPERATOR_BY_VALUE(name);
    return { value: operator.value, label: `${operator.label}（${operator.value}）` };
  });
}

/* --------------------------------------------------------------------------
   节点配置：JSON Schema + ui_schema 与"配置项列表"之间的转换

   节点定义的 config_schema_json 描述这个节点允许配置哪些项，ui_schema_json 描述
   用什么控件渲染。两者合起来就是一张配置项表格，用户不需要分别理解两份 JSON。
   转换时同样保留没被表格管理的约束（minItems、pattern 等）。
   -------------------------------------------------------------------------- */

const CONFIG_FIELD_TYPES = [
  { value: 'string', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'integer', label: '整数' },
  { value: 'boolean', label: '是 / 否' },
  { value: 'enum', label: '下拉选择' },
  { value: 'person-select', label: '人员选择器' },
  { value: 'date', label: '日期' },
];

const CONFIG_FIELD_TYPE_LABEL = (type) => (CONFIG_FIELD_TYPES.find((item) => item.value === type) || {}).label || type;

function isPersonItemSchema(items) {
  return Boolean(items && items.type === 'object' && items.properties && items.properties.person_id);
}

function configFieldsFromSchema(schema, uiSchema) {
  const properties = ((schema || {}).properties) || {};
  const ui = uiSchema || {};
  const required = new Set((schema || {}).required || []);
  const fields = [];
  for (const [key, rule] of Object.entries(properties)) {
    const widget = (ui[key] || {})['ui:widget'];
    const field = { key, title: rule.title || key, required: required.has(key), type: 'string', options: '' };
    if (widget === 'person-select' || isPersonItemSchema(rule.items)) {
      field.type = 'person-select';
    } else if (widget === 'textarea') {
      field.type = 'textarea';
    } else if (rule.type === 'string' && Array.isArray(rule.enum)) {
      field.type = 'enum';
      field.options = rule.enum.join('、');
    } else if (rule.type === 'string' && DATE_FORMATS.includes(rule.format)) {
      field.type = 'date';
      field.options = rule.format;
    } else if (['string', 'number', 'integer', 'boolean'].includes(rule.type)) {
      field.type = rule.type;
    } else {
      field.type = 'unsupported';
    }
    fields.push(field);
  }
  return { fields, simple: fields.every((field) => field.type !== 'unsupported') };
}

function applyConfigFields(schema, uiSchema, fields) {
  const originals = (schema || {}).properties || {};
  const originalUi = uiSchema || {};
  const properties = {};
  const ui = Object.assign({}, originalUi); // 保留 ui:order 这类根级规则
  const required = [];

  fields.forEach((field) => {
    if (!field.key) return;
    const rule = Object.assign({}, originals[field.key] || {});
    const uiRule = Object.assign({}, originalUi[field.key] || {});
    if (field.type === 'unsupported') {
      properties[field.key] = rule;
      return;
    }
    delete rule.enum;
    delete rule.format;
    delete rule.items;
    delete uiRule['ui:widget'];

    if (field.type === 'enum') {
      rule.type = 'string';
      rule.enum = splitOptions(field.options);
      uiRule['ui:widget'] = 'select';
    } else if (field.type === 'person-select') {
      rule.type = 'array';
      rule.minItems = rule.minItems || 1;
      rule.items = {
        type: 'object',
        additionalProperties: false,
        required: ['person_id'],
        properties: { person_id: { type: 'string', format: 'uuid', title: '人员 ID' } },
      };
      uiRule['ui:widget'] = 'person-select';
    } else if (field.type === 'textarea') {
      rule.type = 'string';
      uiRule['ui:widget'] = 'textarea';
    } else if (field.type === 'date') {
      rule.type = 'string';
      rule.format = field.options && DATE_FORMATS.includes(field.options) ? field.options : 'date';
    } else {
      rule.type = field.type;
    }
    rule.title = field.title || field.key;
    properties[field.key] = rule;
    if (Object.keys(uiRule).length) ui[field.key] = uiRule;
    else delete ui[field.key];
    if (field.required) required.push(field.key);
  });

  // 已经删掉的配置项不要留下孤立的 ui 配置
  Object.keys(ui).forEach((key) => {
    if (key.indexOf('ui:') !== 0 && !properties[key]) delete ui[key];
  });

  const next = Object.assign({}, schema || {});
  next.type = 'object';
  next.properties = properties;
  if (required.length) next.required = required;
  else delete next.required;
  return { schema: next, uiSchema: ui };
}

/* 比较值要按字段类型转成对应的 JSON 类型，后端按类型逐项比对。 */
function typedConditionValue(field, operator, raw) {
  const text = String(raw === undefined || raw === null ? '' : raw).trim();
  if (operator === 'IN' || operator === 'NOT_IN') {
    const parsed = parseJsonInput(text, '比较值');
    return Array.isArray(parsed) ? parsed : [parsed];
  }
  if (!field) return text;
  if (field.type === 'boolean') return text === 'true';
  if (field.type === 'number' || field.type === 'integer') return Number(text);
  return text;
}

/* 把一条条件写成人话：金额 > 10000、供应商 属于 ["A","B"]、备注 为空 */
function conditionText(condition, labels) {
  if (!condition) return '';
  const operator = OPERATOR_BY_VALUE(condition.operator) || { symbol: condition.operator };
  const name = (labels && labels[condition.field]) || condition.field.replace(/^approval_form\./, '');
  if (condition.operator === 'IS_EMPTY' || condition.operator === 'NOT_EMPTY') return `${name} ${operator.symbol}`;
  const value = condition.value === undefined ? '' : typeof condition.value === 'string' ? condition.value : formatJson(condition.value);
  return `${name} ${operator.symbol} ${value}`;
}

/* 节点卡片上的配置摘要。人工审批和结束节点用固定说法，其余业务类型按配置项平铺。 */
function nodeConfigSummary(node) {
  const config = node.config || {};
  if (node.node_type === 'APPROVAL' && (config.approval_mode || config.approvers)) {
    const mode = config.approval_mode || '—';
    const count = (config.approvers || []).length;
    return `${mode === 'AND' ? '全部同意' : mode === 'OR' ? '任意一人同意' : mode} · ${count} 位审批人`;
  }
  if (node.node_type === 'END') return '流程完成';
  if (node.node_type === 'START') return '流程入口';
  const entries = Object.entries(config).filter(([, value]) => {
    if (value === '' || value === null || value === undefined) return false;
    return !(Array.isArray(value) && !value.length);
  });
  if (!entries.length) return '未配置';
  return entries
    .slice(0, 2)
    .map(([name, value]) => `${name} = ${typeof value === 'object' ? formatJson(value) : value}`)
    .join(' · ');
}

async function renderVersionEditor(versionId) {
  await paint(async () => {
    const [graph, definitions, persons] = await Promise.all([
      api.get(`/api/admin/process-versions/${versionId}/graph`),
      safe(api.get('/api/admin/node-definitions?limit=100'), []),
      safe(api.get('/api/admin/persons?limit=200'), []),
    ]);
    if (!versionId) throw new Error('缺少版本 ID');

    const definitionById = (id) => definitions.find((item) => item.id === id);
    const personName = (id) => {
      const person = persons.find((item) => item.id === id);
      return person ? person.name : shortId(id);
    };

    // 编辑状态留在内存里：切换页签、打开弹窗、重新渲染都不会丢掉还没保存的改动。
    if (!versionEditorState || versionEditorState.versionId !== versionId) {
      const droppedConfigFields = [];
      versionEditorState = {
        versionId,
        processId: graph.process_id,
        versionNo: graph.version_no,
        status: graph.version_status,
        revision: graph.revision,
        name: graph.name,
        description: graph.description,
        formSchema: Object.assign({}, graph.form_schema || {}),
        formAdvanced: false,
        nodes: graph.nodes.map((node) => {
          const pruned = pruneNodeConfig(node, definitionById(node.node_definition_id));
          droppedConfigFields.push(...pruned.dropped);
          return {
            id: node.id,
            node_definition_id: node.node_definition_id,
            node_type: node.node_type,
            node_definition_name: node.node_definition_name,
            name: node.name,
            config: pruned.config,
            position: Object.assign({}, node.position),
          };
        }),
        connections: ((graph.orchestration || {}).connections || []).map((item) => Object.assign({}, item)),
        dirty: false,
      };
      // 清理过一次就够了，提示一句让用户知道草稿里少了个配置项
      if (droppedConfigFields.length) {
        toast(`已按节点定义忽略失效配置：${[...new Set(droppedConfigFields)].join('、')}`, 'ok');
      }
    }
    const state = versionEditorState;
    const editable = state.status === 'DRAFT';
    const nodes = state.nodes;
    let connections = state.connections;

    const personOptions = persons.map((person) => ({ value: person.id, label: `${person.name}（${shortId(person.id)}）` }));

    /* 空位：放在最右侧一列的下面，避免新节点叠在一起。 */
    function defaultPositionFor() {
      const rightMost = nodes.reduce((max, node) => Math.max(max, nodeBox(node).x), FLOW_PADDING - (FLOW_NODE_WIDTH + 88));
      return {
        x: rightMost + FLOW_NODE_WIDTH + 88,
        y: FLOW_PADDING + (nodes.length % 3) * (FLOW_NODE_HEIGHT + 42),
      };
    }

    /* 把节点定义的 config_schema_json 翻译成弹窗字段，ui_schema_json 里的
       ui:widget=person-select 会渲染成人员选择器，其余按 JSON Schema 基本类型映射。 */
    function buildConfigForm(definition, config) {
      const schema = definition.config_schema_json || {};
      const uiSchema = definition.ui_schema_json || {};
      const properties = schema.properties || {};
      const names = Object.keys(properties);
      const required = new Set(schema.required || []);
      const fields = [];
      const values = {};

      for (const name of names) {
        const rule = properties[name] || {};
        const widget = (uiSchema[name] || {})['ui:widget'];
        const label = `${rule.title || name}${required.has(name) ? ' *' : ''}`;
        const current = config[name];

        if (widget === 'person-select') {
          const itemKeys = ((rule.items || {}).required) || [];
          const itemKey = itemKeys[0] || 'person_id';
          fields.push({ name, label, type: 'multiselect', options: personOptions, wide: true, hint: rule.description || '按住 Ctrl 或 Shift 多选' });
          values[name] = (current || []).map((item) => (item || {})[itemKey]).filter(Boolean);
        } else if (widget === 'textarea') {
          fields.push({ name, label, type: 'textarea', wide: true, hint: rule.description });
          values[name] = current === undefined || current === null ? '' : current;
        } else if (Array.isArray(rule.enum)) {
          fields.push({ name, label, type: 'select', options: rule.enum.map((value) => ({ value, label: String(value) })), hint: rule.description });
          values[name] = current === undefined || current === null ? rule.enum[0] : current;
        } else if (rule.type === 'boolean') {
          fields.push({ name, label, type: 'checkbox', checkboxLabel: rule.description || '是' });
          values[name] = Boolean(current);
        } else if (rule.type === 'integer' || rule.type === 'number') {
          fields.push({ name, label, type: 'number', hint: rule.description });
          values[name] = current === undefined || current === null ? '' : current;
        } else if (rule.type === 'array' || rule.type === 'object') {
          fields.push({ name, label, type: 'code', wide: true, hint: rule.description || `${rule.type === 'array' ? '数组' : '对象'}，按 JSON 填写` });
          values[name] = current === undefined ? (rule.type === 'array' ? '[]' : '{}') : formatJson(current);
        } else {
          fields.push({ name, label, type: 'text', hint: rule.description });
          values[name] = current === undefined || current === null ? '' : current;
        }
      }

      const fromForm = (formValues) => {
        const next = {};
        for (const name of names) {
          const rule = properties[name] || {};
          const widget = (uiSchema[name] || {})['ui:widget'];
          const raw = formValues[name];
          if (widget === 'person-select') {
            const itemKey = (((rule.items || {}).required) || [])[0] || 'person_id';
            next[name] = (raw || []).map((value) => ({ [itemKey]: value }));
          } else if (widget === 'textarea') {
            next[name] = raw;
          } else if (rule.type === 'array' || rule.type === 'object') {
            next[name] = parseJsonInput(raw, rule.title || name);
          } else if (rule.type === 'integer' || rule.type === 'number') {
            next[name] = raw === '' || raw === null ? null : Number(raw);
          } else if (rule.type === 'boolean') {
            next[name] = Boolean(raw);
          } else {
            next[name] = raw;
          }
        }
        return next;
      };

      return { fields, values, fromForm, hasSchema: names.length > 0 };
    }

    function nodeDialog(existing, definition, presetPosition) {
      const isNew = !existing;
      const target = definition || definitionById(existing.node_definition_id) || {
        id: existing.node_definition_id,
        name: NODE_TYPE_TEXT[existing.node_type] || existing.node_type,
        node_type: existing.node_type,
        config_schema_json: {},
        ui_schema_json: {},
      };
      const base = existing || {
        id: uuid4(),
        node_definition_id: target.id,
        node_type: target.node_type,
        node_definition_name: target.name,
        name: target.name,
        config: defaultConfigFor(target),
        position: presetPosition || {},
      };
      const form = buildConfigForm(target, base.config || {});

      formDialog({
        title: isNew ? `新增节点 · ${target.name}` : `编辑节点 · ${base.name}`,
        // 当前取值要回填，否则下拉框会停在第一个选项上，保存时把原配置改掉
        values: Object.assign({ name: base.name }, form.values),
        fields: [
          { name: 'name', label: '节点名称', type: 'text', placeholder: target.name, hint: `画布上显示的名称，留空就用定义名「${target.name}」` },
          ...form.fields,
          ...(form.hasSchema
            ? []
            : target.node_type === 'START'
              ? [{
                  type: 'note',
                  html: '开始节点本身没有可配置项。<strong>这条流程要收集哪些数据</strong>（金额、供应商这类）在下面的「审批表单」里定义。'
                    + ' <button class="btn--link btn--sm" data-act="goto-form">去配置表单字段</button>',
                }]
              : target.node_type === 'CONDITION'
                ? [{
                    type: 'note',
                    html: '条件分支的规则不在这个窗口里配。<strong>点画布上节点卡片里的分支行</strong>，或点这里'
                      + ' <button class="btn--link btn--sm" data-act="goto-branch" data-id="' + esc(base.id) + '">去配置分支</button>'
                      + ' 打开分支编辑器，那里可以增删条件和调整顺序。<br>'
                      + '每条分支去哪，关掉窗口后从卡片上对应那一行的圆点拉线到目标节点。',
                  }]
                : target.node_type === 'END'
                  ? [{
                      type: 'note',
                      html: '结束节点没有配置项。<strong>走到这里就是审批通过、流程完成</strong>；'
                        + '审批被拒绝时实例在审批人点拒绝的那一刻就结束了，不会走到结束节点。',
                    }]
                  : [{ type: 'note', html: '这个节点没有可配置项。' }]),
        ],
        submitText: isNew ? '添加节点' : '保存节点',
        wide: true,
        onSubmit: async (values) => {
          const node = {
            id: base.id,
            node_definition_id: target.id,
            node_type: target.node_type,
            node_definition_name: target.name,
            // 不命名（或清空）就用定义名，不拦着用户必须起名字
            name: (values.name || '').trim() || target.name,
            // 没有配置项时保持原配置不变，避免把已有数据清空
            config: form.hasSchema ? form.fromForm(values) : Object.assign({}, base.config || {}),
            position: Object.keys(base.position || {}).length ? base.position : defaultPositionFor(),
          };
          if (isNew) nodes.push(node);
          else Object.assign(nodes.find((item) => item.id === base.id), node);
          markDirty();
          renderVersionEditor(versionId);
        },
      });
    }

    /* 从左侧面板拖入或点击新增一个节点，并立刻打开配置弹窗。 */
    function createNodeFromDefinition(definitionId, position) {
      if (!editable) {
        toast('已发布版本只读，不能新增节点', 'err');
        return;
      }
      const definition = definitions.find((item) => item.id === definitionId);
      if (!definition) {
        toast('节点定义不存在，请刷新页面', 'err');
        return;
      }
      if (definition.node_type === 'START' && nodes.some((node) => node.node_type === 'START')) {
        toast('每条流程只能有一个开始节点', 'err');
        return;
      }
      nodes.push({
        id: uuid4(),
        node_definition_id: definition.id,
        node_type: definition.node_type,
        node_definition_name: definition.name,
        name: definition.name,
        config: defaultConfigFor(definition),
        position: position || defaultPositionFor(),
      });
      markDirty();
      renderVersionEditor(versionId);
      nodeDialog(nodes[nodes.length - 1], definition);
    }

    /* 连线配置弹窗。连线本身由画布拖拽或 + 号产生，这里只负责"这条线是什么"。 */

    function collectPayload() {
      // 高级模式下以文本框内容为准；JSON 非法时这里直接抛错，保存被挡下
      if (state.formAdvanced || !formFieldsFromSchema(state.formSchema).simple) {
        const area = document.getElementById('form-schema');
        if (area) state.formSchema = parseJsonInput(area.value, '审批表单 Schema');
      }
      return {
        revision: state.revision,
        name: state.name,
        description: state.description || null,
        nodes: nodes.map((node) => ({
          id: node.id,
          node_definition_id: node.node_definition_id,
          name: node.name,
          config: node.config,
          position: node.position,
        })),
        orchestration: { connections: connections.map((item) => Object.assign({}, item)) },
        form_schema: state.formSchema,
      };
    }

    /* 画布上拖动过节点就提示未保存，避免调整完位置直接切走。 */
    function markDirty() {
      state.dirty = true;
      const chip = document.getElementById('flow-dirty');
      if (chip) chip.hidden = false;
    }

    /* 审批表单：默认用字段表维护，Schema 只在高级模式出现。 */
    function formPanelHtml() {
      const parsed = formFieldsFromSchema(state.formSchema);
      const useAdvanced = state.formAdvanced || !parsed.simple;
      const head = `<div class="panel__head">
        <h2 class="panel__title">审批表单</h2>
        <div class="flow-bar">
          <span class="panel__note">审批单上要填什么、分支条件能引用哪些字段，都由这里决定</span>
          ${editable
            ? `<button class="btn btn--sm" data-act="form-mode" data-mode="${useAdvanced ? 'simple' : 'advanced'}">
                 ${useAdvanced ? '切到字段模式' : '高级模式（JSON）'}
               </button>`
            : ''}
        </div>
      </div>`;

      if (useAdvanced) {
        const warning = parsed.simple
          ? ''
          : '<div class="note note--wait" style="margin-bottom:12px">这份表单含字段模式表达不了的结构（例如嵌套对象），已自动切到高级模式，避免编辑时丢配置。</div>';
        return `<div class="panel">${head}
          <div class="panel__body">
            ${warning}
            <div class="note" style="margin-bottom:12px">
              JSON Schema，根类型必须是 object。字段用 properties 声明，必填写进 required；
              分支条件引用的字段必须在这里定义。
            </div>
            <textarea class="textarea textarea--code" id="form-schema" ${editable ? '' : 'readonly'}>${esc(formatJson(state.formSchema))}</textarea>
          </div>
        </div>`;
      }

      const fields = parsed.fields;
      const rows = fields
        .map((field, index) => `<tr data-form-row="${index}">
          <td><input class="input input--cell" data-act="form-field" data-index="${index}" data-prop="key" value="${esc(field.key)}" ${editable ? '' : 'readonly'}></td>
          <td><input class="input input--cell" data-act="form-field" data-index="${index}" data-prop="title" value="${esc(field.title)}" placeholder="显示给填写人看" ${editable ? '' : 'readonly'}></td>
          <td>
            <select class="select input--cell" data-act="form-field" data-index="${index}" data-prop="type" ${editable ? '' : 'disabled'}>
              ${FORM_FIELD_TYPES.map((type) => `<option value="${type.value}"${type.value === field.type ? ' selected' : ''}>${esc(type.label)}</option>`).join('')}
            </select>
          </td>
          <td style="text-align:center">
            <input type="checkbox" data-act="form-field" data-index="${index}" data-prop="required"${field.required ? ' checked' : ''} ${editable ? '' : 'disabled'}>
          </td>
          <td>
            ${field.type === 'enum' || field.type === 'multiselect'
              ? `<input class="input input--cell" data-act="form-field" data-index="${index}" data-prop="options" value="${esc(field.options)}" placeholder="用、分隔，例如 差旅、采购" ${editable ? '' : 'readonly'}>`
              : field.type === 'date'
                ? `<select class="select input--cell" data-act="form-field" data-index="${index}" data-prop="options" ${editable ? '' : 'disabled'}>
                     ${DATE_FORMATS.map((format) => `<option value="${format}"${format === field.options ? ' selected' : ''}>${format === 'date' ? '日期' : format === 'date-time' ? '日期时间' : '时间'}</option>`).join('')}
                   </select>`
                : '<span class="muted">—</span>'}
          </td>
          <td class="is-actions">
            ${editable
              ? `<button class="btn--link btn--sm" data-act="form-field-up" data-index="${index}">上移</button>
                 <button class="btn--link btn--sm" data-act="form-field-down" data-index="${index}">下移</button>
                 <button class="btn--link btn--sm is-danger" data-act="form-field-drop" data-index="${index}">删除</button>`
              : ''}
          </td>
        </tr>`)
        .join('');

      return `<div class="panel">${head}
        <div class="panel__body" style="padding-bottom:14px">
          <div class="note">
            这里定义审批单上要填的内容。业务系统发起审批时按这些字段校验数据，审批流的分支条件也从这里选字段。
            字段键是数据里的名字（建议只用字母、数字和下划线），显示名是给填写人看的。改成已有的字段键会覆盖原字段定义。
          </div>
        </div>
        ${fields.length
          ? `<div class="tbl-wrap"><table class="tbl field-tbl">
               <thead><tr><th>字段键</th><th>显示名</th><th>类型</th><th>必填</th><th>选项 / 格式</th><th></th></tr></thead>
               <tbody>${rows}</tbody>
             </table></div>`
          : `<div class="empty"><div class="empty__title">还没有表单字段</div><div>没有字段时，发起审批不需要填写任何表单数据。</div></div>`}
        ${editable
          ? `<div class="panel__body" style="border-top:1px solid var(--rule-weak)">
               <button class="btn btn--sm btn--primary" data-act="form-field-add">新增字段</button>
             </div>`
          : ''}
      </div>`;
    }

    function updateFormField(index, prop, value) {
      const fields = formFieldsFromSchema(state.formSchema).fields;
      if (!fields[index]) return;
      fields[index][prop] = value;
      state.formSchema = applyFormFields(state.formSchema, fields);
      markDirty();
    }

    function moveFormField(index, step) {
      const fields = formFieldsFromSchema(state.formSchema).fields;
      const target = index + step;
      if (target < 0 || target >= fields.length) return;
      const moved = fields.splice(index, 1)[0];
      fields.splice(target, 0, moved);
      state.formSchema = applyFormFields(state.formSchema, fields);
      markDirty();
      renderVersionEditor(versionId);
    }

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'version-tab': (el) => {
        versionTab = el.dataset.tab;
        renderVersionEditor(versionId);
      },
      'palette-add': (el) => createNodeFromDefinition(el.dataset.definitionId, null),
      // 线中点上的 ×：普通连线直接删，条件分支的一条线只断开去向（分支和条件留着）
      'drop-connection': (el) => {
        const index = Number(el.dataset.conn);
        const connection = connections[index];
        if (!connection) return;
        const node = nodes.find((item) => item.id === connection.source_node_id);
        if (node && node.node_type === 'CONDITION') {
          connection.target_node_id = null;
          toast('已断开这条分支的去向，分支和条件还留着', 'ok');
        } else {
          connections.splice(index, 1);
          toast('已删除这条连线', 'ok');
        }
        markDirty();
        renderVersionEditor(versionId);
      },
      'edit-branch': (el) => {
        const node = nodes.find((item) => item.id === el.dataset.id);
        if (!node) return;
        openBranchDialog(node, nodes, connections, state.formSchema, (built) => {
          // 用弹窗里的阶梯重建这个节点的出线：顺序就是运行时的匹配顺序
          const others = connections.filter((connection) => connection.source_node_id !== node.id);
          const rebuilt = built.map((branch) => {
            const connection = { source_node_id: node.id, target_node_id: branch.target_node_id };
            if (branch.condition) connection.condition = branch.condition;
            return connection;
          });
          connections.length = 0;
          connections.push(...others, ...rebuilt);
          markDirty();
          renderVersionEditor(versionId);
        });
      },
      'goto-branch': (el) => {
        const node = nodes.find((item) => item.id === el.dataset.id);
        closeOverlay();
        if (node) actions['edit-branch']({ dataset: { id: node.id } });
      },
      // 从节点配置弹窗跳到审批表单：流程要收集哪些数据是在流程里配的，不在节点定义里
      'goto-form': () => {
        versionTab = 'form';
        closeOverlay();
        renderVersionEditor(versionId);
        window.scrollTo({ top: 0 });
      },
      'form-mode': (el) => {
        state.formAdvanced = el.dataset.mode === 'advanced';
        renderVersionEditor(versionId);
      },
      'form-field': (el) => {
        const index = Number(el.dataset.index);
        const prop = el.dataset.prop;
        if (prop === 'required') {
          updateFormField(index, prop, Boolean(el.checked));
          return;
        }
        updateFormField(index, prop, el.value);
        // 类型变了要重画整行（选项列和格式列跟着换）
        if (prop === 'type') renderVersionEditor(versionId);
      },
      'form-field-add': () => {
        const fields = formFieldsFromSchema(state.formSchema).fields;
        fields.push({ key: uniqueFieldKey(fields), title: '新字段', type: 'string', required: false, options: '' });
        state.formSchema = applyFormFields(state.formSchema, fields);
        markDirty();
        renderVersionEditor(versionId);
      },
      'form-field-drop': (el) => {
        const fields = formFieldsFromSchema(state.formSchema).fields;
        fields.splice(Number(el.dataset.index), 1);
        state.formSchema = applyFormFields(state.formSchema, fields);
        markDirty();
        renderVersionEditor(versionId);
      },
      'form-field-up': (el) => moveFormField(Number(el.dataset.index), -1),
      'form-field-down': (el) => moveFormField(Number(el.dataset.index), 1),
      'flow-layout': () => {
        autoLayoutNodes(nodes, connections);
        markDirty();
        renderVersionEditor(versionId);
      },
      'edit-node': (el) => nodeDialog(nodes.find((node) => node.id === el.dataset.id)),
      'drop-node': async (el) => {
        const node = nodes.find((item) => item.id === el.dataset.id);
        if (!(await confirmDialog({ title: '删除节点', message: `删除“${node.name}”会同时移除与它相关的连线，需要先保存草稿才会生效。确认删除？`, submitText: '删除', danger: true }))) return;
        nodes.splice(nodes.indexOf(node), 1);
        // 就地删除，保持 connections 与编辑状态指向同一个数组。
        for (let index = connections.length - 1; index >= 0; index -= 1) {
          if (connections[index].source_node_id === node.id || connections[index].target_node_id === node.id) {
            connections.splice(index, 1);
          }
        }
        markDirty();
        renderVersionEditor(versionId);
      },
      'save-graph': async () => {
        const saved = await api.put(`/api/admin/process-versions/${versionId}/graph`, collectPayload());
        toast(`草稿已保存，修订号 ${saved.revision}`, 'ok');
        // 保存成功后丢弃本地副本，重新按服务端数据建立编辑状态。
        versionEditorState = null;
        renderVersionEditor(versionId);
      },
      'validate': async () => {
        const result = await api.post(`/api/admin/process-versions/${versionId}/validate`);
        showIssues(result.valid ? '校验通过' : '校验未通过', result.issues);
      },
      'publish': async () => {
        if (!(await confirmDialog({ title: '发布版本', message: '发布会执行完整校验并把该版本切换为流程当前版本。确认发布？', submitText: '发布' }))) return;
        try {
          await api.post(`/api/admin/process-versions/${versionId}/publish`);
          toast('版本已发布', 'ok');
          location.hash = `#/processes/${graph.process_id}`;
        } catch (err) {
          toast(err.message, 'err');
        }
      },
    });

    const html = `${breadcrumb([
      { text: '审批流', href: '#/processes' },
      { text: state.name, href: `#/processes/${state.processId}` },
      { text: `V${state.versionNo}` },
    ])}
    ${pageHead(
      `${state.name} · V${state.versionNo}`,
      editable
        ? '草稿可编辑。保存会整体覆盖节点和连线，并使用修订号防止多人同时编辑互相覆盖。'
        : '已发布版本永久只读，用于追溯历史实例使用的流程；需要修改请回到流程页创建下一版草稿。',
      `${tag(state.status)}
       ${editable
         ? `<button class="btn" data-act="validate">校验</button>
            <button class="btn btn--primary" data-act="save-graph">保存草稿</button>
            <button class="btn btn--primary" data-act="publish">发布</button>`
         : `<button class="btn" data-act="validate">校验</button>`}`
    )}

    <div class="panel"><div class="panel__body">
      ${kvHtml([
        ['版本 ID', `<span class="code">${esc(state.versionId)}</span>`],
        ['修订号', `<span class="code">${esc(state.revision)}</span>`],
        ['更新时间', esc(fmtTime(graph.updated_at))],
        ['发布时间', esc(fmtTime(graph.published_at))],
      ])}
    </div></div>

    ${editable && flowNeedsLayout(nodes)
      ? `<div class="panel"><div class="panel__body" style="padding-bottom:0">
           <div class="note note--work">检测到节点位置缺失或重叠。点画布上方的“自动排版”可以按连线关系重新摆放。</div>
         </div></div>`
      : ''}

    <div class="panel">
      <div class="panel__head">
        <h2 class="panel__title">流程画布</h2>
        <div class="flow-bar">
          ${editable
            ? `<button class="btn btn--sm" data-act="flow-layout">自动排版</button>`
            : '<span class="panel__note">已发布版本只读，只能查看</span>'}
          <span id="flow-dirty" class="tag tag--wait"${state.dirty ? '' : ' hidden'}>有未保存的改动</span>
          <span class="flow-bar__zoom">
            <button id="flow-zoom-out" title="缩小">−</button>
            <span id="flow-zoom-value">100%</span>
            <button id="flow-zoom-in" title="放大">+</button>
            <button id="flow-zoom-fit" title="适应画布" style="width:auto;padding:0 8px;font-size:12px">适应</button>
          </span>
        </div>
      </div>
      <div class="flow-shell">
        ${flowPaletteHtml(definitions, nodes, editable)}
        ${flowCanvasHtml(nodes, connections, editable, formFieldLabels(state.formSchema))}
      </div>
      <div class="panel__body" style="padding-top:12px">
        <div class="note">
          从左侧把节点拖到画布上新增，拖动节点摆位置，从节点右侧的圆点拖到另一个节点就连上了。
          <strong>普通节点只能有一条去向</strong>，需要分流就放一个「条件分支」节点：
          点它卡片上的分支行打开分支编辑器，前面每条写“如果……”，最后一条是“其余情况”兜底，
          每条分支自己有一个出口，线从那里引出。没配完的分支行会标黄。
          画布改动要点“保存草稿”才写入后端。
        </div>
      </div>
    </div>

    <div class="tabs">
      ${[['form', '审批表单 Schema'], ['raw', '编排数据']]
        .map(([key, label]) => `<button class="tab${versionTab === key ? ' tab--active' : ''}" data-act="version-tab" data-tab="${key}">${label}</button>`)
        .join('')}
    </div>

    ${versionTab === 'form' ? formPanelHtml() : ''}

    ${versionTab === 'raw'
      ? `<div class="panel">
          <div class="panel__head"><h2 class="panel__title">当前编排数据</h2>
            <span class="panel__note">点“保存草稿”时提交的内容，便于核对接口字段</span></div>
          <div class="panel__body">
            <pre class="raw-json">${esc(formatJson({
              revision: state.revision,
              nodes: nodes.map((node) => ({ id: node.id, node_definition_id: node.node_definition_id, name: node.name, config: node.config })),
              orchestration: { connections },
            }))}</pre>
          </div>
        </div>`
      : ''}`;

    return {
      html,
      mount: () => {
        // 高级模式：失焦时顺手更新一次，让画布上的条件措辞跟着变；非法 JSON 留给保存时挡下
        const area = document.getElementById('form-schema');
        if (area && area.addEventListener) {
          area.addEventListener('change', () => {
            try {
              state.formSchema = JSON.parse(area.value);
            } catch (err) {
              /* 保存时会再校验一次并提示具体错误 */
            }
          });
        }
        mountFlowCanvas({
          nodes,
          connections,
          editable,
          onSelect: (id) => nodeDialog(nodes.find((node) => node.id === id)),
          // 从分支行的圆点拖线 = 给这条分支定去向；从节点右侧的圆点拖线 = 连到下一个节点
          onConnect: (sourceId, targetId, branch) => {
            if (branch !== null && branch !== undefined) {
              const result = connectBranchTo(connections, sourceId, branch, targetId);
              if (!result) return;
              markDirty();
              renderVersionEditor(versionId);
              // 新开的分支只要不是兜底那条，就得说明什么条件下走——顺手把配置窗口打开
              if (result.needsCondition) {
                actions['edit-branch']({ dataset: { id: sourceId } });
              }
              return;
            }
            if (hasConnection(connections, sourceId, targetId)) {
              toast('这两个节点已经连过了', 'err');
              return;
            }
            // 普通节点只能有一条出线，想分流就用条件分支节点
            const siblings = connections.filter((item) => item.source_node_id === sourceId);
            if (siblings.length) {
              toast('普通节点只能有一条去向，要分流请加一个条件分支节点', 'err');
              return;
            }
            connections.push({ source_node_id: sourceId, target_node_id: targetId });
            markDirty();
            renderVersionEditor(versionId);
          },
          onCreateNode: (definitionId, position) => createNodeFromDefinition(definitionId, position),
          // 拖拽预览就用节点卡本身，样子和落到画布上之后完全一致
          renderGhost: (definitionId) => {
            const definition = definitionById(definitionId);
            if (!definition) return null;
            const preview = { node_type: definition.node_type, config: defaultConfigFor(definition) };
            return `<div class="flow__node flow__node--${flowNodeVariant(preview)} flow__node--ghost">
              <div class="flow__node-head">
                <span class="flow__node-type">${esc(definition.name)}</span>
                <span class="flow__node-name">${esc(definition.name)}</span>
              </div>
              <div class="flow__node-desc">${esc(nodeConfigSummary(preview))}</div>
            </div>`;
          },
          onMoved: markDirty,
        });
      },
    };
  });
}

/* --------------------------------------------------------------------------
   15. 业务动作
   -------------------------------------------------------------------------- */

async function renderActions() {
  await paint(async () => {
    const actionsList = await api.get('/api/admin/business-actions?limit=200');
    railCounts.actions = actionsList.length;

    const fields = (isNew) => [
      { name: 'action_code', label: '动作标识', type: 'text', required: isNew, placeholder: 'PAYMENT_EXECUTE', hint: isNew ? '全局唯一，统一转大写，创建后不可修改' : '动作标识创建后不可修改，这里仅作展示' },
      { name: 'name', label: '动作名称', type: 'text', required: true, placeholder: '执行付款' },
      { name: 'http_method', label: '调用方法', type: 'select', options: [{ value: 'POST', label: 'POST' }, { value: 'PUT', label: 'PUT' }, { value: 'PATCH', label: 'PATCH' }] },
      { name: 'relative_path', label: '相对路径', type: 'text', required: true, placeholder: '/payments/execute', hint: '必须以单个 / 开头；实际地址由租户的回调基础地址拼接得到' },
      { name: 'timeout_ms', label: '超时时间（毫秒）', type: 'number', placeholder: '5000' },
      { name: 'success_status_codes', label: '成功状态码', type: 'text', placeholder: '200,201', hint: '逗号分隔；留空表示全部 2xx 视为成功' },
      {
        name: 'request_schema_json',
        label: '执行参数 Schema',
        type: 'code',
        wide: true,
        hint: '校验发起审批时传入的 execution_payload，根类型必须是 object',
        placeholder: '{\n  "type": "object",\n  "required": ["payment_id"],\n  "properties": { "payment_id": { "type": "string" } }\n}',
      },
    ];

    function payloadOf(values, isNew) {
      const body = {
        name: values.name,
        description: values.description || null,
        http_method: values.http_method || 'POST',
        relative_path: values.relative_path,
        request_schema_json: parseJsonInput(values.request_schema_json, '执行参数 Schema'),
        timeout_ms: values.timeout_ms === null ? 5000 : values.timeout_ms,
      };
      body.success_status_codes = values.success_status_codes
        ? values.success_status_codes.split(',').map((item) => Number(item.trim())).filter((item) => !Number.isNaN(item))
        : undefined;
      if (isNew) body.action_code = values.action_code;
      else body.status = values.status;
      return body;
    }

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'new-action': () =>
        formDialog({
          title: '新建业务动作',
          fields: fields(true),
          values: { http_method: 'POST', timeout_ms: 5000, request_schema_json: '' },
          submitText: '创建动作',
          wide: true,
          onSubmit: async (values) => {
            await api.post('/api/admin/business-actions', payloadOf(values, true));
            toast('业务动作已创建', 'ok');
            renderActions();
          },
        }),
      'edit-action': (el) => {
        const action = actionsList.find((item) => item.id === el.dataset.id);
        formDialog({
          title: `编辑业务动作 · ${action.name}`,
          fields: fields(false).concat([
            { name: 'status', label: '状态', type: 'select', options: [{ value: 'ENABLED', label: '启用' }, { value: 'DISABLED', label: '停用' }], hint: '停用后不能用于新申请，已经运行的实例不受影响' },
          ]),
          values: {
            action_code: action.action_code,
            name: action.name,
            http_method: action.http_method,
            relative_path: action.relative_path,
            timeout_ms: action.timeout_ms,
            success_status_codes: (action.success_status_codes || []).join(','),
            request_schema_json: Object.keys(action.request_schema || {}).length ? formatJson(action.request_schema) : '',
            status: action.status,
          },
          wide: true,
          onSubmit: async (values) => {
            await api.patch(`/api/admin/business-actions/${action.id}`, payloadOf(values, false));
            toast('业务动作已更新', 'ok');
            renderActions();
          },
        });
      },
    });

    return `${pageHead(
      '业务动作',
      '业务动作描述审批通过后要调用的业务接口。实际请求地址由租户的回调基础地址加相对路径组成，认证使用租户配置的 Service Token。',
      `<button class="btn btn--primary" data-act="new-action">新建业务动作</button>`
    )}
    <div class="panel">
      ${tableHtml(
        [
          { title: '动作标识', render: (row) => `<span class="cell-title code">${esc(row.action_code)}</span>` },
          { title: '名称', render: (row) => esc(row.name) },
          { title: '调用', render: (row) => `<span class="code">${esc(row.http_method)} ${esc(row.relative_path)}</span>` },
          { title: '成功状态码', render: (row) => `<span class="code">${(row.success_status_codes || []).length ? esc(row.success_status_codes.join(', ')) : '全部 2xx'}</span>` },
          { title: '超时', cls: 'is-num', render: (row) => `${esc(row.timeout_ms)} ms` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '操作', cls: 'is-actions', render: (row) => `<button class="btn--link btn--sm" data-act="edit-action" data-id="${esc(row.id)}">编辑</button>` },
        ],
        actionsList,
        { title: '还没有业务动作', hint: '如果审批通过后不需要回调业务系统，可以跳过这一步。' }
      )}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   16. 租户资源授权
   -------------------------------------------------------------------------- */

async function renderGrants() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const tenantParam = params.get('tenant') || '';

  await paint(async () => {
    const [tenants, processes, actionsList] = await Promise.all([
      loadTenantList(),
      safe(api.get('/api/admin/processes?limit=200'), []),
      safe(api.get('/api/admin/business-actions?limit=200'), []),
    ]);

    if (!tenants.length) {
      return `${pageHead('资源授权', '租户只有被授权后，才能用对应流程发起审批、触发对应业务动作。', '')}
        <div class="panel"><div class="empty"><div class="empty__title">还没有租户</div>
        <div>先创建租户，再回来配置授权。</div>
        <p><a class="btn btn--sm" href="#/tenants">去创建租户</a></p></div></div>`;
    }

    const targets = tenantParam ? tenants.filter((item) => item.id === tenantParam) : tenants;
    const [processGroups, actionGroups] = await Promise.all([
      Promise.all(targets.map((tenant) => safe(api.get(`/api/admin/tenants/${tenant.id}/process-bindings`), []))),
      Promise.all(targets.map((tenant) => safe(api.get(`/api/admin/tenants/${tenant.id}/business-action-bindings`), []))),
    ]);
    const withTenant = (groups) =>
      groups.flatMap((list, index) =>
        list.map((item) => Object.assign({}, item, { tenant_name: targets[index].name }))
      );
    const processBindings = withTenant(processGroups);
    const actionBindings = withTenant(actionGroups);

    const processName = (id) => {
      const process = processes.find((item) => item.id === id);
      return process ? process.name : shortId(id);
    };
    const actionName = (id) => {
      const action = actionsList.find((item) => item.id === id);
      return action ? `${action.name}（${action.action_code}）` : shortId(id);
    };
    const tenantOptions = tenants.map((item) => ({ value: item.id, label: item.name }));

    setActions({
      'filter': () => {
        const value = document.getElementById('grant-tenant').value;
        location.hash = value ? `#/grants?tenant=${value}` : '#/grants';
      },
      'bind-process': () =>
        formDialog({
          title: '授权租户使用审批流',
          fields: [
            { name: 'tenant_id', label: '租户', type: 'select', required: true, options: tenantOptions },
            { name: 'process_id', label: '审批流', type: 'select', required: true, options: processes.map((item) => ({ value: item.id, label: `${item.name}${item.status === 'DISABLED' ? '（已停用）' : ''}` })) },
          ],
          values: {},
          submitText: '授权',
          onSubmit: async (values) => {
            await api.post(`/api/admin/tenants/${values.tenant_id}/process-bindings`, { process_id: values.process_id });
            toast('已授权', 'ok');
            renderGrants();
          },
        }),
      'bind-action': () =>
        formDialog({
          title: '授权租户使用业务动作',
          fields: [
            { name: 'tenant_id', label: '租户', type: 'select', required: true, options: tenantOptions },
            { name: 'business_action_id', label: '业务动作', type: 'select', required: true, options: actionsList.map((item) => ({ value: item.id, label: `${item.name}（${item.action_code}）` })) },
          ],
          values: {},
          submitText: '授权',
          onSubmit: async (values) => {
            await api.post(`/api/admin/tenants/${values.tenant_id}/business-action-bindings`, { business_action_id: values.business_action_id });
            toast('已授权', 'ok');
            renderGrants();
          },
        }),
      'toggle-process-binding': async (el) => {
        await api.patch(`/api/admin/tenants/${el.dataset.tenant}/process-bindings/${el.dataset.id}`, { status: el.dataset.next });
        toast('授权状态已更新', 'ok');
        renderGrants();
      },
      'toggle-action-binding': async (el) => {
        await api.patch(`/api/admin/tenants/${el.dataset.tenant}/business-action-bindings/${el.dataset.id}`, { status: el.dataset.next });
        toast('授权状态已更新', 'ok');
        renderGrants();
      },
    });

    return `${pageHead(
      '资源授权',
      '全部租户的授权关系合并展示。授权只决定租户能否使用某个流程或动作，不覆盖流程内部的版本、节点和审批人配置；停用授权不影响已经运行的审批实例。',
      `<select class="select" id="grant-tenant" style="width:180px" data-act="filter">
         <option value="">全部租户</option>
         ${tenants.map((item) => `<option value="${esc(item.id)}"${item.id === tenantParam ? ' selected' : ''}>${esc(item.name)}</option>`).join('')}
       </select>`
    )}
    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">审批流授权</h2>
        <button class="btn btn--sm btn--primary" data-act="bind-process">授权审批流</button></div>
      ${tableHtml(
        [
          { title: '租户', render: (row) => `<span class="cell-title">${esc(row.tenant_name)}</span>` },
          { title: '审批流', render: (row) => esc(processName(row.process_id)) },
          { title: '流程 ID', render: (row) => `<span class="code">${esc(shortId(row.process_id))}</span>` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '授权时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<button class="btn--link btn--sm" data-act="toggle-process-binding" data-id="${esc(row.id)}" data-tenant="${esc(row.tenant_id)}" data-next="${row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'}">${row.status === 'ENABLED' ? '停用' : '启用'}</button>`,
          },
        ],
        processBindings,
        { title: '还没有审批流授权', hint: '授权后业务系统才能用这条流程发起审批。' }
      )}
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">业务动作授权</h2>
        <button class="btn btn--sm btn--primary" data-act="bind-action">授权业务动作</button></div>
      ${tableHtml(
        [
          { title: '租户', render: (row) => `<span class="cell-title">${esc(row.tenant_name)}</span>` },
          { title: '业务动作', render: (row) => esc(actionName(row.business_action_id)) },
          { title: '动作 ID', render: (row) => `<span class="code">${esc(shortId(row.business_action_id))}</span>` },
          { title: '状态', render: (row) => tag(row.status) },
          { title: '授权时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<button class="btn--link btn--sm" data-act="toggle-action-binding" data-id="${esc(row.id)}" data-tenant="${esc(row.tenant_id)}" data-next="${row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'}">${row.status === 'ENABLED' ? '停用' : '启用'}</button>`,
          },
        ],
        actionBindings,
        { title: '还没有业务动作授权', hint: '只有需要审批通过后回调业务系统的租户才需要配置。' }
      )}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   17. 待办与审批工作台
   -------------------------------------------------------------------------- */

async function renderTasks() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const statusFilter = params.get('status') || 'PENDING';
  const personFilter = params.get('person') || '';

  await paint(async () => {
    const persons = await safe(api.get('/api/admin/persons?limit=200'), []);
    if (!persons.length) {
      return `${pageHead('审批任务', '全部审批人的任务集中在这里，管理台可以直接代为处理。', '')}
        <div class="panel"><div class="empty"><div class="empty__title">还没有人员</div>
        <div>审批任务分配给具体人员，先维护人员再配置审批流。</div>
        <p><a class="btn btn--sm" href="#/people">去维护人员</a></p></div></div>`;
    }

    // 任务查询按人员维度提供，管理台在这里扇出到全部人员再合并，得到全量视图。
    const targets = personFilter ? persons.filter((person) => person.id === personFilter) : persons;
    const statusQuery = statusFilter === 'ALL' ? '' : `&status=${statusFilter}`;
    const groups = await Promise.all(
      targets.map((person) =>
        safe(api.get(`/api/approval-tasks?person_id=${esc(person.id)}${statusQuery}&limit=200`), [])
      )
    );
    const tasks = groups
      .flat()
      .sort((left, right) => new Date(right.created_at) - new Date(left.created_at));

    setActions({
      'filter': (el) => {
        const next = new URLSearchParams();
        next.set('status', document.getElementById('task-status').value);
        const person = document.getElementById('task-person').value;
        if (person) next.set('person', person);
        location.hash = `#/tasks?${next.toString()}`;
        void el;
      },
      'approve': (el) => handleTask(el.dataset.id, 'approve'),
      'reject': (el) => handleTask(el.dataset.id, 'reject'),
      'copy': (el) => copyText(el.dataset.copy),
    });

    async function handleTask(taskId, kind) {
      const task = tasks.find((item) => item.id === taskId);
      if (!task) throw new Error('任务已刷新，请重新加载页面');
      formDialog({
        title: `${kind === 'approve' ? '同意' : '拒绝'}审批 · ${personNameOf(persons, task.approver_person_id)}`,
        fields: [
          { name: 'comment', label: '审批意见', type: 'textarea', wide: true, placeholder: kind === 'approve' ? '同意，按合同付款。' : '请说明拒绝的原因。' },
        ],
        values: {},
        submitText: kind === 'approve' ? '同意' : '拒绝',
        wide: true,
        onSubmit: async (values) => {
          // 管理台没有登录身份，代为处理时使用任务所属审批人的身份。
          const result = await api.post(`/api/approval-tasks/${taskId}/${kind}`, {
            person_id: task.approver_person_id,
            comment: values.comment || null,
          });
          invalidateTenantCache();
          toast(`已${kind === 'approve' ? '同意' : '拒绝'}，审批单当前状态 ${STATUS_TEXT[result.instance_status] || result.instance_status}`, 'ok');
          if (result.instance_id) location.hash = `#/instances/${result.instance_id}`;
          else renderTasks();
        },
      });
    }

    const waiting = tasks.filter((item) => item.status === 'PENDING');

    return `${pageHead(
      '审批任务',
      '全部审批人的任务集中在这里，按产生时间倒序。管理台代为处理时使用任务所属审批人的身份，用于联调和验收测试。',
      `<select class="select" id="task-person" style="width:180px" data-act="filter">
         <option value="">全部审批人</option>
         ${persons.map((person) => `<option value="${esc(person.id)}"${person.id === personFilter ? ' selected' : ''}>${esc(person.name)}</option>`).join('')}
       </select>
       <select class="select" id="task-status" style="width:140px" data-act="filter">
         <option value="PENDING"${statusFilter === 'PENDING' ? ' selected' : ''}>只看待办</option>
         <option value="ALL"${statusFilter === 'ALL' ? ' selected' : ''}>全部状态</option>
       </select>`
    )}
    <div class="panel">
      ${statusFilter === 'PENDING' && waiting.length
        ? `<div class="panel__body" style="padding-bottom:0"><div class="note note--work">当前有 ${waiting.length} 条待办等待处理。</div></div>`
        : ''}
      ${tableHtml(
        [
          { title: '审批单', render: (row) => `<a class="cell-title" href="#/instances/${esc(row.instance_id)}">${esc(row.instance_title || '（无标题）')}</a>` },
          { title: '业务单号', render: (row) => `<span class="code">${esc(row.business_key || '—')}</span>` },
          { title: '节点', render: (row) => esc(row.node_name || '—') },
          { title: '审批人', render: (row) => esc(personNameOf(persons, row.approver_person_id)) },
          { title: '任务状态', render: (row) => tag(row.status) },
          { title: '产生时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          { title: '停留时长', cls: 'is-num', render: (row) => `<span class="muted">${esc(fmtMs(row.duration_ms))}</span>` },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `${row.status === 'PENDING'
                ? `<button class="btn--link btn--sm" data-act="approve" data-id="${esc(row.id)}">同意</button>
                   <button class="btn--link btn--sm is-danger" data-act="reject" data-id="${esc(row.id)}">拒绝</button>`
                : ''}
               <a class="btn--link btn--sm" href="#/instances/${esc(row.instance_id)}">详情</a>`,
          },
        ],
        tasks,
        statusFilter === 'PENDING'
          ? { title: '没有待办任务', hint: '业务系统发起审批后，分配给审批人的任务会出现在这里。' }
          : { title: '没有审批记录', hint: '处理过任务后，记录会保留在这里。' }
      )}
    </div>`;
  });
}

async function renderInstance(instanceId) {
  await paint(async () => {
    // 详情接口按租户鉴权，管理台按使用记录自动借用发起该审批的租户密钥。
    const credentials = await credentialsForInstance(instanceId);
    const key = credentials.key || config.apiKey;
    const persons = await safe(api.get('/api/admin/persons?limit=200'), []);

    if (!key) {
      return `${breadcrumb([{ text: '审批任务', href: '#/tasks' }, { text: shortId(instanceId) }])}
        ${pageHead('审批详情', '详情接口在租户模式下要求 X-API-Key，管理台会自动借用发起审批的租户密钥。', '')}
        <div class="panel"><div class="panel__body">
          <div class="note note--wait">没有解析到可用的租户密钥：该审批实例可能没有使用记录（全局模式发起），或者对应租户的 API Key 全部被撤销。可以在租户页面重新签发一个密钥。</div>
          <p style="font-size:13px;color:var(--ink-2)">也可以临时指定一个密钥查询本次请求：</p>
          <div style="display:flex;gap:8px;max-width:520px">
            <input class="input" id="manual-key" placeholder="X-API-Key">
            <button class="btn" data-act="use-manual-key">使用该密钥</button>
          </div>
        </div></div>`;
    }

    const [detail, timeline, executions] = await Promise.all([
      api.get(`/api/approval-instances/${instanceId}`, 'apikey', key),
      api.get(`/api/approval-instances/${instanceId}/timeline`, 'apikey', key),
      safe(api.get(`/api/admin/execution-records?approval_instance_id=${instanceId}`), []),
    ]);

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'approve': (el) => handleTask(el.dataset.id, 'approve'),
      'reject': (el) => handleTask(el.dataset.id, 'reject'),
      'use-manual-key': () => {
        const value = document.getElementById('manual-key').value.trim();
        if (!value) {
          toast('请先填入密钥', 'err');
          return;
        }
        config.apiKey = value;
        saveConfig();
        renderInstance(instanceId);
      },
    });

    async function handleTask(taskId, kind) {
      const task = detail.tasks.find((item) => item.id === taskId);
      if (!task) throw new Error('任务已刷新，请重新加载页面');
      formDialog({
        title: `${kind === 'approve' ? '同意' : '拒绝'}审批 · ${personNameOf(persons, task.approver_person_id)}`,
        fields: [{ name: 'comment', label: '审批意见', type: 'textarea', wide: true }],
        values: {},
        submitText: kind === 'approve' ? '同意' : '拒绝',
        wide: true,
        onSubmit: async (values) => {
          await api.post(
            `/api/approval-tasks/${taskId}/${kind}`,
            { person_id: task.approver_person_id, comment: values.comment || null }
          );
          invalidateTenantCache();
          toast('处理完成', 'ok');
          renderInstance(instanceId);
        },
      });
    }

    const formEntries = Object.entries(detail.approval_form || {});
    const execution = executions[0];

    const timelineHtml = timeline.entries.length
      ? `<div class="timeline">${timeline.entries
          .map((entry) => {
            const node = entry.node_execution;
            const cls = node.status === 'COMPLETED' ? 'timeline__item--done' : node.status === 'REJECTED' ? 'timeline__item--reject' : node.status === 'ACTIVE' ? 'timeline__item--active' : '';
            const records = entry.records.length
              ? entry.records.map((record) => `<div class="opinion">
                  <span class="opinion__who">${esc(record.operator_snapshot && record.operator_snapshot.name ? record.operator_snapshot.name : shortId(record.operator_person_id))}</span>
                  ${record.action === 'APPROVE' ? '同意' : '拒绝'} · ${esc(fmtTime(record.created_at))}
                  ${record.comment ? `<div style="margin-top:4px">${esc(record.comment)}</div>` : ''}
                </div>`).join('')
              : entry.tasks
                .map((task) => `<div class="opinion">
                    <span class="opinion__who">${esc(task.approver_snapshot && task.approver_snapshot.name ? task.approver_snapshot.name : shortId(task.approver_person_id))}</span>
                    ${task.status === 'PENDING' ? '等待处理' : STATUS_TEXT[task.status] || task.status}${task.handled_at ? ` · ${esc(fmtTime(task.handled_at))}` : ''}
                  </div>`)
                .join('');
            return `<div class="timeline__item ${cls}">
              <div class="timeline__dot"></div>
              <div class="timeline__head">
                <span class="timeline__name">${esc(node.node_name)}</span>
                ${tag(node.status)}
                <span class="timeline__meta">${esc(fmtTime(node.entered_at))} · 耗时 ${esc(fmtMs(node.duration_ms))}</span>
                ${node.next_node_name ? `<span class="timeline__meta">→ ${esc(node.next_node_name)}${node.condition_hit === true ? '（条件命中）' : node.condition_hit === false ? '（默认路径）' : ''}</span>` : ''}
              </div>
              ${records}
            </div>`;
          })
          .join('')}</div>`
      : '<div class="empty">流程还没有产生节点执行记录</div>';

    return `${breadcrumb([{ text: '待办任务', href: '#/tasks' }, { text: detail.title }])}
    ${pageHead(
      detail.title,
      `业务单号 ${esc(detail.business_key)} · ${esc(detail.process_name)} V${esc(detail.process_version_no)}`,
      stamp(detail.status)
    )}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">审批单</h2>
        <span class="panel__note">${detail.current_node ? `当前停在「${esc(detail.current_node.node_name)}」` : '流程已结束'} · 已用时 ${esc(fmtMs(detail.duration_ms))}</span></div>
      <div class="panel__body">
        ${kvHtml([
          ['审批实例', `<span class="code">${esc(detail.id)}</span> ${copyButton(detail.id)}`],
          ['所属租户', credentials.tenant ? `${esc(credentials.tenant.name)}（${esc(credentials.tenant.code)}）` : '<span class="muted">全局模式，无租户归属</span>'],
          ['发起人', esc((detail.applicant_snapshot && detail.applicant_snapshot.name) || shortId(detail.applicant_person_id) || '—')],
          ['发起时间', esc(fmtTime(detail.started_at))],
          ['结束时间', esc(fmtTime(detail.finished_at))],
          ['业务动作', detail.action_code ? `<span class="code">${esc(detail.action_code)}</span>` : '<span class="muted">不触发业务执行</span>'],
        ])}
      </div>
      ${formEntries.length
        ? `<div class="panel__head" style="border-top:1px solid var(--rule-weak)"><h3 class="panel__title">审批表单</h3></div>
           <div class="panel__body">${kvHtml(formEntries.map(([key, value]) => [key, `<span class="code">${esc(typeof value === 'object' ? formatJson(value) : value)}</span>`]))}</div>`
        : ''}
    </div>

    ${detail.pending_tasks.length
      ? `<div class="panel">
          <div class="panel__head"><h2 class="panel__title">等待处理的待办</h2>
            <span class="panel__note">管理台代为处理时使用任务所属审批人的身份，仅用于联调和验收</span></div>
          ${tableHtml(
            [
              { title: '审批人', render: (row) => `<span class="cell-title">${esc(personNameOf(persons, row.approver_person_id))}</span>` },
              { title: '节点', render: (row) => esc(row.node_name || '—') },
              { title: '产生时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
              { title: '已等待', cls: 'is-num', render: (row) => `<span class="muted">${esc(fmtMs(row.duration_ms))}</span>` },
              {
                title: '操作', cls: 'is-actions', render: (row) =>
                  `<button class="btn--link btn--sm" data-act="approve" data-id="${esc(row.id)}">同意</button>
                   <button class="btn--link btn--sm is-danger" data-act="reject" data-id="${esc(row.id)}">拒绝</button>`,
              },
            ],
            detail.pending_tasks,
            { title: '没有待办' }
          )}
        </div>`
      : ''}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">会签时间线</h2></div>
      <div class="panel__body">${timelineHtml}</div>
    </div>

    ${detail.action_code
      ? `<div class="panel">
          <div class="panel__head"><h2 class="panel__title">业务执行</h2>
            ${execution ? `<a class="btn btn--sm" href="#/executions/${esc(execution.id)}">查看完整记录</a>` : ''}</div>
          ${execution
            ? `<div class="panel__body">${kvHtml([
                ['执行状态', tag(execution.status)],
                ['调用方式', `<span class="code">${esc(execution.http_method || '—')} ${esc(execution.relative_path || '')}</span>`],
                ['HTTP 状态码', `<span class="code">${esc(execution.http_status_code === null ? '—' : execution.http_status_code)}</span>`],
                ['耗时', esc(fmtMs(execution.duration_ms))],
                ['失败原因', execution.error_message ? `<span style="color:var(--cinnabar)">${esc(execution.error_message)}</span>` : '—'],
              ])}</div>`
            : '<div class="panel__body"><div class="note">审批还未通过，或通过后尚未创建执行记录。</div></div>'}
        </div>`
      : ''}`;
  });
}

/* --------------------------------------------------------------------------
   18. 发起审批（业务系统联调台）
   -------------------------------------------------------------------------- */

async function renderStart() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');

  await paint(async () => {
    const [tenants, processes, persons, actionsList] = await Promise.all([
      loadTenantList(),
      safe(api.get('/api/admin/processes?limit=200'), []),
      safe(api.get('/api/admin/persons?limit=200'), []),
      safe(api.get('/api/admin/business-actions?limit=200'), []),
    ]);

    const usable = processes.filter((item) => item.status === 'ENABLED' && item.current_version_id);
    const tenant = tenants.find((item) => item.id === params.get('tenant')) || tenants[0] || null;
    // 管理台自动借用该租户的有效密钥，联调时不用手工复制。
    const apiKey = tenant ? await tenantApiKey(tenant.id) : null;
    const context = apiKey ? await safe(api.get('/api/tenant/context', 'apikey', apiKey), null) : null;

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'switch-tenant': (el) => {
        location.hash = `#/start?tenant=${el.value}`;
      },
      'use-manual-key': () => {
        const value = document.getElementById('start-apikey').value.trim();
        if (!value) {
          toast('请先填入密钥', 'err');
          return;
        }
        config.apiKey = value;
        saveConfig();
        toast('本次会话将使用这个密钥', 'ok');
        renderStart();
      },
      'sample-form': async () => {
        const process = processes.find((item) => item.id === document.getElementById('start-process').value);
        if (!process || !process.current_version_id) {
          toast('该流程还没有发布版本，无法生成表单示例', 'err');
          return;
        }
        const graph = await api.get(`/api/admin/process-versions/${process.current_version_id}/graph`);
        const properties = ((graph.form_schema || {}).properties) || {};
        const template = {};
        for (const [key, rule] of Object.entries(properties)) {
          if (rule.type === 'number' || rule.type === 'integer') template[key] = 10000;
          else if (rule.type === 'boolean') template[key] = true;
          else if (Array.isArray(rule.enum)) template[key] = rule.enum[0];
          else if (rule.type === 'array') template[key] = [];
          else if (rule.type === 'object') template[key] = {};
          else template[key] = '示例值';
        }
        document.getElementById('start-form').value = formatJson(template);
        if (!Object.keys(template).length) toast('该版本没有声明表单字段，可以留空提交', 'ok');
      },
      'submit-start': async () => {
        const processId = document.getElementById('start-process').value;
        if (!processId) {
          toast('请先选择审批流', 'err');
          return;
        }
        const actionCode = document.getElementById('start-action').value;
        const body = {
          business_key: document.getElementById('start-key').value.trim(),
          title: document.getElementById('start-title').value.trim(),
          applicant_person_id: document.getElementById('start-applicant').value || null,
          approval_form: parseJsonInput(document.getElementById('start-form').value, '审批表单'),
          execution_payload: parseJsonInput(document.getElementById('start-payload').value, '执行参数'),
        };
        if (actionCode) body.action_code = actionCode;
        if (!body.business_key) { toast('业务单号不能为空', 'err'); return; }
        if (!body.title) { toast('审批单标题不能为空', 'err'); return; }

        if (!apiKey && !config.apiKey) {
          toast('该租户没有可用的 API Key，请先在租户页面签发一个', 'err');
          return;
        }

        try {
          const started = await api.post(`/api/processes/${processId}/instances`, body, 'apikey', apiKey || config.apiKey);
          invalidateTenantCache();
          toast(started.idempotent_replay ? '命中幂等，返回已有审批实例' : '审批已发起', 'ok');
          openOverlay(
            dialogShell(
              '发起结果',
              `<div class="issue issue--ok"><div class="issue__code">${esc(started.status)}</div>
                 <div>${started.idempotent_replay ? '本次请求命中了幂等规则，返回的是已有实例，没有重复创建。' : '审批实例已创建，并已生成首批审批任务。'}</div></div>
               <div style="margin-top:14px">${kvHtml([
                 ['审批实例', `<span class="code">${esc(started.instance_id)}</span> ${copyButton(started.instance_id)}`],
                 ['使用版本', `V${esc(started.process_version_no)}`],
                 ['当前节点', esc(started.current_node_name || '已结束')],
                 ['待办人员', (started.pending_approver_person_ids || []).map((id) => `<span class="code">${esc(personNameOf(persons, id))}</span>`).join('、') || '—'],
                 ['发起时间', esc(fmtTime(started.started_at))],
               ])}</div>`,
              `<button class="btn" data-act="close-dialog">关闭</button>
               <a class="btn btn--primary" href="#/instances/${esc(started.instance_id)}">查看审批详情</a>`
            )
          );
          setDialogActions({ 'close-dialog': closeOverlay });
        } catch (err) {
          toast(err.message, 'err');
        }
      },
      'gen-curl': () => {
        const processId = document.getElementById('start-process').value;
        const payload = {
          business_key: document.getElementById('start-key').value.trim(),
          title: document.getElementById('start-title').value.trim(),
          applicant_person_id: document.getElementById('start-applicant').value || null,
          approval_form: parseJsonInput(document.getElementById('start-form').value, '审批表单'),
          execution_payload: parseJsonInput(document.getElementById('start-payload').value, '执行参数'),
        };
        const actionCode = document.getElementById('start-action').value;
        if (actionCode) payload.action_code = actionCode;
        const command = `curl -X POST "${config.base.replace(/\/+$/, '')}/api/processes/${processId}/instances" \\\n  -H "X-API-Key: ${apiKey || config.apiKey || '你的租户APIKey'}" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(payload, null, 2)}'`;
        openOverlay(dialogShell('业务系统调用示例', `<pre class="raw-json">${esc(command)}</pre>`,
          `<button class="btn" data-act="close-dialog">关闭</button><button class="btn btn--primary" data-act="copy-curl">复制命令</button>`), true);
        setDialogActions({
          'close-dialog': closeOverlay,
          'copy-curl': () => copyText(command),
        });
      },
    });

    const processOptions = usable.map((item) => `<option value="${esc(item.id)}">${esc(item.name)} · V${item.current_version_no}</option>`).join('');

    if (!tenants.length) {
      return `${pageHead('发起审批', '这一页模拟业务系统调用发起接口。', '')}
        <div class="panel"><div class="empty"><div class="empty__title">还没有租户</div>
        <div>发起审批需要以某个租户的身份调用，先创建租户并签发 API Key。</div>
        <p><a class="btn btn--sm" href="#/tenants">去创建租户</a></p></div></div>`;
    }

    const maskedKey = apiKey ? `${apiKey.slice(0, 12)}${'•'.repeat(Math.max(4, apiKey.length - 16))}${apiKey.slice(-4)}` : null;

    return `${pageHead(
      '发起审批',
      '这一页模拟业务系统调用发起接口。真实接入时由业务系统用租户 API Key 调用，tenant_id 不进入请求体，由密钥决定。',
      ''
    )}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">第一步 · 选择发起身份</h2>
        ${context ? `<span class="panel__note">密钥已验证：${esc(context.tenant_name)}（${esc(context.tenant_code)}）</span>` : ''}</div>
      <div class="panel__body">
        <div class="form__row--split">
          <div class="field">
            <label class="field__label">租户</label>
            <select class="select" data-act="switch-tenant">
              ${tenants.map((item) => `<option value="${esc(item.id)}"${tenant && item.id === tenant.id ? ' selected' : ''}>${esc(item.name)}（${esc(item.code)}）</option>`).join('')}
            </select>
            <div class="field__hint">管理台自动借用该租户最近签发的有效 API Key，不需要手工复制。</div>
          </div>
          <div class="field">
            <label class="field__label">当前使用的密钥</label>
            ${apiKey
              ? `<div class="code" style="padding-top:6px">${esc(maskedKey)} ${copyButton(apiKey, '复制完整密钥')}</div>`
              : `<div class="note note--wait">该租户没有可用的 API Key，<a href="#/tenants/${esc(tenant.id)}">去签发一个</a>，或临时使用下面的密钥。</div>`}
          </div>
        </div>
        <div class="field" style="max-width:620px;margin-top:14px">
          <label class="field__label">临时使用其他密钥（可选）</label>
          <div style="display:flex;gap:8px">
            <input class="input" id="start-apikey" value="${esc(config.apiKey)}" placeholder="留空则使用上面自动借用的密钥">
            <button class="btn" data-act="use-manual-key">使用</button>
          </div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">第二步 · 填写审批内容</h2>
        <button class="btn btn--sm" data-act="gen-curl">生成调用示例</button></div>
      <div class="panel__body">
        <div class="form">
          <div class="form__row--split">
            <div class="field"><label class="field__label">审批流</label>
              <select class="select" id="start-process">${processOptions}</select>
              ${usable.length ? '' : '<div class="field__hint">没有已发布且启用的审批流，先去创建并发布一条。</div>'}
            </div>
            <div class="field"><label class="field__label">业务单号</label>
              <input class="input" id="start-key" placeholder="PAY-20260923-001">
              <div class="field__hint">同一租户、同一流程下重复使用同一个单号会命中幂等。</div>
            </div>
            <div class="field"><label class="field__label">审批单标题</label>
              <input class="input" id="start-title" placeholder="供应商付款申请">
            </div>
            <div class="field"><label class="field__label">发起人</label>
              <select class="select" id="start-applicant">
                <option value="">不指定</option>
                ${persons.map((person) => `<option value="${esc(person.id)}">${esc(person.name)}</option>`).join('')}
              </select>
            </div>
            <div class="field"><label class="field__label">业务动作</label>
              <select class="select" id="start-action">
                <option value="">不触发业务执行</option>
                ${actionsList.filter((item) => item.status === 'ENABLED').map((item) => `<option value="${esc(item.action_code)}">${esc(item.name)}（${esc(item.action_code)}）</option>`).join('')}
              </select>
              <div class="field__hint">选择动作后，审批通过会回调业务系统。</div>
            </div>
          </div>
          <div class="form__row--split">
            <div class="field">
              <label class="field__label">审批表单 approval_form <button class="btn--link btn--sm" data-act="sample-form">按 Schema 生成示例</button></label>
              <textarea class="textarea textarea--code" id="start-form" placeholder='{ "amount": 10000 }'></textarea>
              <div class="field__hint">按流程版本的表单 Schema 校验，分支条件引用这里的字段。</div>
            </div>
            <div class="field">
              <label class="field__label">执行参数 execution_payload</label>
              <textarea class="textarea textarea--code" id="start-payload" placeholder='{ "payment_id": "PAY-20260923-001", "amount": 10000 }'></textarea>
              <div class="field__hint">按业务动作的请求参数 Schema 校验，只有审批通过后才会发给业务系统。</div>
            </div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn--primary" data-act="submit-start">发起审批</button>
          </div>
        </div>
      </div>
    </div>`;
  });
}

function personNameOf(persons, personId) {
  const person = (persons || []).find((item) => item.id === personId);
  return person ? person.name : shortId(personId);
}

/* --------------------------------------------------------------------------
   19. 执行记录
   -------------------------------------------------------------------------- */

async function renderExecutions() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const statusFilter = params.get('status') || '';

  await paint(async () => {
    const records = await api.get(`/api/admin/execution-records?limit=200${statusFilter ? `&status=${statusFilter}` : ''}`);
    railCounts.executions = records.length;

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'filter': (el) => {
        location.hash = el.value ? `#/executions?status=${el.value}` : '#/executions';
      },
    });

    return `${pageHead(
      '执行记录',
      '审批通过后由后台 Worker 调用业务系统。第一版不自动重试，失败记录保留原因供人工核对。列表不返回响应正文和 Service Token。',
      `<select class="select" style="width:160px" data-act="filter">
        <option value="">全部状态</option>
        ${['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'].map((status) => `<option value="${status}"${statusFilter === status ? ' selected' : ''}>${STATUS_TEXT[status]}</option>`).join('')}
      </select>`
    )}
    <div class="panel">
      ${tableHtml(
        [
          { title: '创建时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          { title: '业务动作', render: (row) => `<span class="code">${esc(row.action_code)}</span>` },
          { title: '调用', render: (row) => `<span class="code">${esc(row.http_method || '—')} ${esc(row.relative_path || '')}</span>` },
          { title: '执行状态', render: (row) => tag(row.status) },
          { title: 'HTTP', cls: 'is-num', render: (row) => esc(row.http_status_code === null ? '—' : row.http_status_code) },
          { title: '耗时', cls: 'is-num', render: (row) => esc(fmtMs(row.duration_ms)) },
          { title: '失败原因', render: (row) => row.error_message ? `<span style="color:var(--cinnabar)">${esc(row.error_message.slice(0, 60))}</span>` : '<span class="muted">—</span>' },
          { title: '操作', cls: 'is-actions', render: (row) => `<a class="btn--link btn--sm" href="#/executions/${esc(row.id)}">详情</a>` },
        ],
        records,
        { title: '还没有执行记录', hint: '审批通过且配置了业务动作时，会在这里生成一条调用记录。' }
      )}
    </div>`;
  });
}

async function renderExecutionDetail(recordId) {
  await paint(async () => {
    const record = await api.get(`/api/admin/execution-records/${recordId}`);

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'view-instance': () => {
        location.hash = `#/instances/${record.approval_instance_id}`;
      },
    });

    return `${breadcrumb([{ text: '执行记录', href: '#/executions' }, { text: shortId(record.id) }])}
    ${pageHead(
      `执行记录 · ${record.action_code}`,
      `审批实例 ${esc(record.approval_instance_id)}`,
      `<button class="btn" data-act="view-instance">查看审批详情</button>`
    )}

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">调用结果</h2>${tag(record.status)}</div>
      <div class="panel__body">
        ${kvHtml([
          ['请求地址', `<span class="code">${esc(record.request_url || '—')}</span>`],
          ['调用方式', `<span class="code">${esc(record.http_method || '—')}</span>`],
          ['HTTP 状态码', `<span class="code">${esc(record.http_status_code === null ? '—' : record.http_status_code)}</span>`],
          ['耗时', esc(fmtMs(record.duration_ms))],
          ['开始时间', esc(fmtTime(record.started_at))],
          ['结束时间', esc(fmtTime(record.finished_at))],
          ['超时设置', `${esc(record.timeout_ms || '—')} ms`],
          ['成功状态码', `<span class="code">${(record.success_status_codes || []).length ? esc(record.success_status_codes.join(', ')) : '全部 2xx'}</span>`],
          ['失败原因', record.error_message ? `<span style="color:var(--cinnabar)">${esc(record.error_message)}</span>` : '—'],
        ])}
      </div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">请求参数</h2>
        <span class="panel__note">审批实例固化下来的执行参数，认证信息不出现在记录里</span></div>
      <div class="panel__body"><pre class="raw-json">${esc(formatJson(record.request_payload || {}))}</pre></div>
    </div>

    <div class="panel">
      <div class="panel__head"><h2 class="panel__title">响应正文</h2>
        <span class="panel__note">保存时已按固定上限截断</span></div>
      <div class="panel__body"><pre class="raw-json">${esc(record.response_body || '（无响应正文）')}</pre></div>
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   20. 使用记录
   -------------------------------------------------------------------------- */

async function renderUsages() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const tenantParam = params.get('tenant') || '';
  const businessKey = params.get('business_key') || '';

  await paint(async () => {
    const tenants = await loadTenantList();
    if (!tenants.length) {
      return `${pageHead('使用记录', '使用记录保存了哪家租户、用哪条流程发起了哪一张单据。', '')}
        <div class="panel"><div class="empty"><div class="empty__title">还没有租户</div><div>业务系统接入后，这里会显示审批使用记录。</div></div></div>`;
    }

    // 使用记录接口按租户提供，管理台扇出到全部租户后合并成一张全量表。
    const targets = tenantParam ? tenants.filter((item) => item.id === tenantParam) : tenants;
    const query = `limit=200${businessKey ? `&business_key=${encodeURIComponent(businessKey)}` : ''}`;
    const groups = await Promise.all(
      targets.map((tenant) => safe(api.get(`/api/admin/tenants/${tenant.id}/process-usage-records?${query}`), []))
    );
    const records = groups
      .flatMap((list, index) => list.map((record) => Object.assign({}, record, { tenant_name: targets[index].name, tenant_code: targets[index].code })))
      .sort((left, right) => new Date(right.created_at) - new Date(left.created_at));

    setActions({
      'copy': (el) => copyText(el.dataset.copy),
      'search': () => {
        const next = new URLSearchParams();
        const tenant = document.getElementById('usage-tenant').value;
        const value = document.getElementById('usage-key').value.trim();
        if (tenant) next.set('tenant', tenant);
        if (value) next.set('business_key', value);
        const text = next.toString();
        location.hash = text ? `#/usages?${text}` : '#/usages';
      },
      'reset': () => {
        location.hash = '#/usages';
      },
    });

    return `${pageHead(
      '使用记录',
      '全部租户的审批发起记录合并展示，按发起时间倒序。审批状态和当前节点在查询时从运行表实时读取。',
      ''
    )}
    <div class="panel">
      <div class="filters">
        <div class="field"><label class="field__label">租户</label>
          <select class="select" id="usage-tenant">
            <option value="">全部租户</option>
            ${tenants.map((item) => `<option value="${esc(item.id)}"${item.id === tenantParam ? ' selected' : ''}>${esc(item.name)}</option>`).join('')}
          </select>
        </div>
        <div class="field"><label class="field__label">业务单号</label>
          <input class="input" id="usage-key" value="${esc(businessKey)}" placeholder="按单号精确查询">
        </div>
        <button class="btn btn--sm btn--primary" data-act="search">查询</button>
        ${tenantParam || businessKey ? '<button class="btn btn--sm" data-act="reset">清空条件</button>' : ''}
      </div>
      ${tableHtml(
        [
          { title: '发起时间', render: (row) => `<span class="muted">${esc(fmtTime(row.created_at))}</span>` },
          { title: '租户', render: (row) => `${esc(row.tenant_name)}<div class="muted code">${esc(row.tenant_code)}</div>` },
          { title: '审批单', render: (row) => `<a class="cell-title" href="#/instances/${esc(row.approval_instance_id)}">${esc(row.approval_title || '—')}</a>` },
          { title: '业务单号', render: (row) => `<span class="code">${esc(row.business_key)}</span>` },
          { title: '业务动作', render: (row) => `<span class="code">${esc(row.action_code || '—')}</span>` },
          { title: '审批状态', render: (row) => tag(row.approval_status || 'ERROR') },
          { title: '当前节点', render: (row) => esc(row.current_node_name || '—') },
          { title: '耗时', cls: 'is-num', render: (row) => esc(fmtMs(row.duration_ms)) },
          {
            title: '操作', cls: 'is-actions', render: (row) =>
              `<a class="btn--link btn--sm" href="#/instances/${esc(row.approval_instance_id)}">查看审批</a>`,
          },
        ],
        records,
        { title: '没有使用记录', hint: '业务系统用租户 API Key 发起审批后，这里会产生记录。' }
      )}
    </div>`;
  });
}

/* --------------------------------------------------------------------------
   21. 路由与导航
   -------------------------------------------------------------------------- */

const NAV = [
  { group: '闭环' },
  { key: 'overview', hash: '#/overview', label: '闭环进度' },
  { key: 'tenants', hash: '#/tenants', label: '租户' },
  { key: 'people', hash: '#/people', label: '人员与部门' },
  { group: '流程配置' },
  { key: 'processes', hash: '#/processes', label: '审批流' },
  { key: 'definitions', hash: '#/definitions', label: '节点定义' },
  { key: 'actions', hash: '#/actions', label: '业务动作' },
  { key: 'grants', hash: '#/grants', label: '资源授权' },
  { group: '运行' },
  { key: 'tasks', hash: '#/tasks', label: '审批任务' },
  { key: 'start', hash: '#/start', label: '发起审批' },
  { key: 'executions', hash: '#/executions', label: '执行记录' },
  { key: 'usages', hash: '#/usages', label: '使用记录' },
];

function activeKey() {
  const head = (location.hash.replace(/^#\/?/, '').split(/[/?]/)[0]) || 'overview';
  if (head === 'versions') return 'processes';
  if (head === 'instances') return 'tasks';
  const known = NAV.some((item) => item.key === head);
  return known ? head : 'overview';
}

function syncRail() {
  const current = activeKey();
  const nav = document.getElementById('rail-nav');
  nav.innerHTML = NAV.map((item) => {
    if (item.group) return `<div class="rail__group">${esc(item.group)}</div>`;
    const count = railCounts[item.key];
    const badge = count === undefined ? '' : `<span class="rail__count">${count}</span>`;
    return `<a class="rail__item${item.key === current ? ' rail__item--active' : ''}" href="${item.hash}">${esc(item.label)}${badge}</a>`;
  }).join('');
}

async function route() {
  const raw = location.hash.replace(/^#/, '') || '/overview';
  const [pathPart, queryPart] = raw.split('?');
  const parts = pathPart.split('/').filter(Boolean);
  const head = parts[0] || 'overview';
  const id = parts[1];

  // 离开版本编排页时丢弃本地编辑副本，避免下次进来看到过期草稿。
  if (head !== 'versions') versionEditorState = null;

  switch (head) {
    case 'overview': return renderOverview();
    case 'tenants': return id ? renderTenantDetail(id) : renderTenants();
    case 'people': return renderPeople();
    case 'processes': return id ? renderProcessDetail(id) : renderProcesses();
    case 'versions': return renderVersionEditor(id);
    case 'definitions': return renderNodeDefinitions();
    case 'actions': return renderActions();
    case 'grants': return renderGrants();
    case 'tasks': return renderTasks();
    case 'instances': return renderInstance(id);
    case 'start': return renderStart();
    case 'executions': return id ? renderExecutionDetail(id) : renderExecutions();
    case 'usages': return renderUsages();
    default:
      location.hash = '#/overview';
      void queryPart;
  }
}

window.addEventListener('hashchange', route);

/* --------------------------------------------------------------------------
   22. 顶部配置与事件委托
   -------------------------------------------------------------------------- */

const GLOBAL_ACTIONS = {
  'demo-on': () => enableDemo(),
  'demo-off': () => {
    window.ApprovalDemo.disable();
    syncDemoBanner();
    toast('已退出示例数据模式', 'ok');
    route();
  },
};

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-act]');
  if (!target) return;
  // 下拉框的展开也会触发 click，交给 change 事件处理，避免刚展开就跳转。
  if (target.tagName === 'SELECT') return;
  // 弹窗的处理函数优先于页面：弹窗打开期间页面可能已经重新渲染过。
  const handler = GLOBAL_ACTIONS[target.dataset.act] || dialogActions[target.dataset.act] || actions[target.dataset.act];
  if (!handler) return;
  event.preventDefault();
  Promise.resolve(handler(target, event)).catch((err) => toast(err.message, 'err'));
});

document.addEventListener('change', (event) => {
  const target = event.target.closest('[data-act]');
  if (!target) return;
  const handler = actions[target.dataset.act];
  if (!handler) return;
  Promise.resolve(handler(target, event)).catch((err) => toast(err.message, 'err'));
});

function bindConfig() {
  const baseInput = document.getElementById('cfg-base');
  const adminInput = document.getElementById('cfg-admin');

  baseInput.value = config.base;
  adminInput.value = config.adminKey;

  const commit = () => {
    config.base = baseInput.value.trim() || 'http://127.0.0.1:8090';
    config.adminKey = adminInput.value.trim();
    saveConfig();
    invalidateTenantCache();
    setLinkState('idle', '未连接');
  };
  [baseInput, adminInput].forEach((input) => input.addEventListener('change', commit));

  document.getElementById('cfg-check').addEventListener('click', async () => {
    commit();
    setLinkState('idle', '连接中…');
    try {
      await api.get('/api/admin/tenants?limit=1');
      setLinkState('ok', '已连接');
      toast('接口连接正常', 'ok');
      route();
    } catch (err) {
      setLinkState('off', err.status === 401 ? '密钥无效' : '连接失败');
      toast(err.message, 'err');
    }
  });
}

function setLinkState(kind, text) {
  const node = document.getElementById('cfg-state');
  node.className = `link-state${kind === 'ok' ? ' link-state--ok' : kind === 'off' ? ' link-state--off' : ''}`;
  node.innerHTML = `<i class="link-state__dot"></i><span>${esc(text)}</span>`;
}

bindConfig();
syncDemoBanner();
syncRail();
route();
