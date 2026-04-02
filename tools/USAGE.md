# tools 目录脚本使用说明

本文档说明 `tools/` 目录下各脚本的用途与常见运行方式。

## 使用前说明

- 建议始终在项目根目录执行命令。
- 下面命令均以项目根目录为当前目录（cwd）。
- 默认配置文件优先读取 `config.json`，不存在时部分脚本会回退到 `config_example.json` 或内置配置。

## 1) download_from_logs.py

用途：

- 从 `logs/` 目录中的 `*_successful_parses.txt` 读取下载链接并批量补下载。
- 支持仅下载 403 项、按日期范围筛选、403 时切换到候选 IP 解析重试。

常用命令：

```bash
# 下载 logs 里所有记录
python .\tools\download_from_logs.py

# 仅下载日志中标记 403 的记录
python .\tools\download_from_logs.py --403-first true

# 开启 403 时 DNS 候选 IP 回退
python .\tools\download_from_logs.py --403-first true --enable-resolve true

# 指定日期范围（支持反向）
python .\tools\download_from_logs.py -d "2026-03-31 to 2016-03-31"

# 自定义输出目录
python .\tools\download_from_logs.py -o downloads
```

主要参数：

- `--403-first true|false`
- `-d, --date "YYYY-MM-DD to YYYY-MM-DD"`
- `-o, --output <目录>`
- `--enable-resolve true|false`
- `--resolve host:port:ip`（可重复传入）

## 2) log_successful_parses.py

用途：

- 按日期和节目配置探测节目 URL 可达性，生成按月日志文件到 `logs-all/`。
- 输出内容包含文件名、节目时间、解析状态、下载链接、请求头。

运行方式：

```bash
python .\tools\log_successful_parses.py
```

配置方式：

- 该脚本不走命令行参数，直接在文件顶部修改：
- `START_DATE`, `END_DATE`
- `OUTPUT_DIR`
- `CONFIG_PATH`
- `READ_TIMEOUT_SECONDS`, `REQUEST_INTERVAL_SECONDS`, `CONNECT_TIMEOUT_SECONDS`

## 3) traverse_cdn_for_primary200.py

用途：

- 从 `logs-all/` 中筛选“成功(主链路200)”记录，遍历候选 CDN IP 做连通性探测。
- 仅控制台输出，不下载文件、不写结果文件。

运行方式：

```bash
python .\tools\traverse_cdn_for_primary200.py
```

可在文件顶部修改：

- `LOGS_DIR`
- `CONNECT_TIMEOUT_SECONDS`, `READ_TIMEOUT_SECONDS`
- `REQUEST_INTERVAL_SECONDS`
- `MAX_200_PER_RECORD`
- `DEFAULT_RESOLVE_RULES`

## 4) analyze_archive_stats.py

用途：

- 统计下载目录与日志目录中的数据覆盖情况。
- 输出按日/周/月的 CSV、对比图，以及节目维度覆盖表（`program_coverage.csv`）。

常用命令：

```bash
python .\tools\analyze_archive_stats.py --downloads-dir .\downloads --logs-dirs .\logs .\logs-all --out-dir .\stats_out --plot-kind line
```

主要参数：

- `--downloads-dir <目录>`
- `--logs-dirs <目录1> <目录2> ...`
- `--out-dir <输出目录>`
- `--config-path <配置文件>`
- `--plot-kind line|bar`
- `--freqs day week month`

## 5) rebuild_info_from_files.py

用途：

- 基于本地已下载音频文件名，按节目时段规则重建每日 `*_program_info.txt`。
- 适合补齐历史下载目录中的信息文件。

常用命令：

```bash
# 按 config.json / config_example.json 中 output_dir 处理
python .\tools\rebuild_info_from_files.py

# 指定目录和日期范围
python .\tools\rebuild_info_from_files.py --o downloads --d "2023-03-01 to 2023-03-31"

# 仅预览，不写入
python .\tools\rebuild_info_from_files.py --dry-run
```

主要参数：

- `--o <下载根目录>`
- `--config <配置文件路径>`
- `--d <单日或范围>`
- `--dry-run`

## 6) deduplicate_files.py

用途：

- 对下载目录按“日期目录 + 基础文件名 + 扩展名”分组选取重复候选。
- 通过大小 + SHA256 校验重复文件后，将重复项移动到 `del/<日期>/`。

运行方式：

```bash
python .\tools\deduplicate_files.py
```

说明：

- 脚本启动后会提示输入目标根目录，直接回车使用默认 `downloads`。
- 默认仅处理带 `_数字` 后缀的重复候选。
