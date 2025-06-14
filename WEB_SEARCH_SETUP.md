# 网络术语搜索功能配置指南

## 概述

TransTube 现在支持自动网络搜索功能，当模型对某个专业术语翻译不确定时，会自动搜索互联网获取准确的翻译。这个功能可以显著提高专业术语的翻译准确性。

## 🔧 配置方法

### 1. 获取搜索API密钥

#### 方法一：使用 Serper API（推荐）
1. 访问 [serper.dev](https://serper.dev)
2. 注册账号并获取 API Key
3. 每月有2500次免费搜索

#### 方法二：使用 Bing Search API
1. 访问 [Azure Cognitive Services](https://azure.microsoft.com/services/cognitive-services/bing-web-search-api/)
2. 创建 Bing Search API 资源
3. 获取 API Key

### 2. 环境变量配置

在你的 `.env` 文件中添加以下配置：

```bash
# 启用网络搜索功能
ENABLE_WEB_SEARCH=true

# 搜索API配置（至少配置一个）
SERPER_API_KEY=your_serper_api_key
BING_SEARCH_API_KEY=your_bing_api_key_here

# 搜索参数配置
MAX_WEB_SEARCH_TERMS=5              # 每个视频最多搜索的术语数量
WEB_SEARCH_CACHE_DAYS=30            # 搜索结果缓存天数
```

### 3. 完整配置示例

```bash
# ===== 术语库配置 =====
USE_PREDEFINED_TERMS=true
AUTO_EXTRACT_TERMS=true
CUSTOM_TERMINOLOGY_PATH=./custom_terms.json
MAX_TERMS_IN_PROMPT=50

# ===== 网络搜索配置 =====
ENABLE_WEB_SEARCH=true
SERPER_API_KEY=your_serper_api_key
MAX_WEB_SEARCH_TERMS=5
WEB_SEARCH_CACHE_DAYS=30

# ===== 翻译质量配置 =====
USE_THREE_STAGE=true
CHECK_TERMINOLOGY=true
TRANSLATION_TEMPERATURE=0.2
```

## 🚀 使用方法

### 方法一：通过环境变量启用（全局）

设置环境变量后，所有翻译任务都会自动启用网络搜索：

```python
# 处理视频，自动使用网络搜索
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "extract_terms": true,
  "use_three_stage": true
}
```

### 方法二：通过API参数控制（单次）

```python
# 为特定视频启用网络搜索
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "extract_terms": true,
  "enable_web_search": true,
  "use_three_stage": true
}
```

### 方法三：直接调用搜索功能

```python
from backend.utils.web_terminology_search import WebTerminologySearcher

# 创建搜索器
searcher = WebTerminologySearcher()

# 搜索单个术语
translation = searcher.search_and_translate("Kubernetes")
print(f"Kubernetes -> {translation}")

# 批量搜索
uncertain_terms = ["GraphQL", "JAMstack", "Serverless"]
results = searcher.batch_search_uncertain_terms(uncertain_terms)
print("搜索结果:", results)
```

## 🎯 工作原理

### 1. 不确定术语检测

系统会自动识别以下类型的术语：

- **专有名词**: 大写开头的单词或短语
- **技术缩写**: 全大写的缩写词（如API、SDK、AI）
- **技术词汇**: 包含特定技术关键词的术语
- **未知术语**: 不在现有术语库中的专业词汇

### 2. 智能搜索策略

```
英文术语 → 构建搜索查询 → 多引擎搜索 → 结果分析 → 提取翻译
    ↓
1. "term" 中文翻译
2. "term" 是什么意思  
3. "term" 中文 含义
4. term translation Chinese
```

### 3. 翻译提取算法

- 使用正则表达式从搜索结果中提取中文翻译
- 计算翻译候选的可信度得分
- 优先选择来自可信来源的翻译
- 自动过滤无效和错误的翻译

### 4. 缓存机制

- 搜索结果自动缓存，避免重复搜索
- 缓存有效期可配置（默认30天）
- 自动清理过期缓存

## 📊 功能特性

### ✅ 优势
- **自动化**: 无需人工干预，自动识别和搜索
- **准确性**: 从权威来源获取准确翻译
- **效率**: 缓存机制避免重复搜索
- **多引擎**: 支持多个搜索引擎，提高成功率
- **可控性**: 可以控制搜索数量和频率

### ⚠️ 限制
- **API费用**: 可能产生搜索API费用
- **网络依赖**: 需要稳定的网络连接
- **速度影响**: 会略微增加翻译时间
- **准确性**: 搜索结果质量取决于网络内容

## 🔍 支持的搜索引擎

### 1. Serper API（推荐）
- **优点**: 基于Google搜索，结果质量高
- **费用**: 每月2500次免费
- **配置**: `SERPER_API_KEY`

### 2. Bing Search API
- **优点**: 微软官方API，稳定可靠
- **费用**: 按使用量计费
- **配置**: `BING_SEARCH_API_KEY`

### 3. DuckDuckGo（备用）
- **优点**: 免费，无需API密钥
- **缺点**: 结果质量较低，可能被限制
- **使用**: 自动作为备用方案

## 📈 效果监控

### 查看搜索日志
```bash
# 查看翻译日志
tail -f backend/logs/translator.log | grep "网络搜索"
```

### 搜索缓存文件
系统会在工作目录创建 `terminology_search_cache.json` 文件，记录所有搜索历史。

### 术语库文件
搜索到的新术语会自动添加到 `extracted_terminology.json` 文件中。

## 🛠️ 故障排除

### 常见问题

**Q: 网络搜索不工作？**
- 检查API密钥是否正确配置
- 确认网络连接正常
- 查看日志文件中的错误信息

**Q: 搜索结果不准确？**
- 检查搜索的术语是否真的是专业术语
- 可以手动添加到自定义术语库
- 调整搜索参数和过滤条件

**Q: 翻译速度变慢？**
- 减少 `MAX_WEB_SEARCH_TERMS` 参数
- 关闭网络搜索功能
- 使用更快的搜索API

### 调试模式

启用详细日志：

```bash
# 设置日志级别
export LOG_LEVEL=DEBUG

# 或在代码中
import logging
logging.getLogger('backend.utils.web_terminology_search').setLevel(logging.DEBUG)
```

## 💡 最佳实践

### 1. 合理使用搜索配额
- 对技术视频启用网络搜索
- 对娱乐视频可以关闭搜索
- 设置合理的搜索术语数量限制

### 2. 结合自定义术语库
- 将高频专业术语添加到自定义术语库
- 定期整理搜索到的术语
- 避免重复搜索已知术语

### 3. 监控和优化
- 定期检查搜索结果质量
- 根据反馈调整搜索策略
- 清理无效的缓存数据

## 🔄 升级说明

现有用户升级到网络搜索功能：

1. 更新代码到最新版本
2. 安装可能需要的依赖包
3. 配置搜索API密钥
4. 启用网络搜索功能
5. 测试翻译效果

```bash
# 更新依赖
pip install requests urllib3

# 测试网络搜索功能
python -c "from backend.utils.web_terminology_search import WebTerminologySearcher; print('网络搜索功能已就绪')"
```

通过合理配置和使用网络搜索功能，你可以显著提高专业术语的翻译质量，特别是对于新兴技术和专业领域的内容。 