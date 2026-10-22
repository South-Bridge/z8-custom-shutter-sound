# 脚本

## 依赖

```bash
pip install numpy
```

## inspect_audio_tables.py

从解密后的 EG 模块里导出音频 kind 分派表,确认资源地址与长度。

```bash
python inspect_audio_tables.py eg.bin
```

输出示例（节选）：

```
=== 长度表 (0x43FB7E70) ===
  kind 10 -> getter 0x40E34920   28800 B (150 ms)
  kind 11 -> getter 0x40E34934    9600 B (50 ms)
  kind 12 -> getter 0x40E34928   19200 B (100 ms)
  kind 13 -> getter 0x40E34930    7680 B (40 ms)
  ...

=== 五个类型 ===
 类型 C:
    合成段/快  kind 14  ROM 0x43FCB750  长度 28800 B (150 ms)
    前段       kind 15  ROM 0x43FD27D0  长度 9600 B (50 ms)
    中段       kind 16  ROM 0x43FD4D50  长度 19200 B (100 ms)
    终段       kind 17  ROM 0x43FD9850  长度 7680 B (40 ms)
```

**这是整条链路的入口**——先用它确认你的固件版本地址是否与文档一致。

## build_custom_sound.py

把自定义 WAV 写进指定类型的音源,并把播放长度延长到整个资源块。

```bash
# 先把任意音频转成 48 kHz 立体声 16-bit
ffmpeg -i input.m4a -ac 2 -ar 48000 -acodec pcm_s16le my_sound.wav

# 生成打过补丁的 EG 模块
python build_custom_sound.py eg.bin my_sound.wav C out_eg.bin
```

脚本会做四件事：

1. 把音频填充/裁剪到 65,280 字节（340 ms），尾部 20 ms 渐隐，峰值归一化 -1.5 dBFS
2. 改写长度 getter：`28800` → `65280`
3. 让"前段"也用同一 getter，并把地址指向块首
4. 重算 EG 尾部 CRC

> ⚠️ 之后还需要：**改版本号**（`0xeb29fc` 公开版本指令、`0x14eaa90` 运行时串、
> 尾部 `-11` 处）、把 EG 放回固件包、重算包级 CRC。这些取决于你用的打包工具，
> 不在本脚本范围内。

## 关于 A 型

A 型（kind 0/1/2/6）只有 2 个常规资源，结构不同，`build_custom_sound.py` 暂不支持。
可以先跑 `inspect_audio_tables.py` 看它的实际布局。

## 验证方法

改完之后不要只看波形——**录音比对**最可靠：

```bash
ffmpeg -i record.m4a -ac 1 -ar 48000 rec.wav
```

然后分析时长和频谱轨迹，确认实际播放的是你写入的内容。
