import type { BusinessAction, BusinessActionBinding, Process, ProcessBinding } from '@/api/types'

import { shortId } from './format'

/**
 * 授权行的展示模型。
 *
 * 授权接口给的是绑定记录（只有资源 UUID 和状态），要显示名称得跟资源表拼一次；
 * 拼不上的（资源被删了、或者资源表没拉起来）回退短 ID —— 与旧的授权页同一口径。
 *
 * 还要把"资源本身已停用"单独标出来：授权还在，但流程/动作已经停用，发起时照样会
 * 失败。列表里不标，用户就只能对着一个启用中的授权猜为什么不行。
 */
export interface GrantRow {
  /** 绑定记录 id —— 停用/启用接口用的是它，不是资源 id */
  id: string
  resourceId: string
  name: string
  resourceShortId: string
  /** 授权本身的状态：ENABLED / DISABLED（停用后记录仍在列表里，还能再启用） */
  status: string
  /** 被授权的资源是否已经不处于启用状态 */
  resourceDisabled: boolean
  created_at: string
}

function row(
  id: string,
  resourceId: string,
  name: string,
  status: string,
  resourceDisabled: boolean,
  created_at: string,
): GrantRow {
  return {
    id,
    resourceId,
    name,
    resourceShortId: shortId(resourceId),
    status,
    resourceDisabled,
    created_at,
  }
}

export function processGrantRows(bindings: ProcessBinding[], processes: Process[]): GrantRow[] {
  return bindings.map((binding) => {
    const process = processes.find((item) => item.id === binding.process_id)
    return row(
      binding.id,
      binding.process_id,
      process ? process.name : shortId(binding.process_id),
      binding.status,
      process ? process.status !== 'ENABLED' : false,
      binding.created_at,
    )
  })
}

export function actionGrantRows(
  bindings: BusinessActionBinding[],
  actions: BusinessAction[],
): GrantRow[] {
  return bindings.map((binding) => {
    const action = actions.find((item) => item.id === binding.business_action_id)
    return row(
      binding.id,
      binding.business_action_id,
      // 动作名带 action_code：配置里到处用的是 code，看着名字能对上
      action ? `${action.name}（${action.action_code}）` : shortId(binding.business_action_id),
      binding.status,
      action ? action.status !== 'ENABLED' : false,
      binding.created_at,
    )
  })
}
