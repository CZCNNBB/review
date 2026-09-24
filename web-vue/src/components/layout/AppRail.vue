<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { activeNavKey, NAV } from '@/router/routes'
import { useShellStore } from '@/stores/shell'

// 侧栏是自研的，没用两库的菜单组件：236px 宽度、左侧 3px 靛青条、计数徽标
// 这套观感是控制台识别度的一部分，套组件库反而要写一堆覆盖。
const route = useRoute()
const shell = useShellStore()

const current = computed(() => activeNavKey(route.path))
</script>

<template>
  <nav class="rail">
    <div class="rail__brand">
      <div class="rail__brand-name">审批中心</div>
      <div class="rail__brand-note">配置台与审批工作台</div>
    </div>

    <div>
      <template v-for="group in NAV" :key="group.group">
        <div class="rail__group">{{ group.group }}</div>
        <a
          v-for="item in group.items"
          :key="item.key"
          class="rail__item"
          :class="{ 'rail__item--active': item.key === current }"
          :href="item.hash"
        >
          {{ item.label }}
          <span v-if="shell.counts[item.key] !== undefined" class="rail__count">
            {{ shell.counts[item.key] }}
          </span>
        </a>
      </template>
    </div>

    <div class="rail__foot">
      <div>接口地址与密钥保存在本机浏览器，不会上传。</div>
    </div>
  </nav>
</template>
