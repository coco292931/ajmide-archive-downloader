import os
import subprocess
import shutil

def check_ffmpeg_path(custom_path=""):
    """
    检查ffmpeg是否可用，如果提供了custom_path则只检查该目录。
    如果没有提供，退回到环境变量检查。
    返回: (is_valid, executable_path)
    """
    # 指定了自定义路径时，仅按用户意图检查该路径，不回退系统 PATH。
    if custom_path:
        custom_path = custom_path.strip()
        if os.path.exists(custom_path):
            # 可能是直接指向可执行文件，或是包含该程序的目录
            if os.path.isdir(custom_path):
                exe_path = os.path.join(custom_path, "ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
                if os.path.exists(exe_path):
                    return True, exe_path
            else:
                if "ffmpeg" in os.path.basename(custom_path).lower():
                    return True, custom_path
        # 如果提供了自定义路径但无效，优先认定为无效，不进行系统回退，以免用户混淆
        return False, ""

    # 未指定自定义路径时，回退到环境变量查找 ffmpeg。
    sys_path = shutil.which("ffmpeg")
    if sys_path:
        return True, sys_path
        
    return False, ""

def build_ffmpeg_cmd(ffmpeg_cmd, input_path, output_path, target_format, bitrate, cover_path=None, threads=0, sample_rate="0"):
    """
    仅生成ffmpeg命令参数列表，不负责执行
    """
    # 统一使用 -y 覆盖输出；上层通过“覆盖模式”决定是否调用该命令。
    cmd = [
        ffmpeg_cmd,
        "-y", # 覆盖输出
        "-i", input_path
    ]
    
    # 是否嵌入封面图片。
    # 当封面可用时会追加第二输入轨，并通过 map 指定音频轨与图片轨。
    if cover_path and os.path.exists(cover_path):
        if target_format.lower() == 'opus':
            # Opus 暂无法通过原生ffmpeg无缝附带图片，保留原始输入不追加第二轨
            pass
        else:
            cmd.extend(["-i", cover_path, "-map", "0:0", "-map", "1:0"])
            if target_format.lower() in ['mp3', 'm4a', 'flac']:
                cmd.extend(["-c:v", "mjpeg", "-disposition:v", "attached_pic"])
    
    # 音频编码器选择：仅显式指定常用格式，其余格式交给 ffmpeg 默认策略。
    if target_format.lower() == 'opus':
        cmd.extend(["-c:a", "libopus"])
    elif target_format.lower() == 'mp3':
        cmd.extend(["-c:a", "libmp3lame"])
    elif target_format.lower() in ['m4a', 'aac']:
        cmd.extend(["-c:a", "aac"])

    # 码率容错：支持传入纯数字（如 96）或 ffmpeg 形式（如 96k）。
    if bitrate:
        if not str(bitrate).endswith('k') and not str(bitrate).endswith('K'):
            bitrate = f"{bitrate}k"
        cmd.extend(["-b:a", str(bitrate)])

    # 线程数为 "0" 时不显式指定，让 ffmpeg 自主决策。
    if threads and str(threads) != "0":
        cmd.extend(["-threads", str(threads)])

    # 采样率为 "0" 时不追加 -ar，避免覆盖源文件或编码器默认采样率。
    if sample_rate and str(sample_rate) != "0":
        cmd.extend(["-ar", str(sample_rate)])

    cmd.append(output_path)
    return cmd
