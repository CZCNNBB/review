<script setup lang="ts">
import { ElOption, ElSelect } from 'element-plus'
import { computed, ref } from 'vue'

import { filterPersonOptions, type PersonOption } from '@/utils/personSelect'

/**
 * 选人控件。所有选人的地方都走它 —— 一处一个裸 ElSelect 的话，
 * "能不能搜""带不带部门"每次都要重新决定一遍。
 *
 * 比裸 ElSelect 多两件事：
 * 1. 能搜：姓名、部门、手机号、邮箱任意一段命中即可；
 * 2. 每个人后面缀着所属部门的小标签，重名的人一眼能分清。
 *
 * 搜索是自己筛选项再交给 ElSelect 渲染的：一旦传了 filter-method，
 * ElSelect 就不再自己按 label 过滤（见 useSelect.updateOptions 的提前返回）。
 */
const props = defineProps<{
  options: PersonOption[]
  multiple?: boolean
  placeholder?: string
  disabled?: boolean
}>()

/** 单选给字符串，多选给数组，与 DynamicForm 里各控件的取值口径一致。 */
const model = defineModel<string | string[]>({ required: true })

const query = ref('')
const visibleOptions = computed(() => filterPersonOptions(props.options, query.value))

function onFilter(next: string): void {
  query.value = next
}

/** 关掉下拉就把查询清掉，下次打开还是完整名单（别指望 ElSelect 一定会回调空串）。 */
function onVisibleChange(open: boolean): void {
  if (!open) query.value = ''
}
</script>

<template>
  <ElSelect
    v-model="model"
    :multiple="props.multiple"
    :disabled="props.disabled"
    :placeholder="props.placeholder || '选择人员…'"
    filterable
    :filter-method="onFilter"
    :collapse-tags="props.multiple"
    collapse-tags-tooltip
    style="width: 100%"
    @visible-change="onVisibleChange"
  >
    <ElOption
      v-for="option in visibleOptions"
      :key="option.value"
      :value="option.value"
      :label="option.label"
    >
      <span class="person-option">
        <span class="person-option__name">{{ option.label }}</span>
        <span class="person-option__meta">
          <span v-for="department in option.departments || []" :key="department" class="tag">
            {{ department }}
          </span>
        </span>
      </span>
    </ElOption>
  </ElSelect>
</template>

<style scoped>
.person-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.person-option__name {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.person-option__meta {
  display: inline-flex;
  flex: none;
  gap: 4px;
}
</style>
