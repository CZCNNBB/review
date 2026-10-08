import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fileApi } from '@/api/modules/file'
import type { ApprovalAttachment } from '@/api/types'
import ApprovalAttachments from '@/components/common/ApprovalAttachments.vue'

vi.mock('@/api/modules/file', () => ({ fileApi: { download: vi.fn() } }))

const DialogStub = defineComponent({
  props: ['open', 'title'],
  emits: ['update:open'],
  template: '<section v-if="open" class="preview-dialog"><slot /><slot name="footer" /></section>',
})
const wrappers: VueWrapper[] = []
const createObjectURL = vi.fn(() => 'blob:attachment-preview')
const revokeObjectURL = vi.fn()

/** 构造文件元数据，测试仅支持的格式会出现预览入口。 */
function attachment(id: string, type: string): ApprovalAttachment {
  return { file_id: id, file_name: id, content_type: type, size_bytes: 100, uploaded_at: '' }
}

/** 挂载共享附件组件，弹窗只替换外壳，保留实际预览内容与关闭逻辑。 */
function mountAttachments(files: ApprovalAttachment[]): VueWrapper {
  const wrapper = mount(ApprovalAttachments, {
    props: { attachments: files },
    global: { stubs: { AppDialog: DialogStub } },
  })
  wrappers.push(wrapper)
  return wrapper
}

/** 按可见文案点击按钮，覆盖用户操作路径。 */
async function clickButton(wrapper: VueWrapper, text: string): Promise<void> {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === text)
  if (!button) throw new Error('未找到按钮：' + text)
  await button.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
})

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
})

describe('审批和抄送共用附件预览', () => {
  it('图片和 PDF 有预览入口，Word 和 Excel 保留下载', () => {
    const wrapper = mountAttachments([
      attachment('图片.png', 'image/png'),
      attachment('材料.pdf', 'application/pdf'),
      attachment(
        '文档.docx',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      ),
      attachment('表格.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    ])
    expect(wrapper.findAll('button').filter((button) => button.text() === '预览')).toHaveLength(2)
    expect(wrapper.findAll('button').filter((button) => button.text() === '下载')).toHaveLength(4)
  })

  it('取得已鉴权的图片内容后展示，关闭时释放文件 URL', async () => {
    vi.mocked(fileApi.download).mockResolvedValue(new Blob(['image'], { type: 'image/png' }))
    const wrapper = mountAttachments([attachment('图片.png', 'image/png')])
    await clickButton(wrapper, '预览')
    expect(fileApi.download).toHaveBeenCalledWith('图片.png')
    expect(wrapper.get('img').attributes('src')).toBe('blob:attachment-preview')
    await clickButton(wrapper, '放大')
    expect(wrapper.get('img').attributes('style')).toContain('125%')
    await clickButton(wrapper, '关闭')
    expect(wrapper.find('.preview-dialog').exists()).toBe(false)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:attachment-preview')
  })

  it('PDF 使用取得的文件内容预览，下载按钮仍然可用', async () => {
    vi.mocked(fileApi.download).mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }))
    const wrapper = mountAttachments([attachment('材料.pdf', 'application/pdf')])
    await clickButton(wrapper, '预览')
    expect(wrapper.get('iframe').attributes('src')).toBe('blob:attachment-preview')
    expect(wrapper.get('iframe').attributes('title')).toContain('材料.pdf')
    expect(wrapper.text()).toContain('下载原文件')
    wrapper.unmount()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:attachment-preview')
  })

  it('加载失败显示错误并允许重试', async () => {
    vi.mocked(fileApi.download)
      .mockRejectedValueOnce(new Error('文件暂时不可读取'))
      .mockResolvedValueOnce(new Blob(['image'], { type: 'image/jpeg' }))
    const wrapper = mountAttachments([attachment('图片.jpg', 'image/jpeg')])
    await clickButton(wrapper, '预览')
    expect(wrapper.get('[role="alert"]').text()).toContain('文件暂时不可读取')
    await clickButton(wrapper, '重试')
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('关闭后才完成的请求不能创建文件 URL 或重新打开弹窗', async () => {
    let resolveDownload!: (blob: Blob) => void
    vi.mocked(fileApi.download).mockReturnValue(
      new Promise<Blob>((resolve) => {
        // 暂停文件响应，模拟大附件仍在加载时用户关闭弹窗。
        resolveDownload = resolve
      }),
    )
    const wrapper = mountAttachments([attachment('图片.png', 'image/png')])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '预览')!
      .trigger('click')
    expect(wrapper.get('[role="status"]').text()).toContain('正在加载')
    await clickButton(wrapper, '关闭')
    resolveDownload(new Blob(['image']))
    await flushPromises()
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.find('.preview-dialog').exists()).toBe(false)
  })
})
