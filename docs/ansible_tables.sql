CREATE TABLE IF NOT EXISTS c_ansible_executions (
  id int(11) NOT NULL AUTO_INCREMENT,
  created_at datetime DEFAULT NULL,
  uid int(11) NOT NULL COMMENT '操作用户ID',
  playbook varchar(256) NOT NULL COMMENT '剧本名称',
  ci_ids json DEFAULT NULL COMMENT '目标CI列表',
  ci_count int(11) DEFAULT 0 COMMENT '目标数量',
  success_count int(11) DEFAULT 0 COMMENT '成功数量',
  failed_count int(11) DEFAULT 0 COMMENT '失败数量',
  status varchar(20) DEFAULT 'Running' COMMENT '状态: Running/Success/Failed/Partial',
  extra_params json DEFAULT NULL COMMENT '额外参数',
  PRIMARY KEY (id),
  KEY ix_c_ansible_executions_created_at (created_at),
  KEY ix_c_ansible_executions_uid (uid),
  KEY ix_c_ansible_executions_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

CREATE TABLE IF NOT EXISTS c_ansible_execution_details (
  id int(11) NOT NULL AUTO_INCREMENT,
  created_at datetime DEFAULT NULL,
  execution_id int(11) NOT NULL COMMENT '关联执行记录ID',
  ci_id int(11) NOT NULL COMMENT 'CI ID',
  ci_name varchar(256) DEFAULT NULL COMMENT '主机名',
  ip varchar(64) DEFAULT NULL COMMENT 'IP地址',
  status varchar(20) DEFAULT NULL COMMENT '状态: Success/Failed',
  
returncode int(11) DEFAULT NULL COMMENT '返回码',
  stdout text DEFAULT NULL COMMENT '标准输出',
  stderr text DEFAULT NULL COMMENT '错误输出',
  PRIMARY KEY (id),
  KEY ix_c_ansible_execution_details_execution_id (execution_id),
  KEY ix_c_ansible_execution_details_ci_id (ci_id),
  CONSTRAINT fk_ansible_detail_execution FOREIGN KEY (execution_id) REFERENCES c_ansible_executions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
