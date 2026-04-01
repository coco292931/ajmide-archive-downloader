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
    args = parser.parse_args()

    only_403 = args.__dict__.get("403_first", "false").lower() == "true"

    code_to_name = load_config()
    logs_dir = "logs"
    downloads_dir = "downloads"

    if not os.path.exists(logs_dir):
        print(f"Logs directory '{logs_dir}' not found.")
        return

    # Process all log files
    for filename in sorted(os.listdir(logs_dir)):
        if filename.endswith("_successful_parses.txt"):
            log_path = os.path.join(logs_dir, filename)
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not "|" in line or line.startswith("===") or line.startswith("文件名") or line.startswith("---"):
                        continue
                    
                    parts = line.split("|")
                    if len(parts) >= 5:
                        file_name_part = parts[0].strip()
                        status_part = parts[2].strip()
                        url_part = parts[3].strip()
                        header_part = parts[4].strip()

                        if only_403 and "403" not in status_part:
                            continue

                        # Generate target path
                        # file_name_part example: 466_20140922_1300.m4a
                        match = re.search(r'^(\d+)_(\d{4})(\d{2})(\d{2})_', file_name_part)
                        if match:
                            code = match.group(1)
                            year = match.group(2)
                            month = match.group(3)
                            day = match.group(4)
                            
                            program_name = code_to_name.get(code, code)
                            date_folder = f"{year}-{month}-{day}"
                            extension = os.path.splitext(file_name_part)[1]
                            
                            target_filename = f"{program_name}{extension}"
                            target_path = os.path.join(downloads_dir, date_folder, target_filename)

                            if os.path.exists(target_path):
                                print(f"File already exists, skipping: {target_path}")
                                continue

                            headers = parse_headers_string(header_part)
                            download_file(url_part, target_path, headers)

if __name__ == "__main__":
    main()
