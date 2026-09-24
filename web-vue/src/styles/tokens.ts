/**
 * 设计令牌的 TypeScript 侧。
 *
 * Ant Design Vue 的主题 token 走的是 JS 对象，无法像 Element Plus 那样直接 `var(--indigo)`，
 * 所以这里放一份与 tokens.css 同源的常量。**改颜色时两边一起改**，别只改一处。
 */
export const PALETTE = {
  paper: '#f2f4f5',
  surface: '#ffffff',
  surfaceSunken: '#f7f9fa',

  ink: '#16202b',
  ink2: '#4a5763',
  ink3: '#7c8894',

  indigo: '#2c4a73',
  indigoDark: '#223a5c',
  indigoWash: '#eaf0f7',

  pine: '#2c6b4f',
  pineWash: '#e9f2ed',

  cinnabar: '#a8342a',
  cinnabarWash: '#fbedeb',

  amber: '#8a5a12',
  amberWash: '#fbf2e2',

  rule: '#d5dbe0',
  ruleWeak: '#e7ebee',
} as const

export const FONT_FAMILY =
  '"PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
