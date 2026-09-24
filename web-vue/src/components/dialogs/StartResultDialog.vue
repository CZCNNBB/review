<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed } from 'vue'

import type { Person, StartedInstance } from '@/api/types'
import AppDialog from '@/components/common/AppDialog.vue'
import CopyButton from '@/components/common/CopyButton.vue'
import KvDescriptions from '@/components/layout/KvDescriptions.vue'
import { formatTime, shortId } from '@/utils/format'

// 发起结果窗。旧版是「拼 HTML + 全局事件委托」，跳详情靠 data-act 改 location.hash；
// 这里链接直接写 href，点到详情页时发起页整体卸载，弹窗跟着消失。
const open = defineModel<boolean>('open', { default: false })

const props = defineProps<{
  started: StartedInstance | null
  /** 待办人员要显示姓名，人员表由发起页手里那份给（旧版 personNameOf 同此） */
  persons: Person[]
}>()

/** 名单里查不到的人只显示 ID 前 8 位，与旧版回落口径一致 */
const pendingNames = computed(() =>
  (props.started?.pending_approver_person_ids || []).map((personId) => {
    const person = props.persons.find((item) => item.id === personId)
    return person ? person.name : shortId(personId)
  }),
)

const pairs = computed(() => {
  const started = props.started
  if (!started) return []
  return [
    { key: '审批实例', slot: 'instanceId' },
    { key: '使用版本', value: `V${started.process_version_no}` },
    { key: '当前节点', value: started.current_node_name || '已结束' },
    { key: '待办人员', slot: 'pendingApprovers' },
    { key: '发起时间', value: formatTime(started.started_at) },
  ]
})
</script>

<template>
  <AppDialog v-model:open="open" title="发起结果" width="620px">
    <template v-if="props.started">
      <div class="issue issue--ok">
        <div class="issue__code">{{ props.started.status }}</div>
        <div>
          {{
            props.started.idempotent_replay
              ? '本次请求命中了幂等规则，返回的是已有实例，没有重复创建。'
              : '审批实例已创建，并已生成首批审批任务。'
          }}
        </div>
      </div>

      <div class="result">
        <KvDescriptions :pairs="pairs">
          <template #instanceId>
            <span class="code">{{ props.started.instance_id }}</span>
            <CopyButton :text="props.started.instance_id" label="复制" />
          </template>
          <template #pendingApprovers>
            <span class="code">{{ pendingNames.join('、') || '—' }}</span>
          </template>
        </KvDescriptions>
      </div>
    </template>

    <template #footer>
      <ElButton @click="open = false">关闭</ElButton>
      <a
        v-if="props.started"
        class="btn btn--primary result__link"
        :href="`#/instances/${props.started.instance_id}`"
        @click="open = false"
      >
        查看审批详情
      </a>
    </template>
  </AppDialog>
</template>

<style scoped>
/* 结论块与下面的键值表之间补一段间距 */
.result {
  margin-top: 14px;
}

/* 底部的链接按钮跟 Element 的按钮排一起，补一点左边距 */
.result__link {
  margin-left: 10px;
}
</style>
