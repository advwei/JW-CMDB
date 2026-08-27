# -*- coding:utf-8 -*-

import ipaddress
import logging

import redis_lock
from flask import abort

from api.extensions import rd
from api.lib.cmdb.cache import CITypeCache
from api.lib.cmdb.ci import CIManager
from api.lib.cmdb.ci import CIRelationManager
from api.lib.cmdb.const import BuiltinModelEnum
from api.lib.cmdb.ipam.const import IPAddressAssignStatus
from api.lib.cmdb.ipam.const import IPAddressBuiltinAttributes
from api.lib.cmdb.ipam.const import OperateTypeEnum
from api.lib.cmdb.ipam.const import SubnetBuiltinAttributes
from api.lib.cmdb.ipam.history import OperateHistoryManager
from api.lib.cmdb.resp_format import ErrFormat
from api.lib.cmdb.search.ci.db.search import Search as SearchFromDB
from api.lib.cmdb.search.ci_relation.search import Search as RelationSearch


class IpAddressManager(object):
    def __init__(self):
        self.ci_type = CITypeCache.get(BuiltinModelEnum.IPAM_ADDRESS) or abort(
            404, ErrFormat.ipam_address_model_not_found.format(BuiltinModelEnum.IPAM_ADDRESS))

        self.type_id = self.ci_type.id

    @staticmethod
    def list_ip_address(parent_id):
        numfound, _, result = CIRelationManager.get_second_cis(parent_id, per_page="all")

        subnet = CIManager.get_ci_by_id(parent_id, need_children=False)
        cidr = subnet.get(SubnetBuiltinAttributes.CIDR) if subnet else None
        if cidr:
            result = IpAddressManager._merge_unrelated_addresses(parent_id, cidr, result)
            numfound = len(result)

        return numfound, result

    @staticmethod
    def _merge_unrelated_addresses(parent_id, cidr, result):
        """Return ``result`` augmented with ipam_address CIs whose IP falls inside
        ``cidr`` but are not linked to the subnet via relation.

        This is intentionally READ-ONLY: it must not mutate data. Repairing the
        missing relations is done out-of-band by
        :meth:`repair_missing_address_relations` (run once after a data import /
        upgrade), not on every GET.

        Matching is done on the *parsed* IP object, so addresses whose ``ip`` was
        stored in a non-canonical form (e.g. zero-padded, trailing ``/32``) still
        line up with the subnet's host list instead of being treated as free.
        """
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return result

        related_ip_map = {ci.get(IPAddressBuiltinAttributes.IP): ci for ci in result
                          if ci and ci.get(IPAddressBuiltinAttributes.IP)}
        if not related_ip_map:
            return result

        def _norm(ip):
            try:
                return ipaddress.ip_address(ip)
            except ValueError:
                return None

        # Read-only scan of all ipam_address; match by parsed IP against the
        # subnet so format differences in the stored ``ip`` cannot hide orphans.
        response, _, _, _, _, _ = SearchFromDB(
            "_type:{}".format(BuiltinModelEnum.IPAM_ADDRESS),
            count=1000000, parent_node_perm_passed=True).search()

        seen = set(related_ip_map.keys())
        missing = []
        for ci in response:
            ip = ci.get(IPAddressBuiltinAttributes.IP)
            if not ip or ip in seen:
                continue
            nip = _norm(ip)
            if nip is None or nip not in network:
                continue
            seen.add(ip)
            missing.append(ci)
        return result + missing

    @staticmethod
    def repair_missing_address_relations():
        """One-time repair for historical ipam_address CIs that exist but are not
        linked to their subnet via relation (e.g. created by older import / scan
        code). Returns the number of relations created.

        Run via the ``cmdb-repair-ipam-relations`` CLI command.
        """
        addresses, _, _, _, _, _ = SearchFromDB(
            "_type:{}".format(BuiltinModelEnum.IPAM_ADDRESS),
            count=1000000, parent_node_perm_passed=True).search()

        # Normalize stored `ip` values to canonical form. Orphaned/free display is
        # caused by addresses whose `ip` was written in a non-canonical format
        # (zero-padded, trailing /32, etc.) which never matches the subnet's host
        # list. Rewriting them makes the frontend merge and exact-match queries line
        # up. Key the lookup by parsed IP so matching is format-agnostic.
        ip2addr = {}
        for ci in addresses:
            ip = ci.get(IPAddressBuiltinAttributes.IP)
            if not ip:
                continue
            try:
                norm_ip = str(ipaddress.ip_address(ip))
            except ValueError:
                ip2addr[ip] = ci
                continue
            if norm_ip != ip:
                try:
                    CIManager().update(ci['_id'], _sync=True,
                                      **{IPAddressBuiltinAttributes.IP: norm_ip})
                except Exception as e:
                    logging.warning(
                        "Failed to normalize IPAM address ip ci=%s: %s", ci.get('_id'), e)
            ip2addr[ipaddress.ip_address(norm_ip)] = ci

        subnets, _, _, _, _, _ = SearchFromDB(
            "_type:{}".format(BuiltinModelEnum.IPAM_SUBNET),
            count=1000000, parent_node_perm_passed=True).search()

        num_fixed = 0
        for sub in subnets:
            cidr = sub.get(SubnetBuiltinAttributes.CIDR)
            if not cidr:
                continue
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue

            _, _, related = CIRelationManager.get_second_cis(sub['_id'], per_page='all')
            related_ips = set()
            for ci in related:
                rip = ci.get(IPAddressBuiltinAttributes.IP)
                if not rip:
                    continue
                try:
                    related_ips.add(str(ipaddress.ip_address(rip)))
                except ValueError:
                    related_ips.add(rip)
            for host in network.hosts():
                host_str = str(host)
                if host_str in related_ips:
                    continue
                addr = ip2addr.get(ipaddress.ip_address(host_str)) or ip2addr.get(host_str)
                if addr is None:
                    continue
                try:
                    IpAddressManager._add_relation(sub['_id'], addr['_id'])
                    num_fixed += 1
                except Exception as e:
                    logging.warning(
                        "Failed to repair IPAM relation subnet=%s address=%s: %s",
                        sub['_id'], addr['_id'], e)
        return num_fixed

    def _get_cis(self, subnet_id, ips):

        q = "_type:{},{}:({})".format(self.type_id, IPAddressBuiltinAttributes.IP, ";".join(ips or []))

        response, _, _, _, _, _ = RelationSearch([subnet_id], level=[1], query=q, count=1000000).search()

        return response

    @staticmethod
    def _add_relation(parent_id, child_id):
        if not parent_id or not child_id:
            return

        CIRelationManager().add(parent_id, child_id, valid=False, apply_async=False)

    @staticmethod
    def calc_used_count(subnet_id):
        q = "{}:true".format(IPAddressBuiltinAttributes.IS_USED)

        return len(set(RelationSearch([subnet_id], level=[1], query=q, count=1000000).search(only_ids=True) or []))

    @staticmethod
    def _calc_assign_count(subnet_id):
        q = "{}:(0;2)".format(IPAddressBuiltinAttributes.ASSIGN_STATUS)

        return len(set(RelationSearch([subnet_id], level=[1], query=q, count=1000000).search(only_ids=True) or []))

    def _update_subnet_count(self, subnet_id, assign_count_computed, used_count=None):
        payload = {}

        cur = CIManager.get_ci_by_id(subnet_id, need_children=False)
        hosts_count = cur.get(SubnetBuiltinAttributes.HOSTS_COUNT, 0)
        assign_count = self._calc_assign_count(subnet_id)

        if assign_count_computed:
            payload[SubnetBuiltinAttributes.ASSIGN_COUNT] = assign_count
        if used_count is not None:
            payload[SubnetBuiltinAttributes.USED_COUNT] = used_count

        payload[SubnetBuiltinAttributes.FREE_COUNT] = hosts_count - assign_count
        CIManager().update(subnet_id, **payload)

    def assign_ips(self, ips, subnet_id, cidr, **kwargs):
        """

        :param ips: ip list
        :param subnet_id: subnet id
        :param cidr: subnet cidr
        :param kwargs: other attributes for ip address
        :return:
        """
        if subnet_id is not None:
            subnet = CIManager.get_ci_by_id(subnet_id)
        else:
            cis, _, _, _, _, _ = SearchFromDB("_type:{},{}:{}".format(
                BuiltinModelEnum.IPAM_SUBNET, SubnetBuiltinAttributes.CIDR, cidr),
                parent_node_perm_passed=True).search()
            if cis:
                subnet = cis[0]
                subnet_id = subnet['_id']
            else:
                return abort(400, ErrFormat.ipam_address_model_not_found)

        with (redis_lock.Lock(rd.r, "IPAM_ASSIGN_ADDRESS_{}".format(subnet_id),
                              expire=60, auto_renewal=True)):
            cis = self._get_cis(subnet_id, ips)
            ip2ci = {}
            for ci in cis:
                cip = ci.get(IPAddressBuiltinAttributes.IP)
                if cip:
                    try:
                        ip2ci[str(ipaddress.ip_address(cip))] = ci
                    except ValueError:
                        ip2ci[cip] = ci

            ci_ids = []
            for ip in ips:
                try:
                    norm_ip = str(ipaddress.ip_address(ip))
                except ValueError:
                    norm_ip = ip
                kwargs['name'] = norm_ip
                kwargs[IPAddressBuiltinAttributes.IP] = norm_ip
                if ip not in ip2ci:
                    ci_id = CIManager.add(self.type_id, _sync=True, **kwargs)
                else:
                    ci_id = ip2ci[ip]['_id']
                    CIManager().update(ci_id, _sync=True, **kwargs)
                ci_ids.append(ci_id)

                self._add_relation(subnet_id, ci_id)

            if ips and IPAddressBuiltinAttributes.ASSIGN_STATUS in kwargs:
                used_count_val = None
                if IPAddressBuiltinAttributes.IS_USED in kwargs:
                    q = "{}:true".format(IPAddressBuiltinAttributes.IS_USED)
                    cur_used = RelationSearch([subnet_id], level=[1], query=q,
                                              count=1000000).search(only_ids=True) or []
                    used_count_val = len(cur_used)
                self._update_subnet_count(subnet_id, True, used_count=used_count_val)

        if kwargs.get(IPAddressBuiltinAttributes.ASSIGN_STATUS) in (
                IPAddressAssignStatus.ASSIGNED, IPAddressAssignStatus.RESERVED):
            OperateHistoryManager().add(operate_type=OperateTypeEnum.ASSIGN_ADDRESS,
                                        cidr=subnet.get(SubnetBuiltinAttributes.CIDR),
                                        description=" | ".join(ips))

        elif kwargs.get(IPAddressBuiltinAttributes.ASSIGN_STATUS) == IPAddressAssignStatus.UNASSIGNED:
            OperateHistoryManager().add(operate_type=OperateTypeEnum.REVOKE_ADDRESS,
                                        cidr=subnet.get(SubnetBuiltinAttributes.CIDR),
                                        description=" | ".join(ips))
