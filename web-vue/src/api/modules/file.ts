import { http } from '@/api/http'

/** 文件上传返回的展示信息，不包含实际对象存储路径。 */
export interface UploadedFile {
  file_id: string
  file_name: string
  content_type: string
  size_bytes: number
  sha256: string
  uploaded_at: string
}

export interface BatchUploadResult {
  file_ids: string[]
  files: UploadedFile[]
}

export const fileApi = {
  /** 业务方使用租户密钥一次上传多个文件，失败时不会得到部分 ID。 */
  async upload(files: File[], apiKey: string): Promise<BatchUploadResult> {
    const body = new FormData()
    for (const file of files) body.append('files', file)
    const response = await http.post<BatchUploadResult>('/api/files', body, {
      authKind: 'apikey',
      apiKey,
      timeout: 120000,
    })
    return response.data
  },

  /** 管理端鉴权后下载审批单附件。 */
  async download(fileId: string): Promise<Blob> {
    const response = await http.get<Blob>(`/api/admin/files/${fileId}/content`, {
      authKind: 'admin',
      responseType: 'blob',
      timeout: 120000,
    })
    return response.data
  },
}
