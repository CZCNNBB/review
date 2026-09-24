<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref, watch } from 'vue'

import AppDialog from '@/components/common/AppDialog.vue'
import DynamicForm from '@/components/form/DynamicForm.vue'
import type { FlowNode, NodeDefinition } from '@/types/domain'
import type { DynamicFieldSpec, NodeFormNoteAction } from '@/utils/nodeConfigForm'
import { buildConfigForm, nodeFormNote } from '@/utils/nodeConfigForm'

// 节点配置弹窗：字段来自节点定义的 JSON Schema，取值回填当前配置。
// 契约：名称留空就用定义名；没有 Schema 的节点给一段说明（说明里的跳转是真实按钮）。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  node: FlowNode
  definition: NodeDefinition
  personOptions: Array<{ value: string; label: string }>
  isNew?: boolean
}>()

const emit = defineEmits<{
  (event: 'save', payload: { name: string; config: Record<string, unknown> }): void
  (event: 'goto-form'): void
  (event: 'goto-branch'): void
}>()

const config = computed(() =>
  buildConfigForm(props.definition, props.node.config, props.personOptions),
)

const values = ref<Record<string, unknown>>({})
const formRef = ref<InstanceType<typeof DynamicForm> | null>(null)

const fields = computed<DynamicFieldSpec[]>(() => {
  const list: DynamicFieldSpec[] = [
    {
      name: 'name',
      label: '节点名称',
      type: 'text',
      placeholder: props.definition.name,
      hint: `画布上显示的名称，留空就用定义名「${props.definition.name}」`,
    },
  ]
  if (config.value.hasSchema) list.push(...config.value.fields)

  const note = nodeFormNote(props.node.node_type, config.value.hasSchema)
  if (note) {
    list.push({ name: '__note', label: '', type: 'note', text: note.text, action: note.action })
  }
  return list
})

// 每次打开都重新构造取值：关掉再打开不该看到上一次的脏值
watch(
  () => open.value,
  (isOpen) => {
    if (!isOpen) return
    values.value = { name: props.node.name, ...config.value.values }
  },
  { immediate: true },
)

function onNoteAction(action: NodeFormNoteAction): void {
  if (action.kind === 'goto-form') emit('goto-form')
  else emit('goto-branch')
}

async function submit(): Promise<void> {
  if (!(await formRef.value?.validate())) return
  const rawName = String(values.value.name || '').trim()
  // 不命名（或清空）就用定义名，不拦着用户必须起名字
  const name = rawName || props.definition.name

  const formValues: Record<string, unknown> = { ...values.value }
  delete formValues.name
  delete formValues.__note

  emit('save', {
    name,
    config: config.value.hasSchema ? config.value.fromForm(formValues) : { ...props.node.config },
  })
  open.value = false
}
</script>

<template>
  <AppDialog
    v-model:open="open"
    :title="props.isNew ? `新增节点 · ${props.definition.name}` : `编辑节点 · ${props.node.name}`"
    width="640px"
  >
    <DynamicForm ref="formRef" v-model="values" :fields="fields" @note-action="onNoteAction" />
    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" @click="submit">{{
        props.isNew ? '添加节点' : '保存节点'
      }}</ElButton>
    </template>
  </AppDialog>
</template>
