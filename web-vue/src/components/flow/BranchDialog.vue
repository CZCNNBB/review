<script setup lang="ts">
import { ElButton, ElOption, ElSelect } from 'element-plus'
import { computed, ref, watch } from 'vue'

import AppDialog from '@/components/common/AppDialog.vue'
import type { Condition, FlowConnection, FlowNode, JSONSchema } from '@/types/domain'
import {
  conditionValueControl,
  operatorOptionsForField,
  type ConditionValueControl,
} from '@/utils/condition'
import { buildBranchConditions, newBranchDraft, type BranchDraft } from '@/utils/flowBranch'
import { orderMark } from '@/utils/format'
import { conditionFieldOptions, formFieldsFromSchema, type FormFieldRow } from '@/utils/schemaForm'

/**
 * 条件分支编辑器。
 *
 * 只配条件：按顺序从上往下判断，命中哪条走哪条；最后一条是「其余情况」兜底。
 * **去向不在这里选** —— 关掉窗口后从卡片上对应那一行的圆点拉线，这里只显示目标名。
 */
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  node: FlowNode
  nodes: FlowNode[]
  connections: FlowConnection[]
  formSchema: JSONSchema
}>()

const emit = defineEmits<{ (event: 'save', built: BranchDraft[]): void }>()

const formFields = computed(() =>
  formFieldsFromSchema(props.formSchema).fields.filter((field) => field.type !== 'unsupported'),
)
const fieldOptions = computed(() => conditionFieldOptions(props.formSchema))

function fieldOf(path: string): FormFieldRow | null {
  return formFields.value.find((field) => `approval_form.${field.key}` === path) || null
}

const branches = ref<BranchDraft[]>([])
const error = ref('')

/** 一行在界面上需要的全部东西，一次算好，模板里就不用再重复推导。 */
interface RowVM {
  index: number
  isLast: boolean
  mark: string
  label: string
  condition: Condition
  field: FormFieldRow | null
  operatorOptions: Array<{ value: string; label: string }>
  control: ConditionValueControl
  targetName: string
  linked: boolean
}

const rows = computed<RowVM[]>(() =>
  branches.value.map((branch, index) => {
    const isLast = index === branches.value.length - 1
    const condition: Condition = branch.condition || { field: '', operator: 'EQ', value: '' }
    const field = fieldOf(condition.field)

    return {
      index,
      isLast,
      mark: isLast ? '—' : orderMark(index + 1),
      label: isLast ? '其余情况' : `条件 ${index + 1}`,
      condition,
      field,
      operatorOptions: operatorOptionsForField(field),
      control: conditionValueControl(field, condition.operator),
      targetName: branch.target_node_id
        ? props.nodes.find((item) => item.id === branch.target_node_id)?.name || '未知节点'
        : '未接去向',
      linked: props.nodes.some(
        (item) => item.id === branch.target_node_id && item.node_type !== 'START',
      ),
    }
  }),
)

watch(
  () => open.value,
  (isOpen) => {
    if (!isOpen) return
    error.value = ''
    // 每次打开都从当前出线重新构造，关掉再打开不残留上次的编辑
    const draft: BranchDraft[] = props.connections
      .filter((item) => item.source_node_id === props.node.id)
      .map((item) => ({
        target_node_id: item.target_node_id,
        condition: item.condition ? { ...item.condition } : null,
      }))
    if (!draft.length) draft.push({ target_node_id: null, condition: null })
    branches.value = draft
  },
  { immediate: true },
)

function addBranch(): void {
  // 新条件插在「其余情况」之前，最后一行的位置不会被打乱
  const draft = [...branches.value]
  draft.splice(Math.max(0, draft.length - 1), 0, newBranchDraft(fieldOptions.value))
  branches.value = draft
  error.value = ''
}

function dropBranch(index: number): void {
  const draft = [...branches.value]
  draft.splice(index, 1)
  branches.value = draft
  error.value = ''
}

function updateCondition(index: number, patch: Partial<Condition>): void {
  const draft = [...branches.value]
  draft[index] = {
    ...draft[index],
    condition: {
      ...(draft[index].condition || { field: '', operator: 'EQ', value: '' }),
      ...patch,
    },
  }
  branches.value = draft
}

function submit(): void {
  const result = buildBranchConditions(branches.value, fieldOf)
  if ('error' in result) {
    error.value = result.error
    return
  }
  emit('save', result.built)
  open.value = false
}
</script>

<template>
  <AppDialog v-model:open="open" :title="`条件分支 · ${props.node.name}`" width="760px">
    <div v-if="!formFields.length" class="note note--wait">
      这条流程还没有定义表单字段，条件无从选起。先在下面的「审批表单」里加上要判断的字段（比如金额、类别），再回来配条件。
    </div>

    <template v-else>
      <div class="note" style="margin-bottom: 14px">
        这里只定条件：按顺序从上往下判断，命中哪条走哪条；最后一条是「其余情况」，兜住上面的条件都不满足的时候。
        每条走哪里，关掉这个窗口后从卡片上对应一行右侧的圆点拉一条线到目标节点。
      </div>

      <div v-for="row in rows" :key="row.index" class="branch-row">
        <div class="branch-row__head">
          <span class="branch-row__mark">{{ row.mark }}</span>
          <span class="branch-row__label">{{ row.label }}</span>
          <button
            v-if="rows.length > 1"
            class="btn--link btn--sm is-danger"
            type="button"
            @click="dropBranch(row.index)"
          >
            删除
          </button>
        </div>

        <div class="branch-row__body">
          <span v-if="row.isLast" class="branch-row__hint">上面的条件都不满足时走这条</span>

          <template v-else>
            <ElSelect
              :model-value="row.condition.field"
              class="input--cell"
              title="条件字段"
              @update:model-value="updateCondition(row.index, { field: String($event) })"
            >
              <ElOption
                v-for="option in fieldOptions"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              />
            </ElSelect>

            <ElSelect
              :model-value="row.condition.operator"
              class="input--cell"
              title="比较方式"
              @update:model-value="updateCondition(row.index, { operator: String($event) })"
            >
              <ElOption
                v-for="option in row.operatorOptions"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              />
            </ElSelect>

            <ElSelect
              v-if="row.control.kind === 'select'"
              :model-value="String(row.condition.value ?? '')"
              class="input--cell"
              @update:model-value="updateCondition(row.index, { value: String($event) })"
            >
              <ElOption
                v-for="option in row.control.options"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              />
            </ElSelect>

            <input
              v-else-if="row.control.kind !== 'none'"
              class="input input--cell"
              :type="row.control.kind === 'number' ? 'number' : 'text'"
              :placeholder="row.control.kind === 'text' ? row.control.placeholder : '要比较的内容'"
              :value="String(row.condition.value ?? '')"
              @input="
                updateCondition(row.index, { value: ($event.target as HTMLInputElement).value })
              "
            />
          </template>

          <span class="branch-row__arrow">去</span>
          <span class="branch-row__target" :class="{ 'is-unlinked': !row.linked }">
            {{ row.targetName }}
          </span>
        </div>
      </div>

      <div style="margin-top: 14px">
        <button class="btn btn--sm" type="button" @click="addBranch">＋ 新增条件</button>
      </div>

      <div v-if="error" class="note note--wait">{{ error }}</div>
    </template>

    <template #footer>
      <ElButton @click="open = false">取消</ElButton>
      <ElButton type="primary" @click="submit">保存</ElButton>
    </template>
  </AppDialog>
</template>
