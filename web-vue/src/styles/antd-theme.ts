import type { ThemeConfig } from 'ant-design-vue/es/config-provider/context'

import { FONT_FAMILY, PALETTE } from './tokens'

/**
 * Ant Design Vue 的主题 token。
 *
 * 两条硬约束：
 * 1. 颜色只能来自 PALETTE，不许在这里写新的 hex —— 与 tokens.css 同源。
 * 2. `zIndexPopupBase` 必须高于 Element Plus 的弹窗层级（2000），否则
 *    ElDialog 里的 a-tooltip / a-select 下拉会被压在弹窗下面看不见。
 */
export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: PALETTE.indigo,
    colorSuccess: PALETTE.pine,
    colorError: PALETTE.cinnabar,
    colorWarning: PALETTE.amber,

    colorText: PALETTE.ink,
    colorTextSecondary: PALETTE.ink2,
    colorTextTertiary: PALETTE.ink3,
    colorTextDescription: PALETTE.ink3,

    colorBorder: PALETTE.rule,
    colorBorderSecondary: PALETTE.ruleWeak,

    colorBgLayout: PALETTE.paper,
    colorBgContainer: PALETTE.surface,
    colorFillQuaternary: PALETTE.surfaceSunken,

    borderRadius: 4,
    borderRadiusLG: 6,
    borderRadiusSM: 4,

    fontFamily: FONT_FAMILY,
    fontSize: 14,
    controlHeight: 32,

    // 现有设计里阴影只用于浮层，不用来做卡片投影
    boxShadow: '0 6px 20px rgba(22, 32, 43, 0.12)',
    boxShadowSecondary: '0 6px 20px rgba(22, 32, 43, 0.12)',

    zIndexPopupBase: 3000,
    motionDurationMid: '0.12s',
    motionDurationSlow: '0.12s',
  },
}
