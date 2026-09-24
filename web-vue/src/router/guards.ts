import type { Router } from 'vue-router'

import { useVersionEditorStore } from '@/stores/versionEditor'

/**
 * 契约①：版本编辑器的工作副本只在两种情况下丢弃 —— 保存成功、或离开编辑器路由。
 *
 * 放在全局守卫里而不是组件的 onBeforeRouteLeave：后者只覆盖组件内发起的导航，
 * 浏览器后退等路径不一定走到；全局守卫是唯一能兜住全部入口的地方，
 * 这也是工作副本必须放 Pinia 的原因（守卫需要一个能直接引用的全局点）。
 */
export function registerGuards(router: Router): void {
  router.beforeEach((to, from) => {
    const leavingEditor = from.path.startsWith('/versions/') && !to.path.startsWith('/versions/')
    if (!leavingEditor) return true

    const editor = useVersionEditorStore()
    if (editor.loaded) editor.reset()
    return true
  })
}
