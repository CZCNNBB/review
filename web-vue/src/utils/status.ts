/** 后端状态码 → 中文。控制台所有状态展示都走这里，不许在页面里另写映射。 */
export const STATUS_TEXT: Record<string, string> = {
  ENABLED: '启用',
  DISABLED: '停用',
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  RUNNING: '审批中',
  APPROVED: '已通过',
  REJECTED: '已拒绝',
  CANCELLED: '已取消',
  ERROR: '异常',
  PENDING: '待办',
  ACTIVE: '进行中',
  COMPLETED: '已完成',
  SUCCEEDED: '成功',
  FAILED: '失败',
}

/** 状态标签的四种语气，对应 .tag--on / off / wait / work 四套配色。 */
export type TagTone = 'on' | 'off' | 'wait' | 'work'

const TAG_ON = ['ENABLED', 'APPROVED', 'PUBLISHED', 'SUCCEEDED', 'COMPLETED']
const TAG_OFF = ['DISABLED', 'REJECTED', 'FAILED', 'ERROR', 'CANCELLED']
const TAG_WAIT = ['PENDING', 'DRAFT']

export function statusText(status?: string | null): string {
  if (!status) return '—'
  return STATUS_TEXT[status] || status
}

export function tagTone(status?: string | null): TagTone {
  if (status && TAG_ON.includes(status)) return 'on'
  if (status && TAG_OFF.includes(status)) return 'off'
  if (status && TAG_WAIT.includes(status)) return 'wait'
  return 'work'
}

/** 审批单详情页大图章的语气：通过 / 拒绝 / 审批中 / 其他。 */
export type StampTone = 'approved' | 'rejected' | 'running' | 'idle'

export function stampTone(status?: string | null): StampTone {
  if (status === 'APPROVED') return 'approved'
  if (status === 'REJECTED') return 'rejected'
  if (status === 'RUNNING') return 'running'
  return 'idle'
}
