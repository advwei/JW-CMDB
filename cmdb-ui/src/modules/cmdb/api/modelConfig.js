import { axios } from '@/utils/request'

const urlPrefix = '/v0.1'

export function getModelConfig() {
  return axios({
    url: urlPrefix + '/model/config',
    method: 'GET',
  })
}

export function saveModelConfig(data) {
  return axios({
    url: urlPrefix + '/model/config',
    method: 'POST',
    data,
  })
}
