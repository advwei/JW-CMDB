"""Diagnostic script - run via: flask shell < diag.py"""
from api.extensions import db
from api.models.cmdb import CIType
from api.lib.cmdb.const import ResourceTypeEnum
from flask import current_app

print("=== USE_ACL:", current_app.config.get('USE_ACL'))

count = db.session.query(CIType).count()
print(f"=== CIType total count: {count}")

if hasattr(CIType, 'deleted'):
    active = db.session.query(CIType).filter(CIType.deleted.is_(False)).count()
    deleted = db.session.query(CIType).filter(CIType.deleted.is_(True)).count()
    nulls = db.session.query(CIType).filter(CIType.deleted.is_(None)).count()
    print(f"=== deleted=0: {active}, deleted=1: {deleted}, deleted=NULL: {nulls}")
    types = db.session.query(CIType).filter(CIType.deleted.is_(False)).limit(5).all()
else:
    types = db.session.query(CIType).limit(5).all()

print(f"=== Sample types ({len(types)}):")
for t in types:
    print(f"  id={t.id}, name={t.name}, deleted={getattr(t, 'deleted', 'N/A')}")

from api.lib.cmdb.ci_type import CITypeManager
result = CITypeManager.get_ci_types()
print(f"\n=== CITypeManager.get_ci_types() returned {len(result)} items")
if result:
    for r in result[:5]:
        print(f"  {r['id']}: {r['name']}")
else:
    print("  (empty)")

from api.lib.perm.acl.acl import ACLManager
from api.lib.perm.acl.acl import is_app_admin
from api.lib.perm.acl.cache import AppCache
from flask_login import current_user
import json

try:
    app = AppCache.get('cmdb')
    print(f"\n=== AppCache.get('cmdb'): {app and app.name}")
except Exception as e:
    print(f"\n=== AppCache.get('cmdb') ERROR: {e}")

try:
    print(f"\n=== current_user: {current_user}")
    admin = is_app_admin('cmdb')
    print(f"=== is_app_admin('cmdb'): {admin}")

    resources = set()
    if current_app.config.get('USE_ACL') and not admin:
        resources = set([i.get('name') for i in ACLManager().get_resources(ResourceTypeEnum.CI_TYPE)])
    print(f"=== ACL resources count: {len(resources)}")
    if resources:
        print(f"  sample: {list(resources)[:5]}")
except Exception as e:
    print(f"\n=== ACL check ERROR: {e}")
    import traceback
    traceback.print_exc()
