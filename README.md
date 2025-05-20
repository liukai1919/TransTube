# 视译通（YouTrans）

一个用于处理YouTube视频的工具，可以下载视频、提取字幕、翻译成中文并将字幕嵌入到视频中。

## 功能特点

- 支持YouTube视频下载
- 自动提取英文字幕
- 使用AI模型将字幕翻译成中文
- 将双语字幕嵌入到视频中
- 提供Web界面，方便操作
- 支持处理长视频的分段任务

## 系统架构

- **前端**: React + Next.js
- **后端**: FastAPI
- **视频处理**: FFmpeg, yt-dlp
- **翻译**: OpenAI API

## 快速开始

### 环境准备

1. 克隆仓库:
```bash
git clone https://github.com/yourusername/TransTube.git
cd TransTube
```

2. 创建Python虚拟环境:
```bash
python3 -m venv venv
source venv/bin/activate  # 在Linux/Mac上
# 或者
venv\Scripts\activate  # 在Windows上
```

3. 安装Python依赖:
```bash
pip install -r requirements.txt
```

4. 安装Node.js依赖:
```bash
cd frontend
npm install
```

5. 安装FFmpeg:
```bash
# 在Ubuntu/Debian上
sudo apt-get update
sudo apt-get install ffmpeg

# 在macOS上
brew install ffmpeg
```

6. 创建`.env`文件并设置API密钥:
```
OPENAI_API_KEY=你的OpenAI_API密钥
```

### 启动应用

1. 启动后端服务:
```bash
# 在项目根目录下
cd backend
uvicorn main:app --reload
```

2. 启动前端开发服务器:
```bash
# 在另一个终端中
cd frontend
npm run dev
```

3. 访问应用:
打开浏览器访问 `http://localhost:3000`

## 使用说明

1. 在应用首页输入YouTube视频链接
2. 点击"开始处理"按钮
3. 等待处理完成
4. 下载处理后的视频或字幕文件

## 技术栈

- Python 3.8+
- React/Next.js
- FFmpeg
- yt-dlp
- OpenAI API

## 许可证

MIT

## 贡献指南

欢迎提交问题和Pull Request来改进这个项目! 
