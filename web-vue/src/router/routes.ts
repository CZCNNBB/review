import type { RouteRecordRaw } from 'vue-router'

/**
 * 路由表。与原版 web/app.js 的 hash 一一对应，链接可直接沿用（#/tenants、#/versions/:id …）。
 * 所有页面懒加载：控制台首屏只加载壳与当前页。
 */
export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/overview' },

  { path: '/overview', name: 'overview', component: () => import('@/views/OverviewView.vue') },

  { path: '/tenants', name: 'tenants', component: () => import('@/views/TenantsView.vue') },
  {
    path: '/tenants/:id',
    name: 'tenant-detail',
    component: () => import('@/views/TenantDetailView.vue'),
  },

  { path: '/people', name: 'people', component: () => import('@/views/PeopleView.vue') },

  { path: '/processes', name: 'processes', component: () => import('@/views/ProcessesView.vue') },
  {
    path: '/processes/:id',
    name: 'process-detail',
    component: () => import('@/views/ProcessDetailView.vue'),
  },
  {
    path: '/versions/:id',
    name: 'version-editor',
    component: () => import('@/views/VersionEditorView.vue'),
  },

  {
    path: '/definitions',
    name: 'definitions',
    component: () => import('@/views/DefinitionsView.vue'),
  },
  { path: '/actions', name: 'actions', component: () => import('@/views/BusinessActionsView.vue') },
  // 授权并进了租户详情页。旧链接直接落到租户列表，别让书签掉进 404。
  { path: '/grants', redirect: '/tenants' },

  { path: '/tasks', name: 'tasks', component: () => import('@/views/TasksView.vue') },
  {
    path: '/instances/:id',
    name: 'instance',
    component: () => import('@/views/InstanceView.vue'),
  },
  { path: '/start', name: 'start', component: () => import('@/views/StartView.vue') },

  {
    path: '/executions',
    name: 'executions',
    component: () => import('@/views/ExecutionsView.vue'),
  },
  {
    path: '/executions/:id',
    name: 'execution-detail',
    component: () => import('@/views/ExecutionDetailView.vue'),
  },

  { path: '/usages', name: 'usages', component: () => import('@/views/UsagesView.vue') },

  // 两库共存基线页：阶段 0 的验收物，不进左侧导航。全部页面迁完后连同这条路由一起删掉。
  { path: '/__baseline', name: 'baseline', component: () => import('@/views/BaselineView.vue') },

  // 未知 hash 与原版一致：回到闭环进度
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

/** 左侧导航分组，与原版 NAV 表一致。 */
export interface NavItem {
  key: string
  hash: string
  label: string
}

export interface NavGroup {
  group: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    group: '闭环',
    items: [
      { key: 'overview', hash: '#/overview', label: '闭环进度' },
      { key: 'tenants', hash: '#/tenants', label: '租户' },
      { key: 'people', hash: '#/people', label: '人员与部门' },
    ],
  },
  {
    group: '流程配置',
    items: [
      { key: 'processes', hash: '#/processes', label: '审批流' },
      { key: 'definitions', hash: '#/definitions', label: '节点定义' },
      { key: 'actions', hash: '#/actions', label: '业务动作' },
    ],
  },
  {
    group: '运行',
    items: [
      { key: 'tasks', hash: '#/tasks', label: '审批任务' },
      { key: 'start', hash: '#/start', label: '发起审批' },
      { key: 'executions', hash: '#/executions', label: '执行记录' },
      { key: 'usages', hash: '#/usages', label: '使用记录' },
    ],
  },
]

/** 子页面归属到哪个导航项高亮：版本编辑器挂在审批流下，审批详情挂在审批任务下。 */
const NAV_ALIAS: Record<string, string> = {
  versions: 'processes',
  instances: 'tasks',
}

/**
 * 由当前路径推出要高亮的导航项 key。
 * 与旧版同口径：取路径首段，子页面按别名归到父项；不认识的路径回落到闭环进度。
 */
export function activeNavKey(path: string | null | undefined): string {
  const head =
    String(path ?? '')
      .replace(/^\//, '')
      .split(/[/?]/)[0] || 'overview'
  if (NAV_ALIAS[head]) return NAV_ALIAS[head]
  const known = NAV.some((group) => group.items.some((item) => item.key === head))
  return known ? head : 'overview'
}
