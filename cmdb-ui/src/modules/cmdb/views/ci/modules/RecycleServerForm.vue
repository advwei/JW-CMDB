<template>
  <CustomDrawer
    :closable="true"
    :title="$t('cmdb.ci.recycleHeader')"
    :visible="drawerVisible"
    @close="onClose"
    placement="right"
    width="500"
    :bodyStyle="{ paddingTop: '20px' }"
  >
    <div class="custom-drawer-bottom-action">
      <a-button @click="onClose">{{ $t('cancel') }}</a-button>
      <a-button type="primary" @click="handleSubmit" :loading="loading">
        {{ $t('cmdb.ci.recycle') }}
      </a-button>
    </div>
    <a-form :form="form" :style="{ paddingTop: '20px' }">
      <a-alert
        type="warning"
        showIcon
        :style="{ marginBottom: '16px' }"
      >
        <template #message>
          {{ $t('cmdb.ci.recycleWarning') }}
        </template>
      </a-alert>
      <a-form-item :label="$t('cmdb.ci.selectCount')">
        <a-tag color="blue">{{ ciIds.length }} {{ $t('cmdb.ci.serverUnits') }}</a-tag>
      </a-form-item>
      <a-form-item :label="$t('cmdb.ci.delstatus')" required>
        <a-select
          v-decorator="['delstatus', { initialValue: '待回收', rules: [{ required: true, message: $t('cmdb.ci.delstatusRequired') }] }]"
          :placeholder="$t('cmdb.ci.delstatusPlaceholder')"
        >
          <a-select-option value="待回收">{{ $t('cmdb.ci.delstatusPending') }}</a-select-option>
          <a-select-option value="已回收">{{ $t('cmdb.ci.delstatusRecycled') }}</a-select-option>
          <a-select-option value="待确认">{{ $t('cmdb.ci.delstatusConfirming') }}</a-select-option>
        </a-select>
      </a-form-item>
    </a-form>
  </CustomDrawer>
</template>

<script>
import { recycleCI } from '@/modules/cmdb/api/ci'

export default {
  name: 'RecycleServerForm',
  props: {
    ciIds: {
      type: Array,
      default: () => [],
    },
  },
  data() {
    return {
      form: this.$form.createForm(this),
      drawerVisible: false,
      loading: false,
    }
  },
  methods: {
    onOpen() {
      this.drawerVisible = true
    },
    onClose() {
      this.drawerVisible = false
      this.form.resetFields()
    },
    handleSubmit() {
      this.form.validateFields((err, values) => {
        if (!err) {
          const that = this
          this.$confirm({
            title: that.$t('warning'),
            content: that.$t('cmdb.ci.recycleConfirm', { count: that.ciIds.length }),
            okType: 'danger',
            onOk() {
              that.loading = true
              recycleCI(that.ciIds.join(','), values.delstatus)
                .then((res) => {
                  if (res.failed > 0 || res.errors.length > 0) {
                    const getErrorPrefix = (type) => {
                      if (type === 'jumpserver_delete') return that.$t('cmdb.ci.jumpserverDeleteFailed')
                      if (type === 'ip_release') return that.$t('cmdb.ci.ipReleaseFailed')
                      return that.$t('cmdb.ci.recycleFailed')
                    }
                    const errorMessages = res.errors.map(e => {
                      return `CI ${e.ci_id}: ${getErrorPrefix(e.type)} - ${e.error}`
                    }).join('\n')
                    that.$notification.warning({
                      key: 'recycle',
                      message: that.$t('cmdb.ci.recyclePartialSuccess'),
                      description: that.$t('cmdb.ci.recycleResult', {
                        success: res.success,
                        failed: res.failed,
                      }) + (errorMessages ? '\n' + errorMessages : ''),
                      duration: 0,
                    })
                  } else {
                    that.$message.success(that.$t('cmdb.ci.recycleSuccess', { count: res.success }))
                  }
                  that.drawerVisible = false
                  that.$emit('recycleDone')
                })
                .catch((error) => {
                  that.$message.error(error.response?.data?.message || that.$t('cmdb.ci.recycleFailed'))
                })
                .finally(() => {
                  that.loading = false
                })
            },
          })
        }
      })
    },
  },
}
</script>
