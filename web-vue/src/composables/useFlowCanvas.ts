import { onBeforeUnmount, ref, type Ref } from 'vue'

import type { FlowConnection, FlowNode, Point } from '@/types/domain'
import { isDragGesture } from '@/utils/flowBranch'
import { createFlowGeometry } from '@/utils/flowGeometry'

export interface FlowCanvasCallbacks {
  onSelectNode: (nodeId: string) => void
  /** branch 为 null 表示从普通节点的出口拉的线 */
  onConnect: (sourceId: string, targetId: string, branch: string | number | null) => void
  onMoveNode: (nodeId: string, position: Point) => void
  onCreateNode: (definitionId: string, position: Point) => void
  /** 新开的分支需要补条件时，直接打开分支编辑器 */
  onEditNode: (nodeId: string) => void
}

interface FlowCanvasOptions {
  viewportRef: Ref<HTMLElement | null>
  stageRef: Ref<HTMLElement | null>
  nodes: () => FlowNode[]
  connections: () => FlowConnection[]
  editable: () => boolean
  scale: Ref<number>
  callbacks: FlowCanvasCallbacks
}

const MIN_SCALE = 0.4
const MAX_SCALE = 1.8

type Mode = 'idle' | 'pan' | 'drag-node' | 'connect'

interface DragNodeState {
  kind: 'drag-node'
  nodeId: string
  element: HTMLElement
  startClient: Point
  origin: Point
  moved: boolean
}

interface ConnectState {
  kind: 'connect'
  nodeId: string
  branch: string | number | null
  startStage: Point
}

interface PanState {
  kind: 'pan'
  startClient: Point
  scrollLeft: number
  scrollTop: number
}

type GestureState = DragNodeState | ConnectState | PanState

/**
 * 画布的交互状态机：拖节点、端口拉线、空白平移、Ctrl+滚轮缩放、面板拖入。
 *
 * **性能上的核心取舍**：拖动期间不写任何响应式数据。
 * 旧实现能边拖边改 node.position，是因为它只写 el.style 和 path.d，绕过了渲染层；
 * Vue 里每次改 position 都会触发全量 computed 重算 + v-for patch。所以这里：
 *   1. 位移只写 DOM 的 transform，nodes 数组原地不动；
 *   2. 位置在 pointerup 才提交一次（提交值与 DOM 上完全一致，视觉零跳变）；
 *   3. 拖动中的坐标放在一个**非响应式** Map 里传给几何计算；
 *   4. 每帧只重算与拖动节点相连的那几条线（旧版是全量重算）。
 */
