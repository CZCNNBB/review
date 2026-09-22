-- tenant.tenant_callback_credential 由早期 HMAC 签名凭据升级为 Service Token 凭据。
--
-- 业务系统为审批中心的服务账号签发长期 Token，审批中心复用业务系统已有的认证请求头。
-- 旧结构保存的是签名密钥和 Key ID，与新方案的字段含义完全不同，必须整表替换。
--
-- 本脚本只面向还没有正式使用回调能力的开发库：
--   * 存在 ACTIVE 凭据时主动中止，先由管理员撤销或确认后手工处理，避免静默丢弃凭据。
--   * 旧 HMAC 凭据在升级后无法用于新方案，REVOKED 记录会随列一起删除。
-- 全新库不需要执行本脚本，data/init.sql 已经直接创建 Service Token 结构。

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM tenant.tenant_callback_credential WHERE status = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'tenant.tenant_callback_credential 中存在 ACTIVE 凭据，请先撤销后再执行本升级脚本';
    END IF;
END
$$;

-- 旧列只用于 HMAC 签名，升级后不再使用。
ALTER TABLE tenant.tenant_callback_credential
    DROP COLUMN IF EXISTS key_id,
    DROP COLUMN IF EXISTS secret_ciphertext;

-- 新结构与 data/init.sql 中的定义保持一致。
ALTER TABLE tenant.tenant_callback_credential
    ADD COLUMN IF NOT EXISTS header_name VARCHAR(100);

ALTER TABLE tenant.tenant_callback_credential
    ADD COLUMN IF NOT EXISTS token_prefix VARCHAR(50);

ALTER TABLE tenant.tenant_callback_credential
    ADD COLUMN IF NOT EXISTS token_ciphertext TEXT;

-- 旧 HMAC 凭据没有对应 Token，升级后无法补全，残留的 REVOKED 行在此清理。
DELETE FROM tenant.tenant_callback_credential;

ALTER TABLE tenant.tenant_callback_credential
    ALTER COLUMN header_name SET NOT NULL,
    ALTER COLUMN header_name SET DEFAULT 'Authorization',
    ALTER COLUMN token_prefix SET NOT NULL,
    ALTER COLUMN token_prefix SET DEFAULT 'Bearer',
    ALTER COLUMN token_ciphertext SET NOT NULL;

ALTER TABLE tenant.tenant_callback_credential
    ADD CONSTRAINT ck_tenant_callback_credential_status
        CHECK (status IN ('ACTIVE', 'REVOKED'));

-- 一个租户同一时间只允许一个 ACTIVE 凭据。
CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_callback_credential_one_active
    ON tenant.tenant_callback_credential (tenant_id)
    WHERE status = 'ACTIVE';

COMMIT;
