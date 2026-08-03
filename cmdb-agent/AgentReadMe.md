# CMDB IPAM Agent

宿主机扫描 Agent + 资产-IPAM 联动同步服务

---

## 一、架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Linux 宿主机                           │
│                                                         │
│  cmdb_agent (OneAgent)          ipam_sync               │
│  ┌─────────────────────┐   ┌──────────────────────┐    │
│  │ • 本机网卡IP扫描     │   │ • 轮询 vmserver 资产  │    │
│  │ • 子网Ping-sweep扫描 │   │ • 同步 private_ip 到  │    │
│  │   (上报在线+离线IP)  │   │   IPAM 标记已使用     │    │
│  │ • 通过 adt/sync 取任务│   │ • 同步 assetname 作为 │    │
│  │ • 结果上报 history   │   │   IP地址描述          │    │
│  └──────────┬──────────┘   └──────────┬───────────┘    │
│             │                         │                │
│             └─────────┬───────────────┘                │
│                       │                                │
│              CMDB API (HTTP)                           │
│                       │                                │
└───────────────────────┼────────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              │   Docker Network   │
              │  cmdb-api:5000     │
              │  cmdb-ui:80        │
              └────────────────────┘
```

**两个 Agent 职责分离：**

| Agent | 职责 | 在线状态影响 |
|-------|------|-------------|
| `cmdb_agent.py` | 本机IP上报 + 子网Ping扫描 | 扫描结果决定 `is_used`（在线/离线） |
| `ipam_sync.py` | 资产IP同步 + HTTP按需扫描服务 | 设置 `is_used=1`（在线）和 `assign_status=0`（已分配），**不负责标离线** |

**在线状态规则：**
- **在线**：由 ping 扫描检测到存活，或由资产同步标记
- **离线**：仅由 ping 扫描检测到不存活时标记
- 资产同步（vmserver等）**不会清除** ping 扫描的在线状态

---

## 二、目录结构

安装后所有文件统一在 `/opt/cmdb-agent/` 目录：

```
/opt/cmdb-agent/
├── cmdb_agent.py          # OneAgent 主机扫描+子网扫描
├── ipam_sync.py           # 资产联动同步 + HTTP扫描服务
├── config.json            # 配置文件
├── data/                  # 状态数据 (agent_id, last_scan等)
└── logs/                  # 日志文件
    ├── cmdb_agent.log
    └── ipam_sync.log
