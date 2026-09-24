import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import './styles/index.css'

// 时间统一按中文格式渲染，formatTime 内部走 dayjs。
dayjs.locale('zh-cn')

const app = createApp(App)

const pinia = createPinia()
// 接口地址与管理密钥这些要跨会话保留。
pinia.use(piniaPluginPersistedstate)

app.use(pinia)
app.use(router)

app.mount('#app')
