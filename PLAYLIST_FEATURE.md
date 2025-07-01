# YouTube 播放列表批量处理功能

## 功能说明

现在 TransTube 支持自动识别和批量处理 YouTube 播放列表了！当您输入一个 YouTube 网址时，系统会自动判断它是单个视频还是播放列表，并提供相应的处理选项。

## 支持的 URL 格式

- 播放列表：`https://www.youtube.com/playlist?list=PLxxxxx`
- 带播放列表的视频：`https://www.youtube.com/watch?v=xxxxx&list=PLxxxxx`
- 单个视频：`https://www.youtube.com/watch?v=xxxxx`

## API 使用方法

### 1. 检查 URL 类型

```bash
POST /api/check-playlist
Content-Type: application/x-www-form-urlencoded

video_url=https://www.youtube.com/playlist?list=PLxxxxx
```

返回示例：
```json
{
  "success": true,
  "is_playlist": true,
  "playlist_info": {
    "type": "playlist",
    "playlist_id": "PLxxxxx",
    "playlist_title": "播放列表标题",
    "uploader": "上传者",
    "video_count": 10,
    "videos": [
      {
        "index": 1,
        "id": "video_id_1",
        "title": "视频标题 1",
        "url": "https://www.youtube.com/watch?v=video_id_1",
        "duration": 300,
        "uploader": "上传者"
      },
      // ... 更多视频
    ]
  }
}
```

### 2. 批量处理播放列表

```bash
POST /api/process-playlist
Content-Type: application/x-www-form-urlencoded

video_url=https://www.youtube.com/playlist?list=PLxxxxx&target_lang=zh&max_videos=5
```

参数说明：
- `video_url`: YouTube 播放列表 URL
- `target_lang`: 目标语言（默认：zh）
- `max_videos`: 最多处理的视频数量（0 表示全部，默认：0）

返回示例：
```json
{
  "message": "已创建批量任务，共 5 个视频",
  "batch_id": "batch-uuid",
  "playlist_title": "播放列表标题",
  "total_videos": 5,
  "video_tasks": [
    {
      "task_id": "task-uuid-1",
      "video_title": "视频标题 1",
      "video_url": "https://www.youtube.com/watch?v=video_id_1",
      "status": "pending"
    },
    // ... 更多任务
  ]
}
```

### 3. 查询批量任务状态

```bash
GET /api/batch/{batch_id}
```

返回示例：
```json
{
  "id": "batch-uuid",
  "type": "batch",
  "playlist_title": "播放列表标题",
  "playlist_id": "PLxxxxx",
  "total_videos": 5,
  "processed_videos": 3,
  "failed_videos": 0,
  "processing_videos": 2,
  "status": "processing",
  "overall_progress": 64,
  "video_tasks": [
    {
      "task_id": "task-uuid-1",
      "video_title": "视频标题 1",
      "video_url": "https://www.youtube.com/watch?v=video_id_1",
      "status": "completed",
      "progress": 100,
      "message": "处理完成",
      "result": {
        "video_url": "http://server/static/videos/video_id_1_sub.mp4",
        "srt_url": "http://server/static/subtitles/video_id_1_zh.srt",
        "download_url": "http://server/static/videos/video_id_1_sub.mp4",
        "duration": 300,
        "title": "视频标题 1",
        "processing_method": "YouTube字幕(手动)"
      }
    },
    // ... 更多任务状态
  ]
}
```

## 使用建议

1. **处理大型播放列表时**：建议使用 `max_videos` 参数限制数量，避免一次处理太多视频
2. **监控进度**：定期调用批量任务状态 API 来监控处理进度
3. **错误处理**：单个视频失败不会影响其他视频的处理
4. **性能考虑**：系统会自动在每个视频任务之间添加延迟，避免对 YouTube 造成过大压力

## 前端集成建议

1. 在用户输入 URL 后，先调用 `/api/check-playlist` 检查类型
2. 如果是播放列表，显示视频列表让用户确认
3. 提供选项让用户选择处理全部或部分视频
4. 使用批量任务 ID 定期查询进度并更新 UI
5. 显示每个视频的处理状态和进度

## 注意事项

- 批量处理会占用较多系统资源，建议合理控制并发数量
- 长时间运行的批量任务可能会因为网络或系统原因中断
- 建议为重要的播放列表处理任务保存批量任务 ID 以便后续查询 