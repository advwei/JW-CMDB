import { axios } from '@/utils/request'

const urlPrefix = '/v0.1'

export function getAnsibleConfig() {
  return axios({
    url: urlPrefix + '/ansible/config',
    method: 'GET',
  })
}

export function updateAnsibleConfig(data) {
  return axios({
    url: urlPrefix + '/ansible/config',
    method: 'POST',
    data,
  })
}

export function getAnsiblePlaybooks() {
  return axios({
    url: urlPrefix + '/ansible/playbooks',
    method: 'GET',
  })
}

export function ansibleSetupServer(ciId, data = {}, isShowMessage = false) {
  return axios({
    url: urlPrefix + `/ansible/setup-server/${ciId}`,
    method: 'POST',
    data,
    isShowMessage,
    timeout: 600000,
  })
}

export function ansibleBatchSetupServer(data = {}, isShowMessage = false) {
  return axios({
    url: urlPrefix + '/ansible/setup-server/batch',
    method: 'POST',
    data,
    isShowMessage,
    timeout: 600000,
  })
}

export function getAnsibleExecutions(params = {}) {
  return axios({
    url: urlPrefix + '/ansible/executions',
    method: 'GET',
    params,
  })
}

export function getAnsibleExecutionDetails(executionId) {
  return axios({
    url: urlPrefix + `/ansible/executions/${executionId}/details`,
    method: 'GET',
  })
}
