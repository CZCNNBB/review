import { describe, expect, it, vi } from 'vitest'

import type { FlowConnection, FlowNode } from '@/types/domain'
import { formatDuration, formatTime, maskSecret, orderMark, shortId } from '@/utils/format'
import { newId } from '@/utils/id'
import { parseJsonInput, stringifyJson } from '@/utils/json'
import { buildCurl, collectPayload, resolveFormSchema } from '@/utils/payload'
import { stampTone, statusText, tagTone } from '@/utils/status'

describe('格式化', () => {
  it('时间：空值给破折号，非法值原样返回，正常值格式化到分钟', () => {
    expect(formatTime(null)).toBe('—')
    expect(formatTime('')).toBe('—')
    expect(formatTime('不是时间')).toBe('不是时间')
    expect(formatTime('2026-09-24T10:05:30')).toBe('2026-09-24 10:05')
  })

  it('耗时按量级换单位', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(320)).toBe('320 毫秒')
    expect(formatDuration(1500)).toBe('1.5 秒')
    expect(formatDuration(65000)).toBe('1 分 5 秒')
    expect(formatDuration(3_900_000)).toBe('1 小时 5 分')
  })

  it('短 ID 与序号', () => {
    expect(shortId('41000000-0000-4000-8000-000000000002')).toBe('41000000')
    expect(shortId(null)).toBe('—')
    expect(orderMark(1)).toBe('①')
    expect(orderMark(3)).toBe('③')
    expect(orderMark(11)).toBe('11.')
  })

  it('密钥打码保留头尾', () => {
    expect(maskSecret('short')).toBe('short')
    expect(maskSecret('1234567890abcdefghij')).toBe('1234567890ab••••••ghij')
  })
})

describe('JSON 工具', () => {
  it('空串当空对象，非法时报中文错误', () => {
    expect(parseJsonInput('', '审批表单')).toEqual({})
    expect(parseJsonInput('{"a":1}', '审批表单')).toEqual({ a: 1 })
    expect(() => parseJsonInput('{oops', '审批表单')).toThrow('审批表单 不是合法的 JSON')
  })

  it('序列化失败时退回字符串', () => {
    const circular: Record<string, unknown> = {}
    circular.self = circular
    expect(stringifyJson(circular)).toBe('[object Object]')
    expect(stringifyJson({ a: 1 })).toBe('{\n  "a": 1\n}')
  })
})

describe('状态映射', () => {
  it('状态码翻译成中文，未知码原样显示', () => {
    expect(statusText('PENDING')).toBe('待办')
    expect(statusText('WHATEVER')).toBe('WHATEVER')
    expect(statusText(null)).toBe('—')
  })

  it('标签语气分四类', () => {
    expect(tagTone('ENABLED')).toBe('on')
    expect(tagTone('REJECTED')).toBe('off')
    expect(tagTone('PENDING')).toBe('wait')
    expect(tagTone('RUNNING')).toBe('work')
  })

  it('图章语气', () => {
    expect(stampTone('APPROVED')).toBe('approved')
    expect(stampTone('REJECTED')).toBe('rejected')
    expect(stampTone('RUNNING')).toBe('running')
    expect(stampTone('CANCELLED')).toBe('idle')
  })
})

describe('前端生成节点 ID（契约⑥）', () => {
  it('生成标准 uuid v4', () => {
    const id = newId()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(newId()).not.toBe(id)
  })

  it('crypto.randomUUID 不可用时退回手工生成', () => {
    const original = globalThis.crypto
    // 只留 getRandomValues，逼着手工拼 uuid
    vi.stubGlobal('crypto', { getRandomValues: original.getRandomValues.bind(original) })
    try {
      const id = newId()
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('保存载荷（契约②）', () => {
  const nodes: FlowNode[] = [
    {
      id: 'n1',
      node_definition_id: 'd1',
      node_type: 'START',
      name: '开始',
      config: {},
      position: { x: 10, y: 20 },
    },
  ]
  const connections: FlowConnection[] = [{ source_node_id: 'n1', target_node_id: 'n2' }]

  it('原样回传 revision，节点只提交后端认识的字段', () => {
    const payload = collectPayload({
      revision: 7,
      name: '付款审批流程',
      description: '',
      formSchema: { type: 'object', properties: {} },
      nodes,
      connections,
    })

    expect(payload.revision).toBe(7)
    expect(payload.description).toBeNull()
    expect(payload.nodes[0]).toEqual({
      id: 'n1',
      node_definition_id: 'd1',
      name: '开始',
      config: {},
      position: { x: 10, y: 20 },
    })
    expect(payload.orchestration.connections).toEqual(connections)
    // 连线是拷贝，改载荷不影响编辑器状态
    expect(payload.orchestration.connections[0]).not.toBe(connections[0])
  })

  it('高级模式下的文本框内容才是 Schema 的权威来源', () => {
    const current = { type: 'object', properties: { a: { type: 'string' } } }
    expect(resolveFormSchema(current, null)).toBe(current)
    expect(resolveFormSchema(current, '{"type":"object"}')).toEqual({ type: 'object' })
    // 非法 JSON 直接挡下保存
    expect(() => resolveFormSchema(current, '{oops')).toThrow('审批表单 Schema 不是合法的 JSON')
  })

  it('curl 示例用当前地址与密钥', () => {
    const command = buildCurl('http://127.0.0.1:8090/', 'p1', { title: 'x' }, '')
    expect(command).toContain('curl -X POST "http://127.0.0.1:8090/api/processes/p1/instances"')
    expect(command).toContain('X-API-Key: 你的租户APIKey')
    expect(command).toContain('"title": "x"')
  })
})
