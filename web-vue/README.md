# 审批中心配置台 · Vue3 + TypeScript

管理台的前端工程化实现。功能与旧的 `backend/web/`（单文件 vanilla JS）逐页对齐，视觉沿用同一套设计令牌，旧版原样保留作为行为对照。

## 跑起来

```bash
npm install
npm run dev          # 开发：http://localhost:5173
npm run build        # 产物到 dist/，由后端挂到 /console
npm run preview      # 预览构建产物
npm run typecheck    # vue-tsc --noEmit
npm run lint         # ESLint（含两个组件库的分工白名单）
npm test             # Vitest：纯函数 + store 契约 + 组件
npm run e2e          # Playwright：跑真浏览器，要一个真后端（见下）
```

端到端用例没有内置数据来源，跑之前指一个后端过去（不配就整体跳过，不会假装跑过）：

```bash
E2E_BACKEND=http://127.0.0.1:8090 \
E2E_ADMIN_KEY=<后端 .env 里的 APPROVAL_ADMIN_KEY> \
npm run e2e
```

后端里得有个**至少两个节点、含条件分支节点的草稿版本**，用例需要的节点都从现有的图里现找；找不到就跳过并说明缺什么。会写库的那条（保存草稿）另要 `E2E_ALLOW_WRITES=1` 才跑，跑完会把改过的字段改回去——开发库是共用的。

三份用例：`canvas.spec.ts`（画布交互与三条契约）、`editor.spec.ts`（工作副本与只读版本）、`pages.spec.ts`（12 个页面各开一遍，挡白屏与整页失败态）。

**部署**：`npm run build` 后重启后端，访问 `http://后端地址:8090/console/`。前端路由是 hash 模式，`/console/` 一个入口就能兜住全部页面，后端不需要 history fallback；`dist/` 不存在时后端照常启动。

## 技术栈

| 用途 | 选型 |
| --- | --- |
| 框架 / 构建 | Vue 3 + TypeScript + Vite |
| 路由 / 状态 | vue-router（hash 模式）· Pinia（+ 持久化） |
| 组件库 | Element Plus + Ant Design Vue（分工见下） |
| 请求 / 工具 | axios · @vueuse/core · dayjs |
| 规范 / 测试 | ESLint + Prettier · Vitest + @vue/test-utils · Playwright |

### 两个组件库的分工规则

> **AntD 负责「把数据摆出来」，Element Plus 负责「把数据录进去」，签名元素两库都不用。**

| 场景 | 选型 |
| --- | --- |
| 数据表、键值面板、页签、空态、整页失败态、Tooltip/Popconfirm | Ant Design Vue |
| 弹窗壳、二次确认、全局提示、所有表单控件、人员多选、加载态 | Element Plus |
| 状态标签 `.tag`、状态戳 `.stamp`、会签时间线 `.timeline`、画布 `.flow*` | 自研（签名元素，见 `styles/signature.css`） |

三条纪律，前两条由 `eslint.config.js` 机械执行：

1. 两库都**显式 import**，不用组件自动导入解析器 —— 有 17 个组件名在两库里重名（`Table`、`Select`、`Tabs`、`Tooltip`…），同时开两个 resolver 必然撞名。
2. 双向白名单：Element 侧禁 `ElTable`/`ElTabs`/`ElEmpty` 等展示件，AntD 侧禁 `Form`/`Input`/`Select`/`Modal` 等录入件。类型导入不受限（`allowTypeImports`）。
3. 一个 role 只有一种实现：表格永远走 `DataTable.vue`，弹窗永远走 `AppDialog.vue`。

主题化：`styles/tokens.css` 是唯一色值源（沿用旧版变量名，`signature.css` 才能整体搬运），Element 走 CSS 变量覆盖、AntD 走 `ConfigProvider` 的 `theme.token`。**两库都关掉了默认阴影与过渡**（现有设计里阴影只用于浮层，圆角只有 4/6px）。AntD 的 `zIndexPopupBase` 提到 3000，否则 ElDialog 里的 Tooltip/下拉会被压在弹窗下面。

## 目录结构

```
src/
├── api/          http.ts（axios 实例：注入密钥、拆 {code,msg,data}、错误归一）
│                 endpoints.ts 路径集中  ·  modules/* 按资源分组  ·  types.ts 实体类型
├── stores/       config（接口地址/密钥）· credentials（租户密钥借用缓存）
│                 shell（侧栏计数）· versionEditor（版本编辑器工作副本）
├── composables/  useFlowCanvas（画布状态机）· useAsyncPage · useConfirm
│                 useUrlFilters（筛选条件 ↔ 地址栏）· useClipboard
├── utils/        纯函数：flowGeometry · flowBranch · flowLayout · flowCanvasModel
│                 schemaForm · schemaConfig · condition · nodeConfigForm · payload
│                 format · json · id · status · table · notify
├── components/   layout/（AppRail AppTopbar PageHead PanelCard KvDescriptions …）
│                 common/（DataTable AppDialog StatusTag StatusStamp IssuesDialog …）
│                 form/（DynamicForm）· schema/（FormFieldTable）· flow/（画布与弹窗）
│                 dialogs/（页面专属弹窗，一弹窗一 SFC）
├── views/        17 个页面 SFC（与路由一一对应）
└── styles/       tokens · base · signature（禁区）· element-theme · antd-theme · overrides
```

## 必须保住的行为契约

每一条都有对应测试钉住（`tests/` 与 `e2e/`）。

