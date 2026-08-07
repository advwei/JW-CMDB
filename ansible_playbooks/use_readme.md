# 1. 剧本说明
setup_server.yml剧本是用于批量初始化Linux服务器配置的，包括修改主机名、修改 root 用户密码、修改 user 用户密码等操作如需其他功能可自己添加逻辑。

# 2. 使用说明
1. 将该剧本放到/opt/ansible/playbooks目录下
2. 在配置中心-Ansible设置- OS 凭证映射里，为每种操作系统配置一个初始密码，这个密码会被 setup_server.yml 剧本用于初始化主机密码

# 3. 逻辑说明
1. 当勾选资产点击Ansible自动化后，如果脚本是 setup_server.yml 且弹出框填了新密码时：
2. 主机清单的 ansible_password 改用配置中心-Ansible设置- OS 凭证映射里的初始密码（creds['ansible_password']）连接服务器；
3. 弹出框的新密码放到 new_password 传给剧本（用于改密）；
4. 其余情况
 - 非 setup_server.yml 或新密码为空取密码逻辑：密码字段从 vmserver 模型的密码字段读取。