"""
遍历日志中“主链路200”记录对应的 CDN 可用性（仅探测，不落盘）。

脚本行为：
1. 从 LOGS_DIR 下的 *_successful_parses.txt 中筛选解析状态包含“成功(主链路200”的记录。
2. 对每条记录先请求主链路，再按 DEFAULT_RESOLVE_RULES 逐个请求候选 CDN IP。
3. 终端实时输出每次请求的状态码或异常，并在最后打印汇总统计。

输入：
- 日志文件中的行格式应包含：文件名 | ... | 解析状态 | 下载链接 | 请求头

输出：
- 仅标准输出（控制台），不生成或修改任何日志/数据文件。

运行方式：
    python .\tools\traverse_cdn_for_primary200.py

可在文件顶部直接调整：
- LOGS_DIR: 日志目录
- CONNECT_TIMEOUT_SECONDS / READ_TIMEOUT_SECONDS: 请求超时
- REQUEST_INTERVAL_SECONDS: 每次探测之间的间隔（秒）
- DEFAULT_RESOLVE_RULES: Host:Port:IP 的候选解析列表
- MAX_200_PER_RECORD: 单个节目内允许的 200 响应上限（超过后跳到下一个节目）
"""

import os
import time
from urllib.parse import urlparse, urlunparse

import requests


# ============================
# Edit runtime config here
# ============================
LOGS_DIR = "logs-all"
CONNECT_TIMEOUT_SECONDS = 2.0
READ_TIMEOUT_SECONDS = 2.0
REQUEST_INTERVAL_SECONDS = 0
MAX_200_PER_RECORD = 5

DEFAULT_RESOLVE_RULES = [
    "ia-bk-i.ajmide.com:80:58.42.59.184",
    "ia-bk-i.ajmide.com:80:42.202.165.200",
    "ia-bk-i.ajmide.com:80:123.54.203.56",
    "ia-bk-i.ajmide.com:80:113.142.216.120",
    "ia-bk-i.ajmide.com:80:113.142.216.125",
    "ia-bk-i.ajmide.com:80:113.142.215.168",
    "ia-bk-i.ajmide.com:80:1.81.2.203",
    "ia-bk-i.ajmide.com:80:36.99.200.7",
    "ia-bk-i.ajmide.com:80:42.202.165.210",
    "ia-bk-i.ajmide.com:80:1.62.64.108",
    "ia-bk-i.ajmide.com:80:111.48.68.139",
    "ia-bk-i.ajmide.com:80:117.162.10.168",
    "ia-bk-i.ajmide.com:80:117.162.11.24",
    "ia-bk-i.ajmide.com:80:117.163.57.175",
    "ia-bk-i.ajmide.com:80:117.163.57.178",
    "ia-bk-i.ajmide.com:80:117.163.57.248",
    "ia-bk-i.ajmide.com:80:119.167.147.74",
    "ia-bk-i.ajmide.com:80:123.12.235.104",
    "ia-bk-i.ajmide.com:80:123.12.235.56",
    "ia-bk-i.ajmide.com:80:123.12.235.57",
    "ia-bk-i.ajmide.com:80:123.6.104.170",
    "ia-bk-i.ajmide.com:80:123.6.25.125",
    "ia-bk-i.ajmide.com:80:180.129.181.100",
    "ia-bk-i.ajmide.com:80:222.138.7.59",
    "ia-bk-i.ajmide.com:80:223.109.219.175",
    "ia-bk-i.ajmide.com:80:36.151.204.170",
    "ia-bk-i.ajmide.com:80:42.225.102.124",
    "ia-bk-i.ajmide.com:80:42.225.102.95",
    "ia-bk-i.ajmide.com:80:61.161.1.110",
    "ia-bk-i.ajmide.com:80:61.243.14.100",
]


def parse_headers_string(header_str):
    headers = {}
    for pair in header_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def parse_resolve_rules(resolve_args):
    resolve_rules = {}
    if not resolve_args:
        return resolve_rules

    for raw_arg in resolve_args:
        for token in raw_arg.split(","):
            token = token.strip().strip('"').strip("'")
            if not token:
                continue

            parts = token.split(":")
            if len(parts) != 3:
                continue

            host = parts[0].strip().lower()
            port_str = parts[1].strip()
            ip = parts[2].strip()
            if not host or not port_str or not ip:
                continue

            try:
                port = int(port_str)
            except ValueError:
                continue

            key = (host, port)
            resolve_rules.setdefault(key, [])
            if ip not in resolve_rules[key]:
                resolve_rules[key].append(ip)

    return resolve_rules


