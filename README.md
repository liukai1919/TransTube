# TransTube - YouTube 视频智能翻译系统

TransTube 是一个基于 AI 的 YouTube 视频翻译系统，支持自动转录、智能翻译和字幕烧录。

## ✨ 主要功能

### 🎯 核心功能
- **WhisperX 自动转录**: 当 YouTube 视频没有字幕时，自动使用 WhisperX 进行高质量转录
- **智能字幕切分**: AI 优化字幕断句，避免过长和生硬的分割
- **三阶段翻译**: 初译 → 反思 → 适配，显著提升翻译质量
- **英文音频转中文配音**: 自动生成中文语音，可直接为视频配音
- **术语库支持**: 自动提取专业术语，确保翻译一致性
- **GPU 加速**: 支持 NVIDIA GPU 加速转录和视频处理
- **断点续跑**: 任务失败后可以恢复，避免重复处理

### 🔧 技术特性
- **FastAPI 后端**: 高性能异步 API
- **Next.js 前端**: 现代化用户界面
- **Docker 一键部署**: 支持 GPU 的容器化部署
- **本地 LLM 支持**: 集成 Ollama，支持本地大语言模型
- **任务队列**: 支持并发处理多个视频

## 🚀 快速开始

### 方式一：Docker 一键部署（推荐）

1. **克隆项目**
```bash
git clone https://github.com/your-username/TransTube.git
cd TransTube
```

2. **启动服务**
```bash
chmod +x start.sh
./start.sh
```

3. **访问应用**
- 前端界面: http://localhost:3001
- 后端 API: http://localhost:8000
- Ollama 服务: http://localhost:11434

### 方式二：本地开发

#### 后端启动
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requeirements.txt
uvicorn main:app --reload --port 8000
```

#### 前端启动
```bash
cd frontend
npm install
npm run dev
```

## 📋 环境要求

### 系统要求
- Python 3.8+
- Node.js 16+
- FFmpeg
- Docker & Docker Compose（Docker 部署）

### GPU 支持（可选）
- NVIDIA GPU
- CUDA 12.1+
- NVIDIA Docker Runtime

### 依赖服务
- Ollama（本地 LLM）
- Redis（任务队列，可选）

## ⚙️ 配置说明

### 环境变量
复制 `env.example` 为 `.env` 并配置：

```env
# OpenAI API 配置（用于翻译）
OPENAI_API_KEY=your_openai_api_key_here

# Ollama 配置（本地 LLM）
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:27b

# 功能开关
USE_WHISPERX=true
USE_THREE_STAGE_TRANSLATION=true
USE_SMART_SPLIT=true
EXTRACT_TERMINOLOGY=true
```

### YouTube Cookies（可选）
如果遇到下载限制，可以配置 YouTube cookies：
1. 将 cookies 文件保存为 `backend/youtube.cookies`
2. 设置文件权限：`chmod 600 backend/youtube.cookies`

## 🎮 使用指南

### 基本使用
1. 在前端页面输入 YouTube 视频链接
2. 选择处理选项（智能切分、三阶段翻译等）
3. 等待处理完成
4. 下载带中文字幕的视频或字幕文件

### 高级功能

#### 断点续跑
如果任务失败，可以通过 API 恢复：
```bash
curl -X POST http://localhost:8000/api/task/{task_id}/resume
```

#### 强制重新处理
如果需要重新处理已有视频：
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "force_reprocess": true
}
```

#### 自定义翻译参数
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "use_smart_split": true,
  "use_three_stage": true,
  "extract_terms": true
}
```

## 🏗️ 架构说明

### 系统架构
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   前端      │    │   后端      │    │   Ollama    │
│  Next.js    │◄──►│  FastAPI    │◄──►│   LLM       │
└─────────────┘    └─────────────┘    └─────────────┘
                           │
                   ┌───────▼───────┐
                   │   处理流程     │
                   │ ┌───────────┐ │
                   │ │ 下载视频  │ │
                   │ └───────────┘ │
                   │ ┌───────────┐ │
                   │ │ 检查字幕  │ │
                   │ └───────────┘ │
                   │ ┌───────────┐ │
                   │ │WhisperX转录│ │
                   │ └───────────┘ │
                   │ ┌───────────┐ │
                   │ │ 智能翻译  │ │
                   │ └───────────┘ │
                   │ ┌───────────┐ │
                   │ │ 字幕烧录  │ │
                   │ └───────────┘ │
                   └───────────────┘
```

### 处理流程
1. **字幕检测**: 检查 YouTube 是否有可用字幕
2. **WhisperX 转录**: 无字幕时使用 AI 转录
3. **智能切分**: 优化字幕断句和可读性
4. **术语提取**: 自动识别专业术语
5. **三阶段翻译**: 初译 → 反思 → 适配
6. **字幕烧录**: 将中文字幕烧录到视频

## 🛠️ 开发指南

### 项目结构
```
TransTube/
├── backend/                 # 后端代码
│   ├── utils/              # 工具模块
│   │   ├── downloader.py   # 视频下载
│   │   ├── transcriber.py  # 语音转录
│   │   ├── translator.py   # 智能翻译
│   │   ├── processor.py    # 视频处理
│   │   └── subtitle_embedder.py # 字幕烧录
│   ├── main.py             # 主应用
│   ├── Dockerfile          # 后端容器
│   └── requeirements.txt   # Python 依赖
├── frontend/               # 前端代码
│   ├── pages/              # 页面组件
│   ├── Dockerfile          # 前端容器
│   └── package.json        # Node.js 依赖
├── docker-compose.yml      # 容器编排
├── start.sh               # 启动脚本
└── README.md              # 项目文档
```

### API 接口

#### 处理视频
```http
POST /api/process
Content-Type: application/json

{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "force_reprocess": false
}
```

#### 查询任务状态
```http
GET /api/task/{task_id}
```

#### 恢复任务
```http
POST /api/task/{task_id}/resume
```

#### 获取视频列表
```http
GET /api/videos
```

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 Apache-2.0 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [VideoLingo](https://github.com/Huanshere/VideoLingo) - 提供了优秀的视频翻译思路
- [WhisperX](https://github.com/m-bain/whisperx) - 高质量语音转录
- [Ollama](https://ollama.ai/) - 本地大语言模型支持

## 📞 支持

如果您遇到问题或有建议，请：
1. 查看 [Issues](https://github.com/your-username/TransTube/issues)
2. 创建新的 Issue
3. 联系维护者

---

**TransTube** - 让 YouTube 视频翻译变得简单高效！ 