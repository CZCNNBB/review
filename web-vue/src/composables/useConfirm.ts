import { ElMessageBox } from 'element-plus'

import { ApiError } from '@/api/errors'

export interface ConfirmOptions {
  title: string
  message: string
  submitText?: string
  /** 危险操作把确认按钮染成朱砂色。 */
  danger?: boolean
}

/**
 * 二次确认。返回 true 表示用户点了确认。
 *
 * 对应旧版的 confirmDialog()。Esc 与点遮罩都算取消 —— 危险操作不能被误触。
 */
export async function confirmAction(options: ConfirmOptions): Promise<boolean> {
  try {
    await ElMessageBox.confirm(options.message, options.title, {
      confirmButtonText: options.submitText || '确定',
      cancelButtonText: '取消',
      type: options.danger ? 'warning' : 'info',
      customClass: options.danger ? 'confirm--danger' : '',
      draggable: false,
      closeOnClickModal: false,
    })
    return true
  } catch {
    return false
  }
}

/** 把操作里的异常统一转成一句可展示的话。 */
export function errorMessageOf(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return String(err)
}
