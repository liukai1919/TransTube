# TransTube 部署检查清单

## 📋 部署前准备

### 系统要求检查
- [ ] Python 3.8+ 已安装
- [ ] Node.js 16+ 已安装
- [ ] Docker 和 Docker Compose 已安装
- [ ] FFmpeg 已安装
- [ ] NVIDIA GPU 驱动已安装（如果使用 GPU）
- [ ] NVIDIA Docker Runtime 已配置（如果使用 GPU）

### 环境配置
- [ ] 复制 `env.example` 为 `.env`
- [ ] 配置 OpenAI API Key（如果使用 OpenAI 翻译）
- [ ] 配置 Ollama 模型设置
- [ ] 设置 YouTube cookies（如果需要）
- [ ] 创建必要的目录权限

## 🚀 部署步骤

### Docker 部署
- [ ] 运行 `./start.sh` 启动所有服务
- [ ] 检查所有容器状态：`docker-compose ps`
- [ ] 查看服务日志：`docker-compose logs -f`

### 本地部署
- [ ] 后端服务启动：`cd backend && uvicorn main:app --reload`
- [ ] 前端服务启动：`cd frontend && npm run dev`
- [ ] Ollama 服务启动：`ollama serve`

## ✅ 功能验证

### 基础功能
- [ ] 前端页面可以访问（http://localhost:3001）
- [ ] 后端 API 可以访问（http://localhost:8000）
- [ ] API 文档可以访问（http://localhost:8000/docs）
- [ ] 视频列表接口正常（GET /api/videos）

### 核心功能
- [ ] YouTube 视频下载功能
- [ ] 字幕检测和提取功能
- [ ] WhisperX 转录功能（无字幕视频）
- [ ] 智能字幕切分功能
- [ ] 三阶段翻译功能
- [ ] 术语库提取功能
- [ ] 字幕烧录功能
- [ ] GPU 加速功能（如果可用）

### 高级功能
- [ ] 任务状态持久化
- [ ] 断点续跑功能
- [ ] 任务恢复功能
- [ ] 缓存结果检测
- [ ] 错误处理和日志记录

## 🧪 测试验证

### 自动化测试
```bash
# 基础功能测试
python test_features.py

# 完整功能测试（包括视频处理）
python test_features.py --full
```

### 手动测试
- [ ] 提交一个短视频（<5分钟）进行处理
- [ ] 检查处理进度和状态更新
- [ ] 验证生成的字幕文件质量
- [ ] 验证烧录后的视频质量
- [ ] 测试任务失败后的恢复功能

## 🔧 性能优化

### GPU 加速验证
```bash
# 检查 NVIDIA GPU 状态
nvidia-smi

# 检查 CUDA 可用性
python -c "import torch; print(torch.cuda.is_available())"

# 检查 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### 内存和存储
- [ ] 确保有足够的磁盘空间（建议 >50GB）
- [ ] 确保有足够的内存（建议 >16GB）
- [ ] 配置适当的并发处理数量

## 🛠️ 故障排除

### 常见问题
- [ ] 端口冲突检查（3001, 8000, 11434, 6379）
- [ ] 权限问题检查（文件和目录权限）
- [ ] 网络连接检查（YouTube 访问，API 调用）
- [ ] 依赖版本兼容性检查

### 日志检查
```bash
# Docker 服务日志
docker-compose logs api
docker-compose logs web
docker-compose logs ollama

# 应用日志
tail -f backend/logs/translator.log
tail -f backend/logs/transcriber.log
```

### 服务重启
```bash
# 重启所有服务
docker-compose restart

# 重启特定服务
docker-compose restart api
docker-compose restart ollama
```

## 📊 监控和维护

### 定期检查
- [ ] 磁盘空间使用情况
- [ ] 内存使用情况
- [ ] GPU 使用情况（如果可用）
- [ ] 任务处理成功率
- [ ] 错误日志分析

### 备份策略
- [ ] 配置文件备份（.env, docker-compose.yml）
- [ ] 任务状态备份（tasks/ 目录）
- [ ] 处理结果备份（static/ 目录）
- [ ] 日志文件轮转配置

## 🔄 更新和升级

### 代码更新
```bash
# 拉取最新代码
git pull origin main

# 重新构建容器
docker-compose build --no-cache

# 重启服务
docker-compose up -d
```

### 依赖更新
- [ ] Python 依赖更新：`pip install -r requirements.txt --upgrade`
- [ ] Node.js 依赖更新：`npm update`
- [ ] Docker 镜像更新：`docker-compose pull`

## 📞 支持和帮助

### 获取帮助
- [ ] 查看项目文档：README.md
- [ ] 查看 API 文档：http://localhost:8000/docs
- [ ] 查看 GitHub Issues
- [ ] 联系项目维护者

### 报告问题
- [ ] 收集错误日志
- [ ] 记录复现步骤
- [ ] 提供系统环境信息
- [ ] 创建 GitHub Issue

---

## ✅ 部署完成确认

当所有检查项都完成后，您的 TransTube 系统就可以正常使用了！

**最终验证**：
1. 访问前端页面：http://localhost:3001
2. 输入一个 YouTube 视频链接
3. 等待处理完成
4. 下载并查看结果

如果一切正常，恭喜您成功部署了 TransTube！🎉 