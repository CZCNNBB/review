<script setup lang="ts">
import { ConfigProvider as AConfigProvider } from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { ElConfigProvider } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import AppRail from '@/components/layout/AppRail.vue'
import AppTopbar from '@/components/layout/AppTopbar.vue'
import { antdTheme } from '@/styles/antd-theme'

// 两个库都不做全局注册：按白名单显式 import，谁负责哪一层由 eslint.config.js 强制。
// 语言包统一走 Provider，两边的日期/分页/空态文案才是中文。
</script>

<template>
  <ElConfigProvider :locale="zhCn">
    <AConfigProvider :locale="zhCN" :theme="antdTheme">
      <AppRail />
      <div class="work">
        <AppTopbar />
        <main class="content">
          <RouterView />
        </main>
      </div>
    </AConfigProvider>
  </ElConfigProvider>
</template>
