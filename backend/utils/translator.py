# -*- coding: utf-8 -*-
"""
字幕翻译：使用本地 Ollama 模型进行专业字幕翻译
支持智能字幕切分、三阶段翻译和术语库功能
"""
import os, requests, srt, tempfile, logging, json, sys, re
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from typing import List, Dict, Tuple, Optional
from googletrans import Translator

# 加载环境变量
load_dotenv()

# Ollama 配置
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")  # 使用 gemma3:27b 模型
# 允许通过环境变量调整生成 token 上限；默认 1024
NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1024"))

# 不翻译的术语列表（保持原样）
NO_TRANSLATE_TERMS = {
    'MCp', 'MCP', 'API', 'SDK', 'IDE', 'GitHub', 'Docker', 'Kubernetes', 'DevOps', 
    'UI', 'UX', 'JSON', 'XML', 'HTTP', 'HTTPS', 'SSL', 'TLS', 'OAuth', 'JWT',
    'CORS', 'WebSocket', 'CDN', 'DNS', 'Redis', 'MongoDB', 'PostgreSQL', 'MySQL',
    'SQLite', 'NoSQL', 'CRM', 'ERP', 'CMS', 'GDPR', 'CCPA', 'IPO', 'CEO', 'CTO',
    'CFO', 'CMO', 'COO', 'CPO', 'VP', 'GM', 'PM', 'PO', 'BA', 'DA', 'SRE',
    'VS Code', 'React', 'Vue', 'Angular', 'Node.js', 'Python', 'JavaScript',
    'TypeScript', 'Java', 'C++', 'C#', 'Go', 'Rust', 'HTML', 'CSS', 'SQL',
    'Claude', 'ChatGPT', 'OpenAI', 'Anthropic', 'Google', 'Microsoft', 'Apple',
    'Amazon', 'Meta', 'Netflix', 'YouTube', 'Twitter', 'LinkedIn', 'Instagram',
    'vibe coding'
}

