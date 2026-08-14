<template>
  <div class="ansible-history">
    <div class="ansible-history-header">
      <span class="ansible-history-title">Ansible 执行日志</span>
    </div>

    <a-card>
      <div class="ansible-history-toolbar">
        <a-space>
          <a-select
            v-model="filterPlaybook"
            placeholder="全部剧本"
            allowClear
            style="width: 220px"
            @change="handleFilterChange"
          >
            <a-select-option v-for="pb in playbookOptions" :key="pb" :value="pb">{{ pb }}</a-select-option>
          </a-select>
          <a-select
            v-model="filterStatus"
            placeholder="全部状态"
            allowClear
            style="width: 150px"
            @change="handleFilterChange"
          >
            <a-select-option value="Success">成功</a-select-option>
            <a-select-option value="Failed">失败</a-select-option>
            <a-select-option value="Partial">部分成功</a-select-option>
            <a-select-option value="Running">执行中</a-select-option>
          </a-select>
        </a-space>
        <a-button @click="fetchData">
          <a-icon type="reload" />
          刷新
        </a-button>
      </div>

      <a-table
        :columns="columns"
        :dataSource="tableData"
        :loading="tableLoading"
        :pagination="pagination"
        rowKey="id"
        @change="handleTableChange"
        size="middle"
      >
        <template slot="status" slot-scope="text">
          <a-tag :color="statusColor(text)">{{ statusLabel(text) }}</a-tag>
        </template>
        <template slot="created_at" slot-scope="text">
          {{ formatTime(text) }}
        </template>
        <template slot="action" slot-scope="text, record">
          <a @click="showDetails(record)">查看详情</a>
        </template>
      </a-table>
    </a-card>

    <a-drawer
      title="执行详情"
      :visible="detailVisible"
      @close="detailVisible = false"
      width="800"
    >
      <template v-if="detailData">
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="剧本">{{ detailData.playbook }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detailData.status)">{{ statusLabel(detailData.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="目标数">{{ detailData.ci_count }}</a-descriptions-item>
          <a-descriptions-item label="成功/失败">{{ detailData.success_count }} / {{ detailData.failed_count }}</a-descriptions-item>
          <a-descriptions-item label="执行时间" :span="2">{{ formatTime(detailData.created_at) }}</a-descriptions-item>
        </a-descriptions>

        <a-table
          :columns="detailColumns"
          :dataSource="detailRecords"
          :loading="detailLoading"
          rowKey="id"
          size="small"
          :pagination="false"
        >
          <template slot="status" slot-scope="text">
            <a-tag :color="statusColor(text)">{{ statusLabel(text) }}</a-tag>
          </template>
          <template slot="action" slot-scope="text, record">
            <a @click="showOutput(record)">查看输出</a>
          </template>
        </a-table>
      </template>
    </a-drawer>

    <a-modal
      v-model="outputVisible"
      title="执行输出"
      width="900"
      :footer="null"
    >
      <template v-if="outputData">
        <a-tabs defaultActiveKey="stdout">
          <a-tab-pane key="stdout" tab="标准输出">
            <pre class="ansible-output">{{ outputData.stdout || '(无输出)' }}</pre>
          </a-tab-pane>
          <a-tab-pane key="stderr" tab="错误输出">
            <pre class="ansible-output ansible-output-error">{{ outputData.stderr || '(无错误)' }}</pre>
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-modal>
  </div>
</template>

<script>
import { getAnsibleExecutions, getAnsibleExecutionDetails } from '@/modules/cmdb/api/ansible'

