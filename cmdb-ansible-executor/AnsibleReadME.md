# CMDB Ansible 集成说明

## 整体架构

```
浏览器 → cmdb-ui (容器) → cmdb-api (容器) → HTTP → Ansible Executor (宿主机) → ansible-playbook → 目标服务器
```

避免docker网络限制，Ansible 执行器部署在**宿主机**上，以获得所需的网络权限。

---

## 新增/修改的文件清单

### 1. cmdb-ansible-executor/（宿主机新服务）

| 文件 | 说明 |
|------|------|
| `app.py` | Flask 应用入口，3个 API 端点 + API Key 鉴权 |
| `executor.py` | 核心逻辑：动态生成 inventory 文件 → `subprocess.run(["ansible-playbook",...])` |
| `config.py` | 环境变量配置（端口、路径、超时等） |
| `requirements.txt` | Python 依赖 |
| `cmdb-ansible.service` | systemd 单元文件 |

API 端点：
- `GET  /api/exec/health` — 健康检查
- `GET  /api/exec/playbooks` — 从 `/opt/ansible/playbooks/` 动态列出 `.yml`/`.yaml` 文件
- `POST /api/exec/run-playbook` — 执行剧本（需 `X-API-Key` 头）

### 2. cmdb-api 后端

| 文件 | 说明 |
|------|------|
| `api/lib/cmdb/ansible.py` (新增) | 类似 jumpserver.py 的集成库：`AnsibleClient` + `AnsibleSync`，读配置、取 CI 数据、调 Executor |
| `api/views/cmdb/ansible.py` (新增) | 4个视图，自动注册到 `/api/v0.1/ansible/` |

API 端点（由 cmdb-api 提供）：

| 路由 | 方法 | 说明 |
|------|------|------|
| `POST /api/v0.1/ansible/setup-server/<ci_id>` | 单 CI 初始化 |
| `POST /api/v0.1/ansible/setup-server/batch` | 批量初始化 |
| `GET  /api/v0.1/ansible/playbooks` | 获取可选剧本列表 |
| `GET/POST /api/v0.1/ansible/config` | Ansible 配置管理 |

### 3. cmdb-ui 前端

| 文件 | 说明 |
|------|------|
| `src/modules/cmdb/api/ansible.js` (新增) | 前端 API 封装 |
| `src/modules/cmdb/views/sync_asset/configCenter.vue` (修改) | 配置中心改为标签页：**JumpServer设置** + **Ansible设置** |
| `src/modules/cmdb/views/ci/instanceList.vue` (修改) | 批量操作栏新增"Ansible初始化"按钮 |
| `src/modules/cmdb/views/ci/modules/ciDetailTab.vue` (修改) | 详情页操作区新增"Ansible初始化"按钮 |

---

## 数据流

```
1. 用户打开配置中心 → Ansible 设置标签页
   → 配置 Executor URL、API Key、OS 凭证映射、字段映射、默认剧本

2. 用户进入 CI 列表 → 勾选要初始化的 vmserver 资产
   → 点击 "Ansible初始化" → 选择剧本 → 确认执行

3. 前端 POST /api/v0.1/ansible/setup-server/batch
   { ci_ids: [1,2,3], playbook: "setup_server.yml", new_password: "xxx" }

4. cmdb-api 循环处理每个 CI：
   a. 调用 CIManager.get_ci_by_id_from_db() 获取 CI 详情
   b. 根据 field_map 提取 IP、hostname、os_version
   c. 从 os_credentials 匹配对应的端口/用户名/密码
   d. POST http://<executor>/api/exec/run-playbook

5. Executor 服务：
   a. 验证输入安全
   b. 生成临时 inventory 文件到 /opt/ansible/inventory/
   c. 执行 ansible-playbook
   d. 清理临时文件
   e. 返回结果

6. 前端展示执行结果
```

---

## 部署步骤

### 前提条件

- 宿主机已安装 Ansible
- Ansible 剧本目录: `/opt/ansible/playbooks/`
- Ansible 清单目录: `/opt/ansible/inventory/`

### 1. 部署 Executor 服务

```bash
# 进入 cmdb-ansible-executor 目录安装依赖
cd /项目目录/cmdb-ansible-executor
pip install -r requirements.txt

# 修改 API Key（务必改为安全的值）
# 编辑 cmdb-ansible.service 中的 EXECUTOR_API_KEY

# 配置 systemd
cp cmdb-ansible.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable cmdb-ansible
systemctl start cmdb-ansible

# 验证
curl http://localhost:18081/api/exec/health
```

### 2. 环境变量说明（Executor 服务）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EXECUTOR_HOST` | `0.0.0.0` | 监听地址 |
| `EXECUTOR_PORT` | `18081` | 监听端口 |
| `EXECUTOR_API_KEY` | `change-me-to-a-secure-key` | API 鉴权密钥 |
| `ANSIBLE_BASE_DIR` | `/opt/ansible` | Ansible 基础目录 |
| `ANSIBLE_TIMEOUT` | `600` | 剧本执行超时（秒） |

### 3. 页面配置

1. 登录 CMDB → 配置中心 → **Ansible 设置**
2. 填写 **Executor 地址**（如 `http://192.168.1.100:18081`）
3. 填写 **API Key**（与 cmdb-ansible.service 中的一致）
4. 配置 **OS 凭证映射**：Ansible远程连接需要的端口/用户名/密码
   | 操作系统 | 端口 | 用户名 | 密码 |
   |---------|------|--------|------|
   | Linux | 22 | root | xxx |

5. 配置 **字段映射**（CI 属性 → Ansible 参数）：
   - IP 字段：`ip, private_ip, public_ip`
   - 主机名字段：`hostname, name`
   - 操作系统字段：`os_version, os, ostype`
6. 选择 **默认剧本**
7. 点击保存

### 4. 使用

- **批量初始化**：进入 CI 列表 → 勾选资产 → 点击"Ansible初始化" → 选剧本 → 确认
- **单资产初始化**：进入 CI 详情页 → 点击"Ansible初始化" → 选剧本 → 确认

---

## 安全说明

- Executor 服务使用 `X-API-Key` 头进行鉴权
- 剧本名称经过正则校验，防止路径穿越
- Inventory 中的变量值自动处理空格（JSON 序列化）
- 临时 inventory 文件执行完成后立即删除

## 扩展：支持 Windows
1. 将 Windows 剧本放入 `/opt/ansible/playbooks/`
2. 在配置中心的 OS 凭证映射中添加 Windows 条目
3. 用户在初始化时选择对应的 Windows 剧本即可
