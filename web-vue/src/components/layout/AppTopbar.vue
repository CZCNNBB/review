<script setup lang="ts">
import { ElButton } from 'element-plus'
import { computed, ref } from 'vue'

import { probeConnection } from '@/api/probe'
import { useConfigStore } from '@/stores/config'

// 顶栏四个控件（接口地址、管理密钥、测试连接、连接状态点）与原版一一对应，
// 保存时机也一致：失焦/回车即保存到 localStorage，不需要额外的“保存”按钮。
const config = useConfigStore()
const baseInput = ref(config.base)
const keyInput = ref(config.adminKey)

const stateText = computed(() => {
  if (config.linkState === 'ok') return '已连接'
  if (config.linkState === 'off') return '连接失败'
  return '未连接'
})

const stateClass = computed(() => ({
  'link-state--ok': config.linkState === 'ok',
  'link-state--off': config.linkState === 'off',
}))

function commitBase(): void {
  config.setBase(baseInput.value)
  baseInput.value = config.base
}

function commitKey(): void {
  config.setAdminKey(keyInput.value)
  keyInput.value = config.adminKey
}

async function testConnection(): Promise<void> {
  commitBase()
  commitKey()
  config.setLinkState(await probeConnection())
}
</script>

<template>
  <header class="topbar">
    <div class="topbar__field">
      <span class="topbar__label">接口地址</span>
      <input
        class="topbar__input topbar__input--wide"
        spellcheck="false"
        :value="baseInput"
        @input="baseInput = ($event.target as HTMLInputElement).value"
        @change="commitBase"
      />
    </div>

    <div class="topbar__field">
      <span class="topbar__label">管理密钥</span>
      <input
        class="topbar__input topbar__input--key"
        type="password"
        spellcheck="false"
        placeholder="X-Admin-Key"
        :value="keyInput"
        @input="keyInput = ($event.target as HTMLInputElement).value"
        @change="commitKey"
      />
    </div>

    <ElButton size="small" @click="testConnection">测试连接</ElButton>

    <span class="link-state" :class="stateClass">
      <i class="link-state__dot"></i><span>{{ stateText }}</span>
    </span>
  </header>
</template>
