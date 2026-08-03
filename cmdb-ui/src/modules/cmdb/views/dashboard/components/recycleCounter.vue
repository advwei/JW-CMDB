<template>
  <a-row :gutter="16">
    <a-col :span="12">
      <div id="recycle-counter-left" :style="{ height: '300px' }"></div>
    </a-col>
    <a-col :span="12">
      <div class="recycle-list">
        <div class="recycle-list-title">{{ $t('cmdb.ci.recentRecycleList') }}</div>
        <a-spin :spinning="listLoading">
          <div v-if="recycleList.length === 0" class="recycle-list-empty">
            {{ $t('noData') }}
          </div>
          <div v-else class="recycle-list-content">
            <div v-for="item in recycleList" :key="item._id" class="recycle-list-item">
              <a-tag :color="getDelstatusColor(item.delstatus)" size="small">
                {{ item.delstatus || '-' }}
              </a-tag>
              <span class="recycle-list-item-name">
                {{ item.private_ip || item.name || item._id }}
              </span>
              <span class="recycle-list-item-time">
                {{ item.updated_at || item.created_at || '-' }}
              </span>
            </div>
          </div>
        </a-spin>
      </div>
    </a-col>
  </a-row>
</template>

<script>
import * as echarts from 'echarts'
import { searchCI } from '@/modules/cmdb/api/ci'
import { getModelConfig } from '@/modules/cmdb/api/modelConfig'

export default {
  name: 'RecycleCounter',
  data() {
    return {
      delserverTypeId: 54,
      chart: null,
      recycleData: {},
      recycleList: [],
      listLoading: false,
      chartLoading: false,
    }
  },
  mounted() {
    this.fetchData()
  },
  methods: {
    async fetchData() {
      this.chartLoading = true
      this.listLoading = true
      try {
        await this.loadModelConfig()
        await this.fetchRecycleStats()
        await this.fetchRecycleList()
      } catch (e) {
        console.error('Failed to fetch recycle data:', e)
      } finally {
        this.chartLoading = false
        this.listLoading = false
      }
    },
    async loadModelConfig() {
      try {
        const res = await getModelConfig()
        const config = res || {}
        this.delserverTypeId = config.delserver_type_id || 54
      } catch (e) {
        console.error('Failed to load model config:', e)
      }
    },
    async fetchRecycleStats() {
      try {
        const res = await searchCI({
          q: '_type:' + this.delserverTypeId,
          facet: ['delstatus'],
          count: 1,
        })
        const facetData = res.facet || {}
        const delstatusValues = facetData['delstatus'] || []

        this.recycleData = {}
        delstatusValues.forEach((item) => {
          const status = item[0] || 'unknown'
          this.recycleData[status] = item[1]
        })

        this.$nextTick(() => {
          this.setChart()
        })
      } catch (e) {
        console.error('Failed to fetch recycle stats:', e)
      }
    },
    async fetchRecycleList() {
      try {
        const res = await searchCI({
          q: '_type:' + this.delserverTypeId,
          sort: '-updated_at',
          count: 10,
        })
        this.recycleList = res.result || []
      } catch (e) {
        console.error('Failed to fetch recycle list:', e)
      }
    },
    setChart() {
      const el = document.getElementById('recycle-counter-left')
      if (!el) return

      if (!this.chart) {
        this.chart = echarts.init(el)
      }

      const labels = Object.keys(this.recycleData)
      const values = Object.values(this.recycleData)

      if (labels.length === 0) {
        this.chart.clear()
        return
      }

      const colorMap = {
        '待回收': '#faad14',
        '已回收': '#52c41a',
        '待确认': '#ff4d4f',
      }

      const colors = labels.map((label) => colorMap[label] || '#1890ff')

      this.chart.setOption({
        color: colors,
        grid: {
          left: 0,
          right: 0,
          top: 50,
          bottom: 0,
          containLabel: true,
        },
        tooltip: {
          trigger: 'item',
        },
        xAxis: {
          type: 'category',
          data: labels,
          axisLabel: {
            fontSize: 10,
          },
        },
        yAxis: {
          type: 'value',
          axisLine: {
            show: false,
          },
        },
        series: [
          {
            data: values,
            type: 'bar',
            barWidth: '40%',
            label: {
              show: true,
              position: 'top',
            },
          },
        ],
      })
    },
    getDelstatusColor(status) {
      const colorMap = {
        '待回收': 'orange',
        '已回收': 'green',
        '待确认': 'red',
      }
      return colorMap[status] || 'blue'
    },
  },
}
</script>

<style lang="less" scoped>
.recycle-list {
  height: 300px;
  display: flex;
  flex-direction: column;

  &-title {
    font-size: 14px;
    font-weight: 500;
    color: #333;
    margin-bottom: 12px;
  }

  &-empty {
    text-align: center;
    padding-top: 80px;
    color: #999;
  }

  &-content {
    flex: 1;
    overflow-y: auto;
  }

  &-item {
    display: flex;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;

    &:last-child {
      border-bottom: none;
    }

    &-name {
      flex: 1;
      margin-left: 8px;
      font-size: 13px;
      color: #333;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    &-time {
      font-size: 12px;
      color: #999;
      margin-left: 8px;
      flex-shrink: 0;
    }
  }
}
</style>