# 预定义专业术语库
PREDEFINED_TERMINOLOGY = {
    # 科技类
    "AI": "人工智能",
    "Machine Learning": "机器学习", 
    "Deep Learning": "深度学习",
    "Neural Network": "神经网络",
    "API": "应用程序接口",
    "Cloud Computing": "云计算",
    "Blockchain": "区块链",
    "IoT": "物联网",
    "VR": "虚拟现实",
    "AR": "增强现实",
    "GPU": "图形处理器",
    "CPU": "中央处理器",
    "RAM": "内存",
    "SSD": "固态硬盘",
    "Database": "数据库",
    "Algorithm": "算法",
    "Framework": "框架",
    "SDK": "软件开发工具包",
    "IDE": "集成开发环境",
    "GitHub": "GitHub",
    "Docker": "Docker",
    "Kubernetes": "Kubernetes",
    "DevOps": "开发运维",
    "Agile": "敏捷开发",
    "Scrum": "Scrum",
    "MVP": "最小可行产品",
    "UI": "用户界面",
    "UX": "用户体验",
    "Frontend": "前端",
    "Backend": "后端",
    "Full Stack": "全栈",
    "Responsive": "响应式",
    "Progressive Web App": "渐进式网页应用",
    "Single Page Application": "单页应用",
    "Microservices": "微服务",
    "RESTful": "RESTful",
    "GraphQL": "GraphQL",
    "JSON": "JSON",
    "XML": "XML",
    "HTTP": "HTTP",
    "HTTPS": "HTTPS",
    "SSL": "SSL",
    "TLS": "TLS",
    "OAuth": "OAuth",
    "JWT": "JWT",
    "CORS": "跨域资源共享",
    "WebSocket": "WebSocket",
    "CDN": "内容分发网络",
    "DNS": "域名系统",
    "Load Balancer": "负载均衡器",
    "Cache": "缓存",
    "Redis": "Redis",
    "MongoDB": "MongoDB",
    "PostgreSQL": "PostgreSQL",
    "MySQL": "MySQL",
    "SQLite": "SQLite",
    "NoSQL": "NoSQL",
    "Big Data": "大数据",
    "Data Science": "数据科学",
    "Analytics": "分析",
    "Visualization": "可视化",
    "Dashboard": "仪表板",
    "Business Intelligence": "商业智能",
    "CRM": "客户关系管理",
    "ERP": "企业资源规划",
    "CMS": "内容管理系统",
    "E-commerce": "电子商务",
    "Fintech": "金融科技",
    "EdTech": "教育科技",
    "HealthTech": "健康科技",
    "Insurtech": "保险科技",
    "Proptech": "房地产科技",
    "Regtech": "监管科技",
    "Legaltech": "法律科技",
    "Cybersecurity": "网络安全",
    "Penetration Testing": "渗透测试",
    "Vulnerability": "漏洞",
    "Encryption": "加密",
    "Two-Factor Authentication": "双因素认证",
    "Single Sign-On": "单点登录",
    "GDPR": "通用数据保护条例",
    "CCPA": "加州消费者隐私法",
    "Compliance": "合规",
    "Audit": "审计",
    "Risk Management": "风险管理",
    "Incident Response": "事件响应",
    "Disaster Recovery": "灾难恢复",
    "Business Continuity": "业务连续性",
    "Quality Assurance": "质量保证",
    "Testing": "测试",
    "Unit Testing": "单元测试",
    "Integration Testing": "集成测试",
    "End-to-End Testing": "端到端测试",
    "Performance Testing": "性能测试",
    "Load Testing": "负载测试",
    "Stress Testing": "压力测试",
    "Security Testing": "安全测试",
    "Usability Testing": "可用性测试",
    "A/B Testing": "A/B测试",
    "Conversion Rate": "转化率",
    "Click-Through Rate": "点击率",
    "Bounce Rate": "跳出率",
    "User Engagement": "用户参与度",
    "User Retention": "用户留存率",
    "Churn Rate": "流失率",
    "Customer Satisfaction": "客户满意度",
    "Net Promoter Score": "净推荐值",
    "Social Media": "社交媒体",
    "Content Marketing": "内容营销",
    "Search Engine Optimization": "搜索引擎优化",
    "Search Engine Marketing": "搜索引擎营销",
    "Pay-Per-Click": "按点击付费",
    "Cost Per Acquisition": "每次获取成本",
    "Return on Investment": "投资回报率",
    "Return on Ad Spend": "广告支出回报率",
    "Lifetime Value": "终身价值",
    "Average Revenue Per User": "平均每用户收入",
    "Monthly Recurring Revenue": "月经常性收入",
    "Annual Recurring Revenue": "年经常性收入",
    "Gross Revenue": "总收入",
    "Net Revenue": "净收入",
    "Profit Margin": "利润率",
    "Break-Even Point": "盈亏平衡点",
    "Cash Flow": "现金流",
    "Burn Rate": "烧钱率",
    "Runway": "资金跑道",
    "Valuation": "估值",
    "Series A": "A轮融资",
    "Series B": "B轮融资",
    "Series C": "C轮融资",
    "IPO": "首次公开募股",
    "Exit Strategy": "退出策略",
    "Due Diligence": "尽职调查",
    "Term Sheet": "条款清单",
    "Equity": "股权",
    "Vesting": "股权归属",
    "Stock Options": "股票期权",
    "Warrants": "认股权证",
    "Convertible Notes": "可转换票据",
    "Preferred Shares": "优先股",
    "Common Shares": "普通股",
    "Board of Directors": "董事会",
    "Advisory Board": "顾问委员会",
    "Chief Executive Officer": "首席执行官",
    "Chief Technology Officer": "首席技术官",
    "Chief Financial Officer": "首席财务官",
    "Chief Marketing Officer": "首席营销官",
    "Chief Operating Officer": "首席运营官",
    "Chief Product Officer": "首席产品官",
    "Vice President": "副总裁",
    "General Manager": "总经理",
    "Product Manager": "产品经理",
    "Project Manager": "项目经理",
    "Program Manager": "项目群经理",
    "Scrum Master": "Scrum主管",
    "Product Owner": "产品负责人",
    "Business Analyst": "业务分析师",
    "Data Analyst": "数据分析师",
    "UX Designer": "用户体验设计师",
    "UI Designer": "用户界面设计师",
    "Graphic Designer": "平面设计师",
    "Web Designer": "网页设计师",
    "Software Engineer": "软件工程师",
    "Software Developer": "软件开发者",
    "Web Developer": "网页开发者",
    "Mobile Developer": "移动端开发者",
    "Game Developer": "游戏开发者",
    "Data Engineer": "数据工程师",
    "Data Scientists": "数据科学家",
    "Machine Learning Engineer": "机器学习工程师",
    "DevOps Engineer": "DevOps工程师",
    "Site Reliability Engineer": "站点可靠性工程师",
    "Security Engineer": "安全工程师",
    "Quality Assurance Engineer": "质量保证工程师",
    "Test Engineer": "测试工程师",
    "Systems Administrator": "系统管理员",
    "Network Administrator": "网络管理员",
    "Database Administrator": "数据库管理员",
    "Cloud Architect": "云架构师",
    "Solution Architect": "解决方案架构师",
    "Enterprise Architect": "企业架构师",
    "Technical Lead": "技术负责人",
    "Team Lead": "团队负责人",
    "Engineering Manager": "工程经理",
    "Director of Engineering": "工程总监",
    "VP of Engineering": "工程副总裁",
    "CTO": "首席技术官",
    
    # 苹果生态系统专用术语
    "Apple": "苹果",
    "iPhone": "iPhone",
    "iPad": "iPad",
    "Mac": "Mac",
    "MacBook": "MacBook",
    "iMac": "iMac",
    "Apple Watch": "Apple Watch",
    "Apple TV": "Apple TV",
    "HomePod": "HomePod",
    "AirPods": "AirPods",
    "Vision Pro": "Vision Pro",
    "visionOS": "visionOS",
    "iOS": "iOS",
    "macOS": "macOS",
    "watchOS": "watchOS",
    "tvOS": "tvOS",
    "iPadOS": "iPadOS",
    "Xcode": "Xcode",
    "Swift": "Swift",
    "SwiftUI": "SwiftUI",
    "UIKit": "UIKit",
    "AppKit": "AppKit",
    "Cocoa": "Cocoa",
    "Cocoa Touch": "Cocoa Touch",
    "Core Data": "Core Data",
    "Core Animation": "Core Animation",
    "Core Graphics": "Core Graphics",
    "AVFoundation": "AVFoundation",
    "AVPlayer": "AVPlayer",
    "AVPlayerViewController": "AVPlayerViewController",
    "RealityKit": "RealityKit",
    "ARKit": "ARKit",
    "SceneKit": "SceneKit",
    "SpriteKit": "SpriteKit",
    "GameplayKit": "GameplayKit",
    "Metal": "Metal",
    "Core ML": "Core ML",
    "Create ML": "Create ML",
    "CloudKit": "CloudKit",
    "HealthKit": "HealthKit",
    "HomeKit": "HomeKit",
    "WatchKit": "WatchKit",
    "CarPlay": "CarPlay",
    "Siri": "Siri",
    "SiriKit": "SiriKit",
    "App Store": "App Store",
    "TestFlight": "TestFlight",
    "Instruments": "Instruments",
    "Simulator": "模拟器",
    "QuickLook": "QuickLook",
    "QLPreviewController": "QLPreviewController",
    "AVExperienceController": "AVExperienceController",
    "VideoPlayerComponent": "VideoPlayerComponent",
    "ImmersiveSpace": "沉浸式空间",
    "WindowGroup": "窗口组",
    "Mixed": "混合",
    "Progressive": "渐进式",
    "Full": "完全",
    "Spatial Video": "空间视频",
    "Spatial Photos": "空间照片",
    "Apple Immersive Video": "苹果沉浸式视频",
    "Apple Projection Media Profile": "苹果投影媒体配置文件",
    "180-degree": "180度",
    "360-degree": "360度",
    "Ultra Wide": "超宽",
    "Stereo": "立体声",
    "Mono": "单声道",
    "Spatial Audio": "空间音频",
    "WWDC": "苹果全球开发者大会",
    "WWDC23": "2023年苹果全球开发者大会", 
    "WWDC24": "2024年苹果全球开发者大会",
    "WWDC 2023": "2023年苹果全球开发者大会",
    "WWDC 2024": "2024年苹果全球开发者大会",
    "developer.apple.com": "苹果开发者网站",
    "Apple Developer": "苹果开发者",
    "Apple.com": "苹果官网",
    "App Review": "应用审核",
    "Human Interface Guidelines": "人机界面指南",
    "Apple Design Awards": "苹果设计奖",
    "Apple Silicon": "苹果芯片",
    "M1": "M1芯片",
    "M2": "M2芯片",
    "M3": "M3芯片",
    "A-series": "A系列芯片",
    "Bionic": "仿生芯片",
    "Neural Engine": "神经网络引擎",
    "Face ID": "面容ID",
    "Touch ID": "触控ID",
    "Lightning": "Lightning接口",
    "USB-C": "USB-C接口",
    "MagSafe": "MagSafe",
    "AirDrop": "隔空投送",
    "Handoff": "接力",
    "Universal Clipboard": "通用剪贴板",
    "Continuity": "连续互通",
    "iCloud": "iCloud",
    "Apple ID": "Apple ID",
    "Spotify": "Spotify",
    "TikTok": "抖音",
    "WeChat": "微信",
    "WhatsApp": "WhatsApp",
    "Telegram": "Telegram",
    
    # 学术和专业术语
    "Research": "研究",
    "Methodology": "方法论",
    "Hypothesis": "假设",
    "Experiment": "实验",
    "Data": "数据",
    "Analysis": "分析",
    "Statistics": "统计",
    "Correlation": "相关性",
    "Causation": "因果关系",
    "Variable": "变量",
    "Sample": "样本",
    "Population": "总体",
    "Bias": "偏差",
    "Peer Review": "同行评议",
    "Publication": "发表",
    "Citation": "引用",
    "Bibliography": "参考文献",
    "Abstract": "摘要",
    "Introduction": "引言",
    "Conclusion": "结论",
    "Discussion": "讨论",
    "Limitation": "局限性",
    "Future Work": "未来工作",
    
    # 新兴技术
    "NFT": "非同质化代币",
    "Cryptocurrency": "加密货币",
    "Bitcoin": "比特币",
    "Ethereum": "以太坊",
    "DeFi": "去中心化金融",
    "Web3": "Web3",
    "Metaverse": "元宇宙",
    "Quantum Computing": "量子计算",
    "Edge Computing": "边缘计算",
    "5G": "5G",
    "6G": "6G",
    "Autonomous Vehicle": "自动驾驶汽车",
    "Smart City": "智慧城市",
    "Digital Twin": "数字孪生",
    "Augmented Analytics": "增强分析",
    "No-Code": "无代码",
    "Low-Code": "低代码",
    "Serverless": "无服务器",
    "JAMstack": "JAMstack",
    "Headless CMS": "无头内容管理系统",
    # ───── 云平台 / 云服务 ─────
    "AWS": "亚马逊云服务",
    "Amazon Web Services": "亚马逊云服务",
    "Azure": "微软云",
    "Google Cloud": "谷歌云",
    "GCP": "谷歌云",
    "Alibaba Cloud": "阿里云",
    "Tencent Cloud": "腾讯云",
    "DigitalOcean": "DigitalOcean",
    "Heroku": "Heroku",
    "Linode": "Linode",
    "Cloudflare": "Cloudflare",
    "SaaS": "软件即服务",
    "PaaS": "平台即服务",
    "IaaS": "基础设施即服务",
    "FaaS": "函数即服务",
    "S3": "S3对象存储",
    "EC2": "EC2计算服务",
    "Lambda": "Lambda函数",
    "RDS": "关系型数据库服务",
    "CloudFront": "CloudFront内容分发",
    "CloudFormation": "CloudFormation模板",
    "Kinesis": "Kinesis数据流",
    "IAM": "身份和访问管理",
    "BigQuery": "BigQuery大数据分析",
    "Cloud Run": "Cloud Run无服务器运行",
    "Blob Storage": "Blob对象存储",
    "Azure Functions": "Azure函数",
    
    # ───── 容器 / DevOps / 可观测性 ─────
    "Container": "容器",
    "Container Image": "容器镜像",
    "Container Registry": "容器仓库",
    "Helm": "Helm",
    "Helm Chart": "Helm模板",
    "Istio": "Istio",
    "Service Mesh": "服务网格",
    "Envoy": "Envoy",
    "Jenkins": "Jenkins",
    "GitLab CI/CD": "GitLab持续集成/交付",
    "CircleCI": "CircleCI",
    "Travis CI": "Travis CI",
    "Ansible": "Ansible",
    "Chef": "Chef",
    "Puppet": "Puppet",
    "Terraform": "Terraform",
    "Packer": "Packer",
    "Vault": "Vault密钥管理",
    "Consul": "Consul服务发现",
    "Prometheus": "Prometheus监控",
    "Grafana": "Grafana可视化",
    "ELK Stack": "ELK日志栈",
    "OpenTelemetry": "开放可观测性",
    "Canary Release": "金丝雀发布",
    "Blue-Green Deployment": "蓝绿部署",
    
    # ───── 数据工程 / 大数据生态 ─────
    "ETL": "抽取转换加载",
    "ELT": "抽取加载转换",
    "Data Warehouse": "数据仓库",
    "Data Lake": "数据湖",
    "Lakehouse": "湖仓",
    "Delta Lake": "Delta Lake",
    "Iceberg": "Iceberg",
    "Hadoop": "Hadoop",
    "Spark": "Spark",
    "Flink": "Flink",
    "Kafka": "Kafka",
    "Pulsar": "Pulsar",
    "Airflow": "Airflow",
    "NiFi": "NiFi",
    "Presto": "Presto",
    "Trino": "Trino",
    
    # ───── 机器学习 / 深度学习框架 ─────
    "PyTorch": "PyTorch",
    "TensorFlow": "TensorFlow",
    "Keras": "Keras",
    "scikit-learn": "scikit-learn",
    "XGBoost": "XGBoost",
    "LightGBM": "LightGBM",
    "NumPy": "NumPy",
    "Pandas": "pandas",
    "Matplotlib": "Matplotlib",
    "Plotly": "Plotly",
    "Seaborn": "Seaborn",
    "MLflow": "MLflow",
    "Kubeflow": "Kubeflow",
    "TFX": "TFX",
    "ONNX": "ONNX",
    "Hugging Face": "Hugging Face",
    "Transformer": "Transformer",
    "BERT": "BERT",
    "GPT": "GPT",
    "LLM": "大语言模型",
    "RNN": "循环神经网络",
    "CNN": "卷积神经网络",
    "GAN": "生成对抗网络",
    "Diffusion Model": "扩散模型",
    "Stable Diffusion": "Stable Diffusion",
    "DALL·E": "DALL·E",
    "Midjourney": "Midjourney",
    "RL": "强化学习",
    "RLHF": "人类反馈强化学习",
    
    # ───── 网络 / 协议 / 基础设施 ─────
    "TCP": "TCP",
    "UDP": "UDP",
    "IP": "IP协议",
    "TCP/IP": "TCP/IP",
    "IPv4": "IPv4",
    "IPv6": "IPv6",
    "FTP": "FTP",
    "SFTP": "SFTP",
    "SSH": "SSH",
    "DHCP": "DHCP",
    "NAT": "网络地址转换",
    "VPN": "虚拟专用网",
    "Reverse Proxy": "反向代理",
    "Nginx": "Nginx",
    "Apache": "Apache",
    "HAProxy": "HAProxy",
    "BGP": "边界网关协议",
    "QoS": "服务质量",
    
    # ───── 信息安全 / 合规 ─────
    "Firewall": "防火墙",
    "WAF": "Web应用防火墙",
    "IDS": "入侵检测系统",
    "IPS": "入侵防御系统",
    "SIEM": "安全信息事件管理",
    "SOC": "安全运营中心",
    "DLP": "数据防泄漏",
    "Zero Trust": "零信任",
    "SAST": "静态应用安全测试",
    "DAST": "动态应用安全测试",
    "RASP": "运行时应用自我保护",
    "CVE": "公共漏洞与暴露",
    "OWASP": "OWASP",
    "OWASP Top Ten": "OWASP前十",
    "MITRE ATT&CK": "MITRE ATT&CK",
    "PKI": "公钥基础设施",
    "MFA": "多因素认证",
    "AES": "高级加密标准",
    "RSA": "RSA",
    "ECC": "椭圆曲线加密",
    "Hash": "哈希",
    "Salt": "盐值",
    
    # ───── 虚拟化 / 硬件加速 ─────
    "VMware": "VMware",
    "Hyper-V": "Hyper-V",
    "KVM": "KVM",
    "VirtualBox": "VirtualBox",
    "Hypervisor": "虚拟机监控器",
    "SR-IOV": "单根I/O虚拟化",
    "NUMA": "非一致性内存访问",
    "RISC-V": "RISC-V",
    "ARM": "ARM架构",
    "FPGA": "现场可编程门阵列",
    "ASIC": "专用集成电路",
    "TPU": "张量处理器",
    "NPU": "神经网络处理器",
    "DPU": "数据处理器",
    
    # ───── Linux / 操作系统 ─────
    "Kernel": "内核",
    "Shell": "Shell",
    "Bash": "Bash",
    "Zsh": "Zsh",
    "Systemd": "Systemd",
    "Cron": "Cron",
    "Cronjob": "定时任务",
    "Package Manager": "包管理器",
    "APT": "APT",
    "YUM": "YUM",
    "RPM": "RPM",
    "Snap": "Snap",
    "Homebrew": "Homebrew",
    
    # ───── 编程语言 / 生态 ─────
    "JavaScript": "JavaScript",
    "TypeScript": "TypeScript",
    "Go": "Go语言",
    "Rust": "Rust",
    "C": "C语言",
    "C++": "C++",
    "C#": "C#",
    "PHP": "PHP",
    "Ruby": "Ruby",
    "Perl": "Perl",
    "Scala": "Scala",
    "Elixir": "Elixir",
    "Haskell": "Haskell",
    "Lua": "Lua",
    "R": "R语言",
    "MATLAB": "MATLAB",
    
    # ───── 前端框架 / 移动开发 ─────
    "React": "React",
    "Next.js": "Next.js",
    "Vue.js": "Vue.js",
    "Nuxt.js": "Nuxt.js",
    "Angular": "Angular",
    "Svelte": "Svelte",
    "Flutter": "Flutter",
    "React Native": "React Native",
    "Electron": "Electron",
    "Expo": "Expo",
    "Tailwind CSS": "Tailwind CSS",
    "Bootstrap": "Bootstrap",
    "Material-UI": "Material-UI",
    "D3.js": "D3.js",
    
    # ───── 设计 / 用户体验 ─────
    "Wireframe": "线框图",
    "Mockup": "高保真原型",
    "Prototype": "原型",
    "Design System": "设计系统",
    "Style Guide": "样式指南",
    "Accessibility": "可访问性",
    "WCAG": "网页内容无障碍指南",
    "User Journey": "用户旅程",
    "Information Architecture": "信息架构",
    "Card Sorting": "卡片分类",
    
    # ───── 协作 / 工具 ─────
    "Jira": "Jira",
    "Confluence": "Confluence",
    "Slack": "Slack",
    "Microsoft Teams": "Microsoft Teams",
    "Zoom": "Zoom",
    "Figma": "Figma",
    "Sketch": "Sketch",
    "Miro": "Miro",
    "Notion": "Notion",
    
    # ───── 产品 / 指标 ─────
    "KPI": "关键绩效指标",
    "OKR": "目标与关键结果",
    "MAU": "月活跃用户",
    "DAU": "日活跃用户",
    "WAU": "周活跃用户",
    "CAC": "获客成本",
    "CPM": "千次曝光成本",
    "CPC": "每次点击成本",
    "LTV": "客户终身价值",
    "North Star Metric": "北极星指标",
    
    # ───── 商业 / 财务 ─────
    "CAGR": "年复合增长率",
    "EBITDA": "息税折旧摊销前利润",
    "Operating Margin": "营业利润率",
    "Gross Margin": "毛利率",
    "CapEx": "资本支出",
    "OpEx": "运营支出",
    "Run Rate": "年化运行率",
    "Dilution": "股权稀释",
    "SAFE": "简单未来股权协议",
    "SPAC": "特殊目的收购公司",
    
    # ───── Apple 生态补充 ─────
    "M4": "M4芯片",
    "Apple Intelligence": "苹果智能",
    "Spatial Computing": "空间计算",
    
    # ───── 新兴技术 / 热点 ─────
    "RAG": "检索增强生成",
    "AIGC": "生成式人工智能内容",
    "Digital Nomad": "数字游民",
    "Green Computing": "绿色计算",
    "Circular Economy": "循环经济",
    "Regenerative AI": "再生式人工智能",
    "Bioinformatics": "生物信息学",
    "Synthetic Data": "合成数据",
    "TinyML": "嵌入式机器学习",
}

