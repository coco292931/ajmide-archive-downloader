#!/usr/bin/env python3
"""
统计下载目录与日志目录中的可识别/可获取文件数量，并按日/周/月输出汇总与图表。

示例:
python .\tools\analyze_archive_stats.py --downloads-dir .\downloads --logs-dirs .\logs --out-dir .\stats_out --plot-kind line
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
SECTION_DATE_RE = re.compile(r"^===\s*(\d{4}-\d{2}-\d{2})\s*===")
FILENAME_RE = re.compile(r"^[^|]+\.(?:m4a|mp3|aac|wav|flac)\s*\|")
STATUS_200_RE = re.compile(r"(?<!\d)200(?!\d)")
CODED_AUDIO_FILE_RE = re.compile(r"^(\d+)_\d{8}_\d{4}\.(?:m4a|mp3|aac|wav|flac)$", re.IGNORECASE)
PROGRAM_INFO_LINK_CODE_RE = re.compile(r"/c_(\d+)/")
HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class DayStat:
    day: date
    downloaded_count: int = 0
    identified_count: int = 0
    obtainable_200_count: int = 0


def safe_parse_day(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def scan_downloaded_files(downloads_dir: Path) -> Dict[date, int]:
    """按目录日期统计已下载文件数量，忽略 program_info 文本。"""
    result: Dict[date, int] = defaultdict(int)

    if not downloads_dir.exists():
        return result

    for day_dir in downloads_dir.iterdir():
        if not day_dir.is_dir():
            continue
        day = safe_parse_day(day_dir.name)
        if day is None:
            continue

        for file_path in day_dir.iterdir():
            if not file_path.is_file():
                continue
            name_lower = file_path.name.lower()
            if name_lower.endswith("_program_info.txt"):
                continue
            result[day] += 1

    return result


def scan_downloaded_files_by_code(downloads_dir: Path) -> Dict[str, int]:
    """按节目 code 统计已下载文件数量，优先从 _program_info.txt 提取链接 code，缺失时回退文件名。"""
    result: Dict[str, int] = defaultdict(int)

    if not downloads_dir.exists():
        return result

    for day_dir in downloads_dir.iterdir():
        if not day_dir.is_dir():
            continue

        audio_files: List[Path] = []
        for candidate in day_dir.iterdir():
            if not candidate.is_file():
                continue
            if candidate.name.lower().endswith("_program_info.txt"):
                continue
            audio_files.append(candidate)

        info_code: Optional[str] = None
        for candidate in day_dir.iterdir():
            if not candidate.is_file() or not candidate.name.lower().endswith("_program_info.txt"):
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            m_info = PROGRAM_INFO_LINK_CODE_RE.search(text)
            if m_info:
                info_code = m_info.group(1)
                break

        for file_path in audio_files:
            m = CODED_AUDIO_FILE_RE.match(file_path.name)
            code: Optional[str] = m.group(1) if m else None

            # 仅在无法从文件名提取 code 且当天只有一个音频时，回退到 program_info 的 code。
            if code is None and len(audio_files) == 1 and info_code is not None:
                code = info_code

            if code is None:
                continue

            result[code] += 1

    return result


def extract_day_from_filename(log_file: Path) -> Optional[date]:
    m = DATE_RE.search(log_file.name)
    if not m:
        return None
    return safe_parse_day(m.group(1))


def parse_log_file(log_file: Path) -> Dict[date, Tuple[int, int]]:
    """
    返回 {day: (identified_count, obtainable_200_count)}。
    identified_count: 在日志中识别到的文件记录数
    obtainable_200_count: 记录中明确包含 (200) 的数量
    """
    per_day_identified: Dict[date, int] = defaultdict(int)
    per_day_200: Dict[date, int] = defaultdict(int)

    fallback_day = extract_day_from_filename(log_file)
    current_day: Optional[date] = fallback_day

    with log_file.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            sec = SECTION_DATE_RE.match(line)
            if sec:
                current_day = safe_parse_day(sec.group(1))
                continue

            if "|" not in line:
                continue

            # 过滤表头/分隔线，保留真正的数据行
            if "文件名" in line or set(line) <= {"-", "|"}:
                continue

            if not FILENAME_RE.match(line):
                continue

            if current_day is None:
                continue

            per_day_identified[current_day] += 1

            parts = [p.strip() for p in line.split("|")]
            # 预期: 文件名 | 节目时间 | 解析状态 | ...
            status = parts[2] if len(parts) >= 3 else ""
            if STATUS_200_RE.search(status):
                per_day_200[current_day] += 1

    merged: Dict[date, Tuple[int, int]] = {}
    for day in set(per_day_identified) | set(per_day_200):
        merged[day] = (per_day_identified.get(day, 0), per_day_200.get(day, 0))
    return merged


def parse_log_file_by_code(log_file: Path) -> Tuple[Dict[str, int], Dict[str, int]]:
    """返回 (identified_by_code, obtainable_200_by_code)。"""
    identified_by_code: Dict[str, int] = defaultdict(int)
    obtainable_200_by_code: Dict[str, int] = defaultdict(int)

    with log_file.open("r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            if "|" not in line:
                continue

            if "文件名" in line or set(line) <= {"-", "|"}:
                continue

            if not FILENAME_RE.match(line):
                continue

            parts = [p.strip() for p in line.split("|")]
            filename = parts[0] if parts else ""
            status = parts[2] if len(parts) >= 3 else ""

            m = CODED_AUDIO_FILE_RE.match(filename)
            if not m:
                continue

            code = m.group(1)
            identified_by_code[code] += 1
            if STATUS_200_RE.search(status):
                obtainable_200_by_code[code] += 1

    return identified_by_code, obtainable_200_by_code


def scan_log_dir(logs_dir: Path) -> Dict[date, Tuple[int, int]]:
    result_identified: Dict[date, int] = defaultdict(int)
    result_200: Dict[date, int] = defaultdict(int)

    if not logs_dir.exists():
        return {}

    for log_file in sorted(logs_dir.glob("*_successful_parses.txt")):
        file_stats = parse_log_file(log_file)
        for day, (identified, ok200) in file_stats.items():
            result_identified[day] += identified
            result_200[day] += ok200

    merged: Dict[date, Tuple[int, int]] = {}
    for day in set(result_identified) | set(result_200):
        merged[day] = (result_identified.get(day, 0), result_200.get(day, 0))
    return merged


def scan_log_dir_by_code(logs_dir: Path) -> Tuple[Dict[str, int], Dict[str, int]]:
    result_identified: Dict[str, int] = defaultdict(int)
    result_200: Dict[str, int] = defaultdict(int)

    if not logs_dir.exists():
        return {}, {}

    for log_file in sorted(logs_dir.glob("*_successful_parses.txt")):
        identified_by_code, obtainable_200_by_code = parse_log_file_by_code(log_file)
        for code, n in identified_by_code.items():
            result_identified[code] += n
        for code, n in obtainable_200_by_code.items():
            result_200[code] += n

    return dict(result_identified), dict(result_200)


def _pick_display_name(names: List[str], code: str) -> str:
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        return code
    for n in cleaned:
        if HAS_CJK_RE.search(n):
            return n
    return cleaned[0]


def load_code_name_map(config_path: Path) -> Dict[str, str]:
    """从配置文件读取 code->display_name 映射；优先中文名。"""
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    schedules = data.get("program_schedules", []) if isinstance(data, dict) else []
    by_code_names: Dict[str, List[str]] = defaultdict(list)

    for item in schedules:
        if not isinstance(item, dict):
            continue
        code_raw = item.get("code")
        name_raw = item.get("name")
        if code_raw is None:
            continue

        code = str(code_raw).strip()
        name = str(name_raw).strip() if name_raw is not None else ""
        if not code:
            continue

        if name and name not in by_code_names[code]:
            by_code_names[code].append(name)

    return {code: _pick_display_name(names, code) for code, names in by_code_names.items()}


def build_program_coverage_rows(
    downloaded_by_code: Dict[str, int],
    identified_by_code: Dict[str, int],
    obtainable_200_by_code: Dict[str, int],
    code_name_map: Dict[str, str],
) -> List[Dict[str, object]]:
    """先按 code 汇总，再按节目名(主键)合并。"""
    all_codes = sorted(
        set(downloaded_by_code.keys())
        | set(identified_by_code.keys())
        | set(obtainable_200_by_code.keys())
        | set(code_name_map.keys())
    )

    by_name: Dict[str, Dict[str, object]] = {}
    for code in all_codes:
        downloaded = downloaded_by_code.get(code, 0)
        identified = identified_by_code.get(code, 0)
        obtainable = obtainable_200_by_code.get(code, 0)
        name = code_name_map.get(code, f"Unknown-{code}")

        if name not in by_name:
            by_name[name] = {
                "codes": set(),
                "program_name": name,
                "downloaded_count": 0,
                "identified_count": 0,
                "obtainable_200_count": 0,
            }

        row = by_name[name]
        cast_codes = row["codes"]
        if isinstance(cast_codes, set):
            cast_codes.add(code)
        row["downloaded_count"] = int(row["downloaded_count"]) + downloaded
        row["identified_count"] = int(row["identified_count"]) + identified
        row["obtainable_200_count"] = int(row["obtainable_200_count"]) + obtainable

    rows: List[Dict[str, object]] = []
    for name, item in by_name.items():
        downloaded = int(item["downloaded_count"])
        identified = int(item["identified_count"])
        obtainable = int(item["obtainable_200_count"])
        capped_downloaded = min(downloaded, obtainable)
        codes = sorted(item["codes"]) if isinstance(item["codes"], set) else []

        rows.append(
            {
                "program_name": name,
                "codes": ",".join(codes),
                "downloaded_count": downloaded,
                "identified_count": identified,
                "obtainable_200_count": obtainable,
                "downloaded_over_obtainable_200_pct": f"{ratio(capped_downloaded, obtainable):.2f}",
                "downloaded_over_identified_pct": f"{ratio(downloaded, identified):.2f}",
                "obtainable_200_over_identified_pct": f"{ratio(obtainable, identified):.2f}",
            }
        )

    rows.sort(
        key=lambda r: (
            int(r["obtainable_200_count"]),
            int(r["identified_count"]),
            int(r["downloaded_count"]),
            str(r["program_name"]),
        ),
        reverse=True,
    )
    return rows


def render_program_coverage_plot(path: Path, rows: List[Dict[str, object]]) -> None:
    """绘制全量节目三层堆叠图：底层总可获取(可识别)、中间已下载、顶层200。"""
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("[WARN] matplotlib 不可用，跳过节目覆盖率绘图。可安装: pip install matplotlib")
        return

    if not rows:
        return

    font_candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans", "HYZhuZiMuTouRenW",  "Consolas"]
    required_texts = [
        "节目抓取覆盖率汇总（全量）",
        "节目名称",
        "数量",
        "总可获取",
        "已下载",
        "200",
    ] + [str(r["program_name"]) for r in rows]
    picked_font, installed_fonts = _pick_best_font(font_candidates, required_texts)
    if picked_font:
        fallback_fonts = [f for f in font_candidates if f != picked_font and f in installed_fonts]
        plt.rcParams["font.sans-serif"] = [picked_font] + fallback_fonts
    else:
        plt.rcParams["font.sans-serif"] = font_candidates
    plt.rcParams["axes.unicode_minus"] = False

    labels = [str(r["program_name"]) for r in rows]
    totals = [int(r["identified_count"]) for r in rows]
    downloaded = [int(r["downloaded_count"]) for r in rows]
    ok200 = [int(r["obtainable_200_count"]) for r in rows]

    fig_h = min(max(8.0, len(rows) * 0.42), 26.0)
    plt.figure(figsize=(16, fig_h))
    y_pos = list(range(len(rows)))

    # 用户要求的层级: 底层总可获取(可识别)、中间已下载、顶层200
    plt.barh(y_pos, totals, color="#DCE6F2", label="总可获取")
    plt.barh(y_pos, downloaded, left=totals, color="#4C78A8", label="已下载")
    plt.barh(y_pos, ok200, left=[totals[i] + downloaded[i] for i in range(len(rows))], color="#F58518", label="200")

    plt.yticks(y_pos, labels)
    plt.xlabel("数量")
    plt.ylabel("节目名称")
    plt.title("节目抓取覆盖率汇总（全量）")
    plt.legend(loc="upper right")

    # 在图中直接展示比值(可解析/已下载/200)，不化简，且左对齐显示。
    max_total = max(totals) if totals else 0
    label_x = max_total * 0.01 if max_total > 0 else 0.5
    for i in range(len(rows)):
        ratio_text = f"{totals[i]}/{downloaded[i]+ok200[i]}/{ok200[i]}"
        plt.text(label_x, y_pos[i], ratio_text, va="center", ha="left", fontsize=8, color="#1f2937")

    plt.tight_layout()

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=170)
    plt.close()


def aggregate_key(day: date, freq: str) -> str:
    if freq == "day":
        return day.isoformat()
    if freq == "week":
        iso_year, iso_week, _ = day.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if freq == "month":
        return f"{day.year:04d}-{day.month:02d}"
    raise ValueError(f"Unsupported frequency: {freq}")


def aggregate_stats(day_stats: Iterable[DayStat], freq: str) -> List[Dict[str, int]]:
    grouped: Dict[str, Dict[str, int]] = defaultdict(lambda: {
        "downloaded_count": 0,
        "identified_count": 0,
        "obtainable_200_count": 0,
    })

    for row in day_stats:
        k = aggregate_key(row.day, freq)
        grouped[k]["downloaded_count"] += row.downloaded_count
        grouped[k]["identified_count"] += row.identified_count
        grouped[k]["obtainable_200_count"] += row.obtainable_200_count

    out: List[Dict[str, int]] = []
    for period in sorted(grouped.keys()):
        item = {"period": period}
        item.update(grouped[period])
        out.append(item)
    return out


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator * 100.0 / denominator


def write_csv(path: Path, rows: List[Dict[str, object]], headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _figure_width(freq: str, points: int) -> float:
    if freq == "day":
        return min(max(16.0, points * 0.22), 64.0)
    if freq == "week":
        return min(max(14.0, points * 0.18), 28.0)
    return min(max(15.5, points * 0.20), 22.0)


def _x_tick_step(freq: str, points: int) -> int:
    if points <= 0:
        return 1
    if freq == "day":
        if points <= 60:
            return 1
        if points <= 120:
            return 2
        if points <= 240:
            return 4
        if points <= 500:
            return 7
        return 14
    if freq == "week":
        if points <= 30:
            return 1
        if points <= 60:
            return 2
        if points <= 120:
            return 4
        return 8
    if points <= 36:
        return 1
    if points <= 72:
        return 2
    return 3


def _font_missing_chars(font_path: str, chars: Iterable[str]) -> int:
    from matplotlib.ft2font import FT2Font

    font = FT2Font(font_path)
    cmap = font.get_charmap()
    return sum(1 for ch in chars if ord(ch) not in cmap)


def _pick_best_font(candidates: List[str], required_texts: List[str]) -> Tuple[Optional[str], List[str]]:
    """按字符覆盖情况选择最佳字体；优先选择能完全覆盖文本的字体。"""
    try:
        from matplotlib import font_manager
    except Exception:
        return None, []

    required_chars = sorted({ch for text in required_texts for ch in text if ch.strip()})
    if not required_chars:
        return candidates[0] if candidates else None, candidates

    best_font: Optional[str] = None
    best_missing = 10**9
    installed_names: List[str] = []

    for name in candidates:
        try:
            font_path = font_manager.findfont(
                font_manager.FontProperties(family=name),
                fallback_to_default=False,
            )
        except Exception:
            continue

        installed_names.append(name)
        missing_count = _font_missing_chars(font_path, required_chars)

        if missing_count == 0:
            return name, installed_names

        if missing_count < best_missing:
            best_missing = missing_count
            best_font = name

    return best_font, installed_names


def render_plot(path: Path, rows: List[Dict[str, int]], title: str, kind: str, freq: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("[WARN] matplotlib 不可用，跳过绘图。可安装: pip install matplotlib")
        return

    font_candidates = ["HYZhuZiMuTouRenW","Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans", "Consolas"]
    required_texts = [
        title,
        "时间",
        "数量",
        "已下载",
        "可识别",
        "可获取(200)",
    ]
    picked_font, installed_fonts = _pick_best_font(font_candidates, required_texts)

    if picked_font:
        # 自动切换: 找到最能覆盖字符的字体放在首位，其余按顺序回退。
        fallback_fonts = [f for f in font_candidates if f != picked_font and f in installed_fonts]
        plt.rcParams["font.sans-serif"] = [picked_font] + fallback_fonts
    else:
        # 无法探测时使用默认候选顺序。
        plt.rcParams["font.sans-serif"] = font_candidates

    plt.rcParams["axes.unicode_minus"] = False

    if not rows:
        return

    x = [r["period"] for r in rows]
    y_downloaded = [r["downloaded_count"] for r in rows]
    y_identified = [r["identified_count"] for r in rows]
    y_obtainable = [r["obtainable_200_count"] for r in rows]

    points = len(x)
    fig_w = _figure_width(freq, points)
    plt.figure(figsize=(fig_w, 6.2))
    idx = list(range(points))
    tick_step = _x_tick_step(freq, points)
    tick_positions = idx[::tick_step] if tick_step > 1 else idx
    tick_labels = [x[i] for i in tick_positions]

    if kind == "bar":
        width = 0.28
        plt.bar([i - width for i in idx], y_downloaded, width=width, label="已下载")
        plt.bar(idx, y_identified, width=width, label="可识别")
        plt.bar([i + width for i in idx], y_obtainable, width=width, label="可获取(200)")
    else:
        # 小端点更适合高密度时间序列      
        plt.plot(idx, y_obtainable, marker="o", markersize=2.2, linewidth=1.4, label="可获取(200)")
        plt.plot(idx, y_identified, marker="o", markersize=2.2, linewidth=1.4, label="可识别")
        plt.plot(idx, y_downloaded, marker="o", markersize=2.2, linewidth=1.4, label="已下载")

    plt.xticks(tick_positions, tick_labels, rotation=55, ha="right")

    plt.title(title)
    plt.xlabel("时间")
    plt.ylabel("数量")
    plt.legend(loc="upper right")
    plt.tight_layout()

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=160)
    plt.close()


def build_day_rows(
    downloaded: Dict[date, int],
    log_stats: Dict[date, Tuple[int, int]],
) -> List[DayStat]:
    all_days = sorted(set(downloaded.keys()) | set(log_stats.keys()))
    rows: List[DayStat] = []
    for d in all_days:
        identified, ok200 = log_stats.get(d, (0, 0))
        rows.append(
            DayStat(
                day=d,
                downloaded_count=downloaded.get(d, 0),
                identified_count=identified,
                obtainable_200_count=ok200,
            )
        )
    return rows


def format_report(day_rows: List[DayStat]) -> str:
    total_downloaded = sum(r.downloaded_count for r in day_rows)
    total_identified = sum(r.identified_count for r in day_rows)
    total_obtainable = sum(r.obtainable_200_count for r in day_rows)

    capped_downloaded_for_obtainable = min(total_downloaded, total_obtainable)
    pct_downloaded_of_obtainable = ratio(capped_downloaded_for_obtainable, total_obtainable)
    pct_downloaded_of_identified = ratio(total_downloaded, total_identified)
    pct_obtainable_of_identified = ratio(total_obtainable, total_identified)

    missing_vs_obtainable = max(total_obtainable - total_downloaded, 0)
    missing_vs_identified = max(total_identified - total_downloaded, 0)
    downloaded_excess_over_obtainable = max(total_downloaded - total_obtainable, 0)

    nonzero_days = [r for r in day_rows if (r.downloaded_count or r.identified_count or r.obtainable_200_count)]
    active_days = len(nonzero_days)

    lines = [
        "统计总览",
        "=" * 36,
        f"统计日期数: {len(day_rows)}",
        f"活跃日期数: {active_days}",
        f"已下载总数: {total_downloaded}",
        f"可识别总数: {total_identified}",
        f"可获取(200)总数: {total_obtainable}",
        "",
        "核心比例",
        "-" * 36,
        f"已获取/能获取(200): {pct_downloaded_of_obtainable:.2f}%",
        f"已获取/能识别: {pct_downloaded_of_identified:.2f}%",
        f"能获取(200)/能识别: {pct_obtainable_of_identified:.2f}%",
        "",
        "缺口估计",
        "-" * 36,
        f"相对可获取(200)尚缺: {missing_vs_obtainable}",
        f"超出可获取(200)计数: {downloaded_excess_over_obtainable}",
        f"相对可识别尚缺: {missing_vs_identified}",
    ]

    if nonzero_days:
        best_day = max(nonzero_days, key=lambda r: ratio(r.downloaded_count, r.obtainable_200_count))
        best_day_raw_pct = ratio(best_day.downloaded_count, best_day.obtainable_200_count)
        best_day_capped_pct = min(best_day_raw_pct, 100.0)
        lines.extend(
            [
                "",
                "附加信息",
                "-" * 36,
                (
                    f"下载覆盖率最高日期(相对200): {best_day.day.isoformat()} "
                    f"{best_day_capped_pct:.2f}% "
                    f"({best_day.downloaded_count}/{best_day.obtainable_200_count})"
                    f"，原始比值={best_day_raw_pct:.2f}%"
                ),
            ]
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计下载与日志中的文件可用性并输出图表")
    parser.add_argument("--downloads-dir", type=Path, default=Path("downloads"), help="下载目录，结构为 YYYY-MM-DD 子目录")
    parser.add_argument(
        "--logs-dirs",
        type=Path,
        nargs="+",
        default=[Path("logs")],
        help="一个或多个日志目录，例如: --logs-dirs logs logs-all",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("stats_out"), help="输出目录")
    parser.add_argument("--config-path", type=Path, default=Path("config.json"), help="配置文件路径，用于 code->节目名映射")
    parser.add_argument("--plot-kind", choices=["line", "bar"], default="line", help="图表类型")
    parser.add_argument(
        "--freqs",
        nargs="+",
        choices=["day", "week", "month"],
        default=["day", "week", "month"],
        help="输出聚合维度",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    downloaded = scan_downloaded_files(args.downloads_dir)
    downloaded_by_code = scan_downloaded_files_by_code(args.downloads_dir)
    merged_identified: Dict[date, int] = defaultdict(int)
    merged_200: Dict[date, int] = defaultdict(int)
    merged_identified_by_code: Dict[str, int] = defaultdict(int)
    merged_200_by_code: Dict[str, int] = defaultdict(int)

    config_path = args.config_path
    if not config_path.exists() and config_path.name == "config.json":
        fallback = Path("config_example.json")
        if fallback.exists():
            config_path = fallback

    for logs_dir in args.logs_dirs:
        partial = scan_log_dir(logs_dir)
        for day, (identified, ok200) in partial.items():
            merged_identified[day] += identified
            merged_200[day] += ok200

        partial_identified_by_code, partial_200_by_code = scan_log_dir_by_code(logs_dir)
        for code, n in partial_identified_by_code.items():
            merged_identified_by_code[code] += n
        for code, n in partial_200_by_code.items():
            merged_200_by_code[code] += n

    log_stats: Dict[date, Tuple[int, int]] = {}
    for day in set(merged_identified) | set(merged_200):
        log_stats[day] = (merged_identified.get(day, 0), merged_200.get(day, 0))

    day_rows = build_day_rows(downloaded, log_stats)

    # 日维度详细数据
    day_table: List[Dict[str, object]] = []
    for r in day_rows:
        day_table.append(
            {
                "period": r.day.isoformat(),
                "downloaded_count": r.downloaded_count,
                "identified_count": r.identified_count,
                "obtainable_200_count": r.obtainable_200_count,
                "downloaded_over_obtainable_200_pct": f"{ratio(r.downloaded_count, r.obtainable_200_count):.2f}",
                "downloaded_over_identified_pct": f"{ratio(r.downloaded_count, r.identified_count):.2f}",
                "obtainable_200_over_identified_pct": f"{ratio(r.obtainable_200_count, r.identified_count):.2f}",
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.out_dir / "stats_day.csv",
        day_table,
        headers=[
            "period",
            "downloaded_count",
            "identified_count",
            "obtainable_200_count",
            "downloaded_over_obtainable_200_pct",
            "downloaded_over_identified_pct",
            "obtainable_200_over_identified_pct",
        ],
    )

    # 多维度聚合与绘图
    for freq in args.freqs:
        agg_rows = aggregate_stats(day_rows, freq)
        write_csv(
            args.out_dir / f"stats_{freq}.csv",
            agg_rows,
            headers=["period", "downloaded_count", "identified_count", "obtainable_200_count"],
        )
        render_plot(
            args.out_dir / f"compare_{freq}.png",
            agg_rows,
            title=f"已下载/可识别/可获取(200) 对比 - {freq}",
            kind=args.plot_kind,
            freq=freq,
        )

    code_name_map = load_code_name_map(config_path)
    program_rows = build_program_coverage_rows(
        downloaded_by_code=downloaded_by_code,
        identified_by_code=dict(merged_identified_by_code),
        obtainable_200_by_code=dict(merged_200_by_code),
        code_name_map=code_name_map,
    )
    write_csv(
        args.out_dir / "program_coverage.csv",
        program_rows,
        headers=[
            "program_name",
            "codes",
            "downloaded_count",
            "identified_count",
            "obtainable_200_count",
            "downloaded_over_obtainable_200_pct",
            "downloaded_over_identified_pct",
            "obtainable_200_over_identified_pct",
        ],
    )
    render_program_coverage_plot(args.out_dir / "program_coverage.png", program_rows)

    report = format_report(day_rows)
    report_path = args.out_dir / "summary.txt"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print("\n输出文件:")
    print(f"- {args.out_dir / 'stats_day.csv'}")
    for freq in args.freqs:
        if freq != "day":
            print(f"- {args.out_dir / f'stats_{freq}.csv'}")
        print(f"- {args.out_dir / f'compare_{freq}.png'}")
    print(f"- {args.out_dir / 'program_coverage.csv'}")
    print(f"- {args.out_dir / 'program_coverage.png'}")
    print(f"- {report_path}")


if __name__ == "__main__":
    main()
