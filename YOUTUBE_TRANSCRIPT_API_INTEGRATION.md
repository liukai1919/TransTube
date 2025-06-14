# YouTube Transcript API 集成说明

## 概述

已成功将 `youtube-transcript-api` 集成到 TransTube 项目中，用于更高效地获取 YouTube 视频字幕。这个集成提供了以下优势：

- **更快的字幕获取**: 直接从 YouTube 获取字幕，无需下载视频
- **多语言支持**: 支持获取多种语言的字幕
- **自动翻译**: 支持 YouTube 的自动翻译功能
- **智能回退**: 如果无法获取字幕，自动回退到 WhisperX 转录
- **英文备选**: 当翻译不可用时，自动提供英文原文

## 新增功能

### 1. 字幕提取器 (`backend/utils/subtitle_extractor.py`)

新增的 `SubtitleExtractor` 类提供了完整的字幕提取功能：

```python
from backend.utils.subtitle_extractor import SubtitleExtractor

extractor = SubtitleExtractor()

# 检查可用字幕
video_id = extractor.extract_video_id("https://www.youtube.com/watch?v=VIDEO_ID")
transcripts = extractor.get_available_transcripts(video_id)

# 下载字幕
srt_path = extractor.download_transcript(video_id, ['en', 'en-US'], prefer_manual=True)
```

### 2. 更新的下载器 (`backend/utils/downloader.py`)

增强了字幕检查功能，优先使用 `youtube-transcript-api`：

```python
from backend.utils.downloader import check_available_subtitles, download_youtube_subtitles

# 检查字幕可用性
subtitle_info = check_available_subtitles("https://www.youtube.com/watch?v=VIDEO_ID")

# 下载字幕
srt_path = download_youtube_subtitles("https://www.youtube.com/watch?v=VIDEO_ID")
```

### 3. 新的 API 端点

#### 检查字幕可用性
```bash
POST /api/check-subtitles
Content-Type: application/x-www-form-urlencoded

video_url=https://www.youtube.com/watch?v=VIDEO_ID
```

#### 仅下载字幕（不处理视频）
```bash
POST /api/download-subtitles
Content-Type: application/x-www-form-urlencoded

video_url=https://www.youtube.com/watch?v=VIDEO_ID
language_codes=en,en-US,en-GB
prefer_manual=true
target_language=zh-Hans
```

## 处理流程优化

新的视频处理流程：

1. **检查字幕可用性** - 使用 `youtube-transcript-api` 检查
2. **优先获取 YouTube 字幕** - 如果有可用字幕，直接下载
3. **智能翻译** - 优先使用 YouTube 翻译，回退到自定义翻译
4. **英文备选** - 如果翻译失败，提供英文原文
5. **智能回退** - 如果无字幕，使用 WhisperX 转录
6. **字幕烧录** - 将字幕烧录到视频

## 使用示例

### 基本使用

```python
# 检查字幕
from backend.utils.subtitle_extractor import check_youtube_subtitles

url = "https://www.youtube.com/watch?v=eMFs-eapRJI"
subtitle_info = check_youtube_subtitles(url)

print(f"手动字幕: {len(subtitle_info['manual'])} 种")
print(f"自动字幕: {len(subtitle_info['generated'])} 种")
```

### 下载字幕

```python
from backend.utils.subtitle_extractor import extract_youtube_subtitles

# 下载英文字幕
srt_path = extract_youtube_subtitles(
    url="https://www.youtube.com/watch?v=eMFs-eapRJI",
    language_codes=['en', 'en-US'],
    prefer_manual=True
)

if srt_path:
    print(f"字幕已保存到: {srt_path}")
```

### API 调用示例

```javascript
// 检查字幕可用性
const checkSubtitles = async (videoUrl) => {
    const formData = new FormData();
    formData.append('video_url', videoUrl);
    
    const response = await fetch('/api/check-subtitles', {
        method: 'POST',
        body: formData
    });
    
    const result = await response.json();
    return result.subtitle_info;
};

// 仅下载字幕
const downloadSubtitles = async (videoUrl) => {
    const formData = new FormData();
    formData.append('video_url', videoUrl);
    formData.append('target_language', 'zh-Hans');
    
    const response = await fetch('/api/download-subtitles', {
        method: 'POST',
        body: formData
    });
    
    const result = await response.json();
    return result.subtitle_content;
};
```

## 优势对比

| 功能 | 原有方式 (yt-dlp + WhisperX) | 新方式 (youtube-transcript-api) |
|------|------------------------------|--------------------------------|
| 速度 | 慢（需要下载音频+转录） | 快（直接获取字幕） |
| 准确性 | 依赖 AI 模型 | YouTube 官方字幕 |
| 资源消耗 | 高（GPU/CPU 密集） | 低（仅网络请求） |
| 多语言 | 需要翻译 | 原生多语言支持 |
| 可靠性 | 依赖模型可用性 | 依赖 YouTube API |

## 配置说明

确保 `requirements.txt` 中包含：

```
youtube-transcript-api>=0.6
srt
```

## 测试

运行测试脚本验证功能：

```bash
python test_subtitle_extractor.py
```

## 注意事项

1. **网络依赖**: 需要稳定的网络连接访问 YouTube
2. **字幕可用性**: 不是所有视频都有字幕
3. **语言支持**: 翻译质量依赖 YouTube 的自动翻译
4. **回退机制**: 当 API 不可用时，自动回退到原有方式
5. **英文备选**: 当中文翻译不可用时，自动提供英文原文，确保用户始终能获得字幕

## 故障排除

### 常见问题

1. **无法获取字幕**
   - 检查视频是否公开
   - 确认视频有可用字幕
   - 检查网络连接

2. **API 限制**
   - YouTube 可能有请求频率限制
   - 考虑添加重试机制

3. **字幕格式问题**
   - 确保 SRT 格式转换正确
   - 检查时间戳格式

### 日志调试

启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 未来改进

1. **缓存机制**: 缓存已获取的字幕
2. **批量处理**: 支持批量下载多个视频字幕
3. **更多格式**: 支持 VTT、ASS 等格式
4. **质量评估**: 评估字幕质量并选择最佳来源 