<template>
  <div class="cmdb-sync-asset">
    <div class="cmdb-sync-asset-header">
      <span class="cmdb-sync-asset-title">{{ $t('cmdb.menu.syncasset') }}</span>
      <a-space>
        <a-select
          :value="syncFilter"
          class="cmdb-sync-asset-filter"
          size="small"
          @change="(val) => { syncFilter = val; pagination.current = 1; loadData() }"
        >
          <a-select-option value="all">{{ $t('cmdb.ci.all') }}</a-select-option>
          <a-select-option value="synced">{{ $t('cmdb.ciType.onetermSync.synced') }}</a-select-option>
          <a-select-option value="not_synced">{{ $t('cmdb.ciType.onetermSync.notSynced') }}</a-select-option>
        </a-select>
        <a-input
          v-model="query"
          class="cmdb-sync-asset-search"
          size="small"
          placeholder="_type:vmserver"
          @pressEnter="pagination.current = 1; loadData()"
        >
          <a-icon slot="prefix" type="search" />
        </a-input>
        <a-button size="small" type="primary" ghost class="ops-button-ghost" @click="pagination.current = 1; loadData()">
          <a-icon type="reload" />
          {{ $t('refresh') }}
        </a-button>
        <a-button size="small" type="primary" ghost @click="$router.push('/cmdb/configcenter')">
          <a-icon type="setting" />
          {{ $t('cmdb.menu.configCenter') }}
        </a-button>
      </a-space>
    </div>

    <a-table
      size="small"
      rowKey="_id"
      :loading="loading"
      :columns="columns"
      :dataSource="data"
      :pagination="pagination"
      @change="handleTableChange"
    >
      <template #sync_status="text, record">
        <a-tag :color="getSyncAssetId(record) ? 'green' : 'orange'">
          {{ getSyncAssetId(record) ? $t('cmdb.ciType.onetermSync.synced') : $t('cmdb.ciType.onetermSync.notSynced') }}
        </a-tag>
      </template>
      <template #asset_id="text, record">
        <span>{{ getSyncAssetId(record) || '-' }}</span>
      </template>
    </a-table>
  </div>
</template>

<script>
import { searchCI } from '@/modules/cmdb/api/ci'

export default {
  name: 'SyncAsset',
  data() {
    return {
      loading: false,
      query: '_type:vmserver',
      syncFilter: 'all',
      data: [],
      pagination: {
        current: 1,
        pageSize: 50,
        total: 0,
        showSizeChanger: true,
        showTotal: (total) => `${this.$t('total')} ${total}`,
      },
      columns: [
        { title: 'CI ID', dataIndex: '_id', width: 90 },
        { title: this.$t('cmdb.ciType.onetermSync.syncStatus'), key: 'sync_status', scopedSlots: { customRender: 'sync_status' }, width: 120 },
        { title: 'Jumpserve ID', key: 'asset_id', scopedSlots: { customRender: 'asset_id' }, width: 160 },
        { title: this.$t('cmdb.ci.assetName'), dataIndex: 'assetname', ellipsis: true },
        { title: 'Hostname', dataIndex: 'hostname', ellipsis: true },
        { title: 'IP', dataIndex: 'private_ip', ellipsis: true },
        { title: 'OS', dataIndex: 'ostype', width: 120 },
        { title: this.$t('updateTime'), dataIndex: '_updated_at', width: 180 },
      ],
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    getSyncAssetId(record) {
      return record.jumpserver_id
    },
    buildQuery() {
      const baseQuery = this.query || '_type:vmserver'
      if (this.syncFilter === 'synced') {
        return `${baseQuery},jumpserver_id:*`
      } else if (this.syncFilter === 'not_synced') {
        return `${baseQuery},~jumpserver_id:*`
      }
      return baseQuery
    },
    async loadData() {
      this.loading = true
      try {
        const res = await searchCI({
          q: this.buildQuery(),
          page: this.pagination.current,
          count: this.pagination.pageSize,
        })
        this.data = res.result || []
        this.pagination = {
          ...this.pagination,
          total: res.numfound || 0,
        }
      } finally {
        this.loading = false
      }
    },
    handleTableChange(pagination) {
      this.pagination = {
        ...this.pagination,
        current: pagination.current,
        pageSize: pagination.pageSize,
      }
      this.loadData()
    },
  },
}
</script>

<style lang="less" scoped>
.cmdb-sync-asset {
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

  &-search {
    width: 320px;
  }

  &-filter {
    width: 120px;
  }
}
</style>