export default {
  name: 'AnsibleHistory',
  data() {
    return {
      tableData: [],
      tableLoading: false,
      pagination: {
        current: 1,
        pageSize: 20,
        total: 0,
        showSizeChanger: true,
        showQuickJumper: true,
        showTotal: (total) => `共 ${total} 条`,
      },
      filterPlaybook: undefined,
      filterStatus: undefined,
      playbookOptions: [],
      pollTimer: null,
      columns: [
        { title: 'ID', dataIndex: 'id', width: 80 },
        { title: '剧本', dataIndex: 'playbook', width: 250 },
        { title: '目标数', dataIndex: 'ci_count', width: 100 },
        { title: '成功', dataIndex: 'success_count', width: 80, customRender: (val) => val || 0 },
        { title: '失败', dataIndex: 'failed_count', width: 80, customRender: (val) => val || 0 },
        { title: '状态', dataIndex: 'status', width: 120, scopedSlots: { customRender: 'status' } },
        { title: '执行时间', dataIndex: 'created_at', width: 180, scopedSlots: { customRender: 'created_at' } },
        { title: '操作', key: 'action', width: 100, scopedSlots: { customRender: 'action' } },
      ],
      detailVisible: false,
      detailData: null,
      detailRecords: [],
      detailLoading: false,
      detailColumns: [
        { title: 'CI ID', dataIndex: 'ci_id', width: 80 },
        { title: '主机名', dataIndex: 'ci_name', width: 180 },
        { title: 'IP', dataIndex: 'ip', width: 150 },
        { title: '状态', dataIndex: 'status', width: 100, scopedSlots: { customRender: 'status' } },
        { title: '返回码', dataIndex: 'returncode', width: 80 },
        { title: '操作', key: 'action', width: 100, scopedSlots: { customRender: 'action' } },
      ],
      outputVisible: false,
      outputData: null,
    }
  },
  mounted() {
    this.fetchData()
    this.startPolling()
  },
  beforeDestroy() {
    this.stopPolling()
  },
  methods: {
    startPolling() {
      this.stopPolling()
      this.pollTimer = setInterval(this.checkRunningAndRefresh, 5000)
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    checkRunningAndRefresh() {
      if (this.tableData.some((r) => r.status === 'Running')) {
        this.fetchData()
      } else {
        this.stopPolling()
      }
    },
    async fetchData() {
      this.tableLoading = true
      try {
        const params = {
          page: this.pagination.current,
          page_size: this.pagination.pageSize,
        }
        if (this.filterPlaybook) params.playbook = this.filterPlaybook
        if (this.filterStatus) params.status = this.filterStatus
        const res = await getAnsibleExecutions(params)
        this.tableData = res.records || []
        this.pagination.total = res.total || 0
        if (!this.playbookOptions.length) {
          const allPlaybooks = [...new Set(this.tableData.map(r => r.playbook).filter(Boolean))]
          this.playbookOptions = allPlaybooks
        }
      } catch (e) {
        console.error('Failed to fetch ansible executions:', e)
      } finally {
        this.tableLoading = false
      }
    },
    handleFilterChange() {
      this.pagination.current = 1
      this.fetchData()
    },
    handleTableChange(pagination) {
      this.pagination.current = pagination.current
      this.pagination.pageSize = pagination.pageSize
      this.fetchData()
    },
    statusColor(status) {
      const map = { Success: 'green', Failed: 'red', Partial: 'orange', Running: 'blue' }
      return map[status] || 'default'
    },
    statusLabel(status) {
      const map = { Success: '成功', Failed: '失败', Partial: '部分成功', Running: '执行中' }
      return map[status] || status
    },
    formatTime(timeStr) {
      if (!timeStr) return '-'
      return timeStr.replace('T', ' ').substring(0, 19)
    },
    async showDetails(record) {
      this.detailData = record
      this.detailVisible = true
      this.detailLoading = true
      try {
        const res = await getAnsibleExecutionDetails(record.id)
        this.detailRecords = res.details || []
      } catch (e) {
        console.error('Failed to fetch execution details:', e)
        this.detailRecords = []
      } finally {
        this.detailLoading = false
      }
    },
    showOutput(record) {
      this.outputData = record
      this.outputVisible = true
    },
  },
}
</script>

<style lang="less" scoped>
.ansible-history {
  padding: 16px;
  &-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  &-title {
    font-size: 16px;
    font-weight: 600;
  }
  &-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
}
.ansible-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  max-height: 500px;
  overflow: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 12px;
  font-family: 'Courier New', Courier, monospace;
  margin: 0;
  &-error {
    color: #f48771;
  }
}
</style>
