import argparse
import json
import os
import re
import time
import requests

def load_config(config_path="config_example.json"):
    if os.path.exists("config.json"):
        config_path = "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    code_to_name = {}
    for program in config.get("program_schedules", []):
        code_to_name[program["code"]] = program["name"]
    return code_to_name

def parse_headers_string(header_str):
    headers = {}
    for pair in header_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            headers[k.strip()] = v.strip()
    return headers

def download_file(url, target_path, headers):
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            print(f"Downloading: {url}")
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            status_code = response.status_code
            if status_code == 403:
                print(f"  Got 403 Forbidden. Skipping.  403错误,跳过")
                return False
            elif status_code == 404:
                print(f"  Got 404 Not Found. Skipping.  404错误,跳过")
                return False
            elif status_code != 200:
                print(f"  Got {status_code}. Retry {attempt+1}/{max_retries}")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                else:
                    print(f"  Failed after {max_retries} retries.")
                    return False
            
            # 200 OK
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  Successfully saved to {target_path} /n成功保存到 {target_path}")
            return True
        except requests.RequestException as e:
            print(f"  Request error: {e}. Retry {attempt+1}/{max_retries} /n请求错误: {e}. 重试 {attempt+1}/{max_retries}")
            if attempt < max_retries:
                time.sleep(1)
                continue
            return False

def main():
    parser = argparse.ArgumentParser(description="Download from logs")
    parser.add_argument("--403-first", type=str, default="false", help="Set to true to only download files marked as 403 in logs/n设置为true只下载日志中标记为403的文件")
    parser.add_argument("-d", "--date", type=str, help="Date range, e.g. '2026-03-31 to 2010-01-01'")
    parser.add_argument("-o", "--output", type=str, default="downloads", help="Custom save directory / 自定义保存目录")
    args = parser.parse_args()

    only_403 = args.__dict__.get("403_first", "false").lower() == "true"
    
    start_dt = None
    end_dt = None
    reverse_order = False
    min_date = ""
    max_date = ""

    if args.date:
        try:
            from datetime import datetime
            d_parts = [p.strip() for p in args.date.split("to")]
            if len(d_parts) == 2:
                start_dt = datetime.strptime(d_parts[0], "%Y-%m-%d")
                end_dt = datetime.strptime(d_parts[1], "%Y-%m-%d")
                reverse_order = start_dt > end_dt
                min_date = min(start_dt, end_dt).strftime("%Y%m%d")
                max_date = max(start_dt, end_dt).strftime("%Y%m%d")
            else:
                print("Invalid date format. Use 'YYYY-MM-DD to YYYY-MM-DD'")
                return
        except ValueError:
            print("Invalid date format. Use 'YYYY-MM-DD to YYYY-MM-DD'")
            return

    code_to_name = load_config()
    logs_dir = "logs"
    downloads_dir = args.output

    if not os.path.exists(logs_dir):
        print(f"Logs directory '{logs_dir}' not found.")
        return

    # Collect logs matching the criteria
    tasks = []
    
    for filename in sorted(os.listdir(logs_dir)):
        if filename.endswith("_successful_parses.txt"):
            log_path = os.path.join(logs_dir, filename)
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "|" not in line or line.startswith("===") or line.startswith("文件名") or line.startswith("---"):
                        continue
                    
                    parts = line.split("|")
                    if len(parts) >= 5:
                        file_name_part = parts[0].strip()
                        status_part = parts[2].strip()
                        url_part = parts[3].strip()
                        header_part = parts[4].strip()

                        if only_403 and "403" not in status_part:
                            continue

                        match = re.search(r'^(\d+)_(\d{4})(\d{2})(\d{2})_', file_name_part)
                        if match:
                            date_str = match.group(2) + match.group(3) + match.group(4)
                            
                            if args.date:
                                if not (min_date <= date_str <= max_date):
                                    continue
                            
                            tasks.append({
                                'date_str': date_str,
                                'file_name_part': file_name_part,
                                'url_part': url_part,
                                'header_part': header_part,
                                'code': match.group(1),
                                'year': match.group(2),
                                'month': match.group(3),
                                'day': match.group(4)
                            })

    if not tasks:
        if args.date:
            print(f"在 {args.date} 区间内未找到符合条件的日志记录。(No logs found for the specified date range)")
        else:
            print("没有找到符合条件的日志记录。(No logs found)")
        return

    # Sort tasks according to date (forward or reverse)
    tasks.sort(key=lambda x: x['date_str'], reverse=reverse_order)

    # Process all matched logs
    for task in tasks:
        program_name = code_to_name.get(task['code'], task['code'])
        date_folder = f"{task['year']}-{task['month']}-{task['day']}"
        extension = os.path.splitext(task['file_name_part'])[1]
        
        target_filename = f"{program_name}{extension}"
        target_path = os.path.join(downloads_dir, date_folder, target_filename)

        if os.path.exists(target_path):
            print(f"File already exists, skipping: {target_path}")
            continue

        headers = parse_headers_string(task['header_part'])
        download_file(task['url_part'], target_path, headers)

if __name__ == "__main__":
    main()
