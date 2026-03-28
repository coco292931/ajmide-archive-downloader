# ajmide-archive-downloader

阿基米德历史节目（往期）下载器

## 说明

此项目是为了纪念Hit FM而生，也同样为了纪念那些离我们而去的声音

这个我从小学就开始听，陪伴我近9年的电台，在25年12月23日零时，永久沉寂了。。

不能说有多伤感，因为时代就是如此发展，电台终将会淡出人们的视野，

只是这次，恰好轮到887而已。

在这曲终人散之时，趁着阿基米德尚存有Hit FM的回放，故写这样一个下载器，保存下来曾经的回忆

## 原理

作为开始，一般来说，我们只需要拿到节目对应的`brand?id`即可，就像这个网址：[阿基米德 - 音乐会旅行](https://m.ajmide.com/m/brand?id=10600723) ，使用浏览器打开后，会发现它自动访问了这个接口：
`https://a.ajmide.com/v33/brand_head.php?brandId=10600723` （只保留必要值）

```json
{
  "code": "0",
  "data": {
    "capacity": [
      {
        "history": {
          "list": [
            [
              {
                "phId": "92605457",
                "topicId": "60667593",
                "producer": "音乐会旅行",
                "author_id": "10600723",
                "programId": "26916",
                "author_name": "音乐会旅行",
                "brand_id": "10600723",
                "programName": "音乐会旅行",
                "presenter": "菡子",
                "subject": "20260327 音乐会旅行",
                "schedule": "13:00-15:00(1-5)",
                "postTime": "2026-03-27 13:00:00",
                "audioAttach": [
                  {
                    "imgPath": "https:\\/\\/img-ossimg-qn.ajmide.com\\/c_up\\/26916.jpg",
                    "subject": "20260327 音乐会旅行",
                    "description": "音乐会旅行",
                    "phId": "92605457",
                    "liveUrl": "https:\\/\\/ia-bk-i.ajmide.com\\/c_18177\\/20260327\\/18177_20260327_1300.m4a",
                    "audioTime": "6905",
                    "isCut": null,
                    "skipHead": "0",
                    "count": 1,
                    "history_type": "1",
                    "schedule": "13:00"
                  }
                ],
              }
            ]
          ],
          "week": "0",
          "liveTime": "13:00-15:00(1-5)",
          "total": "4",
          "now": 1774713600,
          "start": 1517893200,
          "end": 1774846800,
          "current": 1774787163,
          "chinese": "周一至周五13:00-15:00"
        }
      }
    ]
  },
  "message": "",
  "meta": []
}
```

然后就能直接拿到下载地址

```json
"liveUrl": "https:\\/\\/ia-bk-i.ajmide.com\\/c_18177\\/20260327\\/18177_20260327_1300.m4a",
```

但不幸的是，在我写这个代码的前两天（大概是25/3/22左右），阿基米德的hitfm内容全面隐藏，无法直接通过访问网站得到，例如：[阿基米德 - New Music Express新音乐速递](https://m.ajmide.com/m/brand?id=10607663) ，现在打开时已经是空白，访问上述接口也只传空值，只能另辟蹊径。
偶然间，我发现节目下面由用户发布的“前刀”节目依然保留，进入后有剪辑节目的链接。点击链接后虽然跳转到空白页面，但是阿基米德仍然在后台播放了对应节目。通过http toolkit手机抓包分析，指向了一个重要接口：

```bash
https://a.ajmide.com/v18/get_play_list.php?t=t&phid=60068136
```

其中，phid是对应节目的连接（这和上面节目列表的不是一个东西），我推测是按照一定规则生成的流水号码，以此为例，60068136这串数字很可能代表22.3.30当晚的NME节目。

访问这个链接后，我们就得到了对应节目的数据如下（精简版，已转义）：

```json
{
  "code": "0",
  "data": [
    {
      "liveUrl": "http://ia-bk-i.ajmide.com/c_473/20220330/473_20220330_1900.m4a",
      "brandId": "10607663",
      "author_id": "10607663",
      "programId": "10301",
      "name": "New Music Express新音乐速递",
      "imgPath": "https://upload-qn.ajmide.com/p/image/202107/30/340-5xzfdbZ8Yk1627620999672_499x499.jpg",
      "producer": "CRI劲曲调频",
      "presenter": "hacar",
      "postTime": "2022-03-30 19:00:00",
      "liveTime": "03:00:00",
      "shareIntro": "这期节目太精彩太好听了！推荐大家听听，错过会后悔哦~",
      "schedule": "19:00-22:00(1-5)",
      "topicId": "36089025",
      "phid": "60068136",
      "intro": "主播:hacar\n晚间音乐分享,与主持DJ一起享受晚上的自由音乐时光!",
      "programType": 2,
      "shareUrl": "http://ia-bk-i.ajmide.com/c_473/20220330/473_20220330_1900.m4a",
      "sharetitle": "20220330 new music express（New Music Express新音乐速递）",
      "sharecontent": "new music express",
      "subject": "20220330 new music express",
      "subTitle": "20220330 new music express",
      "author_name": "New Music Express新音乐速递",
      "url": "https://upload-qn.ajmide.com/p/image/202107/30/340-5xzfdbZ8Yk1627620999672_499x499.jpg",
      "content": "20220330 new music express",
      "musicTime": "10800"
    }
  ],
  "message": "",
  "meta": {}
}
```

然后就有了节目地址:

```bash
"liveUrl": "http://ia-bk-i.ajmide.com/c_473/20220330/473_20220330_1900.m4a",
"shareUrl": "http://ia-bk-i.ajmide.com/c_473/20220330/473_20220330_1900.m4a""
```

不过事情还没结束，因为473这个代号，似乎只对应New Music Express这一个节目，要想找齐其他所有节目，就要对每一个板块重复上述流程。不过对于一串phid，相邻的几个很有可能是同一个电台的，这样可以减少筛选难度。例如 53570312~53570316 就都是hitfm的。不过就像刚才说的，phid是一个流水代号，所以很有可能重复，且相邻的间隔极大，并不推荐暴力破解，而优先考虑从相邻入手。

经过一番操作，终于拿到了代号表格：


###电台 ID 对照表参考

节目名称 编号 播出时间
morning hits 460    07:00-10:00(1-5)
hit morning show 461    07:00-10:00(1-5)
at40 462    08:00-12:00(6),12:00-16:00(7)
ost 465    16:00-18:00(7)
hit the road 467    12:00-14:00(6)
Rock dj 470    16:00-18:00(6)
BDH 471    16:00-19:00(1-5)
top20 472    18:00-20:00(6-7)
New Music Express 473    19:00-22:00(1-5)
hit fm dance 475    22:00-23:59(1-7)
morning call 20276    06:00-07:00(1-5)
Weekend morning show 20277    08:00-12:00(6,7)
soul make 20278    14:00-16:00(6)
at work network 20279    10:00-13:00(1-5)
lazy afternoon 20280    13:00-16:00(1-5)
Hit FM Dance Carta & Co. 电音 - 卡塔 54502    20:00-22:00(7)
ctdm 未知
music flow 未知



可惜的是，中国电子音乐巅峰榜和music flow没有对应前刀节目，相应的代号经粗略爆破并未获得，希望有uu能获取到。

最后，我们使用下方链接下载对应节目即可

```bash
http://ia-bk-i.ajmide.com/c_{code}/{YYYYMMDD}/{code}_{YYYYMMDD}_{HHmm(start_time).m4a
```

## 功能与使用说明

目前提供了命令行与图形化（GUI）两套操作逻辑：

### 1. 命令行使用

```bash
# 单日下载
python downloader.py -d "25-12-22" -b 662

# 多连日下载（跨度下载），并在每天中间延迟3秒
python downloader.py -d "22-07-01 to 25-12-22" -b 662 --delay 3

# 下载低码率音频，且不下载封面图片，同时指定输出目录为 my_radio_folder
python downloader.py -d "25-12-22" -b 662 -o "my_radio_folder" --low-bitrate --no-images

# 仅下载节目名匹配正则的节目，并用模板自定义输出路径/文件名
python downloader.py -d "25-12-22" -b 662 --name-regex "Music|Morning" --filename-template "{date}\\{id}_{name_en}"
```

**所有支持的命令行参数：**

- `-h`, `--help` : 显示帮助信息。
- `-d DATE`, `--date DATE` : 指定单独日期 (如 `'25-12-22'`) 或日期范围 (如 `'25-11-22 to 25-12-22'`)。
- `-b BROADCAST`, `--broadcast BROADCAST` : 电台ID，默认 `662` (Hit FM)。
- `-o OUTDIR`, `--outdir OUTDIR` : 下载的基础输出目录，默认为 `downloads`。
- `--low-bitrate` : 选择下载低码率音频 (默认情况为下载高码率，带此参数则切换低码率以节省空间)。
- `--no-images` : 阻止下载节目封面图片。
- `--api-key API_KEY` : 用于API鉴权的固定密钥参数（非必要一般无需更改）。
- `--delay DELAY` : 当执行多日持续下载时，请求日期间隔的睡眠时间(秒)，默认 `1.5`。
- `--name-regex NAME_REGEX` : 节目名正则筛选，仅下载匹配的节目（默认空，即不过滤）。
- `--filename-template FILENAME_TEMPLATE` : 自定义输出模板（默认 `{date}\\{name}`，支持 `{id}` `{name}` `{date}` `{name_ch}` `{name_en}` `{bitrate}` `{start_time}` `{end_time}`；其中 `{bitrate}` 输出 `High/Low`）。

说明：Windows 文件系统不允许 `:` `*` `?` 等字符，模板渲染后若包含这些字符，程序会自动转换为对应全角字符以保证可落盘。

高级配置（仅 `config.json`，不在 UI 暴露）：

- `max_rate_kbps`：下载限速（单位 KB/s）。`0` 表示不限速。

### 2. GUI 界面操作 (推荐)

直接运行 `python gui.py` 唤出界面。
**核心特性：**

- **可视化参数调整**：在界面输入日期范围（支持单日或多日）、电台 ID，或是更改保存目录、控制防封禁请求延迟，并支持节目名正则筛选和文件名模板（含自定义子目录）。相关的配置会自动保存到同目录下的 `config.json` 内作为默认预设。
- **模板预览区**：下载页新增“文件名模板预览”，固定以 `Morning Call 音乐叫早` 作为示例，实时展示模板渲染后的完整输出路径。
- **自定义下载项**：可以选择获取默认的高码率音频或是节省空间的低码率；可以选择是否连带下载音频的封面图资源。
- **防止重复与元数据映射**：图片只下载一次（以 `downloaded_images.txt` 缓存），并且按对应节目的名字被重命名，源链接信息保存在 `images_info.txt` 中。下载目录会以日期按规则分类，并在文件夹内生成当天的抓取记录报告 `YYYY-MM-DD_program_info.txt`，包含实际下载的高/低音质标识。
- **二段停止模式 (防烂尾机制)**：
  - 下载过程所有的文件采用 `.part` 缓存形式写入；连接意外中断或主动终止后不会污染目录。
  - **暂停/恢复**：随时中断/恢复主下载线程与转换线程。
  - **软停止**：结束当前文件后自动取消随后的全部任务队列，包含转换队列。
  - **强行停止**：即便正在执行途中，立刻截断释放资源，并彻底清理残断文件与子进程。
- **配置持久化**：退出时系统会自动比对参数差异并防错弹窗提示，避免丢失辛苦调好的配置。所有诸如路径偏好均为干净相对路径标准（如 `"downloads"`）存放于 `config.json`，方便跨设备携带。

## 自动化后处理 (格式转换管线)

//这个是yunting-downloader留下的自动转换管线，对于阿基米德的低码率而言其实完全没有必要使用 （

虽然 m4a 已经比较高效，但是如果全部按高码率保存节目，对储存依然是一笔不小的开销。
通过指定本地 FFmpeg（内置环境检测），图形界面原生支持了**异步多线程自动转换管线**功能：

1. **并行解耦，边下边压**：将下载和转换彻底分作两条完全独立的任务线运作，并通过动态队列衔接。当下载完成某集后，系统将其立即投喂给后处理队列进行降码/转码操作，而下载线程刻不容缓并发拉取下一集，双轨齐发，大幅度缩减耗时！双日志窗（下载与FFmpeg）能实时观测交响乐般的同步执行态。
2. **丰富的转码规格参数**：
   - 支持向 `opus`, `mp3`, `aac`, `m4a` 目标重混流并细控采样率（防 Opus 规范等报错）、固定压缩码率及调用 CPU 线程数。
   - 提供 “跳过现有 / 仅覆盖 0kb 残除 / 全量覆盖” 的3态安全覆写保护。
   - 自由设定独立输出文件夹，也可原地安全覆盖并搭配【转换成功后删除原文件】一键式瘦身。
3. **封面图自动反嵌**：能够监测源同名或源下载图片，并运用 ffmpeg 将其作为【专辑封面素材】反向无损硬写入最终的音频内部（**注：Opus 格式使用原生的 FFmpeg 无法直接嵌入图片流，如果你需要为 Opus 音频嵌入封面，可见下方进阶替代方案**）。
4. **批处理人工干预排队**：系统更支持扫描单日或全集目录寻找遗漏文件，预先生成批处理终端命令清单；用户甚至可在命令编辑区自由增删改查单条命令执行。

#### 📖 进阶：如何为 Opus 封装格式嵌入封面？

目前直接通过 `FFmpeg` 转码为 Opus/Ogg 容器时，因底层容器不支持将图片作为独立视频流打包，直接写入会报错退出。如果您**必须**为 `.opus` / `.ogg` 文件附带封面，建议采用以下两种常用替代方案进行二次处理：

* **方案A：使用 Python 的 `mutagen` 库（推荐）**
  这是最纯净的办法。先通过 FFmpeg 将音频转码为您需要的 `.opus`（不在 ffmpeg 内拼接图片），接着编写一个小脚本，引入 `mutagen` 库。读取事先备好的封面图片并转化为 Base64 编码，最终作为 `METADATA_BLOCK_PICTURE` 这个特定的 Vorbis Comment 标签无损硬写到 `.opus` 之中。
* **方案B：使用官方的 `opusenc` 命令行工具**
  不再直接令 FFmpeg 压缩 opus，而是让其剥离图片纯粹导出无损的 `.wav` 临时音频流。随后调用 Xiph 官方维护的命令行工具，通过 `opusenc --picture cover.jpg input.wav output.opus`，一键令其在编码音频的同时自动妥善完成 Base64 处理封面并合成。

## 维护者快速入口（供后续修改）

为了便于后续接手，本项目可按下面的分层理解：

- `downloader.py`：负责接口签名、节目列表请求、音频/图片下载与落盘。
- `converter.py`：只负责 FFmpeg 检测和命令拼装，不直接执行子进程。
- `gui.py`：负责 UI、状态机（暂停/软停/强停）、任务调度与下载/转码串联。

核心调用链如下：

1. GUI 启动下载：`start_download_thread -> run_download -> download_by_date`。
2. 单文件下载完成后，`downloader.py` 通过 `post_process_cb` 回调通知 GUI。
3. GUI 侧生成 FFmpeg 命令并执行（自动队列或手动批处理）。

后续改动时，建议优先关注这些“联动点”：

- 若修改 `download_by_date(...)` 参数：同步调整 `gui.py` 的调用位置与 README 参数说明。
- 若修改 `build_ffmpeg_cmd(...)` 参数：同步调整 GUI 命令生成、配置读写字段。
- 若新增配置项：同步更新 GUI 变量初始化、`load_config/save_config`、`config_example.json`、README。

推荐最小自检：

- `python -m py_compile gui.py downloader.py converter.py`
- `python gui.py`
- `python downloader.py --help`

### GitHub Actions 自动打包（Windows/macOS/Linux）

仓库已提供工作流文件：`.github/workflows/build-multi-platform.yml`

触发方式：

1. 手动触发：
   
   - 打开 GitHub 仓库的 Actions 页面。
   - 选择 `Build Multi-Platform Releases`。
   - 点击 `Run workflow`，输入版本号（如 `1.0.0`）。
   - 工作流会自动构建三平台二进制，并创建/更新对应版本的 GitHub Release。

2. 发布触发（推荐）：
   
   - 推送符合 `v*` 规则的 tag（如 `v1.0.1`）。
   - 工作流会自动构建三平台二进制，并自动创建 GitHub Release，上传附件。
   - 每个平台会同时生成 GUI 版与 CLI 版（`downloader.py`）。

发布附件命名规则：

- `ajmide-archive-downloader_windows_V1.0.0.exe`
- `ajmide-archive-downloader_linux_V1.0.0.tar.gz`
- `ajmide-archive-downloader_macos_V1.0.0.tar.gz`
- `ajmide-archive-downloader_windows_V1.0.0_CLI.exe`
- `ajmide-archive-downloader_linux_V1.0.0_CLI.tar.gz`
- `ajmide-archive-downloader_macos_V1.0.0_CLI.tar.gz`

示例命令：

```bash
git tag v1.0.1
git push origin v1.0.1
```

注意：

- 若仓库未允许工作流写入 Release，请到仓库 Settings -> Actions -> General，将 Workflow permissions 设为 `Read and write permissions`。
- 当前仅 Windows 使用 `vtfts-knkbe-001.ico` 图标；macOS 如需图标请准备 `.icns` 并在工作流里单独加参数。

## 注意事项



本工具仅供学习使用，请勿用作非法用途