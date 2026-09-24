/**
 * 开发服务器的地址，配置与全局预热共用一份。
 *
 * 预热跑在 globalSetup 里，那时还没有 test 的 baseURL（那是 per-test 的 context 选项），
 * 所以页面跳转要用绝对地址 —— 两边都从这里取，避免端口写两遍对不上。
 */
export const PORT = Number(process.env.E2E_PORT || 5199)
export const BASE_URL = process.env.E2E_BASE_URL || `http://127.0.0.1:${PORT}`
