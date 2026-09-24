import js from '@eslint/js'
import tsParser from '@typescript-eslint/parser'
import globals from 'globals'
import vue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'

/**
 * 两层组件库的分工规则用 ESLint 强制，不靠自觉：
 * AntD 负责「把数据摆出来」（表格/键值/页签/空态），Element Plus 负责「把数据录进去」
 * （弹窗/表单/提示）。两个库有 17 个组件重名，一旦谁都能随手 import，混用就失控了。
 *
 * 页面里也不许直接写 <a-table> / <el-dialog>：表格走 components/common/DataTable.vue，
 * 弹窗走 components/common/AppDialog.vue，由一个封装层吸收全部差异。
 */
const ELEMENT_ALLOWED = [
  'ElDialog',
  'ElForm',
  'ElFormItem',
  'ElInput',
  'ElInputNumber',
  'ElSelect',
  'ElOption',
  'ElCheckbox',
  'ElRadio',
  'ElRadioGroup',
  'ElSwitch',
  'ElButton',
  'ElMessage',
  'ElMessageBox',
  'ElLoading',
  'ElConfigProvider',
  'ElScrollbar',
]

const ANTD_ALLOWED = [
  'Table',
  'TableColumn',
  'Descriptions',
  'DescriptionsItem',
  'Tabs',
  'TabPane',
  'Steps',
  'Step',
  'Empty',
  'Result',
  'Badge',
  'Tooltip',
  'Popconfirm',
  'Tree',
  'TreeNode',
  'ConfigProvider',
  'App',
]

/**
 * 只允许从指定库导入白名单里的导出。
 * ESLint 10 的 no-restricted-imports 用 allowImportNames 表达「除这些以外都禁」。
 */
function restrictLibrary(packageName, allowed, hint) {
  return {
    name: packageName,
    allowImportNames: allowed,
    // 类型导入不受限：白名单管的是「用哪个库的组件」，不是「能不能引它的类型」
    allowTypeImports: true,
    message: `${packageName} 只能显式导入白名单里的组件，见 eslint.config.js。${hint}`,
  }
}

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'playwright-report/**'] },
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.ts', '**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
      globals: { ...globals.browser },
    },
    rules: {
      // 这几条排版规则交给 Prettier，ESLint 只管正确性与架构约束，两边不打架。
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/first-attribute-linebreak': 'off',

      'no-restricted-imports': [
        'error',
        restrictLibrary(
          'element-plus',
          ELEMENT_ALLOWED,
          'Element Plus 只管交互件；展示件（表格/键值/页签/空态）用 Ant Design Vue。',
        ),
        restrictLibrary(
          'ant-design-vue',
          ANTD_ALLOWED,
          'AntD 只管展示件；录入件（表单/弹窗/提示）用 Element Plus。',
        ),
      ],
      // 全库禁止 v-html：旧版靠 esc() 手写转义防 XSS，Vue 里模板插值自动转义，
      // 唯一要 v-html 的地方（动态组件）不存在，所以直接禁掉。
      'vue/no-v-html': 'error',
      'vue/multi-word-component-names': 'off',
      'vue/component-name-in-template-casing': ['error', 'PascalCase'],
      'vue/attributes-order': 'off',
      // 未使用变量交给 vue-tsc 的 noUnusedLocals 判定：基础规则不认 TS 的类型引用，
      // 在 ESLint 里重开一份只会得到两套口径。
      'no-unused-vars': 'off',
    },
  },
  {
    files: ['**/*.spec.ts', 'tests/**/*.ts', 'e2e/**/*.ts'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      'no-restricted-imports': 'off',
    },
  },
  {
    // 构建配置跑在 Node 里
    files: ['*.config.{js,ts}', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
]
