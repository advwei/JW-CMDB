<template>
  <div class="cmdb-config-center">
    <div class="cmdb-config-center-header">
      <span class="cmdb-config-center-title">{{ $t('cmdb.menu.configCenter') }}</span>
    </div>
    <a-tabs defaultActiveKey="jumpserver" @change="onTabChange">
      <a-tab-pane key="jumpserver" tab="JumpServer 设置">
        <a-spin :spinning="loadingJms">
          <a-form :form="jmsForm" layout="vertical" class="cmdb-config-center-form">
            <a-card title="JumpServer 对接配置" class="cmdb-config-card">
              <a-form-item label="JMS_URL（JumpServer 访问地址）">
                <a-input v-decorator="['JMS_URL']" placeholder="https://jumpserver.example.com" />
              </a-form-item>
              <a-form-item label="JMS_TOKEN（API Token）">
                <a-input v-decorator="['JMS_TOKEN']" type="password" placeholder="输入 Token" />
              </a-form-item>
              <a-form-item label="JMS_ACCOUNT_NAME（远程用户配置）">
                <a-input v-decorator="['JMS_ACCOUNT_NAME']" placeholder="如 eveuser" />
              </a-form-item>
            </a-card>
            <a-card title="资产节点 UUID 映射" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置 CI 节点名称与 JumpServer 节点 UUID 的对应关系</p>
              <a-table size="small" :dataSource="nodeMapList" :columns="simpleColumns" rowKey="index" :pagination="false">
                <template slot="keyCol" slot-scope="text, record">
                  <a-input v-model="record.key" placeholder="节点名称 (如 53C-DB-physics)" />
                </template>
                <template slot="valueCol" slot-scope="text, record">
                  <a-input v-model="record.value" placeholder="UUID (如 e1741d1e-...)" />
                </template>
                <template slot="actionCol" slot-scope="text, record">
                  <a-button type="danger" size="small" icon="delete" @click="removeItem(nodeMapList, record.index)" />
                </template>
              </a-table>
              <a-button type="dashed" style="width: 100%; margin-top: 12px" @click="addItem(nodeMapList)">
                <a-icon type="plus" /> 添加映射
              </a-button>
            </a-card>
            <a-card title="资产类型映射" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置 CI 资产类型与 JumpServer 平台 ID 的对应关系</p>
              <a-table size="small" :dataSource="platformMapList" :columns="simpleColumns" rowKey="index" :pagination="false">
                <template slot="keyCol" slot-scope="text, record">
                  <a-input v-model="record.key" placeholder="资产类型 (如 Linux)" />
                </template>
                <template slot="valueCol" slot-scope="text, record">
                  <a-input v-model="record.value" placeholder="平台 ID (如 1)" />
                </template>
                <template slot="actionCol" slot-scope="text, record">
                  <a-button type="danger" size="small" icon="delete" @click="removeItem(platformMapList, record.index)" />
                </template>
              </a-table>
              <a-button type="dashed" style="width: 100%; margin-top: 12px" @click="addItem(platformMapList)">
                <a-icon type="plus" /> 添加映射
              </a-button>
            </a-card>
            <a-card title="远程协议映射" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置操作系统版本与 JumpServer 协议的对应关系</p>
              <a-table size="small" :dataSource="protocolMapList" :columns="protocolColumns" rowKey="index" :pagination="false">
                <template slot="keyCol" slot-scope="text, record">
                  <a-input v-model="record.key" placeholder="操作系统版本 (如 Debian 12.8)" />
                </template>
                <template slot="valueCol" slot-scope="text, record">
                  <a-textarea v-model="record.value" placeholder="[{ &quot;name&quot;: &quot;ssh&quot;, &quot;port&quot;: 2022 }]" :rows="2" />
                </template>
                <template slot="actionCol" slot-scope="text, record">
                  <a-button type="danger" size="small" icon="delete" @click="removeItem(protocolMapList, record.index)" />
                </template>
              </a-table>
              <a-button type="dashed" style="width: 100%; margin-top: 12px" @click="addItem(protocolMapList)">
                <a-icon type="plus" /> 添加映射
              </a-button>
            </a-card>
            <a-row>
              <a-col :span="24" style="text-align: center; margin-top: 24px;">
                <a-space>
                  <a-button type="primary" :loading="savingJms" @click="handleSaveJms">保存配置</a-button>
                  <a-button @click="loadJmsConfig">重置</a-button>
                </a-space>
              </a-col>
            </a-row>
          </a-form>
        </a-spin>
      </a-tab-pane>
      <a-tab-pane key="ansible" tab="Ansible 设置">
        <a-spin :spinning="loadingAnsible">
          <a-form :form="ansibleForm" layout="vertical" class="cmdb-config-center-form">
            <a-card title="Ansible Executor 对接配置" class="cmdb-config-card">
              <a-form-item label="执行器地址（Executor URL）">
                <a-input v-decorator="['executor_url']" placeholder="http://192.168.1.100:18081" />
              </a-form-item>
              <a-form-item label="API Key">
                <a-input v-decorator="['executor_api_key']" type="password" placeholder="输入 Executor API Key" />
              </a-form-item>
              <a-form-item label="默认剧本">
                <a-select v-decorator="['default_playbook']" placeholder="选择默认执行剧本" @focus="fetchPlaybooks">
                  <a-select-option v-for="pb in playbookList" :key="pb" :value="pb">{{ pb }}</a-select-option>
                </a-select>
              </a-form-item>
              <a-form-item label="超时时间（秒）">
                <a-input-number v-decorator="['timeout']" :min="30" :max="3600" style="width: 200px" />
              </a-form-item>
            </a-card>
            <a-card title="CI 字段映射" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置 CI 属性到 Ansible 参数的映射关系</p>
              <a-form-item label="IP 地址字段">
                <a-input v-decorator="['field_map_ip']" placeholder="ip, private_ip, public_ip" />
              </a-form-item>
              <a-form-item label="主机名字段">
                <a-input v-decorator="['field_map_hostname']" placeholder="hostname, name" />
              </a-form-item>
              <a-form-item label="操作系统字段">
                <a-input v-decorator="['field_map_os_version']" placeholder="os_version, os, ostype" />
              </a-form-item>
              <a-form-item label="密码字段">
                <a-input v-decorator="['field_map_password']" placeholder="password, root_password, ssh_password" />
              </a-form-item>
            </a-card>
            <a-card title="OS 凭证映射" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置各操作系统对应的 Ansible 连接端口、用户名和密码</p>
              <a-table size="small" :dataSource="osCredentialList" :columns="credColumns" rowKey="index" :pagination="false">
                <template slot="osCol" slot-scope="text, record">
                  <a-input v-model="record.os" placeholder="操作系统 (如 Debian 12.8)" />
                </template>
                <template slot="portCol" slot-scope="text, record">
                  <a-input-number v-model="record.port" :min="1" :max="65535" style="width: 100%" />
                </template>
                <template slot="userCol" slot-scope="text, record">
                  <a-input v-model="record.user" placeholder="登录用户" />
                </template>
                <template slot="passwordCol" slot-scope="text, record">
                  <a-input-password v-model="record.password" placeholder="登录密码" />
                </template>
                <template slot="actionCol" slot-scope="text, record">
                  <a-button type="danger" size="small" icon="delete" @click="removeItem(osCredentialList, record.index)" />
                </template>
              </a-table>
              <a-button type="dashed" style="width: 100%; margin-top: 12px" @click="addOsCredential">
                <a-icon type="plus" /> 添加操作系统凭证
              </a-button>
            </a-card>
            <a-row>
              <a-col :span="24" style="text-align: center; margin-top: 24px;">
                <a-space>
                  <a-button type="primary" :loading="savingAnsible" @click="handleSaveAnsible">保存配置</a-button>
                  <a-button @click="loadAnsibleConfig">重置</a-button>
                </a-space>
              </a-col>
            </a-row>
          </a-form>
        </a-spin>
      </a-tab-pane>
      <a-tab-pane key="agent" tab="Agent 配置">
        <a-spin :spinning="loadingAgent">
          <div class="cmdb-config-center-form">
            <div style="margin-bottom: 12px; display: flex; justify-content: space-between;">
              <a-button type="primary" icon="plus" @click="openAgentModal()">{{ $t('cmdb.ipam.addAgent') }}</a-button>
              <a-button @click="handleGenerateToken">{{ $t('cmdb.ipam.generateToken') }}</a-button>
            </div>
            <a-table size="small" :dataSource="agentList" :columns="agentColumns" rowKey="agent_id" :pagination="false">
              <template slot="actionCol" slot-scope="text, record">
                <a-space>
                  <a-button type="primary" size="small" @click="openAgentModal(record)">{{ $t('cmdb.ipam.editAgent') }}</a-button>
                  <a-button type="danger" size="small" @click="deleteAgent(record)">{{ $t('cmdb.ipam.deleteAgent') }}</a-button>
                </a-space>
              </template>
            </a-table>
            <a-row>
              <a-col :span="24" style="text-align: center; margin-top: 24px;">
                <a-button type="primary" :loading="savingAgent" @click="handleSaveAgent">{{ $t('save') }}</a-button>
              </a-col>
            </a-row>
          </div>
        </a-spin>
        <a-modal :title="agentModalTitle" :visible="agentModalVisible" @ok="confirmAgentModal" @cancel="agentModalVisible = false">
          <a-form :form="agentForm" layout="vertical">
            <a-form-item :label="$t('cmdb.ipam.agentId')">
              <a-input v-decorator="['agent_id', { rules: [{ required: true, message: $t('cmdb.ipam.agentId') + $t('required') }] }]" placeholder="0x..." />
            </a-form-item>
            <a-form-item :label="$t('cmdb.ipam.agentHost')">
              <a-input v-decorator="['host', { rules: [{ required: true, message: $t('cmdb.ipam.agentHost') + $t('required') }] }]" placeholder="192.168.1.100" />
            </a-form-item>
            <a-form-item :label="$t('cmdb.ipam.agentPort')">
              <a-input-number v-decorator="['port', { initialValue: 8900, rules: [{ required: true, message: $t('cmdb.ipam.agentPort') + $t('required') }] }]" :min="1" :max="65535" style="width: 100%" />
            </a-form-item>
            <a-form-item :label="$t('cmdb.ipam.authToken')">
              <a-input v-decorator="['auth_token']" placeholder="cmdb_agt_..." />
            </a-form-item>
          </a-form>
        </a-modal>
      </a-tab-pane>
      <a-tab-pane key="model" :tab="$t('cmdb.ci.modelConfig')">
        <a-spin :spinning="loadingModel">
          <a-form :form="modelForm" layout="vertical" class="cmdb-config-center-form">
            <a-card :title="$t('cmdb.ci.modelConfig') + ' ID'" class="cmdb-config-card">
              <p class="cmdb-config-desc">配置 CI 模型对应的 Type ID，迁移环境后如果 ID 发生变化，请在此修改</p>
              <a-form-item :label="$t('cmdb.ci.vmserverTypeId')">
                <a-input-number v-decorator="['vmserver_type_id', { rules: [{ required: true }] }]" :min="1" style="width: 200px" />
              </a-form-item>
              <a-form-item :label="$t('cmdb.ci.delserverTypeId')">
                <a-input-number v-decorator="['delserver_type_id', { rules: [{ required: true }] }]" :min="1" style="width: 200px" />
              </a-form-item>
            </a-card>
            <a-row>
              <a-col :span="24" style="text-align: center; margin-top: 24px;">
                <a-space>
                  <a-button type="primary" :loading="savingModel" @click="handleSaveModel">{{ $t('save') }}</a-button>
                  <a-button @click="loadModelConfig">{{ $t('reset') }}</a-button>
                </a-space>
              </a-col>
            </a-row>
          </a-form>
        </a-spin>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script>
