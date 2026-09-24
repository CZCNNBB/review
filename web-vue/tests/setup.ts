import { afterEach, vi } from 'vitest'

/**
 * 组件测试的公共准备。
 * 两库都会用到 jsdom 没实现的两个浏览器 API，缺了会在挂载时直接报错。
 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub)

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

afterEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
})