```

---

## 三、文件清单

| 文件 | 说明 |
|------|------|
| `cmdb_agent.py` | OneAgent 主机扫描+子网扫描 |
| `ipam_sync.py` | 资产联动 + HTTP 扫描服务 (端口 8900) |
| `cmdb-agent.service` | systemd 服务单元 |
| `cmdb-agent-ipam-sync.service` | systemd 服务单元 |
| `install.sh` | 一键安装脚本 |
| `update.sh` | 一键更新脚本 |
| `uninstall.sh` | 一键卸载脚本 |
| `config.json.example` | 配置文件模板 |

---

## 四、安装部署

### 4.1 一键安装

```bash
sudo bash install.sh
```

安装过程：
1. 检测 Python3 + requests
2. 检测/安装 nmap（可选，推荐）
3. 交互式填写 CMDB API 地址、Key、Secret
4. 自动生成 Agent ID（基于 hostname 哈希）
5. 注册两个 systemd 服务并启动
6. 测试 API 连通性

### 4.2 更新

```bash
sudo bash update.sh
```

### 4.3 卸载

```bash
sudo bash uninstall.sh
```

---

## 五、配置说明

`/opt/cmdb-agent/config.json`：

```json
{
    "cmdb_url": "http://192.168.1.100:8000",
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
    "agent_id": "0xabcd1234",
    "interval": 7200,
    "log_level": "INFO",
    "skip_interfaces": ["lo", "docker*", "veth*", "br-*", "tun*", "virbr*"],
    "scan_method": "auto",
    "scan_concurrency": 50,
    "ping_timeout": 2,
    "subnet_scan_interval": 7200,
    "asset_types": ["vmserver", "server", "container"],
    "ip_fields": ["private_ip", "public_ip", "ip"],
    "name_fields": ["assetname", "hostname", "name"],
    "subnet_field": "subnet",
    "auth_token": "",
    "http_port": 8900,
    "http_host": "0.0.0.0"
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `cmdb_url` | — | CMDB API 地址（必填） |
| `api_key` | — | API 认证 Key（必填） |
| `api_secret` | — | API 认证 Secret（必填） |
| `agent_id` | `0x`+hostname哈希 | Agent 唯一标识，创建子网时用到 |
| `interval` | `7200` | 主循环间隔（秒），建议不低于3600 |
| `log_level` | `INFO` | 日志级别：DEBUG/INFO/WARNING/ERROR |
| `skip_interfaces` | `["lo","docker*",...]` | 本机扫描时跳过的网卡 |
| `scan_method` | `auto` | 扫描方式：auto/nmap/fping/arp-scan/ping |
| `scan_concurrency` | `50` | nmap 并行度 |
| `ping_timeout` | `2` | Ping 超时（秒） |
| `subnet_scan_interval` | `7200` | 子网最小扫描间隔（秒） |
| `asset_types` | `["vmserver","server","container"]` | ipam_sync 监听的资产模型 |
| `ip_fields` | `["private_ip","public_ip","ip"]` | 资产中IP字段名 |
| `name_fields` | `["assetname","hostname","name"]` | 资产中名称字段名 |
| `subnet_field` | `subnet` | 资产中关联子网字段名 |
| `auth_token` | `""` | HTTP 扫描服务认证 Token（通过 UI 配置中心生成） |
| `http_port` | `8900` | HTTP 扫描服务监听端口 |
| `http_host` | `0.0.0.0` | HTTP 扫描服务监听地址 |

---

## 六、管理命令

### 6.1 服务管理

```bash
systemctl start   cmdb-agent              # 启动扫描Agent
systemctl stop    cmdb-agent              # 停止
systemctl restart cmdb-agent              # 重启
systemctl status  cmdb-agent              # 状态

systemctl start   cmdb-agent-ipam-sync    # 启动资产同步
systemctl stop    cmdb-agent-ipam-sync    # 停止
systemctl restart cmdb-agent-ipam-sync    # 重启
systemctl status  cmdb-agent-ipam-sync    # 状态
```

### 6.2 手动执行

```bash
# 立即执行一次完整的扫描循环（本机IP+子网扫描）
sudo /opt/cmdb-agent/cmdb_agent.py --once

# 手动扫描指定子网（测试连通性）
sudo /opt/cmdb-agent/cmdb_agent.py --scan-subnet 10.X.X.0/24

# 验证配置
sudo /opt/cmdb-agent/cmdb_agent.py --validate

# 立即执行一次资产同步
sudo /opt/cmdb-agent/ipam_sync.py --once

# 只同步指定类型
sudo /opt/cmdb-agent/ipam_sync.py --sync-type vmserver

# 验证配置
sudo /opt/cmdb-agent/ipam_sync.py --validate
```

### 6.3 日志查看

```bash
journalctl -u cmdb-agent -f              # 实时Agent日志
journalctl -u cmdb-agent-ipam-sync -f    # 实时同步日志
tail -f /opt/cmdb-agent/logs/cmdb_agent.log
tail -f /opt/cmdb-agent/logs/ipam_sync.log
```

---

## 七、核心功能详解

### 7.1 本机IP上报（cmdb_agent）

每 `interval` 秒（默认7200）扫描本机所有非虚拟网卡：
- 读取 `/sys/class/net/*/address` 获取 MAC
- 执行 `ip -o addr show` 获取 IP
- 自动跳过 lo/docker/veth/br-/tun/virbr 等虚拟接口
- 通过 `POST /api/v0.1/ipam/history/scan` 上报
- 设置 `is_used=true`, `assign_status=0`（已分配/已使用）

### 7.2 子网扫描（cmdb_agent）

**工作流程：**

```
CMDB UI 创建子网 → 填写 Agent ID → Agent 轮询取任务 → 执行扫描 → 上报在线+离线IP
```

**详细步骤：**

1. **在 CMDB UI 创建子网**：进入 IPAM → 子网管理 → 添加子网
   - CIDR: `10.X.X.0/24`（示例）
   - 扫描Agent ID: `0xabcd1234`（与 config.json 中 agent_id 一致）
   - 启用扫描: 勾选

2. **Agent 轮询取任务**：`GET /api/v0.1/adt/sync?oneagent_id=0xabcd1234`
   ```json
   {
     "subnet_scan_rules": [{
       "ci_id": 123,
       "cidr": "10.X.X.0/24",
       "scan_enabled": true,
       "agent_id": "0xabcd1234",
       "cron": "",
       "last_scan_time": null
     }]
   }
   ```

3. **Agent 执行扫描**：自动选择可用工具
   - `nmap -sn -n 10.X.X.0/24`（最快，并行）
   - `fping -a -g 10.X.X.0/24`（备选）
   - `arp-scan 10.X.X.0/24`（局域网备选）
   - `ping -c 1 -W 2`（兜底，仅 /24 以下）

4. **Agent 上报在线+离线IP**：`POST /api/v0.1/ipam/history/scan`
   ```json
   {
     "exec_id": "uuid",
     "ci_id": 123,
     "cidr": "10.X.X.0/24",
     "ips": ["10.X.X.1", "10.X.X.10", "10.X.X.100"],
     "offline_ips": ["10.X.X.2", "10.X.X.3", "10.X.X.4"],
     "status": 0,
     "is_used": "1"
   }
   ```

5. **CMDB 自动处理**：
   - 在线IP（`ips`）：设置 `is_used=1`（在线），`assign_status=0`（已分配）
   - 离线IP（`offline_ips`）：设置 `is_used=0`（离线），**不改变 `assign_status`**
   - 自动关联到子网，刷新子网计数器

**扫描间隔控制：**
- `subnet_scan_interval: 7200`（默认2小时）
- 每个子网独立计时，互不影响
- 同一个子网在间隔内不会重复扫描
- 也可通过 cron 表达式在子网扫描规则中精细控制

**扫描工具优先级：**
| 工具 | 速度 | 适用场景 | 安装命令 |
|------|------|----------|----------|
| `nmap -sn` | 最快 | 所有子网（推荐） | `yum install -y nmap` |
| `fping -g` | 极快 | 大子网（/16以上） | `yum install -y fping` |
| `arp-scan` | 快 | 局域网L2扫描 | `yum install -y arp-scan` |
| `ping` | 慢 | 兜底（/24以下） | 系统自带 |

### 7.3 资产联动同步（ipam_sync）

**解决问题：** 资产模型（如 vmserver）创建后，其 `private_ip` 自动在 IPAM 中标记为已使用。

**工作流程：**
1. 轮询 CMDB 中 `vmserver` / `server` 等资产模型（每 `interval` 秒）
2. 读取每个资产的 `private_ip` 和 `assetname`
3. 查找或创建 `ipam_address` 记录
4. 设置 `is_used=true`（在线），`assign_status=0`（已分配）
5. `name` 字段设为 `assetname`
6. 自动关联到正确子网（CIDR 匹配或 `subnet` 引用字段）

**注意：** 资产同步只负责标记在线，**不负责标记离线**。IP 的离线状态仅由 ping 扫描结果决定。

### 7.4 按需扫描（ipam_sync HTTP 服务）

**解决问题：** 运维人员需要在 UI 上随时对一个子网发起扫描，不等 Agent 轮询周期。

**架构：**
```
┌─────────────────────────────────────────────┐
│              ipam_sync.py                    │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │ 主循环（周期同步） │  │ HTTP Server :8900 │  │
│  │ sync_assets()    │  │ POST /scan       │  │
│  └─────────────────┘  └────────┬─────────┘  │
│                                │             │
│                         daemon 线程          │
└────────────────────────────────┼─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │ ThreadPoolExecutor(20)    │
                    │ ping -c 1 -W 1 (并发)     │
                    └──────────────────────────┘
```

**工作流程：**
1. CMDB UI 右键子网 → "扫描子网"
2. CMDB API → `POST /ipam/subnet/{id}/scan` → 查找 Agent 地址 → `POST http://agent:8900/scan`
3. Agent HTTP 服务接收请求，验证 `X-Auth-Token`，启动后台线程
4. 后台线程用 `ipaddress.ip_network(cidr)` 展开所有主机 IP
5. `ThreadPoolExecutor(max_workers=20)` 并发 ping
6. 收集在线IP和离线IP → `POST /api/v0.1/ipam/history/scan` 上报

**上报数据示例：**
```json
{
  "exec_id": "uuid",
  "ci_id": 123,
  "cidr": "10.X.X.0/24",
  "ips": ["10.X.X.1", "10.X.X.10"],
  "offline_ips": ["10.X.X.2", "10.X.X.3"],
  "is_used": "1"
}
```

**认证配置：**
- 在 CMDB UI → 配置中心 → Agent 配置 中管理 Agent 列表
- 每个 Agent 配置 `host`、`port`、`auth_token`
- Agent 端启动时读取本地 `config.json` 的 `auth_token` 字段
- Token 可通过配置中心的"生成 Token"按钮自动生成

---

## 八、Agent 协议说明

### 8.1 Agent → CMDB Server（HMAC 认证）

| 方向 | 方法 | 路径 | 用途 |
|------|------|------|------|
| Agent → Server | GET | `/api/v0.1/adt/sync` | 轮询扫描任务 |
| Agent → Server | POST | `/api/v0.1/ipam/history/scan` | 上报扫描结果（含在线+离线IP） |
| Agent → Server | GET | `/api/v0.1/ci/s` | 查询 CI |

**认证方式：** `_key` + `_secret` HMAC-SHA1
- `_key`: API Key
- `_secret`: sha1(url_path + secret + 排序后的参数值拼接)

**用户权限：** Agent 使用的 API Key 需要具备 `cmdb_agent` 或 `admin` 角色权限。

### 8.2 Server → Agent（Token 认证）

CMDB Server 通过 HTTP 调用 Agent 的扫描服务接口：

| 方向 | 方法 | 路径 | 用途 |
|------|------|------|------|
| Server → Agent | GET | `http://agent:8900/health` | 健康检查 |
| Server → Agent | POST | `http://agent:8900/scan` | 触发子网 Ping 扫描 |

**认证方式：** `X-Auth-Token` 请求头
- Token 在 CMDB UI 配置中心中为每个 Agent 独立设置
- Agent 启动时从 `/opt/cmdb-agent/config.json` 读取 `auth_token`
- 请求头不匹配时返回 `401 Unauthorized`

**扫描流程：**
```
CMDB UI (右键点击子网 → "扫描子网")
    ↓ POST /api/v0.1/ipam/subnet/{subnet_id}/scan
CMDB API Server (SubnetScanView → SubnetManager.trigger_scan)
    ↓ POST http://agent:8900/scan (X-Auth-Token)
Agent HTTP Server (ipam_sync.py 内嵌, daemon 线程, port 8900)
    ↓ 后台线程并发 ping
Agent → CMDB Server: POST /api/v0.1/ipam/history/scan (上报在线+离线IP)
```
