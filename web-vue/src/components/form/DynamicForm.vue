<script setup lang="ts">
import {
  ElCheckbox,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElOption,
  ElSelect,
} from 'element-plus'
import { computed, ref } from 'vue'

import CodeTextarea from '@/components/common/CodeTextarea.vue'
import PersonSelect from '@/components/form/PersonSelect.vue'
import type { DynamicFieldSpec, NodeFormNoteAction } from '@/utils/nodeConfigForm'

/**
 * 按字段描述符渲染表单。旧版 formDialog(options) 的字段模型原样保留：
 * text / number / select / multiselect / textarea / code / checkbox / note，
 * 加上 required、hint、wide、placeholder。
 *
 * 与旧版的区别：note 里的跳转按钮不再是拼进 HTML 的 data-act 按钮，
 * 而是结构化数据 + 真实按钮，点击后 emit('note-action', action)。
 */
const props = defineProps<{
  fields: DynamicFieldSpec[]
  /** 后端/解析错误显示在表单底部，对应旧版的 #dialog-error */
  error?: string
}>()

const emit = defineEmits<{
  (event: 'note-action', action: NodeFormNoteAction): void
}>()

const model = defineModel<Record<string, unknown>>({ required: true })

/** 自校验产生的错误，与父组件传进来的 error 一起显示。 */
const localError = ref('')

const controlFields = computed(() => props.fields.filter((field) => field.type !== 'note'))
const noteFields = computed(() => props.fields.filter((field) => field.type === 'note'))

function valueOf(name: string): unknown {
  const value = model.value[name]
  return value === undefined || value === null ? '' : value
}

function setValue(name: string, value: unknown): void {
  model.value = { ...model.value, [name]: value }
}

/** 空值的口径与旧版 formDialog 一致：空串、null、undefined、空数组都算没填。 */
function isEmptyValue(value: unknown): boolean {
  if (value === undefined || value === null) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

/**
 * 交给父组件的提交按钮调用：校验通过返回 true。
 *
 * 必填由这里自己判定，不走 ElForm 的表单级校验：它依赖组件内部的字段注册与
 * model 路径解析，实测对空值也返回通过（字段级 validate 才是准的），用它等于
 * 把必填做成摆设。自己判还有两个好处：语义明确（空数组也算没填），
 * 错误文案与旧版 formDialog 的「xx 不能为空」完全一致。
 */
async function validate(): Promise<boolean> {
  const missing = props.fields.find(
    (field) => field.required && field.type !== 'note' && isEmptyValue(model.value[field.name]),
  )
  if (!missing) {
    localError.value = ''
    return true
  }
  // 标签里的必填星号去掉再拼文案，读起来更顺
  localError.value = `${missing.label.replace(/\s*\*$/, '')}不能为空`
  return false
}

defineExpose({ validate })
</script>

<template>
  <ElForm :model="model" label-position="top" @submit.prevent>
    <ElFormItem
      v-for="field in controlFields"
      :key="field.name"
      :label="field.label"
      :class="{ form__wide: field.wide }"
    >
      <ElSelect
        v-if="field.type === 'select'"
        :model-value="String(valueOf(field.name))"
        style="width: 100%"
        @update:model-value="setValue(field.name, $event)"
      >
        <ElOption
          v-for="option in field.options || []"
          :key="option.value"
          :value="option.value"
          :label="option.label"
        />
      </ElSelect>

      <PersonSelect
        v-else-if="field.type === 'person-select'"
        :model-value="(valueOf(field.name) as string[]) || []"
        :options="field.options || []"
        multiple
        @update:model-value="setValue(field.name, $event)"
      />

      <ElSelect
        v-else-if="field.type === 'multiselect'"
        :model-value="(valueOf(field.name) as string[]) || []"
        multiple
        collapse-tags
        collapse-tags-tooltip
        style="width: 100%"
        @update:model-value="setValue(field.name, $event)"
      >
        <ElOption
          v-for="option in field.options || []"
          :key="option.value"
          :value="option.value"
          :label="option.label"
        />
      </ElSelect>

      <ElInputNumber
        v-else-if="field.type === 'number'"
        :model-value="valueOf(field.name) === '' ? null : Number(valueOf(field.name))"
        :controls="false"
        style="width: 100%"
        @update:model-value="setValue(field.name, $event === null ? '' : String($event))"
      />

      <ElCheckbox
        v-else-if="field.type === 'checkbox'"
        :model-value="Boolean(valueOf(field.name))"
        @update:model-value="setValue(field.name, $event)"
      >
        {{ field.checkboxLabel || field.label }}
      </ElCheckbox>

      <CodeTextarea
        v-else-if="field.type === 'code' || field.type === 'textarea'"
        :model-value="String(valueOf(field.name))"
        :rows="field.type === 'code' ? 8 : 4"
        :placeholder="field.placeholder"
        @update:model-value="setValue(field.name, $event)"
      />

      <ElInput
        v-else
        :model-value="String(valueOf(field.name))"
        :placeholder="field.placeholder"
        @update:model-value="setValue(field.name, $event)"
      />

      <div v-if="field.hint" class="field__hint">{{ field.hint }}</div>
    </ElFormItem>

    <div v-for="(field, index) in noteFields" :key="index" class="note">
      {{ field.text }}
      <button
        v-if="field.action"
        class="btn--link btn--sm"
        type="button"
        @click="emit('note-action', field.action)"
      >
        {{ field.action.label }}
      </button>
    </div>

    <div v-if="localError || props.error" class="note note--wait">
      {{ localError || props.error }}
    </div>
  </ElForm>
</template>

<style scoped>
.form__wide {
  display: block;
}
.field__hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.5;
}
</style>