# 设置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加文件日志处理器
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'translator.log')
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# 添加控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
console_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

# 测试日志
logger.debug("这是一条测试日志 - DEBUG")
logger.info("这是一条测试日志 - INFO")
logger.warning("这是一条测试日志 - WARNING")
logger.error("这是一条测试日志 - ERROR")

def protect_no_translate_terms(text: str) -> Tuple[str, Dict[str, str]]:
    """
    保护不翻译的术语，在翻译前将它们替换为占位符
    
    Args:
        text: 原始文本
        
    Returns:
        Tuple[str, Dict[str, str]]: (保护后的文本, 占位符映射)
    """
    protected_text = text
    replacements = {}
    
    # 按长度排序，优先处理长术语
    sorted_terms = sorted(NO_TRANSLATE_TERMS, key=len, reverse=True)
    
    for i, term in enumerate(sorted_terms):
        if term and term in protected_text:
            placeholder = f"__NO_TRANSLATE_{i}__"
            replacements[placeholder] = term
            # 使用单词边界进行精确匹配
            protected_text = re.sub(r'\b' + re.escape(term) + r'\b', placeholder, protected_text, flags=re.IGNORECASE)
    
    return protected_text, replacements

def restore_no_translate_terms(text: str, replacements: Dict[str, str]) -> str:
    """
    恢复不翻译的术语，将占位符替换回原始术语
    
    Args:
        text: 翻译后的文本
        replacements: 占位符映射
        
    Returns:
        str: 恢复后的文本
    """
    restored_text = text
    
    for placeholder, original_term in replacements.items():
        restored_text = restored_text.replace(placeholder, original_term)
    
    return restored_text