import { axios } from '@/utils/request'
import { getAnsiblePlaybooks } from '@/modules/cmdb/api/ansible'
import { getModelConfig, saveModelConfig } from '@/modules/cmdb/api/modelConfig'

const jmsUrlPrefix = '/v0.1'

export default {
  name: 'ConfigCenter',
  data() {
    return {
      jmsForm: this.$form.createForm(this),
      ansibleForm: this.$form.createForm(this),
      loadingJms: false,
      savingJms: false,
      loadingAnsible: false,
      savingAnsible: false,
      nodeMapList: [],
      platformMapList: [],
      protocolMapList: [],
      playbookList: [],
      osCredentialList: [],
      loadingAgent: false,
      savingAgent: false,
      agentList: [],
      agentModalVisible: false,
      agentModalTitle: '',
      editingAgentIndex: -1,
      agentForm: this.$form.createForm(this),
      modelForm: this.$form.createForm(this),
      loadingModel: false,
      savingModel: false,
      agentColumns: [
        { title: 'Agent ID', dataIndex: 'agent_id', key: 'agent_id' },
        { title: '地址', dataIndex: 'host', key: 'host' },
        { title: '端口', dataIndex: 'port', key: 'port' },
        { title: 'Token', dataIndex: 'auth_token', key: 'auth_token', ellipsis: true, width: '35%' },
        { title: '操作', key: 'actionCol', scopedSlots: { customRender: 'actionCol' }, width: '30%' },
      ],
      simpleColumns: [
        { title: '名称', key: 'keyCol', scopedSlots: { customRender: 'keyCol' }, width: '40%' },
        { title: '值', key: 'valueCol', scopedSlots: { customRender: 'valueCol' }, width: '40%' },
        { title: '操作', key: 'actionCol', scopedSlots: { customRender: 'actionCol' }, width: '20%' },
      ],
      protocolColumns: [
        { title: '操作系统版本', key: 'keyCol', scopedSlots: { customRender: 'keyCol' }, width: '40%' },
        { title: '协议配置 (JSON)', key: 'valueCol', scopedSlots: { customRender: 'valueCol' }, width: '40%' },
        { title: '操作', key: 'actionCol', scopedSlots: { customRender: 'actionCol' }, width: '20%' },
      ],
      credColumns: [
        { title: '操作系统', key: 'osCol', scopedSlots: { customRender: 'osCol' }, width: '25%' },
        { title: '端口', key: 'portCol', scopedSlots: { customRender: 'portCol' }, width: '15%' },
        { title: '用户', key: 'userCol', scopedSlots: { customRender: 'userCol' }, width: '25%' },
        { title: '密码', key: 'passwordCol', scopedSlots: { customRender: 'passwordCol' }, width: '25%' },
        { title: '操作', key: 'actionCol', scopedSlots: { customRender: 'actionCol' }, width: '10%' },
      ],
    }
  },
  mounted() {
    this.loadJmsConfig()
    this.loadAnsibleConfig()
    this.loadAgentConfig()
    this.loadModelConfig()
  },
  methods: {
    onTabChange(key) {
      if (key === 'ansible') {
        this.fetchPlaybooks()
        this.loadAnsibleConfig()
      }
      if (key === 'agent') {
        this.loadAgentConfig()
      }
      if (key === 'model') {
        this.loadModelConfig()
      }
    },
    async fetchPlaybooks() {
      try {
        this.playbookList = (await getAnsiblePlaybooks()).playbooks || []
      } catch (e) {
        this.playbookList = []
      }
    },
    async loadJmsConfig() {
      this.loadingJms = true
      try {
        const res = await axios({ url: jmsUrlPrefix + '/jms/config', method: 'GET' })
        const config = res || {}
        const formFields = {}
        formFields['JMS_URL'] = config.JMS_URL || ''
        formFields['JMS_TOKEN'] = config.JMS_TOKEN || ''
        formFields['JMS_ACCOUNT_NAME'] = config.JMS_ACCOUNT_NAME || ''
        this.jmsForm.setFieldsValue(formFields)
        this.loadMapList('nodeMapList', config.JMS_NODE_MAP)
        this.loadMapList('platformMapList', config.JMS_PLATFORM_MAP)
        this.loadMapList('protocolMapList', config.JMS_PROTOCOL_MAP, true)
      } finally {
        this.loadingJms = false
      }
    },
    async loadAnsibleConfig() {
      this.loadingAnsible = true
      try {
        const res = await axios({ url: jmsUrlPrefix + '/ansible/config', method: 'GET' })
        const config = res || {}
        const formFields = {}
        formFields['executor_url'] = config.executor_url || ''
        formFields['executor_api_key'] = config.executor_api_key || ''
        formFields['default_playbook'] = config.default_playbook || ''
        formFields['timeout'] = config.timeout != null ? config.timeout : 300
        const fieldMap = config.field_map || {}
        formFields['field_map_ip'] = (fieldMap.ip || []).join(', ')
        formFields['field_map_hostname'] = (fieldMap.hostname || []).join(', ')
        formFields['field_map_os_version'] = (fieldMap.os_version || []).join(', ')
        formFields['field_map_password'] = (fieldMap.password || []).join(', ')
        this.$nextTick(() => {
          this.ansibleForm.setFieldsValue(formFields)
        })
        this.loadOsCredentialList(config.os_credentials)
      } catch (e) {
        console.error('loadAnsibleConfig error', e)
      } finally {
        this.loadingAnsible = false
      }
    },
    loadMapList(listName, mapData, isJson) {
      const list = []
      if (mapData) {
        Object.entries(mapData).forEach(([key, value], index) => {
          list.push({ index, key, value: isJson ? JSON.stringify(value) : String(value) })
        })
      }
      this[listName] = list
      if (this[listName].length === 0) {
        this.addItem(this[listName])
      }
    },
    loadOsCredentialList(credentials) {
      const list = []
      if (Array.isArray(credentials)) {
        credentials.forEach((item, index) => {
          list.push({
            index,
            os: item.os || '',
            port: item.port || 22,
            user: item.user || '',
            password: item.password || '',
          })
        })
      }
      this.osCredentialList = list
      if (this.osCredentialList.length === 0) {
        this.addOsCredential()
      }
    },
    addItem(list) {
      const maxIndex = list.length > 0 ? Math.max(...list.map((item) => item.index)) : -1
      list.push({ index: maxIndex + 1, key: '', value: '' })
    },
    addOsCredential() {
      const maxIndex = this.osCredentialList.length > 0 ? Math.max(...this.osCredentialList.map((item) => item.index)) : -1
      this.osCredentialList.push({ index: maxIndex + 1, os: 'Linux', port: 22, user: 'root', password: 'eve.1234' })
    },
    removeItem(list, idx) {
      const i = list.findIndex((item) => item.index === idx)
      if (i !== -1) list.splice(i, 1)
    },
    toMap(list, isJson) {
      const map = {}
      list.forEach((item) => {
        if (item.key.trim()) {
          map[item.key.trim()] = isJson ? item.value.trim() : item.value.trim()
        }
      })
      return map
    },
    async handleSaveJms() {
      this.savingJms = true
      try {
        const values = await new Promise((resolve, reject) => {
          this.jmsForm.validateFields((err, vals) => {
            if (err) return reject(err)
            resolve(vals)
          })
        })
        const nodeMap = this.toMap(this.nodeMapList)
        const platformMap = this.toMap(this.platformMapList)
        const protocolMap = this.toMap(this.protocolMapList, true)
        const protocolMapParsed = {}
        for (const [key, value] of Object.entries(protocolMap)) {
          try {
            protocolMapParsed[key] = JSON.parse(value)
          } catch (e) {
            this.$message.error('协议配置 JSON 格式错误: ' + key)
            return
          }
        }
        const accountName = values.JMS_ACCOUNT_NAME || ''
        const payload = {
          JMS_URL: values.JMS_URL || '',
          JMS_TOKEN: values.JMS_TOKEN || '',
          JMS_ACCOUNT_NAME: accountName,
          JMS_ACCOUNT_USERNAME: accountName,
          JMS_NODE_MAP: nodeMap,
          JMS_PLATFORM_MAP: platformMap,
          JMS_PROTOCOL_MAP: protocolMapParsed,
        }
        await axios({ url: jmsUrlPrefix + '/jms/config', method: 'POST', data: payload })
        this.$message.success('保存成功')
      } catch (e) {
        if (e) this.$message.error('保存失败: ' + (e.message || e))
      } finally {
        this.savingJms = false
      }
    },
    async loadAgentConfig() {
      this.loadingAgent = true
      try {
        const res = await axios({ url: '/v0.1/ipam/agent/config', method: 'GET' })
        this.agentList = (res?.agents) || []
      } catch (e) {
        console.error('loadAgentConfig error', e)
      } finally {
        this.loadingAgent = false
      }
    },
    async handleSaveAgent() {
      this.savingAgent = true
      try {
        await axios({ url: '/v0.1/ipam/agent/config', method: 'POST', data: { agents: this.agentList } })
        this.$message.success(this.$t('saveSuccess'))
      } catch (e) {
        this.$message.error(this.$t('saveFailed') + ': ' + (e.message || e))
      } finally {
        this.savingAgent = false
      }
    },
    openAgentModal(record) {
      this.editingAgentIndex = record ? this.agentList.indexOf(record) : -1
      this.agentModalTitle = record ? this.$t('cmdb.ipam.editAgent') : this.$t('cmdb.ipam.addAgent')
      this.agentModalVisible = true
      this.$nextTick(() => {
        if (record) {
          this.agentForm.setFieldsValue({
            agent_id: record.agent_id,
            host: record.host,
            port: record.port,
            auth_token: record.auth_token,
          })
        } else {
          this.agentForm.resetFields()
        }
      })
    },
    confirmAgentModal() {
      this.agentForm.validateFields((err, values) => {
        if (err) return
        const agent = {
          agent_id: values.agent_id,
          host: values.host,
          port: Number(values.port) || 8900,
          auth_token: values.auth_token || '',
        }
        if (this.editingAgentIndex >= 0) {
          this.$set(this.agentList, this.editingAgentIndex, agent)
        } else {
          this.agentList.push(agent)
        }
        this.agentModalVisible = false
      })
    },
    deleteAgent(record) {
      this.$confirm({
        title: this.$t('cmdb.ipam.deleteAgentConfirm'),
        onOk: () => {
          const idx = this.agentList.indexOf(record)
          if (idx !== -1) this.agentList.splice(idx, 1)
        },
      })
    },
    async handleGenerateToken() {
      try {
        const res = await axios({ url: '/v0.1/ipam/agent/token', method: 'GET' })
        const token = res?.token || ''
        if (token) {
          try {
            await navigator.clipboard.writeText(token)
            this.$message.success('Token: ' + token + ' (已复制到剪贴板)')
          } catch {
            this.$message.success('Token: ' + token)
          }
        }
      } catch (e) {
        this.$message.error(this.$t('cmdb.ipam.scanSubnetFailed') + ': ' + (e.message || e))
      }
    },
    async handleSaveAnsible() {
      this.savingAnsible = true
      try {
        const values = await new Promise((resolve, reject) => {
          this.ansibleForm.validateFields((err, vals) => {
            if (err) return reject(err)
            resolve(vals)
          })
        })
        const fieldMapIp = (values.field_map_ip || '').split(',').map((s) => s.trim()).filter(Boolean)
        const fieldMapHostname = (values.field_map_hostname || '').split(',').map((s) => s.trim()).filter(Boolean)
        const fieldMapOs = (values.field_map_os_version || '').split(',').map((s) => s.trim()).filter(Boolean)
        const fieldMapPassword = (values.field_map_password || '').split(',').map((s) => s.trim()).filter(Boolean)
        const osCredentials = this.osCredentialList
          .filter((item) => item.os.trim())
          .map((item) => ({
            os: item.os.trim(),
            port: Number(item.port) || 22,
            user: item.user.trim(),
            password: item.password,
          }))
        const payload = {
          executor_url: values.executor_url || '',
          executor_api_key: values.executor_api_key || '',
          default_playbook: values.default_playbook || '',
          timeout: values.timeout || 300,
          field_map: {
            ip: fieldMapIp.length ? fieldMapIp : ['ip', 'private_ip', 'public_ip'],
            hostname: fieldMapHostname.length ? fieldMapHostname : ['hostname', 'name'],
            os_version: fieldMapOs.length ? fieldMapOs : ['os_version', 'os', 'ostype'],
            password: fieldMapPassword.length ? fieldMapPassword : ['password', 'root_password', 'ssh_password'],
          },
          os_credentials: osCredentials,
        }
        await axios({ url: jmsUrlPrefix + '/ansible/config', method: 'POST', data: payload })
        this.$message.success('保存成功')
      } catch (e) {
        if (e) this.$message.error('保存失败: ' + (e.message || e))
      } finally {
        this.savingAnsible = false
      }
    },
    async loadModelConfig() {
      this.loadingModel = true
      try {
        const res = await getModelConfig()
        const config = res || {}
        this.$nextTick(() => {
          this.modelForm.setFieldsValue({
            vmserver_type_id: config.vmserver_type_id != null ? config.vmserver_type_id : 52,
            delserver_type_id: config.delserver_type_id != null ? config.delserver_type_id : 54,
          })
        })
      } catch (e) {
        console.error('loadModelConfig error', e)
      } finally {
        this.loadingModel = false
      }
    },
    async handleSaveModel() {
      this.savingModel = true
      try {
        const values = await new Promise((resolve, reject) => {
          this.modelForm.validateFields((err, vals) => {
            if (err) return reject(err)
            resolve(vals)
          })
        })
        const payload = {
          vmserver_type_id: Number(values.vmserver_type_id) || 52,
          delserver_type_id: Number(values.delserver_type_id) || 54,
        }
        await saveModelConfig(payload)
        this.$message.success(this.$t('saveSuccess'))
      } catch (e) {
        if (e) this.$message.error(this.$t('saveFailed') + ': ' + (e.message || e))
      } finally {
        this.savingModel = false
      }
    },
  },
}
</script>

<style lang="less" scoped>
.cmdb-config-center {
  padding: 16px;
  &-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }
  &-title {
    font-size: 16px;
    font-weight: 600;
  }
  &-form {
    max-width: 800px;
    margin: 0 auto;
  }
  &-desc {
    color: #888;
    font-size: 13px;
    margin-bottom: 12px;
  }
}
.cmdb-config-card {
  margin-bottom: 16px;
}
</style>
