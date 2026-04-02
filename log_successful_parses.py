import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse

import requests

from downloader import _build_ajmide_headers, _build_programs_for_date, _load_program_schedules


# ============================
# 直接在这里修改运行配置（无需传参）
# ============================
START_DATE = "2022-4-1"
END_DATE = "2022-4-30"
OUTPUT_DIR = "logs-all"
CONFIG_PATH = "config.json"
READ_TIMEOUT_SECONDS = 5.0
REQUEST_INTERVAL_SECONDS = 0.05
CONNECT_TIMEOUT_SECONDS = 5.0

# 内置解析规则：当节目探测失败时，按顺序切换到下一个 IP 重试。
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


def _parse_resolve_rules(resolve_args):
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


def _get_url_host_port(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed, host, port


def _build_resolved_request(url, ip):
    parsed, host, port = _get_url_host_port(url)
    original_port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80

    if original_port and original_port != default_port:
        host_header = f"{host}:{original_port}"
    else:
        host_header = host

    resolved_netloc = f"{ip}:{port}"
    resolved_url = urlunparse(parsed._replace(netloc=resolved_netloc))
    return resolved_url, host_header, parsed.scheme


RESOLVE_RULES = _parse_resolve_rules(DEFAULT_RESOLVE_RULES)


def _parse_date(date_text):
    value = date_text.strip().lower()
    if value in ("now", "today"):
        return datetime.now()

    for fmt in ("%y-%m-%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"无效日期格式: {date_text}，请使用 YY-MM-DD 或 YYYY-MM-DD")


def _iter_date_range(start_dt, end_dt):
    step = 1 if end_dt >= start_dt else -1
    current = start_dt
    while (step == 1 and current <= end_dt) or (step == -1 and current >= end_dt):
        yield current
        current += timedelta(days=step)


def _format_program_time(start_time_ms):
    if not start_time_ms:
        return "未知"
    return datetime.fromtimestamp(start_time_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def _probe_url(download_url, read_timeout_seconds):
    headers = _build_ajmide_headers(download_url)

    def _run_probe(url, request_headers, scheme):
        response = requests.get(
            url,
            headers=request_headers,
            stream=True,
            allow_redirects=True,
            timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout_seconds),
            verify=(scheme != "https"),
        )
        status_code = response.status_code
        response.close()
        return status_code

    parsed, host, port = _get_url_host_port(download_url)
    print(f"探测 URL: {download_url}")
    candidate_ips = RESOLVE_RULES.get((host, port), [])

    try:
        primary_status = _run_probe(download_url, headers, parsed.scheme)
    except requests.RequestException as exc:
        return False, f"失败({type(exc).__name__}: {exc})", headers

    if 200 <= primary_status < 300:
        return True, "成功(主链路200)", headers

    if primary_status == 404:
        retry_results = []
        for ip in candidate_ips[:2]:
            resolved_url, host_header, scheme = _build_resolved_request(download_url, ip)
            resolved_headers = dict(headers)
            resolved_headers["Host"] = host_header
            try:
                status_code = _run_probe(resolved_url, resolved_headers, scheme)
            except requests.RequestException:
                continue

            retry_results.append(status_code)
            if 200 <= status_code < 300:
                return True, f"成功(404后切换命中200,{ip})", resolved_headers

        if retry_results and all(code == 404 for code in retry_results):
            return False, "失败(404-资源不存在)", headers
        return False, "失败(404-切换后仍不可用)", headers

    if primary_status == 403:
        success_ips = []
        for ip in candidate_ips:
            resolved_url, host_header, scheme = _build_resolved_request(download_url, ip)
            resolved_headers = dict(headers)
            resolved_headers["Host"] = host_header
            try:
                status_code = _run_probe(resolved_url, resolved_headers, scheme)
            except requests.RequestException:
                continue

            if 200 <= status_code < 300:
                success_ips.append(ip)

        if success_ips:
            return True, f"成功(200,[{','.join(success_ips)}])", headers
        return False, "失败(403-禁止访问)", headers

    return False, f"失败({primary_status})", headers


def _save_monthly_logs(month_records, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for month in sorted(month_records.keys()):
        month_file = os.path.join(output_dir, f"{month}_successful_parses.txt")
        with open(month_file, "w", encoding="utf-8") as f:
            f.write(f"# {month} 成功解析记录\n\n")
            for day in sorted(month_records[month].keys()):
                f.write(f"=== {day} ===\n")
                f.write("文件名 | 节目时间 | 解析状态 | 对应下载连接 | 请求头\n")
                f.write("-" * 120 + "\n")

                day_items = sorted(
                    month_records[month][day],
                    key=lambda x: x["program_time"],
                )
                for item in day_items:
                    f.write(
                        f"{item['file_name']} | {item['program_time']} | {item['parse_status']} | "
                        f"{item['download_url']} | {item['request_header']}\n"
                    )
                f.write("\n")


def run(start_date, end_date, output_dir, config_path, read_timeout_seconds, interval_seconds):
    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)

    program_schedules = _load_program_schedules(config_path)
    month_records = defaultdict(lambda: defaultdict(list))
    os.makedirs(output_dir, exist_ok=True)

    total_generated = 0
    total_success = 0
    total_failed = 0

    for date_obj in _iter_date_range(start_dt, end_dt):
        date_str = date_obj.strftime("%Y-%m-%d")
        print(f"处理日期: {date_str}")

        program_list = _build_programs_for_date(date_obj, program_schedules)
        if not program_list:
            print(f"  无节目: {date_str}")
            continue

        for program in program_list:
            total_generated += 1
            download_url = program.get("downloadUrl") or program.get("playUrlHigh")
            if not download_url:
                total_failed += 1
                continue

            ok, parse_status, headers = _probe_url(download_url, read_timeout_seconds)

            parsed_path = urlparse(download_url).path
            file_name = os.path.basename(parsed_path) or "unknown_file"
            program_time = _format_program_time(program.get("startTime", 0))
            month = date_obj.strftime("%Y-%m")
            day = date_obj.strftime("%Y-%m-%d")

            header_text = (
                f"Host={headers.get('Host', '')}; "
                f"Authorization={headers.get('Authorization', '')}; "
                f"User-Agent={headers.get('User-Agent', '')}"
            )

            should_persist = ok or parse_status == "失败(403-禁止访问)"

            if should_persist:
                month_records[month][day].append(
                    {
                        "file_name": file_name,
                        "program_time": program_time,
                        "parse_status": parse_status,
                        "download_url": download_url,
                        "request_header": header_text,
                    }
                )

            if ok:
                total_success += 1
                print(f"  成功: {file_name} | {parse_status}")
            else:
                total_failed += 1
                if should_persist:
                    print(f"  失败已记录: {file_name} | {parse_status}")
                else:
                    print(f"  跳过失败: {download_url} | {parse_status}")

            if interval_seconds > 0:
                time.sleep(interval_seconds)

        # 每天处理完成后立即落盘，避免长任务期间看不到日志文件。
        _save_monthly_logs(month_records, output_dir)

    _save_monthly_logs(month_records, output_dir)
    print("\n任务完成")
    print(f"总节目数: {total_generated}")
    print(f"成功记录数(含403): {total_success}")
    print(f"失败数: {total_failed}")
    print(f"输出目录: {os.path.abspath(output_dir)}")


def main():
    run(
        start_date=START_DATE,
        end_date=END_DATE,
        output_dir=OUTPUT_DIR,
        config_path=CONFIG_PATH,
        read_timeout_seconds=READ_TIMEOUT_SECONDS,
        interval_seconds=REQUEST_INTERVAL_SECONDS,
    )


if __name__ == "__main__":
    main()