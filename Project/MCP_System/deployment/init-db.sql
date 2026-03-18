-- MCP System Database Initialization
-- 初始化脚本

-- 创建扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 创建基础管理员用户
-- 密码为 'admin123'，应该在生产环境中修改
INSERT INTO users (username, email, hashed_password, display_name, is_active, is_verified)
VALUES ('admin', 'admin@mcp.system', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj9SjKEq7.2W', 'System Administrator', true, true)
ON CONFLICT (username) DO NOTHING;

-- 创建管理员角色
INSERT INTO roles (name, description, is_system)
VALUES ('admin', 'Full system access', true)
ON CONFLICT (name) DO NOTHING;

-- 分配管理员角色给管理员用户
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin'
ON CONFLICT DO NOTHING;

COMMIT;