def get_url_host_port(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed, host, port


def build_resolved_request(url, ip):
    parsed, host, port = get_url_host_port(url)
    original_port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80

    if original_port and original_port != default_port:
        host_header = f"{host}:{original_port}"
    else:
        host_header = host

    resolved_netloc = f"{ip}:{port}"
    resolved_url = urlunparse(parsed._replace(netloc=resolved_netloc))
    return resolved_url, host_header, parsed.scheme


def iter_primary_200_records(logs_dir):
    for filename in sorted(os.listdir(logs_dir)):
        if not filename.endswith("_successful_parses.txt"):
            continue

        log_path = os.path.join(logs_dir, filename)
        with open(log_path, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if (
                    not line
                    or "|" not in line
                    or line.startswith("===")
                    or line.startswith("文件名")
                    or line.startswith("---")
                    or line.startswith("#")
                ):
                    continue

                parts = [part.strip() for part in line.split("|", 4)]
                if len(parts) < 5:
                    continue

                file_name, _, parse_status, download_url, header_text = parts
                if "成功(主链路200" not in parse_status:
                    continue

                yield {
                    "file_name": file_name,
                    "parse_status": parse_status,
                    "download_url": download_url,
                    "header_text": header_text,
                    "source_log": filename,
                }


def probe_once(url, headers, scheme):
    response = requests.get(
        url,
        headers=headers,
        stream=True,
        allow_redirects=True,
        timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        verify=(scheme != "https"),
    )
    status_code = response.status_code
    response.close()
    return status_code


def main():
    if not os.path.exists(LOGS_DIR):
        print(f"Logs directory not found: {LOGS_DIR}")
        return

    resolve_rules = parse_resolve_rules(DEFAULT_RESOLVE_RULES)
    records = list(iter_primary_200_records(LOGS_DIR))

    if not records:
        print("No records with status containing '成功(主链路200' were found.")
        return

    print(f"Found {len(records)} records. Start traversing CDN...")

    total_requests = 0
    success_2xx = 0
    for index, record in enumerate(records, start=1):
        download_url = record["download_url"]
        headers = parse_headers_string(record["header_text"])
        parsed, host, port = get_url_host_port(download_url)
        candidate_ips = resolve_rules.get((host, port), [])
        status_200_count = 0

        print(f"\n[{index}/{len(records)}] {record['file_name']} | {record['source_log']}")
        print(f"  URL: {download_url}")

        # Probe primary URL first.
        try:
            status = probe_once(download_url, headers, parsed.scheme)
            total_requests += 1
            if 200 <= status < 300:
                success_2xx += 1
            if status == 200:
                status_200_count += 1
            print(f"  primary -> {status}")
        except requests.RequestException as exc:
            total_requests += 1
            print(f"  primary -> ERR:{type(exc).__name__}: {exc}")

        if status_200_count > MAX_200_PER_RECORD:
            print(f"  [skip] 200 响应次数 {status_200_count} > {MAX_200_PER_RECORD}，跳到下一个节目")
            continue

        # Traverse all configured CDN IPs for this host:port.
        for ip in candidate_ips:
            resolved_url, host_header, scheme = build_resolved_request(download_url, ip)
            resolved_headers = dict(headers)
            resolved_headers["Host"] = host_header
            try:
                status = probe_once(resolved_url, resolved_headers, scheme)
                total_requests += 1
                if 200 <= status < 300:
                    success_2xx += 1
                if status == 200:
                    status_200_count += 1
                print(f"  resolve {ip} -> {status}")
            except requests.RequestException as exc:
                total_requests += 1
                print(f"  resolve {ip} -> ERR:{type(exc).__name__}: {exc}")

            if status_200_count > MAX_200_PER_RECORD:
                print(f"  [skip] 200 响应次数 {status_200_count} > {MAX_200_PER_RECORD}，跳到下一个节目")
                break

            if REQUEST_INTERVAL_SECONDS > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS)

    print("\nDone.")
    print(f"Total probe records: {len(records)}")
    print(f"Total HTTP requests: {total_requests}")
    print(f"Total 2xx responses: {success_2xx}")


if __name__ == "__main__":
    main()