export function useFlowCanvas(options: FlowCanvasOptions) {
  const mode = ref<Mode>('idle')
  const tempEdge = ref<string | null>(null)
  const dropHint = ref<Point | null>(null)
  const draggingNodeId = ref<string | null>(null)

  /** 拖动中的临时坐标：故意用普通 Map，不进 Vue 响应式系统。 */
  const overrides = new Map<string, Point>()
  let gesture: GestureState | null = null
  let rafId = 0
  let pendingPointer: { clientX: number; clientY: number } | null = null
  /** 面板拖入时浏览器可能在 dragover 期间不给数据，留一份兜底。 */
  let palettePayload: string | null = null

  const escape = (value: string): string =>
    typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(value) : value

  function viewport(): HTMLElement | null {
    return options.viewportRef.value
  }

  function stage(): HTMLElement | null {
    return options.stageRef.value
  }

  /** 屏幕坐标 → 画布坐标（含滚动与缩放）。 */
  function toStage(clientX: number, clientY: number): Point {
    const container = viewport()
    if (!container) return { x: 0, y: 0 }
    const rect = container.getBoundingClientRect()
    return {
      x: (container.scrollLeft + clientX - rect.left) / options.scale.value,
      y: (container.scrollTop + clientY - rect.top) / options.scale.value,
    }
  }

  /** 只重算与某个节点相连的连线：拖动时其他线不可能变。 */
  function repaintEdgesOf(nodeId: string): void {
    const stageEl = stage()
    if (!stageEl) return

    const connections = options.connections()
    const geometry = createFlowGeometry(options.nodes(), connections, overrides)

    connections.forEach((connection, index) => {
      if (connection.source_node_id !== nodeId && connection.target_node_id !== nodeId) return
      const edge = geometry.edgeOf(connection)
      if (!edge) return

      stageEl
        .querySelectorAll(`path[data-conn="${index}"]`)
        .forEach((path) => path.setAttribute('d', edge.d))

      const tools = stageEl.querySelector<HTMLElement>(`.flow__edge-tools[data-conn="${index}"]`)
      if (tools) {
        tools.style.left = `${edge.mid.x}px`
        tools.style.top = `${edge.mid.y}px`
      }
    })
  }

  function scheduleTick(): void {
    if (rafId) return
    rafId = requestAnimationFrame(() => {
      rafId = 0
      tick()
    })
  }

  function tick(): void {
    if (!gesture) return
    const pointer = pendingPointer
    if (!pointer) return

    if (gesture.kind === 'drag-node') {
      const dx = (pointer.clientX - gesture.startClient.x) / options.scale.value
      const dy = (pointer.clientY - gesture.startClient.y) / options.scale.value
      if (isDragGesture(dx, dy)) gesture.moved = true
      if (!gesture.moved) return

      const position = {
        x: Math.round(gesture.origin.x + dx),
        y: Math.round(gesture.origin.y + dy),
      }
      overrides.set(gesture.nodeId, position)
      gesture.element.style.transform = `translate3d(${position.x}px, ${position.y}px, 0)`
      repaintEdgesOf(gesture.nodeId)
      return
    }

    if (gesture.kind === 'connect') {
      const target = toStage(pointer.clientX, pointer.clientY)
      const start = gesture.startStage
      tempEdge.value = `M ${start.x} ${start.y} L ${target.x} ${target.y}`
    }
  }

  /** 拉线起点取被按住端口的中心，缩放后依然对得上。 */
  function portCenter(port: HTMLElement): Point {
    const rect = port.getBoundingClientRect()
    return toStage(rect.left + rect.width / 2, rect.top + rect.height / 2)
  }

  function onPointerDown(event: PointerEvent): void {
    const container = viewport()
    if (!container || event.button !== 0) return
    // 一次只处理一个手势
    if (mode.value !== 'idle') return

    const target = event.target as HTMLElement
    const nodeElement = target.closest<HTMLElement>('.flow__node')
    const editable = options.editable()

    // 端口判定必须排在 data-act 前面：分支行的圆点画在带 data-act 的行内部，
    // 先判 data-act 会把「按住圆点拉线」误当成「点这一行」。
    const port = target.closest<HTMLElement>('.flow__port--out, .flow__row-port')
    if (editable && nodeElement && port) {
      const rawBranch = port.dataset.branch
      mode.value = 'connect'
      gesture = {
        kind: 'connect',
        nodeId: nodeElement.dataset.id as string,
        branch: rawBranch === undefined ? null : rawBranch === 'new' ? 'new' : Number(rawBranch),
        startStage: portCenter(port),
      }
      tempEdge.value = `M ${gesture.startStage.x} ${gesture.startStage.y} L ${gesture.startStage.x} ${gesture.startStage.y}`
      container.setPointerCapture(event.pointerId)
      event.preventDefault()
      return
    }

    if (target.closest('[data-act]')) return

    if (editable && nodeElement) {
      const nodeId = nodeElement.dataset.id as string
      const node = options.nodes().find((item) => item.id === nodeId)
      if (!node) return
      mode.value = 'drag-node'
      draggingNodeId.value = nodeId
      gesture = {
        kind: 'drag-node',
        nodeId,
        element: nodeElement,
        startClient: { x: event.clientX, y: event.clientY },
        origin: { ...node.position },
        moved: false,
      }
      nodeElement.classList.add('is-dragging')
      container.setPointerCapture(event.pointerId)
      event.preventDefault()
      return
    }

    // 点线中点或标签时不平移，留给它们的点击事件
    if (target.closest('.flow__edge-label, .flow__edge-hit, .flow__edge-del')) return

    mode.value = 'pan'
    gesture = {
      kind: 'pan',
      startClient: { x: event.clientX, y: event.clientY },
      scrollLeft: container.scrollLeft,
      scrollTop: container.scrollTop,
    }
    container.classList.add('is-panning')
    container.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: PointerEvent): void {
    if (mode.value === 'idle' || !gesture) return
    pendingPointer = { clientX: event.clientX, clientY: event.clientY }

    if (gesture.kind === 'pan') {
      const container = viewport()
      if (!container) return
      container.scrollLeft = gesture.scrollLeft - (event.clientX - gesture.startClient.x)
      container.scrollTop = gesture.scrollTop - (event.clientY - gesture.startClient.y)
      return
    }

    scheduleTick()
  }

  function finishPointer(event: PointerEvent): void {
    if (mode.value === 'idle' || !gesture) return

    // 先收走状态再回调：回调里会重渲染，重入时看到的就是一致状态
    const finished = gesture
    gesture = null
    mode.value = 'idle'
    pendingPointer = null
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
    viewport()?.classList.remove('is-panning')

    if (finished.kind === 'drag-node') {
      finished.element.classList.remove('is-dragging')
      draggingNodeId.value = null
      const position = overrides.get(finished.nodeId) || finished.origin
      overrides.delete(finished.nodeId)
      if (finished.moved) options.callbacks.onMoveNode(finished.nodeId, position)
      else options.callbacks.onSelectNode(finished.nodeId)
      return
    }

    if (finished.kind === 'connect') {
      tempEdge.value = null
      const hovered = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null
      const targetNode = hovered?.closest<HTMLElement>('.flow__node')
      const targetId = targetNode?.dataset.id
      if (targetId && targetId !== finished.nodeId) {
        options.callbacks.onConnect(finished.nodeId, targetId, finished.branch)
      }
    }
  }

  /** 缩放：带焦点补偿，缩放前后光标下的内容不跑。 */
  function applyScale(next: number, focus?: Point): void {
    const container = viewport()
    if (!container) return
    const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next))
    const previous = options.scale.value
    if (clamped === previous) return

    if (focus) {
      const before = {
        x: (container.scrollLeft + focus.x) / previous,
        y: (container.scrollTop + focus.y) / previous,
      }
      options.scale.value = clamped
      requestAnimationFrame(() => {
        container.scrollLeft = before.x * clamped - focus.x
        container.scrollTop = before.y * clamped - focus.y
      })
      return
    }
    options.scale.value = clamped
  }

  function onWheel(event: WheelEvent): void {
    if (!event.ctrlKey && !event.metaKey) return
    event.preventDefault()
    const container = viewport()
    if (!container) return
    const rect = container.getBoundingClientRect()
    applyScale(options.scale.value * (event.deltaY < 0 ? 1.1 : 0.9), {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    })
  }

  /** 面板拖入的落点：以光标为中心，不越出画布左上角。 */
  function dropPosition(clientX: number, clientY: number): Point {
    const container = viewport()
    const rect = container?.getBoundingClientRect()
    const point = toStage(clientX, clientY)
    if (!container || !rect) return { x: Math.max(0, point.x), y: Math.max(0, point.y) }
    return {
      x: Math.max(0, Math.round(point.x - 92)),
      y: Math.max(0, Math.round(point.y - 35)),
    }
  }

  function onDragOver(event: DragEvent): void {
    if (!options.editable()) return
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
    dropHint.value = dropPosition(event.clientX, event.clientY)
  }

  function onDragLeave(event: DragEvent): void {
    // 只在真正离开画布容器时清提示，否则子元素之间移动会闪
    if (event.target === viewport()) dropHint.value = null
  }

  function onDrop(event: DragEvent): void {
    if (!options.editable()) return
    event.preventDefault()
    dropHint.value = null
    const definitionId = event.dataTransfer?.getData('text/plain') || palettePayload
    palettePayload = null
    if (!definitionId) return
    options.callbacks.onCreateNode(definitionId, dropPosition(event.clientX, event.clientY))
  }

  function startPaletteDrag(definitionId: string): void {
    palettePayload = definitionId
  }

  function attach(): void {
    const container = viewport()
    if (!container) return
    container.addEventListener('pointerdown', onPointerDown)
    container.addEventListener('pointermove', onPointerMove)
    container.addEventListener('pointerup', finishPointer)
    container.addEventListener('pointercancel', finishPointer)
    // 必须显式声明 passive:false 才能 preventDefault；依赖 @wheel.prevent 在部分浏览器不生效
    container.addEventListener('wheel', onWheel, { passive: false })
    container.addEventListener('dragover', onDragOver)
    container.addEventListener('dragleave', onDragLeave)
    container.addEventListener('drop', onDrop)
  }

  onBeforeUnmount(() => {
    const container = viewport()
    if (!container) return
    container.removeEventListener('pointerdown', onPointerDown)
    container.removeEventListener('pointermove', onPointerMove)
    container.removeEventListener('pointerup', finishPointer)
    container.removeEventListener('pointercancel', finishPointer)
    container.removeEventListener('wheel', onWheel)
    container.removeEventListener('dragover', onDragOver)
    container.removeEventListener('dragleave', onDragLeave)
    container.removeEventListener('drop', onDrop)
    if (rafId) cancelAnimationFrame(rafId)
  })

  return {
    tempEdge,
    dropHint,
    draggingNodeId,
    applyScale,
    attach,
    startPaletteDrag,
    toStage,
    escapeId: escape,
  }
}
