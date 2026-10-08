/** 执行联调面板的真实页面脚本，验证附件上传与发起按钮之间的状态传递。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const { JSDOM } = require('../web-vue/node_modules/jsdom');

const html = fs.readFileSync(0, 'utf8');

/** 创建隔离的页面；模拟接口响应，不访问真实审批中心或 OSS。 */
function createPage(uploadSucceeds = true) {
  const requests = [];
  const dom = new JSDOM(html, {
    url: 'http://localhost:9000/',
    runScripts: 'dangerously',
    beforeParse(window) {
      // 禁用回调轮询，让每个用例仅观察用户主动触发的请求。
      window.setInterval = () => 0;
      window.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        let body;
        if (url === '/_upload') {
          body = uploadSucceeds
            ? { ok: true, file_ids: ['file-1'], files: [
                { file_id: 'file-1', file_name: '合同.pdf', size_bytes: 12 },
              ] }
            : { ok: false, msg: 'OSS 上传失败' };
        } else if (url === '/start') {
          body = { ok: true, instance_id: 'instance-1', pending_approver_person_ids: [] };
        } else if (url.startsWith('/_status')) {
          body = { ok: true, status: 'RUNNING', pending_tasks: [], attachments: [], timeline_entries: [] };
        } else {
          body = { count: 0, events: [] };
        }
        return { ok: body.ok !== false, json: async () => body };
      };
    },
  });
  const input = dom.window.document.getElementById('files');
  let selected = [];
  // jsdom 无系统文件选择器；模拟选择状态，并保留清空 input.value 的真实语义。
  Object.defineProperty(input, 'files', { get: () => selected });
  Object.defineProperty(input, 'value', {
    get: () => selected.length ? 'C:\\fakepath\\合同.pdf' : '',
    set: (value) => { if (value === '') selected = []; },
  });
  return {
    dom,
    requests,
    selectFile() {
      /** 模拟用户选择一个 PDF，随后触发页面的文件选择事件。 */
      selected = [new dom.window.File(['%PDF-content'], '合同.pdf', { type: 'application/pdf' })];
      input.dispatchEvent(new dom.window.Event('change'));
    },
  };
}

/** 等待按钮操作完成，防止断言跑在异步上传和审批请求之前。 */
async function clickAndWait(page, id) {
  const button = page.dom.window.document.getElementById(id);
  button.click();
  for (let attempt = 0; attempt < 100; attempt += 1) {
    await new Promise((resolve) => setImmediate(resolve));
    if (!button.disabled) return;
  }
  throw new Error('页面操作未完成：' + id);
}

test('选择文件后直接发起，会先上传并携带 file_ids', async () => {
  const page = createPage();
  try {
    page.selectFile();
    await clickAndWait(page, 'start');
    const upload = page.requests.find((request) => request.url === '/_upload');
    assert.ok(upload, '选中文件必须先调用上传接口');
    assert.equal(upload.options.body.getAll('files')[0].name, '合同.pdf');
    const start = page.requests.find((request) => request.url === '/start');
    assert.deepEqual(JSON.parse(start.options.body).file_ids, ['file-1']);
    assert.ok(page.requests.indexOf(upload) < page.requests.indexOf(start));
  } finally {
    page.dom.window.close();
  }
});

test('上传失败时停止发起，保留所选文件以便重试', async () => {
  const page = createPage(false);
  try {
    page.selectFile();
    await clickAndWait(page, 'start');
    assert.ok(page.requests.some((request) => request.url === '/_upload'));
    assert.equal(page.requests.some((request) => request.url === '/start'), false);
    assert.equal(page.dom.window.document.getElementById('files').files.length, 1);
    assert.match(page.dom.window.document.getElementById('result').textContent, /上传失败/);
  } finally {
    page.dom.window.close();
  }
});

test('先手动上传再发起，沿用 file_id 且不重复上传', async () => {
  const page = createPage();
  try {
    page.selectFile();
    await clickAndWait(page, 'upload');
    await clickAndWait(page, 'start');
    assert.equal(page.requests.filter((request) => request.url === '/_upload').length, 1);
    const start = page.requests.find((request) => request.url === '/start');
    assert.deepEqual(JSON.parse(start.options.body).file_ids, ['file-1']);
  } finally {
    page.dom.window.close();
  }
});

test('未选择附件时可直接发起，不调用上传接口', async () => {
  const page = createPage();
  try {
    await clickAndWait(page, 'start');
    assert.equal(page.requests.some((request) => request.url === '/_upload'), false);
    assert.ok(page.requests.some((request) => request.url === '/start'));
  } finally {
    page.dom.window.close();
  }
});
