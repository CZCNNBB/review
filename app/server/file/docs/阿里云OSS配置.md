# 阿里云 OSS 配置（审批附件）

项目通过服务端的 S3 兼容驱动连接阿里云 OSS。业务系统和浏览器只调用审批中心的文件接口，不直接持有 OSS 密钥。

## 1. 创建 Bucket

在阿里云 OSS 控制台创建一个专用于审批附件的 Bucket。记录 **Bucket 名称**和**地域 ID**，例如 `approval-files-demo`、`cn-hangzhou`。访问权限选择**私有**，保留**阻止公共访问**。开始时使用标准存储；审批详情下载需要直接读取文件。

Bucket 所在地域创建后不能修改。部署在阿里云同地域 ECS 时可考虑内网 Endpoint；本地 Windows 开发机使用公网 Endpoint。

## 2. 创建 RAM 用户和 AccessKey

在阿里云 RAM 控制台创建供审批中心后端使用的 RAM 用户，并为其创建 AccessKey。不要使用主账号 AccessKey，也不要把密钥写进仓库或前端配置。

给该 RAM 用户添加仅针对这个 Bucket 对象的自定义权限策略；将 `approval-files-demo` 换成实际 Bucket 名称：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "oss:PutObject",
        "oss:GetObject",
        "oss:DeleteObject",
        "oss:AbortMultipartUpload"
      ],
      "Resource": ["acs:oss:*:*:approval-files-demo/*"]
    }
  ]
}
```

这些权限对应上传、下载、上传失败时的补偿删除，以及大文件分片上传失败时取消分片。服务本身不列举 Bucket 对象，因此不需要授予 `oss:ListObjects`。

## 3. 配置后端环境变量

以下是 **PowerShell 当前终端会话**的示例。请替换 Bucket、地域、Endpoint 和密钥；不要把实际 AccessKey 发给他人或提交到 Git。

```powershell
$env:APPROVAL_FILE_STORAGE = "s3"
$env:APPROVAL_FILE_S3_PROVIDER = "aliyun"
$env:APPROVAL_FILE_S3_BUCKET = "approval-files-demo"
$env:APPROVAL_FILE_S3_REGION = "cn-hangzhou"
$env:APPROVAL_FILE_S3_ENDPOINT = "https://s3.oss-cn-hangzhou.aliyuncs.com"
$env:AWS_ACCESS_KEY_ID = "你的 RAM AccessKey ID"
$env:AWS_SECRET_ACCESS_KEY = "你的 RAM AccessKey Secret"
```

`boto3` 按标准 AWS 环境变量读取凭据，项目只读取前五项存储配置。更换地域时，**Region 与 Endpoint 必须和 Bucket 所在地域一致**。后端部署为服务时，需在实际启动该服务的环境中设置变量；只在本地 PowerShell 设置不会传到服务器。

阿里云的 boto3 接入在 `APPROVAL_FILE_S3_PROVIDER=aliyun` 下使用 S3 V2 签名和虚拟主机访问，这是阿里云官方给出的兼容方式。其他 S3 兼容存储可省略此变量，使用 `generic`。

## 4. 安装依赖、迁移数据库并验证

在后端使用的 Python 环境安装 `requirements.txt`（其中包含 `boto3` 和 `python-multipart`）。先执行 `data/migrations/20260929_approval_files.sql` 建表，再重启后端。此前约定不在远程数据库自动执行迁移，因此需要在准备好环境后由你执行。

用一份小 PDF 和 PNG 调用 `POST /api/files`，两个文件都返回 `file_id` 后，再带 `file_ids` 发起审批。检查审批详情或抄送详情能看到并下载附件。上传失败时依次核对 Bucket 名称、地域与 Endpoint、RAM 权限、AccessKey 和服务器时间。

官方参考：[阿里云使用 AWS SDK 访问 OSS](https://help.aliyun.com/zh/oss/developer-reference/use-aws-sdks-to-access-oss)、[创建 Bucket](https://help.aliyun.com/zh/oss/user-guide/create-a-bucket-4)、[RAM Policy](https://help.aliyun.com/en/oss/user-guide/ram-policy/)。
