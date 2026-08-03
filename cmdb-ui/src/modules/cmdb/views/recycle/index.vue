<template>
  <div class="cmdb-recycle">
    <div class="cmdb-recycle-header">
      <span class="cmdb-recycle-title">{{ $t('cmdb.ci.recycleResourceOverview') }}</span>
    </div>

    <a-row :gutter="[16, 16]" class="cmdb-recycle-count-stats">
      <a-col :span="6">
        <a-card class="cmdb-recycle-stat-card">
          <a-statistic
            :title="$t('cmdb.ci.recycleTotal')"
            :value="countStats.total"
            :valueStyle="{ color: '#1890ff' }"
          />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="cmdb-recycle-stat-card">
          <a-statistic
            :title="$t('cmdb.ci.delstatusPending')"
            :value="countStats.pending"
            :valueStyle="{ color: '#faad14' }"
          />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="cmdb-recycle-stat-card">
          <a-statistic
            :title="$t('cmdb.ci.delstatusRecycled')"
            :value="countStats.recycled"
            :valueStyle="{ color: '#52c41a' }"
          />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card class="cmdb-recycle-stat-card">
          <a-statistic
            :title="$t('cmdb.ci.delstatusConfirming')"
            :value="countStats.confirming"
            :valueStyle="{ color: '#ff4d4f' }"
          />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]" class="cmdb-recycle-stats">
      <a-col :span="8" v-for="status in statusList" :key="status.key">
        <a-card :title="status.label" :bordered="true" class="cmdb-recycle-status-card">
          <div class="cmdb-recycle-stat-item">
            <span class="cmdb-recycle-stat-label">{{ $t('cmdb.ci.cpuTotal') }}</span>
            <span class="cmdb-recycle-stat-value" :style="{ color: status.color }">{{ resourceStats[status.key].cpu }} {{ $t('cmdb.ci.cores') }}</span>
          </div>
          <div class="cmdb-recycle-stat-item">
            <span class="cmdb-recycle-stat-label">{{ $t('cmdb.ci.ramTotal') }}</span>
            <span class="cmdb-recycle-stat-value" :style="{ color: status.color }">{{ resourceStats[status.key].ram }} {{ $t('cmdb.ci.gb') }}</span>
          </div>
          <div class="cmdb-recycle-stat-item">
            <span class="cmdb-recycle-stat-label">{{ $t('cmdb.ci.hdTotal') }}</span>
            <span class="cmdb-recycle-stat-value" :style="{ color: status.color }">{{ resourceStats[status.key].hd }} {{ $t('cmdb.ci.gb') }}</span>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]">
      <a-col :span="24">
        <a-card :title="$t('cmdb.ci.recycleList')">
          <div class="cmdb-recycle-toolbar">
            <a-space>
              <a-select
                v-model="filterDelstatus"
                :placeholder="$t('cmdb.ci.delstatusPlaceholder')"
                allowClear
                style="width: 200px"
                @change="handleFilterChange"
              >
                <a-select-option value="待回收">{{ $t('cmdb.ci.delstatusPending') }}</a-select-option>
                <a-select-option value="已回收">{{ $t('cmdb.ci.delstatusRecycled') }}</a-select-option>
                <a-select-option value="待确认">{{ $t('cmdb.ci.delstatusConfirming') }}</a-select-option>
              </a-select>
              <a-button
                type="danger"
                :disabled="!selectedRowKeys.length"
                @click="handleCancelRecycle"
              >
                {{ $t('cmdb.ci.cancelRecycle') }}
              </a-button>
            </a-space>
            <a-input-search
              v-model="searchKeyword"
              :placeholder="$t('cmdb.ci.searchPlaceholder')"
              style="width: 300px"
              @search="handleSearch"
            />
          </div>
          <a-table
            :columns="columns"
            :dataSource="tableData"
            :loading="tableLoading"
            :pagination="pagination"
            :rowKey="record => record._id"
            :rowSelection="{ selectedRowKeys, onChange: onSelectChange }"
            @change="handleTableChange"
            size="middle"
          >
            <template slot="delstatus" slot-scope="text">
              <a-tag :color="getDelstatusColor(text)">{{ text || '-' }}</a-tag>
            </template>
            <template slot="action" slot-scope="text, record">
              <a @click="showDetail(record)">{{ $t('cmdb.ci.detail') }}</a>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>

    <a-drawer
      :title="$t('cmdb.ci.recycleDetail')"
      :visible="detailVisible"
      @close="detailVisible = false"
      width="600"
    >
      <a-descriptions bordered :column="1" size="small">
        <a-descriptions-item label="ID">{{ detailData._id }}</a-descriptions-item>
        <a-descriptions-item :label="$t('cmdb.ci.delstatus')">
          <a-tag :color="getDelstatusColor(detailData.delstatus)">{{ detailData.delstatus || '-' }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item v-for="(value, key) in detailFields" :key="key" :label="key">
          {{ value }}
        </a-descriptions-item>
      </a-descriptions>
    </a-drawer>
  </div>
</template>

<script>
import { searchCI, cancelRecycleCI } from '@/modules/cmdb/api/ci'
import { getModelConfig } from '@/modules/cmdb/api/modelConfig'

export default {
  name: 'RecycleResourceOverview',
  data() {
    return {
      delserverTypeId: 54,
      countStats: { total: 0, pending: 0, recycled: 0, confirming: 0 },
      resourceStats: {
        pending: { cpu: 0, ram: 0, hd: 0 },
        recycled: { cpu: 0, ram: 0, hd: 0 },
        confirming: { cpu: 0, ram: 0, hd: 0 },
      },
      statusList: [
        { key: 'pending', label: this.$t('cmdb.ci.delstatusPending'), color: '#faad14' },
        { key: 'recycled', label: this.$t('cmdb.ci.delstatusRecycled'), color: '#52c41a' },
        { key: 'confirming', label: this.$t('cmdb.ci.delstatusConfirming'), color: '#ff4d4f' },
      ],
      tableData: [],
      tableLoading: false,
      filterDelstatus: undefined,
      searchKeyword: '',
      pagination: {
        current: 1,
        pageSize: 20,
        total: 0,
        showSizeChanger: true,
        showQuickJumper: true,
        showTotal: (total, range) => `${range[0]}-${range[1]} / ${total}`,
      },
      sortBy: '-_id',
      selectedRowKeys: [],
      detailVisible: false,
      detailData: {},
      columns: [
        { title: 'ID', dataIndex: '_id', width: 80, sorter: true },
        { title: this.$t('cmdb.ci.delstatus'), dataIndex: 'delstatus', width: 120, scopedSlots: { customRender: 'delstatus' } },
        { title: this.$t('cmdb.ci.assetName'), dataIndex: 'assetname', width: 150 },
        { title: this.$t('cmdb.ci.privateIP'), dataIndex: 'private_ip', width: 150 },
        { title: this.$t('cmdb.ci.hostname'), dataIndex: 'hostname', width: 150 },
        { title: this.$t('cmdb.ci.osVersion'), dataIndex: 'os_version', width: 150 },
        { title: this.$t('cmdb.ci.actions'), width: 100, scopedSlots: { customRender: 'action' } },
      ],
    }
  },
  computed: {
    detailFields() {
      const skip = ['_id', '_type', 'delstatus']
      const fields = {}
      Object.keys(this.detailData).forEach((key) => {
        if (!skip.includes(key) && this.detailData[key] !== null && this.detailData[key] !== undefined) {
          fields[key] = typeof this.detailData[key] === 'object' ? JSON.stringify(this.detailData[key]) : this.detailData[key]
        }
      })
      return fields
    },
  },
  async mounted() {
    await this.loadModelConfig()
    this.fetchResourceStats()
    this.fetchTableData()
  },
  methods: {
    async loadModelConfig() {
      try {
        const res = await getModelConfig()
        const config = res || {}
        this.delserverTypeId = config.delserver_type_id || 54
      } catch (e) {
        console.error('Failed to load model config:', e)
      }
    },
    statusKeyMap(status) {
      const map = { '待回收': 'pending', '已回收': 'recycled', '待确认': 'confirming' }
      return map[status] || 'confirming'
    },
    async fetchResourceStats() {
      try {
        const res = await searchCI({
          q: '_type:' + this.delserverTypeId,
          fl: 'cpu_count,ram_size,hd_size,delstatus',
          count: 10000,
        })
        const result = res.result || []
        const stats = {
          pending: { cpu: 0, ram: 0, hd: 0 },
          recycled: { cpu: 0, ram: 0, hd: 0 },
          confirming: { cpu: 0, ram: 0, hd: 0 },
        }
        const counts = { total: 0, pending: 0, recycled: 0, confirming: 0 }

        result.forEach((item) => {
          const statusKey = this.statusKeyMap(item.delstatus)
          counts.total++
          counts[statusKey]++
          stats[statusKey].cpu += Number(item.cpu_count) || 0
          stats[statusKey].ram += Number(item.ram_size) || 0
          stats[statusKey].hd += Number(item.hd_size) || 0
        })

        this.countStats = counts
        this.resourceStats = stats
      } catch (e) {
        console.error('Failed to fetch resource stats:', e)
      }
    },
    async fetchTableData() {
      this.tableLoading = true
      try {
        let q = '_type:' + this.delserverTypeId
        if (this.filterDelstatus) {
          q += ',delstatus:' + this.filterDelstatus
        }
        if (this.searchKeyword) {
          q += ',*' + this.searchKeyword + '*'
        }

        const res = await searchCI({
          q,
          count: this.pagination.pageSize,
          page: this.pagination.current,
          sort: this.sortBy,
        })
        this.tableData = (res.result || []).map((item) => ({
          ...item,
          key: item._id,
        }))
        this.pagination.total = res.numfound || 0
      } catch (e) {
        console.error('Failed to fetch table data:', e)
      } finally {
        this.tableLoading = false
      }
    },
    handleFilterChange() {
      this.pagination.current = 1
      this.fetchTableData()
    },
    handleSearch() {
      this.pagination.current = 1
      this.fetchTableData()
    },
    handleTableChange(pagination, filters, sorter) {
      this.pagination.current = pagination.current
      this.pagination.pageSize = pagination.pageSize
      if (sorter.field) {
        this.sortBy = sorter.order === 'descend' ? '-' + sorter.field : sorter.field
      }
      this.fetchTableData()
    },
    showDetail(record) {
      this.detailData = record
      this.detailVisible = true
    },
    getDelstatusColor(status) {
      const colorMap = { '待回收': 'orange', '已回收': 'green', '待确认': 'red' }
      return colorMap[status] || 'blue'
    },
    onSelectChange(selectedRowKeys) {
      this.selectedRowKeys = selectedRowKeys
    },
    handleCancelRecycle() {
      const that = this
      this.$confirm({
        title: that.$t('warning'),
        content: that.$t('cmdb.ci.cancelRecycleConfirm', { count: that.selectedRowKeys.length }),
        okType: 'danger',
        onOk() {
          cancelRecycleCI(that.selectedRowKeys.join(','))
            .then((res) => {
              if (res.failed > 0 || res.errors.length > 0) {
                const errorMessages = res.errors.map(e => `CI ${e.ci_id}: ${e.error}`).join('\n')
                that.$notification.warning({
                  key: 'cancelRecycle',
                  message: that.$t('cmdb.ci.cancelRecyclePartialSuccess'),
                  description: that.$t('cmdb.ci.cancelRecycleResult', {
                    success: res.success,
                    failed: res.failed,
                  }) + (errorMessages ? '\n' + errorMessages : ''),
                  duration: 0,
                })
              } else {
                that.$message.success(that.$t('cmdb.ci.cancelRecycleSuccess', { count: res.success }))
              }
              that.selectedRowKeys = []
              that.fetchResourceStats()
              that.fetchTableData()
            })
            .catch((error) => {
              that.$message.error(error.response?.data?.message || that.$t('cmdb.ci.cancelRecycleFailed'))
            })
        },
      })
    },
  },
}
</script>

<style lang="less" scoped>
.cmdb-recycle {
  padding: 16px;
  background-color: #fff;
  border-radius: @border-radius-box;
  height: calc(100vh - 64px);
  overflow: auto;

  &-header {
    margin-bottom: 16px;
  }

  &-title {
    font-size: 18px;
    font-weight: 600;
    color: @text-color_1;
  }

  &-stats {
    margin-bottom: 16px;
  }

  &-count-stats {
    margin-bottom: 16px;
  }

  &-stat-card {
    text-align: center;
  }

  &-status-card {
    text-align: center;
  }

  &-stat-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid #f0f0f0;

    &:last-child {
      border-bottom: none;
    }
  }

  &-stat-label {
    font-size: 14px;
    color: #666;
  }

  &-stat-value {
    font-size: 18px;
    font-weight: 600;
  }

  &-toolbar {
    display: flex;
    justify-content: space-between;
    margin-bottom: 16px;
  }
}
</style>
