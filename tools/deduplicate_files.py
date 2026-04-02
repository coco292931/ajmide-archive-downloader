import hashlib
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# ============================
# 直接在这里修改默认配置（无需环境变量）
# ============================
DEFAULT_TARGET_ROOT = "downloads"
TRASH_DIR_NAME = "del"
HASH_CHUNK_SIZE = 1024 * 1024
DATE_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SUFFIX_PATTERN = re.compile(r"^(?P<base>.+?)(?:_(?P<idx>\d+))?$")


@dataclass
class FileItem:
    path: Path
    date_dir: str
    ext: str
    base_name: str
    suffix_idx: int
    size: int


def parse_name(stem: str) -> tuple[str, int]:
    match = SUFFIX_PATTERN.match(stem)
    if not match:
        return stem, 0
    base = match.group("base")
    idx = match.group("idx")
    return base, int(idx) if idx is not None else 0


def calculate_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def collect_files(root: Path) -> list[FileItem]:
    items: list[FileItem] = []
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        if date_dir.name == TRASH_DIR_NAME:
            continue

        for file_path in sorted(date_dir.glob("*")):
            if not file_path.is_file():
                continue
            base, idx = parse_name(file_path.stem)
            items.append(
                FileItem(
                    path=file_path,
                    date_dir=date_dir.name,
                    ext=file_path.suffix.lower(),
                    base_name=base,
                    suffix_idx=idx,
                    size=file_path.stat().st_size,
                )
            )
    return items


def group_candidates(items: list[FileItem]) -> dict[tuple[str, str, str], list[FileItem]]:
    grouped: dict[tuple[str, str, str], list[FileItem]] = defaultdict(list)
    for item in items:
        key = (item.date_dir, item.base_name.lower(), item.ext)
        grouped[key].append(item)

    candidates: dict[tuple[str, str, str], list[FileItem]] = {}
    for key, group in grouped.items():
        # 只处理带 _数字 后缀的候选组
        if any(x.suffix_idx > 0 for x in group):
            candidates[key] = sorted(group, key=lambda x: (x.suffix_idx, x.path.name.lower()))
    return candidates


def ensure_target_name(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    counter = 1
    while True:
        candidate = target_path.with_name(f"{stem}__dupmove{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_duplicate(file_item: FileItem, root: Path) -> Path:
    date_segment = file_item.date_dir if DATE_DIR_PATTERN.match(file_item.date_dir) else "unknown-date"
    target_dir = root / TRASH_DIR_NAME / date_segment
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = ensure_target_name(target_dir / file_item.path.name)
    shutil.move(str(file_item.path), str(target_path))
    return target_path


def deduplicate(root: Path) -> None:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"目录不存在或不是文件夹: {root}")

    print(f"实际处理目录: {root.resolve()}")

    items = collect_files(root)
    candidates = group_candidates(items)

    checked_groups = 0
    moved_count = 0

    for _, group in sorted(candidates.items(), key=lambda kv: kv[0]):
        checked_groups += 1

        # 先按大小聚类，再按哈希确认，保留最小 suffix_idx 的第一个文件
        size_groups: dict[int, list[FileItem]] = defaultdict(list)
        for item in group:
            size_groups[item.size].append(item)

        for same_size_items in size_groups.values():
            if len(same_size_items) < 2:
                continue

            hash_groups: dict[str, list[FileItem]] = defaultdict(list)
            for item in same_size_items:
                digest = calculate_sha256(item.path)
                hash_groups[digest].append(item)

            for digest_items in hash_groups.values():
                if len(digest_items) < 2:
                    continue

                digest_items = sorted(digest_items, key=lambda x: (x.suffix_idx, x.path.name.lower()))
                keep = digest_items[0]
                duplicates = digest_items[1:]

                for dup in duplicates:
                    target = move_duplicate(dup, root)
                    moved_count += 1
                    print(f"移动重复文件: {dup.path} -> {target} (保留: {keep.path.name})")

    print("\n去重完成")
    print(f"扫描候选组: {checked_groups}")
    print(f"移动重复文件数: {moved_count}")


def main() -> None:
    user_input = input(f"请输入要处理的根目录（默认: {DEFAULT_TARGET_ROOT}）: ").strip()
    user_input = user_input.strip('"').strip("'")
    target_root = Path(user_input or DEFAULT_TARGET_ROOT)
    deduplicate(target_root)


if __name__ == "__main__":
    main()