def chat_with_ollama(system_prompt: str, user_prompt: str) -> str:
    """
    调用本地 Ollama Chat API，返回 assistant 的全文内容
    """
    payload_chat = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,  # 降低温度以获得更稳定的输出
            "top_p": 0.95,
            "repeat_penalty": 1.1,
            "top_k": 40,
            "num_predict": NUM_PREDICT,
        }
    }
    try:
        logger.info(f"正在使用模型 {OLLAMA_MODEL} 进行处理...")
        logger.debug(f"请求参数: {json.dumps(payload_chat, ensure_ascii=False)}")
        
        # 新版 Ollama (>=0.1.28) 支持 /api/chat
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload_chat, timeout=180)  # 增加超时时间
        if resp.status_code == 404:
            logger.info("Chat API 不可用，尝试使用 Generate API...")
            # 回退到旧版 /api/generate
            payload_gen = {
                "model": OLLAMA_MODEL,
                "prompt": f"{system_prompt}\n\n{user_prompt}",
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "repeat_penalty": 1.1,
                    "top_k": 40,
                    "num_predict": NUM_PREDICT,
                }
            }
            logger.debug(f"Generate API 请求参数: {json.dumps(payload_gen, ensure_ascii=False)}")
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload_gen, timeout=180)
        
        resp.raise_for_status()
        data = resp.json()
        
        # 记录原始响应以便调试
        logger.debug(f"Ollama 响应: {json.dumps(data, ensure_ascii=False)}")
        
        # /api/chat 返回 {"message":{"content":...}}
        if "message" in data:
            return data["message"]["content"]
        # /api/generate 返回 {"response": "..."}
        if "response" in data:
            return data["response"]
        raise ValueError(f"无法解析 Ollama 返回数据: {data}")
    except requests.exceptions.Timeout:
        logger.error("Ollama API 请求超时")
        raise Exception("翻译请求超时，请稍后重试")
    except requests.exceptions.ConnectionError:
        logger.error(f"无法连接到 Ollama 服务: {OLLAMA_URL}")
        raise Exception("无法连接到翻译服务，请确保 Ollama 正在运行")
    except Exception as e:
        logger.error(f"Ollama 调用失败: {str(e)}", exc_info=True)
        raise

def merge_terminology(extracted_terms: Dict[str, str], predefined_terms: Dict[str, str]) -> Dict[str, str]:
    """
    合并自动提取的术语和预定义术语库，预定义术语优先级更高
    """
    merged = extracted_terms.copy()
    
    # 预定义术语优先级更高，覆盖自动提取的术语
    for en_term, zh_term in predefined_terms.items():
        # 支持不同大小写和变体的匹配
        found_match = False
        for existing_term in list(merged.keys()):
            if en_term.lower() == existing_term.lower():
                merged[existing_term] = zh_term  # 使用预定义翻译
                found_match = True
                break
        
        if not found_match:
            merged[en_term] = zh_term
    
    logger.info(f"术语库合并完成: 自动提取 {len(extracted_terms)} 个，预定义 {len(predefined_terms)} 个，最终 {len(merged)} 个")
    return merged

def validate_terminology(terminology: Dict[str, str]) -> Dict[str, str]:
    """
    验证和清理术语库，移除无效的术语对
    """
    validated = {}
    
    for en_term, zh_term in terminology.items():
        # 检查英文术语
        if not en_term or not isinstance(en_term, str) or len(en_term.strip()) == 0:
            continue
            
        # 检查中文翻译
        if not zh_term or not isinstance(zh_term, str) or len(zh_term.strip()) == 0:
            continue
            
        # 清理术语
        clean_en = en_term.strip().strip('"\'')
        clean_zh = zh_term.strip().strip('"\'')
        
        # 避免自我翻译（英文翻译成自己）
        if clean_en.lower() == clean_zh.lower():
            continue
            
        # 长度检查
        if len(clean_en) > 100 or len(clean_zh) > 50:
            continue
            
        validated[clean_en] = clean_zh
    
    logger.debug(f"术语库验证: 原始 {len(terminology)} 个，验证后 {len(validated)} 个")
    return validated

def load_custom_terminology(custom_path: Optional[str] = None) -> Dict[str, str]:
    """
    加载自定义术语库文件
    """
    custom_terms = {}
    
    if custom_path and os.path.exists(custom_path):
        try:
            with open(custom_path, 'r', encoding='utf-8') as f:
                custom_terms = json.load(f)
            logger.info(f"加载自定义术语库: {len(custom_terms)} 个术语")
        except Exception as e:
            logger.error(f"加载自定义术语库失败: {str(e)}")
    
    return custom_terms

def save_terminology(terminology: Dict[str, str], save_path: str):
    """
    保存术语库到文件
    """
    try:
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(terminology, f, ensure_ascii=False, indent=2)
        logger.info(f"术语库已保存到: {save_path}")
    except Exception as e:
        logger.error(f"术语库保存失败: {str(e)}")

