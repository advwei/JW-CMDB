import hashlib
import os

import openpyxl
import requests
from urllib.parse import urlparse

URL = "http://10.0.0.0:8000/api/v0.1/ci"
SEARCH_URL = "{}/s".format(URL)
KEY = ""
SECRET = ""
EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ip_import_temp.xlsx")


def build_api_key(path, params):
    values = "".join([str(params[k]) for k in sorted((params or {}).keys())
                      if k not in ("_key", "_secret") and not isinstance(params[k], (dict, list))])
    _secret = "".join([path, SECRET, values]).encode("utf-8")
    params["_secret"] = hashlib.sha1(_secret).hexdigest()
    params["_key"] = KEY

    return params


def add_ci(payload):
    payload = build_api_key(urlparse(URL).path, payload)

    return requests.post(URL, json=payload).json()


def update_ci(payload, ci_id=None):
    url = "{url}/{ci_id}".format(url=URL, ci_id=ci_id) if ci_id is not None else URL

    payload = build_api_key(urlparse(url).path, payload)

    return requests.put(url, json=payload).json()


def delete_ci(ci_id):
    url = "{url}/{ci_id}".format(url=URL, ci_id=ci_id)

    payload = build_api_key(urlparse(url).path, {})

    return requests.delete(url, json=payload).json()


def get_ci(payload):
    payload = build_api_key(urlparse(URL).path, payload)

    return requests.get(URL, params=payload).json()


def search_ci(payload):
    payload = build_api_key(urlparse(SEARCH_URL).path, payload)

    return requests.get(SEARCH_URL, params=payload).json()


def read_excel_ip_usage(excel_path):
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb.active
    ip_usage_map = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        ip = row[0]
        usage = row[1]
        if ip is not None and usage is not None:
            ip_usage_map[str(ip).strip()] = str(usage).strip()
    wb.close()
    return ip_usage_map


if __name__ == "__main__":
    ip_usage_map = read_excel_ip_usage(EXCEL_PATH)
    print("从 Excel 读取到 {} 条 IP->Usage 映射".format(len(ip_usage_map)))

    payload = {
        "q": "_type:41,is_used:1,assign_status:0",
        "count": 100000,
        "page": 1,
    }
    result = search_ci(payload)
    ci_list = result.get("result", [])
    print("从接口获取到 {} 条已分配 IP 记录".format(len(ci_list)))

    success = 0
    failed = 0
    for ci in ci_list:
        ip = ci.get("name", "")
        ci_id = ci.get("_id")
        if ip in ip_usage_map:
            usage_val = ip_usage_map[ip]
            resp = update_ci({"usage": usage_val}, ci_id=ci_id)
            if "ci_id" in resp and resp.get("code") != 400:
                print("[OK]   IP: {} -> usage: {} (ci_id={})".format(ip, usage_val, ci_id))
                success += 1
            else:
                print("[FAIL] IP: {} -> usage: {} (ci_id={}) - {}".format(ip, usage_val, ci_id, resp))
                failed += 1

    print("\n完成！成功: {}, 失败: {}".format(success, failed))