| # | 契约 | 测试落点 |
| --- | --- | --- |
| ① | 版本编辑器的工作副本：切页签、开弹窗、拖动画布都不丢未保存改动；只有离开路由或保存成功才丢弃 | `stores/versionEditor.spec.ts` + `e2e/editor.spec.ts` |
| ② | 保存载荷原样带上 `revision` 乐观锁 | `utils/payload.spec.ts` + `stores/versionEditor.spec.ts` |
| ③ | 条件分支出线顺序 = 运行时匹配顺序，最后一条恒为「其余情况」且不带 condition | `utils/flow.spec.ts` + `components/BranchDialog.spec.ts` + `e2e/canvas.spec.ts` |
| ④ | 普通节点只能有一条出线，分流必须走条件分支节点 | `utils/flow.spec.ts` + `e2e/canvas.spec.ts` |
| ⑤ | 拖节点位移 ≤2px 视为点击（打开节点配置弹窗） | `utils/flow.spec.ts` + `e2e/canvas.spec.ts` |
| ⑥ | 节点 ID 由前端生成（uuid），保存时才提交 | `utils/misc.spec.ts` |
| ⑦ | 只读版本（status ≠ DRAFT）画布与表单都不可编辑 | `stores/versionEditor.spec.ts` + `e2e/editor.spec.ts` |
| ⑧ | 管理台按「使用记录 → 租户 → 有效 Key」自动借用租户密钥并缓存，写操作后失效 | `stores/credentials`（单测）+ 各运行侧页面 |

### 画布的取舍（唯一"反 Vue 直觉"的地方）

旧实现能边拖边改 `node.position`，是因为它只写 `el.style` 和 `path.d`，绕过了渲染层；Vue 里每次改 position 都会触发全量 computed 重算 + v-for patch。所以：

1. **拖动期间不写任何响应式数据** —— 位移只写 DOM 的 `transform`，`nodes` 原地不动；
2. 位置在 `pointerup` 才提交一次（提交值与 DOM 上完全一致，视觉零跳变）；
3. 拖动中的坐标放在一个非响应式 `Map` 里传给几何计算；
4. 每帧只重算**与拖动节点相连的那几条线**（旧版是全量重算）。

命中判定顺序也照搬旧版：**端口判定必须排在 `data-act` 前面**（分支行的圆点画在带 `data-act` 的行内部，顺序反了会把"按住圆点拉线"误当成"点这一行"）。

## 与旧版 `backend/web/` 的行为差异

移植是照搬为主，下面这些是刻意的改动，逐条列出便于对照：

**修掉的旧问题**

1. `pruneNodeConfig` 在找不到节点定义时会把节点配置**整份清空**并静默保存 —— 改成原样保留，交给后端校验。
2. 节点配置弹窗**漏传回填值**，导致"打开配置直接保存"会把审批模式从 OR 改成 AND、把审批人清空 —— 已回填。
3. 节点名称曾是必填，每次编辑都要重打 —— 现在留空即用定义名。
4. `#/tenants` 列表行的「编辑」按钮没有对应处理函数，点了没反应 —— 已接上。
5. 列表页 `railCounts.persons` 与导航 key `people` 不匹配，人员徽标从来没亮过 —— 已对齐。
6. 业务动作编辑弹窗每次提交都会写 `description: null`，把已配好的说明抹掉 —— 不再提交该字段。
7. 部门成员弹窗把「停用过的成员」也排除在候选之外且无恢复入口，等于停用即永久移除 —— 现在只排除仍启用的。
8. 签发 API Key 后自动复制一次并关窗，复制失败密钥就永久丢失 —— 改为停在「复制明文」态，确认后关闭。
9. 条件取值里的数组以前用带缩进的 JSON，渲染在单行小药丸里会被截断 —— 改成紧凑 JSON。
10. 若干处理器没有 try/catch（靠全局兜底） —— 统一 catch + toast。
11. 用 `esc()` 拼 URL 参数、以及"页面头部注册了但没人用的 action"这类死代码 —— 未移植。
12. **通用表单弹窗的必填校验**：曾依赖 ElForm 的表单级校验，而它对空值也返回通过（必填形同虚设）—— 改为组件自己判定，语义是"空串/null/undefined/空数组都算没填"。

**刻意的行为变化**

13. 页面里用 `?tab=` 表达页签（人员与部门）、`?person=` / `?status=` / `?tenant=` / `?business_key=` 表达筛选 —— 刷新与分享链接能保持同一视图。旧版部分是模块级变量，切走再回来会重置。
14. 主数据（人员、租户、密钥）加载失败时显示整页错误面板，只有辅助数据才静默兜底 —— 旧版一律 `safe()`，失败时表现为"空空如也"，很难排查。
15. 弹窗里的说明文案（开始/条件分支/结束节点）从拼 HTML 的 `data-act` 按钮改成结构化数据 + 真实按钮，全库不再使用 `v-html`。
16. **示例数据模式（旧版 `demo.js`）没有移植**：它只是为了在没后端时把页面点一遍，实际联调里是个要一直维护两套数据源的负担。现在接口报错就如实报错。

**保持不变**

- 接口路径、请求头（`X-Admin-Key` / `X-API-Key`）、`{code,msg,data}` 信封、错误文案（含 401/403/404/503 的中文兜底）。
- localStorage 键：`approval-console.config`（老用户填过的接口地址与密钥无感迁移）。
- 「按租户/按人扇出拉全量再前端合并」的取数方式（分页优化另开任务）。
- 管理台代审批人处理任务（用任务所属审批人的身份调用），这是联调设计不是漏洞。

## 还没做的

- 组件级的下拉按需引入（现在整包引了两个库的 CSS，388KB / gzip 后 54KB）。
- 列表分页（后端接口目前是 limit 拉全量）。
- 审批人页面（面向审批人员的界面）—— 本工程只覆盖管理台。
- 深色模式、i18n。