def extract_terminology(srt_path: str, custom_terminology_path: Optional[str] = None, enable_web_search: bool = True) -> Dict[str, str]:
    """
    从字幕中提取专业术语和专有名词，生成双语术语库
    结合预定义术语库和自定义术语库
    """
    try:
        # 读取字幕内容
        with open(srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
        
        # 合并所有字幕文本
        all_text = " ".join([sub.content for sub in subs])
        
        # 增强的系统提示，包含更具体的指导
        system_prompt = (
            "You are a terminology extraction expert. Extract technical terms, proper nouns, "
            "brand names, and specialized vocabulary from the given English subtitle text. "
            "Return a JSON object with English terms as keys and their Chinese translations as values. "
            "Focus on:\n"
            "1) Technical terms and jargon (e.g., API, algorithm, framework)\n"
            "2) Proper nouns (names, places, companies)\n"
            "3) Brand names and product names (e.g., iPhone, Google, Microsoft)\n"
            "4) Specialized vocabulary in the video's domain\n"
            "5) Acronyms and abbreviations (e.g., AI, ML, UI/UX)\n"
            "6) Industry-specific terms\n"
            "Guidelines:\n"
            "- Provide accurate, commonly used Chinese translations\n"
            "- For brand names, use established Chinese names when available\n"
            "- Avoid over-translating common English words\n"
            "- Focus on terms that would benefit from consistent translation\n"
            "Return only the JSON object, no explanations."
        )
        
        # 分批处理长文本
        extracted_terms = {}
        text_chunks = [all_text[i:i+1500] for i in range(0, len(all_text), 1500)]
        
        for i, chunk in enumerate(text_chunks[:3]):  # 限制最多处理3个chunk
            user_prompt = f"Extract terminology from this subtitle text (part {i+1}):\n\n{chunk}"
            
            logger.info(f"正在提取术语库 (第 {i+1}/{min(len(text_chunks), 3)} 部分)...")
            response = chat_with_ollama(system_prompt, user_prompt)
            
            # 尝试解析 JSON
            try:
                chunk_terminology = json.loads(response.strip())
                extracted_terms.update(chunk_terminology)
            except json.JSONDecodeError:
                logger.warning(f"第 {i+1} 部分术语提取返回的不是有效JSON，尝试从文本中提取")
                # 如果不是JSON，尝试从文本中提取术语对
                lines = response.strip().split('\n')
                for line in lines:
                    if ':' in line and len(line.split(':', 1)) == 2:
                        en, zh = line.split(':', 1)
                        extracted_terms[en.strip().strip('"')] = zh.strip().strip('"')
        
        # 验证自动提取的术语
        extracted_terms = validate_terminology(extracted_terms)
        
        # 加载自定义术语库
        custom_terms = load_custom_terminology(custom_terminology_path)
        
        # 合并所有术语库：预定义 > 自定义 > 自动提取
        final_terminology = merge_terminology(extracted_terms, PREDEFINED_TERMINOLOGY)
        final_terminology = merge_terminology(final_terminology, custom_terms)
        
        # 网络搜索增强（如果启用）
        if enable_web_search:
            try:
                from .web_terminology_search import enhance_terminology_with_web_search
                
                # 合并所有字幕文本用于不确定术语检测
                all_text = " ".join([sub.content for sub in subs])
                
                # 使用网络搜索增强术语库
                final_terminology = enhance_terminology_with_web_search(
                    all_text, 
                    final_terminology, 
                    max_search_terms=int(os.getenv("MAX_WEB_SEARCH_TERMS", "5"))
                )
                
                logger.info("网络搜索增强术语库完成")
                
            except ImportError:
                logger.warning("网络搜索模块未找到，跳过网络搜索增强")
            except Exception as e:
                logger.error(f"网络搜索增强失败: {str(e)}")
        
        logger.info(f"术语库构建完成: 总计 {len(final_terminology)} 个术语")
        
        # 保存最终术语库到临时文件以供调试
        temp_terminology_path = os.path.join(os.path.dirname(srt_path), 'extracted_terminology.json')
        save_terminology(final_terminology, temp_terminology_path)
        
        return final_terminology
            
    except Exception as e:
        logger.error(f"术语提取失败: {str(e)}")
        # 至少返回预定义术语库
        return PREDEFINED_TERMINOLOGY.copy()

def smart_chinese_subtitle_split(text: str, max_chars: int = 20) -> List[str]:
    """
    智能中文字幕切分，专门优化纯中文内容的分行
    """
    if len(text) <= max_chars:
        return [text]
    
    # 移除多余空格，规范化文本
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 如果文本仍然包含英文单词，先处理空格分割
    if re.search(r'[A-Za-z]+', text):
        # 有英文内容，使用原来的逻辑
        english_words = re.findall(r'[A-Za-z]+', text)
        
        # 尝试在空格处分割（适用于中英混合）
        if ' ' in text:
            space_positions = [i for i, char in enumerate(text) if char == ' ']
            mid_pos = len(text) // 2
            
            for pos in sorted(space_positions, key=lambda x: abs(x - mid_pos)):
                # 如果空格后紧跟英文字符，跳过该断点，避免把英文单词推到下一行
                if pos + 1 < len(text) and text[pos + 1].isalpha():
                    continue
                part1 = text[:pos]
                part2 = text[pos + 1:]
                
                # 检查是否切断英文单词
                cut_word = False
                for word in english_words:
                    word_start = text.find(word)
                    word_end = word_start + len(word) if word_start != -1 else -1
                    if word_start <= pos < word_end:
                        cut_word = True
                        break
                
                if (len(part1) <= max_chars and len(part2) <= max_chars and 
                    len(part1) >= 3 and not cut_word):
                    return [part1.strip(), part2.strip()]
    
    # 纯中文处理逻辑
    # 中文标点符号切分优先级（按重要性排序）
    primary_punctuation = ['。', '！', '？']  # 句号类
    secondary_punctuation = ['，', '；', '：']  # 逗号类  
    tertiary_punctuation = ['、', '…', '——']  # 其他
    
    # 按优先级尝试标点符号分割
    for punct_group in [primary_punctuation, secondary_punctuation, tertiary_punctuation]:
        for punct in punct_group:
            if punct in text:
                punct_positions = [i for i, char in enumerate(text) if char == punct]
                if punct_positions:
                    # 选择最接近中间的标点位置
                    mid_pos = len(text) // 2
                    best_pos = min(punct_positions, key=lambda x: abs(x - mid_pos))
                    
                    if best_pos < len(text) - 1:
                        part1 = text[:best_pos + 1]
                        part2 = text[best_pos + 1:].strip()
                        
                        if (len(part1) <= max_chars and len(part2) <= max_chars and 
                            len(part1) >= 3 and len(part2) >= 2):
                            return [part1.strip(), part2.strip()]
    
    # 如果没有合适的标点，尝试在连接词处分割
    connectors = ['的时候', '然后', '因为', '所以', '但是', '而且', '不过', '的', '了', '在', '和', '与', '或']
    
    for connector in connectors:
        if connector in text:
            connector_pos = text.find(connector)
            if connector_pos > 0 and connector_pos < len(text) - len(connector):
                split_pos = connector_pos + len(connector)
                part1 = text[:split_pos]
                part2 = text[split_pos:].strip()
                
                if (len(part1) <= max_chars and len(part2) <= max_chars and 
                    len(part1) >= 5 and len(part2) >= 2):
                    return [part1.strip(), part2.strip()]
    
    # 最后手段：在合适的位置智能分割
    mid = len(text) // 2
    
    # 向前后搜索，避免在重要词汇中间分割
    for offset in range(min(5, mid // 2)):
        # 向前搜索
        split_pos = mid - offset
        if split_pos > 3 and split_pos < len(text) - 2:
            part1 = text[:split_pos]
            part2 = text[split_pos:]
            if len(part1) <= max_chars and len(part2) <= max_chars:
                return [part1.strip(), part2.strip()]
        
        # 向后搜索
        split_pos = mid + offset
        if split_pos > 3 and split_pos < len(text) - 2:
            part1 = text[:split_pos]
            part2 = text[split_pos:]
            if len(part1) <= max_chars and len(part2) <= max_chars:
                return [part1.strip(), part2.strip()]
    
    # 最终兜底：强制分割
    return [text[:max_chars].strip(), text[max_chars:].strip()]

def optimize_chinese_subtitle_readability(zh_srt_path: str) -> str:
    """
    优化中文字幕可读性，重新切分过长的字幕
    """
    try:
        with open(zh_srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
        
        optimized_subs = []
        
        for sub in subs:
            content = sub.content.strip()
            
            # 检查是否需要分行（超过20个字符或包含过长的单行）
            lines = content.split('\n')
            needs_optimization = False
            
            for line in lines:
                if len(line.strip()) > 20:  # 中文字幕单行最多20字符
                    needs_optimization = True
                    break
            
            if needs_optimization:
                # 重新整理所有行为一行，然后重新分割
                # 保持单词间的空格，避免英文单词被连在一起
                full_text = ' '.join(line.strip() for line in lines if line.strip())
                
                # 使用智能分行
                optimized_lines = smart_chinese_subtitle_split(full_text, max_chars=20)
                sub.content = '\n'.join(optimized_lines)
                
                logger.debug(f"优化字幕分行: '{content}' -> '{sub.content}'")
            
            optimized_subs.append(sub)
        
        # 保存优化后的字幕
        optimized_srt_content = srt.compose(optimized_subs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".optimized.srt", delete=False, encoding="utf-8") as optimized_file:
            optimized_file.write(optimized_srt_content)
            optimized_path = optimized_file.name
        
        logger.info(f"中文字幕可读性优化完成: {optimized_path}")
        return optimized_path
        
    except Exception as e:
        logger.error(f"中文字幕优化失败: {str(e)}")
        return zh_srt_path  # 返回原文件

def smart_subtitle_split(text: str, max_chars: int = 42) -> List[str]:
    """
    智能字幕切分，避免一行过长和断句生硬
    """
    if len(text) <= max_chars:
        return [text]
    
    # 尝试在标点符号处分割
    punctuation = ['. ', '! ', '? ', ', ', '; ', ': ', ' - ', ' — ']
    
    for punct in punctuation:
        if punct in text:
            parts = text.split(punct)
            if len(parts) == 2:
                part1 = parts[0] + punct.strip()
                part2 = parts[1]
                if len(part1) <= max_chars and len(part2) <= max_chars:
                    return [part1, part2]
    
    # 如果没有合适的标点符号，在空格处分割
    words = text.split()
    if len(words) > 1:
        mid = len(words) // 2
        part1 = ' '.join(words[:mid])
        part2 = ' '.join(words[mid:])
        if len(part1) <= max_chars and len(part2) <= max_chars:
            return [part1, part2]
    
    # 最后手段：强制分割
    return [text[:max_chars], text[max_chars:]]

def optimize_subtitle_readability(srt_path: str) -> str:
    """
    优化字幕可读性，重新切分过长的字幕
    """
    try:
        with open(srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
        
        system_prompt = (
            "You are a subtitle readability optimizer. Re-split English subtitles for better readability. "
            "Guidelines:\n"
            "1) Each line should be ≤42 characters\n"
            "2) Split at natural pause points (punctuation, conjunctions)\n"
            "3) Maintain meaning and timing\n"
            "4) Avoid splitting compound words or phrases\n"
            "5) Return the same number of subtitle entries\n"
            "Format: Return each subtitle on a new line, exactly as provided but with optimized line breaks."
        )
        
        optimized_subs = []
        
        for sub in subs:
            if len(sub.content) > 42:
                # 使用AI优化切分
                user_prompt = f"Optimize this subtitle for readability:\n{sub.content}"
                try:
                    optimized_content = chat_with_ollama(system_prompt, user_prompt)
                    sub.content = optimized_content.strip()
                except Exception as e:
                    logger.warning(f"AI优化失败，使用规则切分: {str(e)}")
                    # 回退到规则切分
                    split_lines = smart_subtitle_split(sub.content)
                    sub.content = '\n'.join(split_lines)
            
            optimized_subs.append(sub)
        
        # 保存优化后的字幕
        optimized_srt_content = srt.compose(optimized_subs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".optimized.srt", delete=False, encoding="utf-8") as optimized_file:
            optimized_file.write(optimized_srt_content)
            optimized_path = optimized_file.name
        
        logger.info(f"字幕可读性优化完成: {optimized_path}")
        return optimized_path
        
    except Exception as e:
        logger.error(f"字幕优化失败: {str(e)}")
        return srt_path  # 返回原文件

def check_terminology_consistency(text: str, terminology: Dict[str, str]) -> Tuple[str, List[str]]:
    """
    检查翻译中的术语一致性，并提供修正建议
    """
    issues = []
    corrected_text = text
    
    if not terminology:
        return corrected_text, issues
    
    # 检查是否有英文术语没有被正确翻译
    for en_term, zh_term in terminology.items():
        # 使用正则表达式进行更精确的匹配
        pattern = r'\b' + re.escape(en_term) + r'\b'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            issues.append(f"发现未翻译术语: {en_term} -> 应翻译为: {zh_term}")
            # 替换为正确的中文术语
            corrected_text = re.sub(pattern, zh_term, corrected_text, flags=re.IGNORECASE)
    
    # 检查是否有术语翻译不一致的情况
    for en_term, correct_zh in terminology.items():
        if en_term in text and correct_zh not in text:
            # 可能存在不一致的翻译
            issues.append(f"术语翻译可能不一致: {en_term}")
    
    return corrected_text, issues

def enhance_translation_with_terminology(text: str, terminology: Dict[str, str]) -> str:
    """
    使用术语库增强翻译质量
    """
    if not terminology:
        return text
    
    # 预处理：确保所有术语都被正确识别和翻译
    enhanced_text = text
    
    # 按术语长度排序，先处理长术语避免部分匹配问题
    sorted_terms = sorted(terminology.items(), key=lambda x: len(x[0]), reverse=True)
    
    for en_term, zh_term in sorted_terms:
        # 使用单词边界匹配，避免部分匹配
        pattern = r'\b' + re.escape(en_term) + r'\b'
        enhanced_text = re.sub(pattern, zh_term, enhanced_text, flags=re.IGNORECASE)
    
    return enhanced_text

def has_blank_terminology_issues(text: str) -> bool:
    """
    检测文本是否存在空白专有名词问题
    改进版本：更精确地检测真正的空白问题，而不是正常的专有名词
    """
    if not text:
        return True
    
    # 首先检查是否包含正常的专有名词（这些不是问题）
    normal_terms = NO_TRANSLATE_TERMS | set(PREDEFINED_TERMINOLOGY.keys())
    
    # 如果文本只包含正常的专有名词和中文，则不是问题
    text_words = re.findall(r'\b[A-Za-z]+\b', text)
    if text_words:
        # 检查所有英文单词是否都是正常的专有名词
        all_normal = all(word in normal_terms for word in text_words)
        if all_normal:
            return False  # 所有英文单词都是正常的专有名词，不是问题
        
    # 检测真正的空白模式（这些才是问题）
    blank_patterns = [
        r'",\s*$',           # 行尾的 ","
        r'^\s*",\s*',        # 行首的 ","
        r'",\s*",',          # ", ,"
        r'",\s*,\s*',        # ", ,"
        r'",\s*。',          # ", 。"
        r'",\s*，',          # ", ，"
        r'",\s*！',          # ", ！"
        r'",\s*？',          # ", ？"
        r'",\s*；',          # ", ；"
        r'",\s*：',          # ", ："
        r'^\s*",\s*$',       # 整行只是 ","
        r'\s+",\s+',         # 被空格包围的 ","
        r'",\s*\d+',         # ", 数字"
        r'",\s*[\u4e00-\u9fff]',  # ", 中文"（但排除正常的专有名词）
        r'[\u4e00-\u9fff]\s*",',  # "中文 ,"
        r'Vision\s*OS["\']?\s*,',  # Vision OS",
        r'Vision\s*Pro["\']?\s*,', # Vision Pro",
        r'^\s*,\s*$',        # 整行只是 ","
        r'\s+,\s+',          # 被空格包围的 ","
    ]
    
    for pattern in blank_patterns:
        if re.search(pattern, text):
            return True
    
    # 检查是否有连续的空白引号
    if re.search(r'",\s*",', text) or re.search(r'",\s*,\s*",', text):
        return True
    
    # 检查是否有孤立的引号或逗号
    if re.search(r'\b",\b', text) or re.search(r'\b,\b', text):
        return True
    
    return False

def three_stage_translation(text: str, terminology: Dict[str, str] = None) -> str:
    """
    三阶段翻译：初译 -> 反思 -> 适配
    增强术语一致性检查和专有名词保护
    确保不再产生空白专有名词
    """
    # 预处理：保护不翻译的术语
    protected_text, replacements = protect_no_translate_terms(text)
    
    # 预处理：使用术语库增强原文
    if terminology:
        protected_text = enhance_translation_with_terminology(protected_text, terminology)
    
    # 构建术语库提示
    terminology_prompt = ""
    if terminology:
        # 只选择最重要的术语，避免提示过长
        important_terms = dict(list(terminology.items())[:50])  # 限制术语数量
        term_list = "\n".join([f"- {en}: {zh}" for en, zh in important_terms.items()])
        terminology_prompt = (
            f"\n\nIMPORTANT TERMINOLOGY (must use these exact translations):\n{term_list}\n"
            "CRITICAL RULES:\n"
            "1. Use ONLY the Chinese translations provided above for these terms\n"
            "2. For terms not in the list: translate them appropriately but NEVER leave blank\n"
            "3. If unsure about a translation, keep the original English term rather than leaving blank\n"
            "4. ABSOLUTELY FORBIDDEN: replacing terms with empty quotes (\"\"), commas, or blank spaces\n"
            "5. When encountering proper nouns like 'Vision Pro', 'visionOS', etc., either translate them or keep them as-is\n"
        )
    
    # 增强的系统提示 - 重点强调不要留空白
    system_prompt = (
        "You are a professional subtitle translator specializing in technical content. "
        "Translate the English subtitle to natural Simplified Chinese. "
        "CRITICAL REQUIREMENTS - THESE RULES ARE ABSOLUTE: "
        "1. Use the provided terminology translations EXACTLY as specified\n"
        "2. For proper nouns, brand names, technical terms: translate them or keep them if commonly used in Chinese\n"
        "3. NEVER EVER leave terms as blank spaces, empty quotes (\"\"), or lone commas\n"
        "4. If you cannot translate a term, keep the original English term intact\n"
        "5. Create a single, coherent Chinese sentence without line breaks\n"
        "6. Make the translation natural and colloquial while maintaining technical accuracy\n"
        "7. ZERO TOLERANCE for blank replacements - every word must have meaning\n"
        "8. Output format: single line of Chinese text only\n"
        "9. No explanations, no options, no meta-commentary\n"
        "10. QUALITY CHECK: Before finalizing, ensure no blanks, empty quotes, or meaningless punctuation\n"
        + terminology_prompt
    )
    
    try:
        # 一次性完成翻译，但加强监控
        translation = chat_with_ollama(system_prompt, f"Translate to Chinese only (NO BLANKS ALLOWED):\n{protected_text}")
        
        # 恢复不翻译的术语
        translation = restore_no_translate_terms(translation, replacements)
        
        # 清理翻译结果
        cleaned_translation = clean_translation_output(translation.strip())
        
        # 立即检查是否有空白问题
        if has_blank_terminology_issues(cleaned_translation):
            logger.warning(f"检测到空白问题: {cleaned_translation}")
            # 使用预防系统和立即修复
            try:
                from .prevention_system import check_and_fix_blank_issues
                cleaned_translation, was_fixed = check_and_fix_blank_issues(cleaned_translation)
                if was_fixed:
                    logger.info(f"预防系统修复: {cleaned_translation}")
                else:
                    # 备用修复方案
                    from .immediate_fix import fix_current_subtitle_issues
                    cleaned_translation = fix_current_subtitle_issues(cleaned_translation)
                    logger.info(f"备用修复: {cleaned_translation}")
            except ImportError:
                logger.error("无法导入修复工具")
        
        # 术语一致性检查和修正
        if terminology:
            corrected_translation, issues = check_terminology_consistency(cleaned_translation, terminology)
            if issues:
                logger.debug(f"术语一致性问题: {issues}")
                cleaned_translation = corrected_translation
        
        # 进一步确保纯中文输出
        cleaned_translation = ensure_pure_chinese(cleaned_translation, terminology)
        
        # 最终检查 - 这是最后一道防线
        if has_blank_terminology_issues(cleaned_translation):
            logger.error(f"最终防线：仍有空白问题: {cleaned_translation}")
            try:
                from .prevention_system import check_and_fix_blank_issues, validate_translation_before_save
                # 使用全面验证和修复
                cleaned_translation, remaining_issues = validate_translation_before_save(text, cleaned_translation)
                if remaining_issues:
                    logger.warning(f"最终验证仍有问题: {remaining_issues}")
                    # 最后的备用修复
                    from .immediate_fix import fix_current_subtitle_issues
                    cleaned_translation = fix_current_subtitle_issues(cleaned_translation)
                logger.info(f"最终防线修复: {cleaned_translation}")
            except ImportError:
                logger.error("无法导入修复工具")
        
        # 确保结果不为空
        if not cleaned_translation or not cleaned_translation.strip():
            logger.error("翻译结果为空，使用原文")
            cleaned_translation = text
        
        logger.debug(f"翻译结果: {cleaned_translation}")
        return cleaned_translation
        
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        # 回退到简单翻译
        return translate_simple(text, terminology)

def ensure_pure_chinese(text: str, terminology: Dict[str, str] = None) -> str:
    """
    确保字幕内容为纯中文，但保留重要的专有名词
    改进版本：更智能地处理专有名词，包括AI相关术语
    """
    import re
    
    if not text or not text.strip():
        return text
    
    # 合并所有术语库
    protected_terms = set()
    if terminology:
        protected_terms.update(terminology.keys())
    
    # 添加预定义术语
    protected_terms.update(PREDEFINED_TERMINOLOGY.keys())
    
    # 添加不翻译术语
    protected_terms.update(NO_TRANSLATE_TERMS)
    
    # 添加常见的应该保留的专有名词模式
    common_proper_nouns = {
        # 苹果生态
        "Apple", "iPhone", "iPad", "Mac", "Vision Pro", "visionOS", "iOS", "macOS", 
        "Swift", "SwiftUI", "Xcode", "RealityKit", "ARKit", "AVPlayer", "QuickLook",
        "WWDC", "App Store", "TestFlight",
        
        # 常见科技品牌和产品
        "Google", "Microsoft", "Amazon", "Facebook", "Meta", "Netflix", "YouTube", 
        "Android", "Windows", "Linux", "Chrome", "Safari", "Firefox",
        "GitHub", "Docker", "Kubernetes", "React", "Vue", "Angular",
        
        # 编程语言和技术
        "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
        "HTML", "CSS", "SQL", "NoSQL", "JSON", "XML", "API", "REST", "GraphQL",
        
        # AI和机器学习相关
        "Claude", "ChatGPT", "OpenAI", "Anthropic", "GPT", "LLM", "AI", "ML", 
        "Machine Learning", "Deep Learning", "Neural Network", "TensorFlow", 
        "PyTorch", "Scikit-learn", "Pandas", "NumPy", "Matplotlib", "Jupyter",
        
        # 其他常见专有名词
        "VR", "AR", "IoT", "SaaS", "PaaS", "IaaS", "DevOps", "CI/CD", "AWS", 
        "Azure", "GCP", "Cloud", "Blockchain", "Bitcoin", "Ethereum", "NFT"
    }
    
    protected_terms.update(common_proper_nouns)
    
    # 临时替换保护专有名词
    temp_replacements = {}
    protected_text = text
    
    for i, term in enumerate(sorted(protected_terms, key=len, reverse=True)):
        if term and re.search(r'\b' + re.escape(term) + r'\b', protected_text, re.IGNORECASE):
            placeholder = f"__PROTECTED_TERM_{i}__"
            temp_replacements[placeholder] = term
            # 使用单词边界进行精确匹配
            protected_text = re.sub(r'\b' + re.escape(term) + r'\b', placeholder, protected_text, flags=re.IGNORECASE)
    
    # 移除剩余的英文单词（但保留保护的术语）
    # 只移除独立的英文单词，避免影响中文字符
    protected_text = re.sub(r'\b[A-Za-z]+\b', '', protected_text)
    
    # 恢复保护的专有名词
    for placeholder, original_term in temp_replacements.items():
        protected_text = protected_text.replace(placeholder, original_term)
    
    # 清理多余的空格和标点
    protected_text = re.sub(r'\s+', ' ', protected_text).strip()
    protected_text = protected_text.strip(' .,!?;:')
    
    # 如果清理后文本为空，返回原文
    if not protected_text.strip():
        logger.warning(f"文本清理后变为空白，返回原文: {text[:50]}...")
        return text.strip()
    
    return protected_text

def clean_translation_output(text: str) -> str:
    """
    Clean the raw translation output from the model.
    Aims to remove common artifacts like prefixes, quotes, and normalize mixed language content.
    """
    import re
    logger.debug(f"Original text for cleaning: '{text}'")

    # Start with the input text
    current_text = text.strip()

    # Remove common instructional prefixes or model self-correction phrases
    prefixes_to_remove = [
        r"^(翻译结果|翻译|译文)[:：\s]*",
        r"^Chinese translation[:：\s]*",
        r"^Translation[:：\s]*",
        r"^Chinese[:：\s]*",
        r"^Simplified Chinese[:：\s]*",
        r"^Sure, here is the translation[:：\s]*",
        r"^Here's the translation[:：\s]*",
        r"^Okay, here's the translation[:：\s]*",
        r"^The translation is[:：\s]*",
        r"^\s*\"", # Leading quote with optional spaces
    ]
    for prefix_pattern in prefixes_to_remove:
        current_text = re.sub(prefix_pattern, '', current_text, flags=re.IGNORECASE).strip()

    # Remove common suffixes or end-of-generation markers
    suffixes_to_remove = [
        r"\"\s*$", # Trailing quote with optional spaces
    ]
    for suffix_pattern in suffixes_to_remove:
        current_text = re.sub(suffix_pattern, '', current_text, flags=re.IGNORECASE).strip()

    # Handle quotes
    if current_text.startswith('"') and current_text.endswith('"'):
        current_text = current_text[1:-1]
    elif current_text.startswith("'") and current_text.endswith("'"):
        current_text = current_text[1:-1]
    elif current_text.startswith(''') and current_text.endswith('''):
        current_text = current_text[1:-1]
    elif current_text.startswith('"') and current_text.endswith('"'):
        current_text = current_text[1:-1]

    # Normalize spacing around mixed Chinese-English words
    # 移除中英之间的所有空格，不再强制在英文→中文处插入空格
    current_text = re.sub(r'([\u4e00-\u9fff])\s*([A-Za-z])', r'\1\2', current_text)
    current_text = re.sub(r'([A-Za-z])\s*([\u4e00-\u9fff])', r'\1\2', current_text)
    
    # But avoid too many spaces around single words
    current_text = re.sub(r'\s+', ' ', current_text).strip()
    
    # Clean up excessive spacing around punctuation
    current_text = re.sub(r'\s+([，。！？；：、])', r'\1', current_text)  # Remove space before Chinese punctuation
    current_text = re.sub(r'([，。！？；：、])\s+', r'\1', current_text)   # Remove space after Chinese punctuation

    # 移除出现在两个中文字符之间的空格（不影响中英混排保留的空格）
    current_text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', current_text)

    cleaned_text = current_text.strip()

    if not cleaned_text and text:
        logger.warning(f"clean_translation_output resulted in empty string for input: '{text[:100]}...'. Returning snippet of original text.")
        return text.strip()[:200]
    
    logger.debug(f"Cleaned translation: '{cleaned_text}'")
    return cleaned_text

def translate_simple(text: str, terminology: Dict[str, str] = None) -> str:
    """
    简单翻译（回退方案）
    """
    # 保护不翻译的术语
    protected_text, replacements = protect_no_translate_terms(text)
    
    terminology_prompt = ""
    if terminology:
        term_list = "\n".join([f"- {en}: {zh}" for en, zh in terminology.items()])
        terminology_prompt = f"\n\nTerminology reference:\n{term_list}\n"
    
    system_prompt = (
        "You are a professional subtitle translator. "
        "Translate to natural Simplified Chinese ONLY. "
        "Output only Chinese characters, no English, no explanations. "
        + terminology_prompt
    )
    
    try:
        translation = chat_with_ollama(system_prompt, f"Translate: {protected_text}")
        # 恢复不翻译的术语
        translation = restore_no_translate_terms(translation, replacements)
        return clean_translation_output(translation.strip())
    except Exception as e:
        logger.error(f"简单翻译失败: {str(e)}")
        return text  # 返回原文

# 全局常量：提示词与分隔符
DELIMITER = "|||"

def translate_subtitle_batch_enhanced(subs, terminology: Dict[str, str] = None, use_three_stage: bool = True, batch_size: int = 3):
    """
    增强版字幕批量翻译，支持术语库和三阶段翻译
    """
    translated_subs = []
    
    # 构建术语库提示
    terminology_prompt = ""
    if terminology:
        term_list = "\n".join([f"- {en}: {zh}" for en, zh in terminology.items()])
        terminology_prompt = f"\n\nTerminology reference (use these translations consistently):\n{term_list}\n"
    
    if use_three_stage:
        # 使用三阶段翻译（逐条处理以保证质量）
        for i, sub in enumerate(subs):
            logger.info(f"三阶段翻译进度: {i+1}/{len(subs)}")
            try:
                translated_content = three_stage_translation(sub.content, terminology)
                # 只保留中文翻译，不保留英文原文
                sub.content = translated_content
                translated_subs.append(sub)
            except Exception as e:
                logger.error(f"三阶段翻译失败，使用简单翻译: {str(e)}")
                translated_content = translate_simple(sub.content, terminology)
                # 只保留中文翻译，不保留英文原文
                sub.content = translated_content
                translated_subs.append(sub)
    else:
        # 使用批量翻译（更快但质量可能略低）
        for i in range(0, len(subs), batch_size):
            batch = subs[i:i + batch_size]
            start_idx = i + 1
            
            # 保护不翻译的术语
            batch_text_parts = []
            all_replacements = {}
            
            for j, s in enumerate(batch):
                protected_content, replacements = protect_no_translate_terms(s.content.replace(DELIMITER, ' '))
                batch_text_parts.append(f"{start_idx + j}{DELIMITER}{protected_content}")
                all_replacements.update(replacements)
            
            batch_text = "\n".join(batch_text_parts)
            
            logger.info(f"批量翻译进度: {i//batch_size + 1}/{(len(subs) + batch_size - 1)//batch_size}")
            
            system_prompt = (
                "You are a professional bilingual subtitle translator. "
                "Translate each English subtitle line into concise, natural Simplified Chinese. "
                "CRITICAL: Output ONLY Chinese characters, absolutely NO English text. "
                "Requirements:\n"
                "1) Translate ALL words to Chinese - do not keep any English words\n"
                "2) For proper nouns, brand names: translate them completely to Chinese\n"
                "3) Create single-line Chinese translations without internal line breaks\n"
                "4) Do NOT merge, split, or omit lines\n"
                "5) Output the SAME number of lines in the SAME order\n"
                f"6) Format exactly: <index>{DELIMITER}<Chinese_translation_only>\n"
                "7) No mixed language, no English words, no explanations\n"
                + terminology_prompt
            )
            
            prompt = (
                "以下字幕已按行编号，格式 <编号>{0}<英文内容>。\n"
                "请逐行翻译为简体中文，遵守：\n"
                "• 不增删或合并行；\n"
                "• 译文口语、自然，保留专有名词；\n"
                f"• 仅输出 <编号>{0}<中文译文>，不要输出英文和其他说明。\n\n"
                "字幕：\n{1}"
            ).format(DELIMITER, batch_text)
            
            try:
                assistant_content = chat_with_ollama(system_prompt, prompt)
                translated_lines = assistant_content.strip().split('\n')
                
                # 解析翻译结果
                mapping = {}
                for line in translated_lines:
                    if not line.strip() or DELIMITER not in line:
                        continue
                    try:
                        idx_str, zh = line.split(DELIMITER, 1)
                        idx = int(idx_str.strip())
                        # 恢复不翻译的术语
                        zh = restore_no_translate_terms(zh.strip(), all_replacements)
                        mapping[idx] = zh
                    except ValueError:
                        continue
                
                # 应用翻译结果
                for j, sub in enumerate(batch, start=start_idx):
                    zh = mapping.get(j)
                    if zh:
                        # 清理翻译结果，只保留中文翻译
                        cleaned_zh = clean_translation_output(zh)
                        
                        # 进一步清理，确保纯中文内容
                        cleaned_zh = ensure_pure_chinese(cleaned_zh, terminology)
                        
                        # 如果翻译结果过长，进行智能分行
                        if len(cleaned_zh) > 20:
                            split_lines = smart_chinese_subtitle_split(cleaned_zh, max_chars=20)
                            cleaned_zh = '\n'.join(split_lines)
                        
                        sub.content = cleaned_zh
                    translated_subs.append(sub)
                    
            except Exception as e:
                logger.error(f"批量翻译失败: {str(e)}")
                translated_subs.extend(batch)
    
    return translated_subs

def translate_srt_to_zh(srt_path: str, use_smart_split: bool = True, use_three_stage: bool = True, extract_terms: bool = True, custom_terminology_path: Optional[str] = None, enable_web_search: bool = True) -> str:
    """
    将 SRT 字幕文件翻译成中文
    支持智能切分、三阶段翻译和术语库
    
    Args:
        srt_path: SRT 文件路径
        use_smart_split: 是否使用智能字幕切分
        use_three_stage: 是否使用三阶段翻译
        extract_terms: 是否提取术语库
        
    Returns:
        str: 翻译后的 SRT 文件路径
    """
    try:
        # 1. 智能字幕切分优化（英文字幕）
        if use_smart_split:
            logger.info("正在优化英文字幕可读性...")
            srt_path = optimize_subtitle_readability(srt_path)
        
        # 2. 提取术语库
        terminology = {}
        if extract_terms:
            logger.info("正在提取术语库...")
            terminology = extract_terminology(srt_path, custom_terminology_path, enable_web_search)
        
        # 3. 读取字幕文件
        with open(srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
            
        logger.info(f"开始翻译字幕，共 {len(subs)} 条")
        if terminology:
            logger.info(f"使用术语库，包含 {len(terminology)} 个术语")
        
        # 4. 翻译字幕
        translated_subs = translate_subtitle_batch_enhanced(
            subs, 
            terminology=terminology, 
            use_three_stage=use_three_stage
        )
        
        # 5. 生成翻译后的字幕文件
        zh_srt_content = srt.compose(translated_subs)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".zh.srt", delete=False, encoding="utf-8") as zh_file:
            zh_file.write(zh_srt_content)
            zh_temp_path = zh_file.name
        
        # 6. 优化中文字幕的分行和可读性
        logger.info("正在优化中文字幕分行...")
        zh_optimized_path = optimize_chinese_subtitle_readability(zh_temp_path)
        
        # 清理临时文件
        if zh_temp_path != zh_optimized_path and os.path.exists(zh_temp_path):
            os.unlink(zh_temp_path)
                
        logger.info(f"字幕翻译和优化完成，已保存到: {zh_optimized_path}")
        return zh_optimized_path
        
    except Exception as e:
        logger.error(f"字幕翻译失败: {str(e)}")
        raise Exception(f"字幕翻译失败: {str(e)}")

def translate_text(text: str, target_lang: str = 'zh') -> str:
    """
    使用 Google Translate API 翻译文本
    """
    try:
        translator = Translator()
        result = translator.translate(text, dest=target_lang)
        return result.text
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        raise

def translate_srt(srt_path: str, target_lang: str = 'zh') -> str:
    """
    翻译 SRT 字幕文件
    """
    try:
        # 读取原始字幕文件
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析字幕内容
        subs = pysrt.open(srt_path)
        
        # 翻译每个字幕条目
        for sub in subs:
            sub.text = translate_text(sub.text, target_lang)
        
        # 创建临时文件保存翻译后的字幕
        temp_srt = tempfile.NamedTemporaryFile(suffix='.srt', delete=False)
        subs.save(temp_srt.name, encoding='utf-8')
        
        return temp_srt.name
    except Exception as e:
        logger.error(f"字幕翻译失败: {str(e)}")
        raise

def translate_video_title(title: str) -> str:
    """
    翻译视频标题为中文
    
    Args:
        title: 英文标题
        
    Returns:
        str: 中文标题
    """
    try:
        if not title or title.strip() == "":
            return "未命名视频"
        
        # 如果标题已经是中文，直接返回
        chinese_chars = len([c for c in title if '\u4e00' <= c <= '\u9fff'])
        if chinese_chars > len(title) * 0.3:  # 如果中文字符超过30%，认为已经是中文
            return title
        
        system_prompt = (
            "You are a professional video title translator. "
            "Translate the English video title to natural Simplified Chinese. "
            "Requirements:\n"
            "1) Output only Chinese characters\n"
            "2) Keep the title concise and attractive\n"
            "3) Preserve the main meaning and keywords\n"
            "4) No English words or explanations\n"
            "5) Maximum 30 Chinese characters\n"
        )
        
        user_prompt = f"Translate this video title to Chinese:\n{title}"
        
        translation = chat_with_ollama(system_prompt, user_prompt)
        cleaned_translation = clean_translation_output(translation.strip())
        
        # 如果翻译失败或为空，返回原标题
        if not cleaned_translation or len(cleaned_translation.strip()) == 0:
            return title
            
        logger.info(f"标题翻译: {title} -> {cleaned_translation}")
        return cleaned_translation
        
    except Exception as e:
        logger.error(f"标题翻译失败: {str(e)}")
        return title  # 翻译失败时返回原标题