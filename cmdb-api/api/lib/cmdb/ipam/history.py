# -*- coding:utf-8 -*-

import logging
import traceback

from flask_login import current_user

from api.lib.cmdb.ipam.const import IPAddressAssignStatus
from api.lib.cmdb.ipam.const import IPAddressBuiltinAttributes
from api.lib.mixin import DBMixin
from api.models.cmdb import IPAMOperationHistory
from api.models.cmdb import IPAMSubnetScan
from api.models.cmdb import IPAMSubnetScanHistory


class OperateHistoryManager(DBMixin):
    cls = IPAMOperationHistory

    def _can_add(self, **kwargs):
        kwargs['uid'] = current_user.uid

        return kwargs

    def _can_update(self, **kwargs):
        pass

    def _can_delete(self, **kwargs):
        pass


class ScanHistoryManager(DBMixin):
    cls = IPAMSubnetScanHistory

    def _can_add(self, **kwargs):
        return kwargs

    def add(self, **kwargs):
        is_used = kwargs.pop('is_used', None)
        ci_id = kwargs.pop('ci_id', None)
        ips = kwargs.pop('ips', None)
        offline_ips = kwargs.pop('offline_ips', None)
        skip_assign_status = str(kwargs.pop('skip_assign_status', '')).lower() in ('true', '1')

        # Keep only valid model columns — this is the authoritative filter
        # that prevents any non-model field (is_used, _key, _secret, etc.) from
        # reaching IPAMSubnetScanHistory.create()
        valid_columns = self.cls.get_columns()
        model_kwargs = {k: v for k, v in kwargs.items() if k in valid_columns}
        if ips is not None:
            model_kwargs['ips'] = ips

        # Save scan history record first
        try:
            existed = self.cls.get_by(exec_id=model_kwargs.get('exec_id'), first=True, to_dict=False)
            if existed is None:
                self.cls.create(**model_kwargs)
            else:
                existed.update(**model_kwargs)
            logging.info("Saved scan history: exec_id=%s, cidr=%s", model_kwargs.get('exec_id'), model_kwargs.get('cidr'))
        except Exception as e:
            logging.error("Failed to save scan history: %s\n%s", e, traceback.format_exc())

        # Assign online IPs to subnet
        if ips:
            from api.lib.cmdb.ipam.address import IpAddressManager
            ip_kwargs = {}
            if not skip_assign_status:
                ip_kwargs[IPAddressBuiltinAttributes.ASSIGN_STATUS] = IPAddressAssignStatus.ASSIGNED
            if str(is_used or '0') in ('1', 'true', 'True'):
                ip_kwargs[IPAddressBuiltinAttributes.IS_USED] = 1
            try:
                IpAddressManager().assign_ips(ips, ci_id, model_kwargs.get('cidr'), **ip_kwargs)
                logging.info("Assigned %d IPs to subnet %s", len(ips), ci_id)
            except Exception as e:
                logging.error("Failed to assign IPs for subnet %s: %s\n%s", ci_id, e, traceback.format_exc())

        # Mark offline IPs as not used (only is_used, do not change assign_status)
        if offline_ips:
            from api.lib.cmdb.ipam.address import IpAddressManager
            try:
                IpAddressManager().assign_ips(
                    offline_ips, ci_id, model_kwargs.get('cidr'),
                    **{IPAddressBuiltinAttributes.IS_USED: 0})
                logging.info("Marked %d IPs offline for subnet %s", len(offline_ips), ci_id)
            except Exception as e:
                logging.error("Failed to mark offline IPs for subnet %s: %s\n%s", ci_id, e, traceback.format_exc())

        # Update last_scan_time
        if ips or offline_ips:
            try:
                scan_rule = IPAMSubnetScan.get_by(ci_id=ci_id, first=True, to_dict=False)
                if scan_rule is not None:
                    scan_rule.update(last_scan_time=model_kwargs.get('start_at'))
            except Exception as e:
                logging.error("Failed to update last_scan_time for subnet %s: %s", ci_id, e)

        # Cleanup old records (keep last 100)
        try:
            for i in self.cls.get_by(only_query=True).order_by(self.cls.id.desc()).offset(100):
                i.delete()
        except Exception as e:
            logging.warning("Failed to cleanup old scan history: %s", e)

    def _can_update(self, **kwargs):
        pass

    def _can_delete(self, **kwargs):
        pass
