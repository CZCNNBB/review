/** 控制台用到的领域类型。与后端的 Pydantic Schema 一一对应（backend/app/server 下各模块的 schemas 目录）。 */

export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

/** 节点执行类型。后端只认这四种，节点定义不能凭空造新类型。 */
export type NodeType = 'START' | 'APPROVAL' | 'CONDITION' | 'END' | (string & {})

export interface FlowNode {
  id: string
  node_definition_id: string
  node_type: NodeType
  node_definition_name?: string | null
  name: string
  config: Record<string, unknown>
  position: Point
}

/** 条件分支的一条判断：字段路径 + 比较符 + 取值。 */
export interface Condition {
  field: string
  operator: string
  value?: unknown
}

/**
 * 一条编排连线。
 * 条件分支的出线可以暂时没有目标（先在节点里配好条件，再去画布上拉线），
 * 所以 target_node_id 允许为 null。
 */
export interface FlowConnection {
  source_node_id: string
  target_node_id: string | null
  condition?: Condition | null
}

/** JSON Schema 的宽松表示：控制台只读取它需要的那些关键字。 */
export interface JSONSchema {
  type?: string | string[]
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  format?: string
  properties?: Record<string, JSONSchema>
  required?: string[]
  items?: JSONSchema
  minItems?: number
  additionalProperties?: boolean
  [key: string]: unknown
}

/**
 * ui_schema_json：键是配置项名或根级指令，值是控件提示。
 * 根级指令 `ui:order` 是数组，所以值不能限定成对象。
 */
export type UISchema = Record<string, unknown>

export interface NodeDefinition {
  id: string
  node_type: NodeType
  name: string
  description?: string | null
  icon?: string | null
  config_schema_json: JSONSchema
  ui_schema_json: UISchema
  status: string
  created_at?: string
  updated_at?: string
}

/** 一条流程校验问题。 */
export interface ValidationIssue {
  code: string
  message: string
  node_id?: string | null
  field?: string | null
  connection_index?: number | null
}
