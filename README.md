# music-tagger

自动化音乐元数据整理工具。监控 NAS 临时目录，对新入库的音乐文件自动识别、补全标签、下载封面和歌词、重命名并归类。

## 安装

```bash
cd /Volumes/openclaw/music-tagger

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .

# 可选：安装音频指纹支持（需要系统安装 chromaprint）
pip install -e ".[acoustid]"
```

## 使用方式

### 方式一：一键处理

最简单的用法，扫描 → 匹配 → 标签 → 重命名 → 归类，一步到位：

```bash
music-tagger run
```

处理完成后，整理好的文件会出现在 `/Volumes/Music/临时/已整理/艺术家/专辑名/` 下，确认无误后手动移入正式曲库。

### 方式二：分步执行

适合需要中途检查或手动干预的场景：

```bash
# 1. 扫描临时目录，发现新文件
music-tagger scan

# 2. 搜索匹配（提取线索 + QQ音乐搜索）
music-tagger match

# 3. 查看匹配结果，确认无误
music-tagger list -s matched

# 4. 写入标签 + 封面 + 歌词
music-tagger tag

# 5. 重命名为「艺术家 - 歌名」格式
music-tagger rename

# 6. 归类到 已整理/ 目录
music-tagger organize
```

### 方式三：查看状态与问题处理

```bash
# 查看各状态文件数量
music-tagger status

# 列出所有文件
music-tagger list

# 只看失败的文件
music-tagger list -s failed

# 只看待人工确认的（低置信度匹配）
music-tagger list -s pending_review

# 重试所有失败文件
music-tagger retry

# 重试指定文件
music-tagger retry --id 42
```

### 方式四：定时自动运行

配合 cron 或 launchd 实现定时监控：

```bash
# cron 示例：每小时检查一次
0 * * * * cd /Volumes/openclaw/music-tagger && .venv/bin/music-tagger run >> logs/cron.log 2>&1
```

macOS launchd 方式，创建 `~/Library/LaunchAgents/com.music-tagger.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.music-tagger</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Volumes/openclaw/music-tagger/.venv/bin/music-tagger</string>
        <string>run</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>WorkingDirectory</key>
    <string>/Volumes/openclaw/music-tagger</string>
    <key>StandardOutPath</key>
    <string>/Volumes/openclaw/music-tagger/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Volumes/openclaw/music-tagger/logs/launchd-error.log</string>
</dict>
</plist>
```

```bash
# 加载
launchctl load ~/Library/LaunchAgents/com.music-tagger.plist

# 卸载
launchctl unload ~/Library/LaunchAgents/com.music-tagger.plist
```

### 方式五：作为 MCP Server 供 Agent 调用（规划中）

后续可封装为 MCP Server，供 Claude Code、openclaw 等 agent 直接调用：

```bash
music-tagger serve
```

Agent 可调用的工具：`scan_new_music`、`process_all`、`get_status`、`list_tracks`、`retry_failed`、`manual_tag`。

## 配置

编辑 `config.yaml`：

```yaml
paths:
  watch_dir: /Volumes/Music/临时           # 监控目录
  organized_dir: /Volumes/Music/临时/已整理  # 整理完成目录

matching:
  confidence_threshold: 0.80               # 低于此值进入人工队列

tagging:
  overwrite: false                         # 只补缺不覆盖已有标签
```

## 处理流程

```
临时目录新文件
  → 扫描（MD5 去重）
  → 提取线索（嵌入标签 / 文件名 / 目录名）
  → QQ音乐搜索匹配
  → 写入标签 + 封面 + 歌词
  → 重命名为「艺术家 - 歌名」
  → 归类到 已整理/艺术家/专辑名/
  → 用户确认后手动移入正式曲库
```

## 支持格式

| 格式 | 标签读取 | 标签写入 | 封面嵌入 |
|------|---------|---------|---------|
| FLAC | ✅ | ✅ | ✅ |
| M4A  | ✅ | ✅ | ✅ |
| MP3  | ✅ | ✅ | ✅ |
| WAV  | ✅ | ✅ | ✅ |
| APE  | ✅ | ❌ | ❌ |
