# -*- coding: utf-8 -*-
"""
翻译系统配置文件
包含术语库管理、翻译参数、质量控制等配置选项
"""
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class TerminologyConfig:
    """术语库配置"""
    # 预定义术语库开关
    use_predefined_terms: bool = True
    
    # 自定义术语库文件路径
    custom_terminology_path: Optional[str] = None
    
    # 自动提取术语开关
    auto_extract_terms: bool = True
    
    # 网络搜索增强
    enable_web_search: bool = False  # 默认关闭，需要用户主动启用
    max_web_search_terms: int = 5
    web_search_cache_days: int = 30
    
    # 术语库合并策略 (priority: 'predefined' > 'custom' > 'extracted' > 'web_search')
    merge_strategy: str = "priority"  # or "merge_all"
    
    # 术语库大小限制（避免prompt过长）
    max_terms_in_prompt: int = 50
    
    # 术语匹配模式
    case_sensitive: bool = False
    
    # 术语验证开关
    validate_terms: bool = True
    
    # 术语库保存路径
    output_terminology_path: Optional[str] = None

@dataclass
class TranslationConfig:
    """翻译配置"""
    # 翻译模式
    use_three_stage: bool = True
    
    # 批量翻译大小
    batch_size: int = 3
    
    # 模型参数
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.1
    num_predict: int = 1024
    
    # 翻译质量控制
    max_retries: int = 3
    
    # 时间控制
    timeout_seconds: int = 180
    
    # 输出控制
    ensure_pure_chinese: bool = True
    max_chinese_chars_per_line: int = 20

@dataclass
class QualityConfig:
    """翻译质量配置"""
    # 术语一致性检查
    check_terminology_consistency: bool = True
    
    # 长度检查
    check_translation_length: bool = True
    max_length_ratio: float = 2.0  # 中文长度/英文长度的最大比例
    
    # 翻译完整性检查
    check_completeness: bool = True
    
    # 字符检查
    check_invalid_chars: bool = True
    invalid_chars: List[str] = field(default_factory=lambda: ['□', '■', '▲', '●'])
    
    # 格式检查
    check_formatting: bool = True
    
    # 自动修正
    auto_correct: bool = True

@dataclass
class TranslationSystemConfig:
    """翻译系统总配置"""
    terminology: TerminologyConfig = field(default_factory=TerminologyConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    
    @classmethod
    def load_from_env(cls) -> 'TranslationSystemConfig':
        """从环境变量加载配置"""
        config = cls()
        
        # 术语库配置
        config.terminology.use_predefined_terms = os.getenv("USE_PREDEFINED_TERMS", "true").lower() == "true"
        config.terminology.custom_terminology_path = os.getenv("CUSTOM_TERMINOLOGY_PATH")
        config.terminology.auto_extract_terms = os.getenv("AUTO_EXTRACT_TERMS", "true").lower() == "true"
        config.terminology.enable_web_search = os.getenv("ENABLE_WEB_SEARCH", "false").lower() == "true"
        config.terminology.max_web_search_terms = int(os.getenv("MAX_WEB_SEARCH_TERMS", "5"))
        config.terminology.max_terms_in_prompt = int(os.getenv("MAX_TERMS_IN_PROMPT", "50"))
        
        # 翻译配置
        config.translation.use_three_stage = os.getenv("USE_THREE_STAGE", "true").lower() == "true"
        config.translation.batch_size = int(os.getenv("TRANSLATION_BATCH_SIZE", "3"))
        config.translation.temperature = float(os.getenv("TRANSLATION_TEMPERATURE", "0.2"))
        config.translation.max_retries = int(os.getenv("TRANSLATION_MAX_RETRIES", "3"))
        config.translation.timeout_seconds = int(os.getenv("TRANSLATION_TIMEOUT", "180"))
        
        # 质量控制配置
        config.quality.check_terminology_consistency = os.getenv("CHECK_TERMINOLOGY", "true").lower() == "true"
        config.quality.auto_correct = os.getenv("AUTO_CORRECT", "true").lower() == "true"
        
        return config
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            "terminology": {
                "use_predefined_terms": self.terminology.use_predefined_terms,
                "custom_terminology_path": self.terminology.custom_terminology_path,
                "auto_extract_terms": self.terminology.auto_extract_terms,
                "max_terms_in_prompt": self.terminology.max_terms_in_prompt,
                "case_sensitive": self.terminology.case_sensitive,
                "validate_terms": self.terminology.validate_terms,
            },
            "translation": {
                "use_three_stage": self.translation.use_three_stage,
                "batch_size": self.translation.batch_size,
                "temperature": self.translation.temperature,
                "top_p": self.translation.top_p,
                "max_retries": self.translation.max_retries,
                "timeout_seconds": self.translation.timeout_seconds,
                "ensure_pure_chinese": self.translation.ensure_pure_chinese,
            },
            "quality": {
                "check_terminology_consistency": self.quality.check_terminology_consistency,
                "check_translation_length": self.quality.check_translation_length,
                "check_completeness": self.quality.check_completeness,
                "auto_correct": self.quality.auto_correct,
            }
        }

# 默认配置实例
DEFAULT_CONFIG = TranslationSystemConfig()

