# ajmide-archive-downloader

阿基米德历史节目（往期）下载器

## 目录

1. [说明](#说明)
2. [写在前面](#写在前面)
3. [文件目录](#文件目录)
4. [原理](#原理)

## 说明

此项目是为了纪念Hit FM而生，也同样为了纪念那些离我们而去的声音

这个我从小学就开始听，陪伴我近9年的电台，在25年12月23日零时，永久沉寂了。。

不能说有多伤感，因为时代就是如此发展，电台终将会淡出人们的视野，

只是这次，恰好轮到887而已。

在这曲终人散之时，趁着阿基米德尚存有Hit FM的回放，故写这样一个下载器，保存下来曾经的回忆

## 写在前面

本工具是[云听历史节目下载器](https://github.com/coco292931/yunting-archive-downloader)的衍生项目，如果你需要近几年（每个电台不一样）的高质量音频内容，强烈建议你先去那里看看，那里配置更简单轻松，操作步骤也相对较少，是小白友好型项目。

由于本项目的核心目的是获取hitfm历史节目的下载链接，然而因为阿基米德官方隐藏内容，导致现在不能从hitfm的节目信息页获取到任何有价值的信息，所以本工具暂时不支持直接从节目信息页自动抓取音频文件（对于能打开节目信息页面的，这并不难，具体方法可以看原理的开头部分）。并且由于阿基米德文件保存逻辑，暂时只能通过手动配置文件来实现解析（具体方法和核心代码在原理部分可以找到）。

工具本身预先写入了hitfm的解析配置，运行release里面的发布文件即可无需配置下载hitfm历史节目。如果你需要下载其他电台节目，请按照下方原理指示寻找并配置对应的phid和c_id（理论上只要是广播类型的节目就都可以使用这个方法）。

## 文件目录

```bash
│  downloader.py  # 下载器核心代码
│  converter.py  # ffmpeg转换代码
│  favicon.ico
│  gui.py # UI界面核心代码
│  LICENSE
│  README.md
├─.github
│  └─workflows
│       # github action对应文件
├─ajmd-res
│       # 本文件夹存放phid爆破的响应文件，方便后续再进行分析
├─images_all
│       # 本文件夹存放节目图片 txt中是图片对应信息
```

## 原理

本部分以解析hitfm节目为例；本方法理论上适用于所有广播类型的节目（只要能打开对应详情页或者能找到对应的前刀节目）。

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
"liveUrl": "https://ia-bk-i.ajmide.com/c_18177/20260327/18177_20260327_1300.m4a",  //注意需要转义掉斜杠
```

但不幸的是，在我写这个代码的前两天（大概是25/3/24左右），阿基米德的hitfm内容全面隐藏（经检查，大部分的广播详情页面都受到了影响），无法直接通过访问网站得到，例如：[阿基米德 - New Music Express新音乐速递](https://m.ajmide.com/m/brand?id=10607663) ，现在打开时已经是空白，访问上述接口也只传空值，只能另辟蹊径。

偶然间，我发现节目下面由用户发布的“前刀”节目依然保留，进入后有能点击跳转被剪辑的节目，虽然跳转到空白页面，但是阿基米德app仍然成功解析了音频并开始播放。

通过http toolkit手机抓包分析，指向了一个重要接口：

```bash
https://a.ajmide.com/v18/get_play_list.php?t=t&phid=60068136
```

其中，phid是对应节目的连接（这和上面的brand?id不是一个东西），我推测是按照一定规则生成的流水号码，例如60068136这串数字很可能代表22.3.30当晚的NME节目。

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
"shareUrl": "http://ia-bk-i.ajmide.com/c_473/20220330/473_20220330_1900.m4a"
```

不过事情还没结束，因为473这个代号（暂且称做c_id），似乎只对应New Music Express这一个节目，要想找齐其他所有节目，就要对每一个板块重复上述流程。不过好在对于一串phid，相邻的几个很有可能是同一个电台的，这样大幅降低了搜索难度。例如 53570312~53570316 就都是hitfm的。不过就像刚才说的，phid是一个流水代号，所以很有可能出现好几个phid都指向同一个节目的情况，并且不同日期的phid间隔可能极大，并不推荐从phid暴力破解，而优先考虑从相邻入手。

当然你也可以从c_id进行推理，不过由于其要求时间节点也要对应，且返回的**除文件本身外没有别的任何信息**，还需要花时间推测属于哪一档节目，也是不太划算的。我建议只有在使用phid找得差不多的时候，再通过c_id寻找收益更高。

phid相邻爆破精简版代码如下：

```python
import requests, json, time, os

TARGET = "CRI\u52b2\u66f2\u8c03\u9891"  #指定搜索的producer名，在这里是 CRI劲曲调频 
HEADERS = {
    "Accept-Encoding": "gzip", "Authorization": "uauth", "Connection": "Keep-Alive",
    "Host": "a.ajmide.com", "If-Modified-Since": "Sat, 28 Mar 2026 12:36:07 GMT",
    "User-Agent": "ajmd/4.0.2 (Android 10; HLK-AL00; 7820948e-f866-3e84-abbd-abxxxxb30ae6; ajmd; 7820948e-f866-3e84-abbd-abxxxxb30ae6)"  #设备UA定义，模拟阿基米德app
}
SAVE_DIR = r"C:\cri_output"  #在这里选择响应json文件保存目录
os.makedirs(SAVE_DIR, exist_ok=True)

idx = 1
for phid in range(60068136, 60069137):  #指定搜索范围 （从60068136到60069136）
    try:
        data = requests.get(f"https://a.ajmide.com/v18/get_play_list.php?t=t&phid={phid}", headers=HEADERS, timeout=10).json()
        matched = [x for x in data.get("data", []) if x.get("producer") == TARGET]  #如果你想搜索其他字段，修改这里的producer
        if matched:
            with open(os.path.join(SAVE_DIR, f"{idx:04d}.json"), "w", encoding="utf-8") as f:
                json.dump({"phid": phid, "matched_items": matched}, f, ensure_ascii=False, indent=2)
            print(f"phid={phid} ✓ → {idx:04d}.json")
            idx += 1
        else:
            print(f"phid={phid} -")
    except Exception as e:
        print(f"phid={phid} 失败: {e}")
    time.sleep(0.3)
```

c_id相邻爆破精简版代码如下：

```python
import requests, time
from datetime import date, timedelta

CHANNELS = [x for x in range(450,480)] # c_id频道列表范围
print(CHANNELS)
START = date(2015, 4, 24) # 开始寻找的日期，这里使用周5,6,7进行破解，这样对节目的覆盖率更高。（然而日期越老，能获取到文件的概率就越小，建议多增加几个日期）
END   = date(2015, 4, 26)
HOURS = [f"{h:02d}00" for h in range(24)] # 这里设置时间规则，此处是24小时整点
#HOURS += [f"{h:02d}30" for h in range(24)] # 取消注释这一行可以加入半点的枚举。请结合电台自行修改

day = START
while day <= END:
    d = day.strftime("%Y%m%d")
    for ch in CHANNELS:
        for h in HOURS:
            url = f"http://ia-bk-i.ajmide.com/c_{ch}/{d}/{ch}_{d}_{h}.m4a"
            #print(url)
            try:
                r = requests.head(url, timeout=5)
                if r.status_code == 200:
                    print(f"✓ {url}")
            except:
                pass
            time.sleep(0.5)
    day += timedelta(days=1)
    print('='*20)

```

c_id爆破后会输出一系列能访问的音频文件链接，点击链接收听筛选即可。

经过一番操作，终于拿到了代号表格： `在爆破时发现，easy fm 的c_id与hit fm紧邻，如果你正在进行easy fm的搜索工作，你可以优先从ajmd-res文件夹内的phid和下方的c_id入手`

| 节目名称 | c_id | 播出时间 |
| --------- | ------ | --------- |
| music flow | 459 | 00:00-06:00(1-5),00:00-08:00(6-7);很多年之前 |
| Morning Hits阳光音乐早餐 | 460 | 07:00-10:00(1-5) |
| hit morning show | 461 | 07:00-10:00(1-5),08:00-09:00(6;17年之前) |
| at 40 | 462 | 08:00-12:00(6),12:00-16:00(7),09:00-13:00(6;17年之前),20:00-24:00(7;17年之前) |
| At work network工作随身听 | 463 | 10:00-13:00(1-5;很多年之前) |
| weekend ride | 464 | 13:00-15:00(6);很多年之前 |
| Weekend Morning Show | 464 | 09:00-12:00(7);很多年之前 |
| Hit FM OST电影原声坊 | 465 | 16:00-18:00(7),12:00-14:00(7;很多年之前) |
| Lazy Afternoon慵懒下午茶 | 466 | 13:00-16:00(1-5;很多年之前) |
| Hit the Road在路上 | 467 | 12:00-14:00(6),14:00-16:00(7;很多年之前) |
| | 468 | 15:00-16:00(6) |
| | 469 | 16:00-18:00(6) |
| Rock DJ摇滚DJ | 470 | 16:00-18:00(6) |
| Big Drive Home开车现场秀 | 471 | 16:00-19:00(1-5) |
| Top 20 Countdown顶尖20排行榜 | 472 | 18:00-20:00(6-7) |
| New Music Express新音乐速递 | 473 | 19:00-22:00(1-5) |
| 电音？ | 474 | 20:00-22:00(6;很多年之前) |
| Hit FM Dance电音 | 475 | 22:00-23:59(1-7),20:00-23:59(7;21年2月开始) |
| Morning Call音乐叫早 | 20276 | 06:00-07:00(1-5) |
| Weekend Morning Show周末早间音乐 | 20277 | 08:00-12:00(6,7) |
| Soul Make心灵制造 | 20278 | 14:00-16:00(6) |
| At work network工作随身听 | 20279 | 10:00-13:00(1-5) |
| Lazy Afternoon慵懒下午茶 | 20280 | 13:00-16:00(1-5) |
| Hit FM Dance Carta & Co.电音-卡塔 | 54502 | 20:00-22:00(7) |
| CTDM Chart《中国电子音乐巅峰榜》 | 未知 | 在周日at 40时间段播出 |

```bash
✓ http://ia-bk-i.ajmide.com/c_464/20150425/464_20150425_1300.m4a
✓ http://ia-bk-i.ajmide.com/c_468/20150425/468_20150425_1500.m4a
✓ http://ia-bk-i.ajmide.com/c_469/20150425/469_20150425_1600.m4a
====================
✓ http://ia-bk-i.ajmide.com/c_464/20150426/464_20150426_0900.m4a
```

可惜的是，中国电子音乐巅峰榜（被部分合并）和近几年的music flow没有对应前刀节目，相应的代号经粗略爆破并未获得，希望有uu能获取到。

并且由于阿基米德本身的原因，有可能出现节目名称与实际对不上的情况，暂时无法解决（例如hitfm dance在部分解析的时候，时间是2200-2400,1-7；然而21年2月开始可能是改节目单了，实际上周日的播出时间是20-24。又如at40在周日有12:00-16:00这个播出时间段，但是当我们查看22/7/3的节目单会发现，下载到的音频其实是由rock DJ和CTDM组成的“合并节目”。推测是阿基米德没有更新节目单所致，不过由于rock DJ和CTDM的解析结果本身并不包含周日这个时间段，所以即使输入了“正确的”网址也是解析失败，唯一的获取独立文件的方式是在下载后手动切分）

最后，我们使用下方链接下载对应节目即可

```bash
http://ia-bk-i.ajmide.com/c_{code}/{YYYYMMDD}/{code}_{YYYYMMDD}_{HHmm(start_time)}.m4a

例如：
http://ia-bk-i.ajmide.com/c_20276/20220330/20276_20220330_0600.m4a
```

配置的保存可以参考config_example.json

```json
{
  "program_schedules": [
    {"name": "Morning Hits阳光音乐早餐", "code": "460", "slots": [{"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "10:00"}]},
    {"name": "at 40", "code": "462", "slots": [{"days": [6], "start": "08:00", "end": "12:00"}, {"days": [7], "start": "12:00", "end": "16:00"}]}
  ]
}
```

每一个节目配置由以下几部分组成：

- name：保存到本地时显示的文件名
- code：对应c_id
- slots：储存形式为列表，每一项中包含星期+时间点

例如Morning Hits的 slots 是 `[{"days": [1, 2, 3, 4, 5], "start": "07:00", "end": "10:00"}]`，说明其在周1~周5的7:00~10:00播出。

at 40 的 slots 是 `[{"days": [6], "start": "08:00", "end": "12:00"}, {"days": [7], "start": "12:00", "end": "16:00"}]`,由两项组成，说明其在周6的8:00~12:00，和周日的12:00~16:00都有播出

slots配置是允许交叉的，例如`[{"days": [6], "start": "08:00", "end": "12:00"}, {"days": [6], "start": "08:00", "end": "16:00"}]`和`[{"days": [6], "start": "08:00", "end": "12:00"}, {"days": [6], "start": "18:00", "end": "16:00"}]`都可以被正常识别，但如果当天同一个节目在不同时间段同时被解析成功，那么后面第n个解析成功的文件末尾会加上`_(n-1)`以作区分，形式如`xxx_1.m4a`,`xxx_2.m4a`等。需要注意的是，如果一天内同一时间段配置了多个节目，那么该时间段的这几个节目会被视为一组互补节目，互补节目组内只要有一个任务下载成功，组内后续其他任务都会被跳过。所以如果你想用时下载多个电台，强烈建议你使用多个配置文件避免出现上述问题。


## 功能与使用说明

目前提供了命令行与图形化（GUI）两套操作逻辑：

### 1. 命令行使用

```bash
# 单日下载
python downloader.py -d "25-12-22"

# 多连日下载（跨度下载），并在每天中间延迟3秒
python downloader.py -d "14-09-18 to 25-12-22" --delay 3

# 反向下载（从现在向过去）
python downloader.py -d "25-12-22 to 14-9-18" --delay 2

# 指定输出目录为 my_radio_folder
python downloader.py -d "25-12-22" -o "my_radio_folder"

# 仅下载节目名匹配正则的节目，并用模板自定义输出路径/文件名
python downloader.py -d "25-12-22" --name-regex "Music|Morning" --filename-template "{date}\\{id}_{name_en}"
```

**所有支持的命令行参数：**

- `-h`, `--help` : 显示帮助信息。
- `-d DATE`, `--date DATE` : 指定单独日期 (如 `'25-12-22'` 或 `'now'`) 或日期范围 (如 `'25-11-22 to 25-12-22'`，支持反向如 `'now to 25-12-22'`)。
- `-o OUTDIR`, `--outdir OUTDIR` : 下载的基础输出目录，默认为 `downloads`。
- `--delay DELAY` : 当执行多日持续下载时，请求日期间隔的睡眠时间(秒)，默认 `1.5`。
- `--name-regex NAME_REGEX` : 节目名正则筛选，仅下载匹配的节目（默认空，即不过滤；节目名称依赖配置文件）。
- `--filename-template FILENAME_TEMPLATE` : 自定义输出模板（默认 `{date}\\{name}`，支持 `{id}` `{name}` `{date}` `{name_ch}` `{name_en}` `{start_time}` `{end_time}`）。

说明：Windows 文件系统不允许 `:` `*` `?` 等字符，模板渲染后若包含这些字符，程序会自动转换为对应全角字符。

高级配置（仅 `config.json`，不在 UI 暴露）：

- `max_rate_kbps`：下载限速（单位 KB/s）。`0` 表示不限速。实际上阿基米德本身对单个连接限速约2~3MB/s，但似乎没有封禁策略
- `program_schedules`：节目映射列表。下载器会按该映射在本地拼接 URL；若缺失或格式错误，会回退到内置默认映射。

### 2. GUI 界面操作 (推荐)

直接运行release中文件，或clone本项目并在文件夹中运行 `python gui.py` 唤出界面。
**核心特性：**

- **可视化参数调整**：在界面输入日期范围（支持单日或多日），或是更改保存目录、控制防封禁请求延迟，并支持节目名正则筛选和文件名模板（含自定义子目录）。节目映射固定从 `config.json` 的 `program_schedules` 读取。相关的配置会自动保存到同目录下的 `config.json` 内作为默认预设。
- **模板预览区**：下载页新增“文件名模板预览”，固定以 `Morning Call 音乐叫早` 作为示例，实时展示模板渲染后的完整输出路径。
- **下载开关精简**：下载页面仅保留“下载后自动转换音频格式”开关。其余下载项采用固定基础策略。
- **防止重复与元数据映射**：源链接信息保存在 `images_info.txt` 中。下载目录会以日期按规则分类，并在文件夹内生成当天的抓取记录报告 `YYYY-MM-DD_program_info.txt`，包含对应的音频信息标识。
- **二段停止模式 (防烂尾机制)**：
  - 下载过程所有的文件采用 `.part` 缓存形式写入；连接意外中断或主动终止后不会污染目录。
  - **暂停/恢复**：随时中断/恢复主下载线程与转换线程。
  - **软停止**：结束当前文件后自动取消随后的全部任务队列，包含转换队列。
  - **强行停止**：即便正在执行途中，立刻截断释放资源，并彻底清理残断文件与子进程。
- **配置持久化**：退出时系统会自动比对参数差异并防错弹窗提示，避免丢失配置。支持并默认使用相对路径存储，方便跨设备携带。

## 自动化后处理 (格式转换管线)

//这个是 [云听下载器](https://github.com/coco292931/yunting-archive-downloader) 留下的自动转换管线，对于阿基米德的最高60k的码率而言其实完全没有必要使用 （

虽然 m4a 已经比较高效，但是如果全部按高码率保存节目，对储存依然是一笔不小的开销。
通过指定本地 FFmpeg（内置环境检测），图形界面原生支持了**异步多线程自动转换管线**功能：

1. **并行解耦，边下边压**：将下载和转换彻底分作两条完全独立的任务线运作，并通过动态队列衔接。当下载完成某集后，系统将其立即投喂给后处理队列进行降码/转码操作，而下载线程刻不容缓并发拉取下一集，双轨齐发，大幅度缩减耗时！双日志窗（下载与FFmpeg）能实时观测交响乐般的同步执行态。
2. **丰富的转码规格参数**：
   - 支持向 `opus`, `mp3`, `aac`, `m4a` 目标重混流并细控采样率（防 Opus 规范等报错）、固定压缩码率及调用 CPU 线程数。
   - 提供 “跳过现有 / 仅覆盖 0kb 残除 / 全量覆盖” 的3态安全覆写保护。
   - 自由设定独立输出文件夹，也可原地安全覆盖并搭配【转换成功后删除原文件】一键式瘦身。
3. **封面图自动反嵌**：能够监测源同名或源下载图片，并运用 ffmpeg 将其作为【专辑封面素材】反向无损硬写入最终的音频内部（**注：Opus 格式使用原生的 FFmpeg 无法直接嵌入图片流，如果你需要为 Opus 音频嵌入封面，可见下方进阶替代方案**）。
4. **批处理人工干预排队**：系统更支持扫描单日或全集目录寻找遗漏文件，预先生成批处理终端命令清单；用户甚至可在命令编辑区自由增删改查单条命令执行。

## 维护者快速入口（供后续修改）

为了便于后续接手，本项目可按下面的分层理解：

- `downloader.py`：负责读取 `program_schedules`、本地拼接节目 URL、音频/图片下载与落盘。
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
- 当前仅 Windows 使用 `favicon.ico` 图标；macOS 如需图标请准备 `.icns` 并在工作流里单独加参数。

## 注意事项

本工具仅供学习使用，请勿用作非法用途
