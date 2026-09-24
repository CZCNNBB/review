import { describe, expect, it } from 'vitest'

import type { BusinessAction, BusinessActionBinding, Process, ProcessBinding } from '@/api/types'
import { actionGrantRows, processGrantRows } from '@/utils/grantRows'

function process(over: Partial<Process> & { id: string }): Process {
  return {
    name: `流程 ${over.id}`,
    description: null,
    status: 'ENABLED',
    current_version_id: null,
    current_version_no: null,
    draft_version_id: null,
    draft_version_no: null,
    node_count: 0,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  }
}

function action(over: Partial<BusinessAction> & { id: string }): BusinessAction {
  return {
    action_code: `CODE_${over.id}`,
    name: `动作 ${over.id}`,
    description: null,
    http_method: 'POST',
    relative_path: '/pay',
    request_schema: null,
    success_status_codes: [200],
    timeout_ms: 5000,
    status: 'ENABLED',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  }
}

function processBinding(over: Partial<ProcessBinding> & { id: string }): ProcessBinding {
  return {
    tenant_id: 't1',
    process_id: 'p1',
    status: 'ENABLED',
    created_at: '2026-09-24T06:00:00Z',
    updated_at: '2026-09-24T06:00:00Z',
    ...over,
  }
}

function actionBinding(
  over: Partial<BusinessActionBinding> & { id: string },
): BusinessActionBinding {
  return {
    tenant_id: 't1',
    business_action_id: 'a1',
    status: 'ENABLED',
    created_at: '2026-09-24T06:00:00Z',
    updated_at: '2026-09-24T06:00:00Z',
    ...over,
  }
}

const PROCESS_ID = '41000000-0000-4000-8000-000000000001'

describe('授权行', () => {
  it('绑定的资源还在表里：显示名称与短 ID，按授权状态给行状态', () => {
    const rows = processGrantRows(
      [processBinding({ id: 'b1', process_id: PROCESS_ID })],
      [process({ id: PROCESS_ID, name: '付款审批流程' })],
    )

    expect(rows).toEqual([
      {
        id: 'b1',
        resourceId: PROCESS_ID,
        name: '付款审批流程',
        resourceShortId: '41000000',
        status: 'ENABLED',
        resourceDisabled: false,
        created_at: '2026-09-24T06:00:00Z',
      },
    ])
  })

  it('资源查不到时回退短 ID，且不硬说它停用了', () => {
    const rows = processGrantRows([processBinding({ id: 'b1', process_id: PROCESS_ID })], [])

    expect(rows[0].name).toBe('41000000')
    expect(rows[0].resourceDisabled).toBe(false)
  })

  it('资源自身被停用要标出来 —— 授权还在，但发起时照样会失败', () => {
    const rows = processGrantRows(
      [processBinding({ id: 'b1', process_id: PROCESS_ID })],
      [process({ id: PROCESS_ID, status: 'DISABLED' })],
    )

    expect(rows[0].status).toBe('ENABLED')
    expect(rows[0].resourceDisabled).toBe(true)
  })

  it('停用中的授权仍然出现在列表里（否则没法再启用）', () => {
    const rows = processGrantRows(
      [processBinding({ id: 'b1', process_id: PROCESS_ID, status: 'DISABLED' })],
      [process({ id: PROCESS_ID })],
    )

    expect(rows).toHaveLength(1)
    expect(rows[0].status).toBe('DISABLED')
  })

  it('业务动作的名字带上 action_code，配置里到处用的是它', () => {
    const rows = actionGrantRows(
      [actionBinding({ id: 'b2', business_action_id: 'act-1' })],
      [action({ id: 'act-1', name: '执行付款', action_code: 'PAYMENT_EXECUTE' })],
    )

    expect(rows[0].name).toBe('执行付款（PAYMENT_EXECUTE）')
  })
})