# 领域特定配置
DOMAIN_CONFIGS = {
    "technology": TranslationSystemConfig(
        terminology=TerminologyConfig(
            use_predefined_terms=True,
            auto_extract_terms=True,
            max_terms_in_prompt=100,  # 技术类视频术语更多
        ),
        translation=TranslationConfig(
            use_three_stage=True,
            batch_size=2,  # 技术翻译需要更高质量
            temperature=0.1,  # 更低的温度保证准确性
        )
    ),
    
    "business": TranslationSystemConfig(
        terminology=TerminologyConfig(
            use_predefined_terms=True,
            auto_extract_terms=True,
            max_terms_in_prompt=60,
        ),
        translation=TranslationConfig(
            use_three_stage=True,
            batch_size=3,
            temperature=0.2,
        )
    ),
    
    "entertainment": TranslationSystemConfig(
        terminology=TerminologyConfig(
            use_predefined_terms=False,  # 娱乐内容专业术语较少
            auto_extract_terms=True,
            max_terms_in_prompt=30,
        ),
        translation=TranslationConfig(
            use_three_stage=False,  # 可以使用快速翻译
            batch_size=5,
            temperature=0.3,  # 稍高温度保证自然流畅
        )
    ),
    
    "education": TranslationSystemConfig(
        terminology=TerminologyConfig(
            use_predefined_terms=True,
            auto_extract_terms=True,
            max_terms_in_prompt=80,
        ),
        translation=TranslationConfig(
            use_three_stage=True,
            batch_size=2,
            temperature=0.15,  # 教育内容需要高准确性
        ),
        quality=QualityConfig(
            check_terminology_consistency=True,
            check_translation_length=True,
            auto_correct=True,
        )
    )
}

def get_config_for_domain(domain: str) -> TranslationSystemConfig:
    """根据领域获取对应配置"""
    return DOMAIN_CONFIGS.get(domain, DEFAULT_CONFIG)

def detect_video_domain(title: str, description: str = "") -> str:
    """简单的视频领域检测"""
    content = (title + " " + description).lower()
    
    # 技术类关键词
    tech_keywords = [
        'programming', 'coding', 'software', 'development', 'api', 'algorithm',
        'machine learning', 'ai', 'artificial intelligence', 'data science',
        'web development', 'app development', 'technology', 'tech', 'computer',
        'javascript', 'python', 'react', 'tutorial', 'programming tutorial'
    ]
    
    # 商业类关键词
    business_keywords = [
        'business', 'marketing', 'sales', 'finance', 'investment', 'startup',
        'entrepreneur', 'management', 'leadership', 'strategy', 'consulting',
        'market', 'revenue', 'profit', 'growth'
    ]
    
    # 教育类关键词
    education_keywords = [
        'education', 'learning', 'course', 'lesson', 'tutorial', 'training',
        'academic', 'university', 'college', 'school', 'teach', 'study',
        'lecture', 'seminar', 'workshop'
    ]
    
    # 娱乐类关键词
    entertainment_keywords = [
        'entertainment', 'movie', 'music', 'game', 'gaming', 'comedy',
        'funny', 'vlog', 'lifestyle', 'travel', 'food', 'cooking',
        'review', 'unboxing', 'reaction'
    ]
    
    # 计算各领域得分
    tech_score = sum(1 for kw in tech_keywords if kw in content)
    business_score = sum(1 for kw in business_keywords if kw in content)
    education_score = sum(1 for kw in education_keywords if kw in content)
    entertainment_score = sum(1 for kw in entertainment_keywords if kw in content)
    
    scores = {
        'technology': tech_score,
        'business': business_score,
        'education': education_score,
        'entertainment': entertainment_score
    }
    
    # 返回得分最高的领域
    max_domain = max(scores, key=scores.get)
    max_score = scores[max_domain]
    
    # 如果得分太低，返回默认
    if max_score < 2:
        return 'general'
    
    return max_domain

# 专业术语库补充
DOMAIN_SPECIFIC_TERMS = {
    "technology": {
        "Frontend": "前端",
        "Backend": "后端",
        "Full Stack": "全栈",
        "DevOps": "开发运维",
        "CI/CD": "持续集成/持续部署",
        "Microservices": "微服务",
        "Container": "容器",
        "Kubernetes": "Kubernetes",
        "Docker": "Docker",
        "AWS": "亚马逊云服务",
        "Azure": "微软云",
        "GCP": "谷歌云平台",
        "Serverless": "无服务器",
    },
    
    "business": {
        "B2B": "企业对企业",
        "B2C": "企业对消费者",
        "SaaS": "软件即服务",
        "KPI": "关键绩效指标",
        "ROI": "投资回报率",
        "MVP": "最小可行产品",
        "Go-to-Market": "市场推广策略",
        "Product-Market Fit": "产品市场匹配",
        "Customer Acquisition Cost": "客户获取成本",
        "Lifetime Value": "客户生命周期价值",
    },
    
    "education": {
        "MOOC": "大规模开放在线课程",
        "E-learning": "在线学习",
        "Curriculum": "课程体系",
        "Assessment": "评估",
        "Pedagogy": "教学法",
        "Learning Management System": "学习管理系统",
        "Blended Learning": "混合学习",
        "Flipped Classroom": "翻转课堂",
    }
}

def get_domain_terms(domain: str) -> Dict[str, str]:
    """获取特定领域的术语库"""
    return DOMAIN_SPECIFIC_TERMS.get(domain, {}) 