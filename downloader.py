import requests
import os
import sys
import json
from datetime import datetime, timedelta
import time
import hashlib
import re
import random
import uuid
from urllib.parse import urlparse

_UA_DEVICE_POOL = [
    "HLK-AL00",
    "VOG-AL00",
    "M2007J3SC",
    "NOH-AN00",
    "PCT-AL10",
]

_BASE_HEADERS = {
    "Accept-Encoding": "gzip",
    "Authorization": "uauth",
    "Connection": "Keep-Alive",
    "Host": "a.ajmide.com",
    "If-Modified-Since": "Sat, 28 Mar 2026 12:36:07 GMT",
}

_ROTATE_EVERY = 8
_header_state = {
    "count": 0,
    "headers": None,
}

_DOWNLOAD_RETRY_MAX = 2
_DOWNLOAD_RETRY_SLEEP_SECONDS = 1.5
# 仅设置读取超时 5s，不设置连接超时。
_REQUEST_TIMEOUT = (None, 5)
CONFIG_FILE = "config.json"

# Hit FM 节目到 c_{code} 映射及播出时段。
# day: 1-7 => 周一到周日。
DEFAULT_PROGRAM_SCHEDULES = [
    {"name": "Morning Hits阳光音乐早餐", "code": "460", "slots": [{"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "10:00"}]},
    {"name": "hit morning show", "code": "461", "slots": [{"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "10:00"}]},
    {"name": "at 40", "code": "462", "slots": [{"days": [6], "start": "08:00", "end": "12:00"}, {"days": [7], "start": "12:00", "end": "16:00"}]},
    {"name": "Hit FM OST电影原声坊", "code": "465", "slots": [{"days": [7], "start": "16:00", "end": "18:00"}]},
    {"name": "Hit the Road在路上", "code": "467", "slots": [{"days": [6], "start": "12:00", "end": "14:00"}]},
    {"name": "Rock DJ摇滚DJ", "code": "470", "slots": [{"days": [6], "start": "16:00", "end": "18:00"}]},
    {"name": "Big Drive Home开车现场秀", "code": "471", "slots": [{"days": [1, 2, 3, 4, 5], "start": "16:00", "end": "19:00"}]},
    {"name": "Top 20 Countdown顶尖20排行榜", "code": "472", "slots": [{"days": [6, 7], "start": "18:00", "end": "20:00"}]},
    {"name": "New Music Express新音乐速递", "code": "473", "slots": [{"days": [1, 2, 3, 4, 5], "start": "19:00", "end": "22:00"}]},
    {"name": "Hit FM Dance电音", "code": "475", "slots": [{"days": [1, 2, 3, 4, 5, 6, 7], "start": "22:00", "end": "23:59"}]},
    {"name": "Morning Call音乐叫早", "code": "20276", "slots": [{"days": [1, 2, 3, 4, 5], "start": "06:00", "end": "07:00"}]},
    {"name": "Weekend Morning Show周末早间音乐", "code": "20277", "slots": [{"days": [6, 7], "start": "08:00", "end": "12:00"}]},
    {"name": "Soul Make心灵制造", "code": "20278", "slots": [{"days": [6], "start": "14:00", "end": "16:00"}]},
    {"name": "At work network工作随身听", "code": "20279", "slots": [{"days": [1, 2, 3, 4, 5], "start": "10:00", "end": "13:00"}]},
    {"name": "Lazy Afternoon慵懒下午茶", "code": "20280", "slots": [{"days": [1, 2, 3, 4, 5], "start": "13:00", "end": "16:00"}]},
    {"name": "Hit FM Dance Carta & Co.电音-卡塔", "code": "54502", "slots": [{"days": [7], "start": "20:00", "end": "22:00"}]},
]


def _is_valid_program_schedules(value):
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if "name" not in item or "code" not in item or "slots" not in item:
            return False
        if not isinstance(item.get("slots"), list):
            return False
    return True


def _load_program_schedules(config_path=CONFIG_FILE):
    if not os.path.exists(config_path):
        return DEFAULT_PROGRAM_SCHEDULES

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        schedules = config.get("program_schedules")
        if _is_valid_program_schedules(schedules):
            return schedules
        print("警告：config.json 中 program_schedules 无效，已回退内置映射。")
        return DEFAULT_PROGRAM_SCHEDULES
    except Exception as e:
        print(f"警告：读取 config.json 的 program_schedules 失败，已回退内置映射: {e}")
        return DEFAULT_PROGRAM_SCHEDULES


def _build_download_url(code, date_obj, start_hhmm):
    ymd = date_obj.strftime("%Y%m%d")
    hhmm = start_hhmm.replace(":", "")
    return f"http://ia-bk-i.ajmide.com/c_{code}/{ymd}/{code}_{ymd}_{hhmm}.m4a"


def _build_programs_for_date(date_obj, schedules=None):
    weekday = date_obj.isoweekday()
    items = []
    source = schedules if schedules is not None else DEFAULT_PROGRAM_SCHEDULES
    for program in source:
        code = str(program["code"])
        name = program["name"]
        for slot in program.get("slots", []):
            if weekday not in slot.get("days", []):
                continue

            start_dt = datetime.strptime(
                f"{date_obj.strftime('%Y-%m-%d')} {slot['start']}:00", "%Y-%m-%d %H:%M:%S"
            )
            end_dt = datetime.strptime(
                f"{date_obj.strftime('%Y-%m-%d')} {slot['end']}:00", "%Y-%m-%d %H:%M:%S"
            )

            url = _build_download_url(code, date_obj, slot["start"])
            items.append(
                {
                    "programName": name,
                    "startTime": int(start_dt.timestamp() * 1000),
                    "endTime": int(end_dt.timestamp() * 1000),
                    "playUrlHigh": url,
                    "playUrlLow": url,
                    "downloadUrl": url,
                    "image": "",
                    "imageLong": "",
                }
            )

    # 以开始时间排序，保持输出和下载顺序稳定。
    items.sort(key=lambda x: (x.get("startTime", 0), x.get("programName", "")))
    return items


def _build_ajmide_headers(target_url=""):
    # 每隔固定请求次数轮换机型与 UUID，尽量贴近真实设备指纹变化。
    if (
        _header_state["headers"] is None
        or _header_state["count"] % _ROTATE_EVERY == 0
    ):
        device = random.choice(_UA_DEVICE_POOL)
        uid = str(uuid.uuid4())
        headers = dict(_BASE_HEADERS)
        parsed = urlparse(target_url or "")
        if parsed.netloc:
            headers["Host"] = parsed.netloc
        headers["User-Agent"] = (
            f"ajmd/4.0.2 (Android 10; {device}; {uid}; ajmd; {uid})"
        )
        _header_state["headers"] = headers

    _header_state["count"] += 1
    return dict(_header_state["headers"])

def _load_downloaded_images(log_file):
    # 图片去重缓存：存储已下载 URL，避免重复请求相同图片地址。
    if not os.path.exists(log_file):
        return set()
    with open(log_file, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def _save_downloaded_image(log_file, url):
    # 追加写入，保持历史记录，便于跨天任务复用缓存。
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"{url}\n")

def download_image(url, img_dir, downloaded_images_log, images_info_log, safe_program_name, suffix=""):
    # 返回值会写入节目清单文本，作为“图片处理结果”提示。
    if not url:
        return ""
    
    images_cache = _load_downloaded_images(downloaded_images_log)
        
    try:
        parsed_url = urlparse(url)
        # 用图片URL的最后一段作为文件名，如果有特殊字符这里暂且忽略，通常是随机字符串.jpg
        original_name = os.path.basename(parsed_url.path)
        if not original_name:
            original_name = hashlib.md5(url.encode('utf-8')).hexdigest() + ".jpg"

        _, ext = os.path.splitext(original_name)
        if not ext:
            ext = ".jpg"

        # 使用节目名称命名
        new_img_name = f"{safe_program_name}{suffix}{ext}"
        img_path = os.path.join(img_dir, new_img_name)
        
        # 双重去重：URL 命中缓存或目标文件已存在，都视为可跳过。
        is_cached = url in images_cache
        if os.path.exists(img_path) or is_cached:
            if not is_cached:
                _save_downloaded_image(downloaded_images_log, url)
            return f"（跳过：{new_img_name}）"
            
        print(f"正在下载图片: {url} -> {img_path}")
        img_response = requests.get(url, headers=_build_ajmide_headers(url), stream=True, timeout=_REQUEST_TIMEOUT)
        img_response.raise_for_status()
        with open(img_path, 'wb') as f:
            for chunk in img_response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        # 记录到已下载列表
        _save_downloaded_image(downloaded_images_log, url)

        # 写入图片详情txt
        with open(images_info_log, 'a', encoding='utf-8') as info_f:
            info_f.write(f"本地命名: {new_img_name}\n")
            info_f.write(f"原始文件: {original_name}\n")
            info_f.write(f"来源地址: {url}\n")
            info_f.write("-" * 40 + "\n")

        return f"（新保存：{new_img_name}）"
    except Exception as e:
        print(f"下载图片失败 {url}: {e}")
        return "（下载失败）"


class _TokenBucketLimiter:
    def __init__(self, rate_kbps):
        self.rate_bps = max(float(rate_kbps), 0.0) * 1024.0
        self.capacity = max(self.rate_bps * 0.5, 16 * 1024)
        self.tokens = self.capacity
        self.last_ts = time.monotonic()

    def consume(self, size_bytes):
        if self.rate_bps <= 0:
            return
        need = float(size_bytes)
        while True:
            now = time.monotonic()
            elapsed = max(0.0, now - self.last_ts)
            self.last_ts = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_bps)
            if self.tokens >= need:
                self.tokens -= need
                return
            wait_s = (need - self.tokens) / self.rate_bps
            time.sleep(min(max(wait_s, 0.001), 0.2))


def _download_audio_with_retry(download_url, file_path, part_path, state_checker, limiter, download_progress_cb, retry_max=None):
    last_error = None
    max_retry = int(retry_max) if retry_max is not None else _DOWNLOAD_RETRY_MAX
    max_retry = max(max_retry, 1)

    for attempt in range(1, max_retry + 1):
        try:
            download_headers = _build_ajmide_headers(download_url)
            audio_response = requests.get(download_url, headers=download_headers, stream=True, timeout=_REQUEST_TIMEOUT)
            audio_response.raise_for_status()

            # 每次重试都从头写 .part，保证目标文件完整性。
            with open(part_path, 'wb') as f:
                for chunk in audio_response.iter_content(chunk_size=8192):
                    if state_checker:
                        state_checker(is_chunk=True)
                    if chunk:
                        if limiter:
                            limiter.consume(len(chunk))
                        if download_progress_cb:
                            try:
                                download_progress_cb(len(chunk))
                            except Exception:
                                pass
                        f.write(chunk)

            os.replace(part_path, file_path)
            return True, None, attempt

        except Exception as e:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass

            if type(e).__name__ == 'StopDownloadException':
                raise

            last_error = e
            if attempt < max_retry:
                print(f"下载失败，自动重试({attempt}/{max_retry}) -> {download_url}")
                sleep_steps = int(_DOWNLOAD_RETRY_SLEEP_SECONDS * 10)
                for _ in range(max(sleep_steps, 1)):
                    if state_checker:
                        state_checker(is_chunk=False)
                    time.sleep(0.1)

    return False, str(last_error), max_retry


class _SafeFormatDict(dict):
    def __missing__(self, key):
        # 未知变量保持原样，避免模板中断。
        return "{" + key + "}"


def _sanitize_component_for_path(value):
    if value is None:
        return ""

    text = str(value)
    # Windows 非法文件名字符统一转全角，保留可读性。
    translate_map = {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
    cleaned = "".join(translate_map.get(ch, ch) for ch in text).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned or "_"


def _split_program_name(name):
    raw = (name or "").strip()
    pattern = r"^(?P<en>[A-Za-z0-9][A-Za-z0-9&().,'!?:/\-\s]*?)\s+(?P<ch>[\u3400-\u9fff].*)$"
    m = re.match(pattern, raw)
    if m:
        return m.group("en").strip(), m.group("ch").strip()

    if re.search(r"[\u3400-\u9fff]", raw):
        return "", raw
    return raw, ""


def _render_filename_template(template, values):
    tpl = (template or "").strip() or r"{date}\{name}"
    return tpl.format_map(_SafeFormatDict(values))


def _extract_audio_extension(download_url):
    ext = os.path.splitext(urlparse(download_url).path)[1].lower()
    return ext if ext else ".m4a"


def _build_output_file_path(base_downloads_dir, template_rendered, download_url, fallback_date, fallback_name):
    rel = (template_rendered or "").strip().replace("/", os.sep).replace("\\", os.sep)
    if not rel:
        rel = os.path.join(fallback_date, fallback_name)

    if os.path.isabs(rel):
        drive, tail = os.path.splitdrive(rel)
        parts = [p for p in tail.split(os.sep) if p not in ("", ".", "..")]
        safe_parts = [_sanitize_component_for_path(p) for p in parts]
        if drive:
            path_no_ext = os.path.join(drive + os.sep, *safe_parts)
        else:
            path_no_ext = os.path.join(os.sep, *safe_parts)
    else:
        parts = [p for p in rel.split(os.sep) if p not in ("", ".", "..")]
        safe_parts = [_sanitize_component_for_path(p) for p in parts]
        if not safe_parts:
            safe_parts = [_sanitize_component_for_path(fallback_date), _sanitize_component_for_path(fallback_name)]
        path_no_ext = os.path.join(base_downloads_dir, *safe_parts)

    return path_no_ext + _extract_audio_extension(download_url)


def _resolve_program_info_dir(base_downloads_dir, filename_template, date_str):
    # 与 GUI 预览保持一致：使用固定示例节目生成“对应目录”。
    sample_name = "Morning Call 音乐叫早"
    sample_en, sample_ch = _split_program_name(sample_name)
    sample_values = {
        "id": "1",
        "name": _sanitize_component_for_path(sample_name),
        "date": _sanitize_component_for_path(date_str),
        "name_ch": _sanitize_component_for_path(sample_ch),
        "name_en": _sanitize_component_for_path(sample_en),
        "bitrate": "High",
        "start_time": _sanitize_component_for_path("06:00:00"),
        "end_time": _sanitize_component_for_path("07:00:00"),
    }
    rendered = _render_filename_template(filename_template, sample_values)
    sample_file_path = _build_output_file_path(
        base_downloads_dir=base_downloads_dir,
        template_rendered=rendered,
        download_url="https://example.com/sample.m4a",
        fallback_date=date_str,
        fallback_name=_sanitize_component_for_path(sample_name),
    )
    sample_dir = os.path.dirname(sample_file_path)
    return sample_dir if sample_dir else base_downloads_dir

def download_by_date(date_str, base_downloads_dir="downloads", high_bitrate=True, download_imgs=True,
                     state_checker=None, post_process_cb=None, download_progress_cb=None, name_filter_regex="", filename_template=r"{date}\{name}", max_rate_kbps=0):
    """
    根据指定日期下载电台回放.
    日期格式应为 "YY-MM-DD", 例如 "25-12-22".
        回调约定:
            - state_checker(is_chunk=bool): GUI 用于暂停/停止协作式中断
            - post_process_cb(name, file_path, date): 单文件下载完成后触发后处理
            - download_progress_cb(byte_count): 用于实时速率统计
    """
    try:
        # 将 "YY-MM-DD" 格式转换为 "YYYY-MM-DD"
        input_date = datetime.strptime(date_str, "%y-%m-%d")
        formatted_date = input_date.strftime("%Y-%m-%d")
    except ValueError:
        print(f"错误：日期格式不正确: {date_str}。请使用 'YY-MM-DD' 格式。")
        return {
            "date": date_str,
            "generated": 0,
            "success": 0,
            "failed": 1,
            "ignored_complementary": 0,
            "skipped_existing": 0,
            "skipped_name_filter": 0,
            "unresolved_failures": 1,
        }

    name_pattern = None
    if name_filter_regex and name_filter_regex.strip():
        try:
            name_pattern = re.compile(name_filter_regex)
        except re.error as e:
            print(f"错误：节目筛选正则表达式无效: {e}")
            return

    limiter = _TokenBucketLimiter(max_rate_kbps) if float(max_rate_kbps or 0) > 0 else None
    if limiter:
        print(f"下载限速已启用: {max_rate_kbps} KB/s")

    print(f"正在按映射规则拼接 {formatted_date} 的节目URL...")
    program_schedules = _load_program_schedules()
    program_list = _build_programs_for_date(input_date, program_schedules)
    if not program_list:
        print(f"在 {formatted_date} 未匹配到可下载节目（当前硬编码映射可能不包含该日期时段）。")
        return {
            "date": formatted_date,
            "generated": 0,
            "success": 0,
            "failed": 0,
            "ignored_complementary": 0,
            "skipped_existing": 0,
            "skipped_name_filter": 0,
            "unresolved_failures": 0,
        }

    # 输出结构:
    # - <base>/images/*
    # - <base>/downloaded_images.txt
    # - program_info 目录与 filename_template 对应（同规则推导）
    # - 音频文件路径由 filename_template 动态决定，可包含子目录
    day_report_dir = _resolve_program_info_dir(base_downloads_dir, filename_template, formatted_date)
    images_dir = os.path.join(base_downloads_dir, "images")
    downloaded_images_log = os.path.join(base_downloads_dir, "downloaded_images.txt")
    images_info_log = os.path.join(images_dir, "images_info.txt")

    for path_to_create in [base_downloads_dir, day_report_dir, images_dir]:
        if not os.path.exists(path_to_create):
            os.makedirs(path_to_create)
    
    print(f"已生成 {len(program_list)} 条节目URL，准备下载...")

    generated_count = len(program_list)
    success_count = 0
    failed_count = 0
    ignored_complementary_count = 0
    skipped_existing_count = 0
    skipped_name_filter_count = 0

    # 保存每日节目信息的txt文件
    info_txt_path = os.path.join(day_report_dir, f"{formatted_date}_program_info.txt")
    with open(info_txt_path, 'w', encoding='utf-8') as info_file:
        info_file.write(f"=== {formatted_date} 节目信息 ===\n\n")
        slot_success = {}
        failed_items = []
        slot_total = {}
        for p in program_list:
            st = p.get("startTime", 0)
            et = p.get("endTime", 0)
            if st:
                sdt = datetime.fromtimestamp(st / 1000.0)
                s_date = sdt.strftime('%Y-%m-%d')
                s_time = sdt.strftime('%H:%M:%S')
            else:
                s_date = formatted_date
                s_time = "00:00:00"

            if et:
                edt = datetime.fromtimestamp(et / 1000.0)
                e_time = edt.strftime('%H:%M:%S')
            else:
                e_time = "00:00:00"

            sk = (s_date, s_time, e_time)
            slot_total[sk] = slot_total.get(sk, 0) + 1

        for program_index, program in enumerate(program_list, start=1):
            # 在“节目粒度”进行中断检查: 软停止会阻止后续节目继续下载。
            if state_checker:
                state_checker(is_chunk=False)
                
            program_name = program.get("programName", "unknown_program")
            if name_pattern and not name_pattern.search(program_name):
                print(f"筛选跳过: {program_name}")
                skipped_name_filter_count += 1
                continue

            start_time_ms = program.get("startTime", 0)
            end_time_ms = program.get("endTime", 0)
            
            # 格式化时间
            if start_time_ms:
                start_dt = datetime.fromtimestamp(start_time_ms / 1000.0)
                program_date_str = start_dt.strftime('%Y-%m-%d')
                start_time_only = start_dt.strftime('%H:%M:%S')
                start_time_full = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                program_date_str = formatted_date
                start_time_only = "00:00:00"
                start_time_full = "未知"

            if end_time_ms:
                end_dt = datetime.fromtimestamp(end_time_ms / 1000.0)
                end_time_only = end_dt.strftime('%H:%M:%S')
                end_time_full = end_dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                end_time_only = "00:00:00"
                end_time_full = "未知"

            slot_key = (program_date_str, start_time_only, end_time_only)
            is_complementary_slot = slot_total.get(slot_key, 0) > 1

            if is_complementary_slot and slot_success.get(slot_key, 0) > 0:
                print(f"互补跳过：'{program_name}' 与同时间段节目互补，已有成功任务。")
                info_file.write(f"互补策略: 同时间段已有成功任务，跳过当前节目\n")
                info_file.write("-" * 40 + "\n")
                ignored_complementary_count += 1
                continue
            
            # 获取图片链接
            image_url = program.get("image", "")
            image_long_url = program.get("imageLong", "")

            # 拆分英文/中文节目名
            name_en_raw, name_ch_raw = _split_program_name(program_name)

            bitrate_tag = "High" if high_bitrate else "Low"

            # 自定义命名模板变量
            format_values = {
                "id": str(program_index),
                "name": _sanitize_component_for_path(program_name),
                "date": _sanitize_component_for_path(program_date_str),
                "name_ch": _sanitize_component_for_path(name_ch_raw),
                "name_en": _sanitize_component_for_path(name_en_raw),
                "bitrate": bitrate_tag,
                "start_time": _sanitize_component_for_path(start_time_only),
                "end_time": _sanitize_component_for_path(end_time_only),
            }
            
            # 决定使用哪种码率
            if high_bitrate:
                download_url = program.get("playUrlHigh")
            else:
                # 尝试获取低码率，找不到就用默认
                download_url = program.get("playUrlLow") or program.get("downloadUrl")

            template_rendered = _render_filename_template(filename_template, format_values)
            file_path = _build_output_file_path(
                base_downloads_dir=base_downloads_dir,
                template_rendered=template_rendered,
                download_url=download_url or "",
                fallback_date=program_date_str,
                fallback_name=_sanitize_component_for_path(program_name),
            )
            file_dir = os.path.dirname(file_path)
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir, exist_ok=True)
            part_path = file_path + ".part"

            # 图片下载逻辑与音频下载解耦，失败不会阻断后续音频抓取。
            image_name_base = os.path.splitext(os.path.basename(file_path))[0]
            if download_imgs:
                img_result = download_image(image_url, images_dir, downloaded_images_log, images_info_log, image_name_base) if image_url else "无"
                img_long_result = download_image(image_long_url, images_dir, downloaded_images_log, images_info_log, image_name_base, "_long") if image_long_url else "无"
            else:
                img_result = "跳过"
                img_long_result = "跳过"

            # 将信息写入文本文件
            info_file.write(f"节目名称: {program_name}\n")
            info_file.write(f"节目序号: {program_index}\n")
            info_file.write(f"开始时间: {start_time_full}\n")
            info_file.write(f"结束时间: {end_time_full}\n")
            info_file.write(f"下载链接: {download_url}\n")
            info_file.write(f"模板结果: {template_rendered}\n")
            info_file.write(f"输出路径: {file_path}\n")
            info_file.write(f"展示图片: {image_url} {img_result}\n")
            info_file.write(f"长版图片: {image_long_url} {img_long_result}\n")
            info_file.write("-" * 40 + "\n")

            if not download_url:
                print(f"警告：节目 '{program_name}' 没有找到可用下载链接，跳过。")
                continue

            if os.path.exists(file_path):
                print(f"文件 '{file_path}' 已存在，跳过下载。")
                slot_success[slot_key] = slot_success.get(slot_key, 0) + 1
                success_count += 1
                skipped_existing_count += 1
                # 即使是已存在文件，也触发后处理回调，便于 GUI 做统一转换排队。
                if post_process_cb:
                    post_process_cb(os.path.splitext(os.path.basename(file_path))[0], file_path, formatted_date)
                continue

            print(f"正在下载 '{program_name}' 到 '{file_path}'...")

            try:
                ok, err_msg, used_attempt = _download_audio_with_retry(
                    download_url=download_url,
                    file_path=file_path,
                    part_path=part_path,
                    state_checker=state_checker,
                    limiter=limiter,
                    download_progress_cb=download_progress_cb,
                    retry_max=1 if is_complementary_slot else _DOWNLOAD_RETRY_MAX,
                )

                if ok:
                    slot_success[slot_key] = slot_success.get(slot_key, 0) + 1
                    success_count += 1
                    if used_attempt > 1:
                        print(f"'{program_name}' 重试成功（第 {used_attempt} 次）。")
                    else:
                        print(f"'{program_name}' 下载完成。")
                else:
                    failed_count += 1
                    failed_items.append({
                        "program_name": program_name,
                        "slot_key": slot_key,
                        "download_url": download_url,
                        "error": err_msg,
                    })
                    print(f"错误：下载 '{program_name}' 失败（已重试 {used_attempt} 次）: {err_msg}")
                    continue

                if post_process_cb:
                    post_process_cb(os.path.splitext(os.path.basename(file_path))[0], file_path, formatted_date)

            except Exception as e:
                # 无论发生什么异常，清理可能存在的 .part 文件
                if os.path.exists(part_path):
                    try:
                        os.remove(part_path)
                    except:
                        pass
                print(f"错误：下载 '{program_name}' 失败或被中断: {e}")
                # StopDownloadException 可能来自 GUI 模块，不同模块类身份不一致，
                # 这里按异常名识别并继续上抛，确保可中断整个日期循环。
                if type(e).__name__ == 'StopDownloadException':
                    raise

        unresolved_failures = []
        for item in failed_items:
            if slot_success.get(item["slot_key"], 0) > 0:
                print(
                    f"互补容错：'{item['program_name']}' 下载失败，但同时间段已有成功任务，已忽略。"
                )
                ignored_complementary_count += 1
            else:
                unresolved_failures.append(item)

        if unresolved_failures:
            print("以下任务最终失败（无同时间段互补成功）：")
            for item in unresolved_failures:
                print(f" - {item['program_name']} | {item['download_url']} | {item['error']}")

    print(
        f"汇总: 生成 {generated_count} | 成功 {success_count} | 失败 {failed_count} | "
        f"互补忽略 {ignored_complementary_count} | 已存在跳过 {skipped_existing_count} | 名称筛选跳过 {skipped_name_filter_count}"
    )
    unresolved_count = len(unresolved_failures)
    if unresolved_count > 0:
        print(f"未解决失败: {unresolved_count}")

    print(f"\n{formatted_date} 的所有节目下载任务已完成。信息已保存至 {info_txt_path}\n")
    return {
        "date": formatted_date,
        "generated": generated_count,
        "success": success_count,
        "failed": failed_count,
        "ignored_complementary": ignored_complementary_count,
        "skipped_existing": skipped_existing_count,
        "skipped_name_filter": skipped_name_filter_count,
        "unresolved_failures": unresolved_count,
    }

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="阿基米德电台下载器")
    parser.add_argument("-d", "--date", help="指定单独日期 (如 '25-12-22'/'now') 或日期范围 (如 '25-11-22 to 25-12-22'，支持反向)", default="25-12-22")
    parser.add_argument("-o", "--outdir", help="基础输出目录，默认是'downloads'", default="downloads")
    parser.add_argument("--low-bitrate", help="下载低码率音频 (默认下载高码率)", action="store_true")
    parser.add_argument("--no-images", help="不下载封面图片", action="store_true")
    parser.add_argument("--delay", help="多日持续下载时，每天之间的间隔时间(秒)", type=float, default=1.5)
    parser.add_argument("--name-regex", help="节目名筛选正则（匹配才下载）", default="")
    parser.add_argument("--filename-template", help=r"自定义输出模板，默认 '{date}\\{name}'", default=r"{date}\{name}")
    
    args = parser.parse_args()
    date_arg = args.date.strip()

    def _parse_cli_date_literal(value):
        v = value.strip().lower()
        if v in ("now", "today"):
            return datetime.now()
        return datetime.strptime(value.strip(), "%y-%m-%d")
    
    high_bit = not args.low_bitrate
    dl_imgs = not args.no_images
    
    # 命令行支持 "YY-MM-DD to YY-MM-DD" 范围写法。
    total_unresolved_failures = 0
    if " to " in date_arg:
        parts = date_arg.split(" to ")
        if len(parts) == 2:
            start_str, end_str = parts[0].strip(), parts[1].strip()
            try:
                start_date = _parse_cli_date_literal(start_str)
                end_date = _parse_cli_date_literal(end_str)

                step_days = 1 if end_date >= start_date else -1
                curr_date = start_date
                while (step_days == 1 and curr_date <= end_date) or (step_days == -1 and curr_date >= end_date):
                    result = download_by_date(
                        curr_date.strftime("%y-%m-%d"),
                        base_downloads_dir=args.outdir,
                        high_bitrate=high_bit,
                        download_imgs=dl_imgs,
                        name_filter_regex=args.name_regex,
                        filename_template=args.filename_template,
                    )
                    if isinstance(result, dict):
                        total_unresolved_failures += int(result.get("unresolved_failures", 0) or 0)
                    curr_date += timedelta(days=step_days)
                    should_wait = (step_days == 1 and curr_date <= end_date) or (step_days == -1 and curr_date >= end_date)
                    if should_wait:
                        time.sleep(args.delay)
            except ValueError:
                print("错误：日期范围解析失败，请确保格式如 '25-11-22 to 25-12-22' 或 'now to 25-12-22'。")
                sys.exit(2)
        else:
            print("错误：日期范围格式不正确。")
            sys.exit(2)
    else:
        # 单独日期下载
        result = download_by_date(
            _parse_cli_date_literal(date_arg).strftime("%y-%m-%d"),
            base_downloads_dir=args.outdir, 
            high_bitrate=high_bit, 
            download_imgs=dl_imgs, 
            name_filter_regex=args.name_regex,
            filename_template=args.filename_template,
        )
        if isinstance(result, dict):
            total_unresolved_failures += int(result.get("unresolved_failures", 0) or 0)

    if total_unresolved_failures > 0:
        print(f"存在未解决失败任务，总计: {total_unresolved_failures}")
        sys.exit(1)

    sys.exit(0)

