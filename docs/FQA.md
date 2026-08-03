# 1. inner加密
 ## 初始化
 ```bash
docker exec -it cmdb-api sh
flask cmdb-inner-secrets-init
 ```
初始化成功之后终端会输出五个解封密钥(unseal key)和一个根密钥(root token)，需要手动将这些密钥保存下来放在安全的地方，以便后面安全地使用, 否则会导致后续无法解封秘钥，从而使密码功能不可用。

最简单的做法是在api容器里的配置文件settings.py 的配置项INNER_TRIGGER_TOKEN 填上root token 然后重启api服务即可。

# 2. 前端查看密码报错
如果初始化的时候没有完整显示根密钥且密码已经被inner加密

  ## 2.1 进入cmdb-api删除旧密钥
```bash
docker exec -it cmdb-api sh 
```

```python
python -c "
from api.app import create_app
app = create_app()
with app.app_context():
    from api.models.cmdb import InnerKV
    from api.extensions import db
    keys_to_delete = ['root_key', 'encrypt_key', 'root_key_salt', 'encrypt_key_salt']
    for k in keys_to_delete:
        count = InnerKV.query.filter_by(key=k).delete()
        db.session.commit()
        print(f'{k}: deleted {count} row(s)')
"
```

  ## 2.2 删除redis缓存

```bash
docker exec -it cmdb-cache bash
redis-cli -h cmdb-cache DEL "CMDB::cmdb::secret::seal_status"
redis-cli -h cmdb-cache DEL "CMDB::cmdb::secret::secrets_share"
```
  ## 2.3 重新初始化密钥

```bash
docker exec -it cmdb-api \
env CMDB_SHOW_ROOT_TOKEN_ON_INIT=true \
flask cmdb-inner-secrets-init
```

  ## 2.4 清空旧密码值

```mysql
# 确认数量
SELECT a.id, a.name, a.alias, COUNT(v.id) as value_count 
   FROM c_attributes a 
   LEFT JOIN c_value_texts v ON v.attr_id = a.id 
   WHERE a.is_password = 1 
   GROUP BY a.id, a.name, a.alias;
# 清空历史密码，前端重新输入
UPDATE c_value_texts SET value = '' WHERE attr_id = <上一步查到的ID>;
```

# 3. 创建Ansible数据表
如果Ansible执行日志页面报错，可能是缺失数的Ansible的表：c_ansible_executions、c_ansible_execution_details

```sql
#cmdb-db容器新增挂载
cd /opt/cmdb_ts
vi docker-compose.yml

#编辑cmdb-db容器volumes:
- ./docs/ansible_tables.sql:/docker-entrypoint-initdb.d/ansible_tables.sql

#重启容器
docker compose up -d cmdb-db

#进入数据库容器
docker exec -it cmdb-api sh

#更新sql命令
mysql -u root -p cmdb < docs/ansible_tables.sql
```