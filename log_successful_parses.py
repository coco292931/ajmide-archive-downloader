import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from downloader import _build_ajmide_headers, _build_programs_for_date, _load_program_schedules


# ============================
# 直接在这里修改运行配置（无需传参）
# ============================
START_DATE = "2014-9-22"
END_DATE = "2025-12-22"
OUTPUT_DIR = "logs"
CONFIG_PATH = "config.json"
READ_TIMEOUT_SECONDS = 5.0
REQUEST_INTERVAL_SECONDS = 0.1
CONNECT_TIMEOUT_SECONDS = 5.0


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
    try:
        response = requests.get(
            download_url,
            headers=headers,
            stream=True,
            allow_redirects=True,
            timeout=(CONNECT_TIMEOUT_SECONDS, read_timeout_seconds),
        )
        status_code = response.status_code
        response.close()

        if 200 <= status_code < 300:
            return True, f"成功({status_code})", headers
        if status_code == 403:
            return True, "成功(403-禁止访问，按成功记录)", headers
        return False, f"失败({status_code})", headers
    except requests.RequestException as exc:
        return False, f"失败({type(exc).__name__}: {exc})", headers


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
            if ok:
                total_success += 1
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

                month_records[month][day].append(
                    {
                        "file_name": file_name,
                        "program_time": program_time,
                        "parse_status": parse_status,
                        "download_url": download_url,
                        "request_header": header_text,
                    }
                )
                print(f"  成功: {file_name} | {parse_status}")
            else:
                total_failed += 1
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