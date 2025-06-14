# -*- coding: utf-8 -*-
"""
专有名词空白问题预防和监控系统
确保翻译过程中不会产生空白专有名词
"""
import re
import logging
import json
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class BlankIssueReport:
    """空白问题报告"""
    text: str
    patterns_found: List[str]
    timestamp: datetime
    fixed_text: Optional[str] = None
    fix_applied: bool = False

class BlankTerminologyPreventionSystem:
    """空白专有名词预防系统"""
    
    def __init__(self):
        self.issues_detected = []
        self.prevention_rules = self._load_prevention_rules()
        self.monitoring_enabled = True
        
    def _load_prevention_rules(self) -> Dict[str, str]:
        """加载预防规则"""
        return {
            # 空白模式检测规则
            'blank_quotes': r'",\s*\w+',
            'trailing_quotes': r'\w+\s*",',
            'double_quotes': r'",\s*",',
            'quote_numbers': r'",\s*\d+',
            'vision_os_issue': r'Vision\s*OS["\']?\s*,',
            'vision_pro_issue': r'Vision\s*Pro["\']?\s*,',
            'api_repetition': r'应用程序接口\s*接口\s*接口',
            'lone_comma': r'^\s*,\s*$',
            'empty_replacement': r'\s+"",\s*',
        }
    
    def detect_blank_issues(self, text: str) -> BlankIssueReport:
        """检测空白问题"""
        patterns_found = []
        
        for rule_name, pattern in self.prevention_rules.items():
            if re.search(pattern, text):
                patterns_found.append(rule_name)
                logger.warning(f"检测到空白模式 {rule_name}: {pattern}")
        
        report = BlankIssueReport(
            text=text,
            patterns_found=patterns_found,
            timestamp=datetime.now()
        )
        
        if patterns_found:
            self.issues_detected.append(report)
            
        return report
    
    def apply_prevention_fix(self, text: str) -> str:
        """应用预防性修复"""
        if not text:
            return text
            
        fixed_text = text
        
        # 应用修复规则
        fix_rules = {
            r'Vision\s*OS["\']?\s*,?\s*(\d+)': r'visionOS \1',
            r'Vision\s*Pro["\']?\s*,?\s*(\d+)': r'Vision Pro \1',
            r'应用程序接口\s*接口\s*接口': 'API',
            r'应用程序接口\s*接口': 'API',
            r'",\s*(\d+)': r'visionOS \1',
            r'",\s*团队': '苹果团队',
            r'我是\s*",': '我是苹果',
            r'\s*",\s*': ' ',
            r'\s*,"\s*': ' ',
            r'"\s*,\s*': ' ',
        }
        
        for pattern, replacement in fix_rules.items():
            if re.search(pattern, fixed_text):
                before = fixed_text
                fixed_text = re.sub(pattern, replacement, fixed_text, flags=re.IGNORECASE)
                logger.info(f"预防性修复: '{before}' -> '{fixed_text}'")
        
        # 清理多余空格
        fixed_text = re.sub(r'\s+', ' ', fixed_text).strip()
        
        return fixed_text
    
    def validate_translation_quality(self, original: str, translation: str) -> Tuple[bool, List[str]]:
        """验证翻译质量"""
        issues = []
        
        # 检查是否有空白问题
        blank_report = self.detect_blank_issues(translation)
        if blank_report.patterns_found:
            issues.extend([f"空白模式: {pattern}" for pattern in blank_report.patterns_found])
        
        # 检查翻译是否为空
        if not translation.strip():
            issues.append("翻译结果为空")
        
        # 检查是否过度删除了内容
        if len(translation) < len(original) * 0.3:
            issues.append("翻译结果过短，可能丢失内容")
        
        # 检查是否含有过多英文（允许专有名词）
        english_ratio = len(re.findall(r'[a-zA-Z]+', translation)) / max(len(translation.split()), 1)
        if english_ratio > 0.3:
            issues.append(f"英文比例过高: {english_ratio:.2%}")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def get_statistics(self) -> Dict:
        """获取监控统计信息"""
        total_issues = len(self.issues_detected)
        fixed_issues = sum(1 for issue in self.issues_detected if issue.fix_applied)
        
        # 统计最常见的问题类型
        pattern_counts = {}
        for issue in self.issues_detected:
            for pattern in issue.patterns_found:
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        
        return {
            "total_issues_detected": total_issues,
            "issues_fixed": fixed_issues,
            "fix_rate": fixed_issues / total_issues if total_issues > 0 else 0,
            "most_common_patterns": sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "monitoring_enabled": self.monitoring_enabled,
            "last_detection": self.issues_detected[-1].timestamp if self.issues_detected else None
        }
    
    def save_report(self, filepath: str):
        """保存监控报告"""
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "statistics": self.get_statistics(),
            "recent_issues": [
                {
                    "text": issue.text,
                    "patterns": issue.patterns_found,
                    "timestamp": issue.timestamp.isoformat(),
                    "fixed": issue.fix_applied,
                    "fixed_text": issue.fixed_text
                }
                for issue in self.issues_detected[-10:]  # 最近10个问题
            ]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"监控报告已保存: {filepath}")

# 全局预防系统实例
prevention_system = BlankTerminologyPreventionSystem()

def check_and_fix_blank_issues(text: str) -> Tuple[str, bool]:
    """
    检查并修复空白问题
    返回: (修复后的文本, 是否进行了修复)
    """
    if not prevention_system.monitoring_enabled:
        return text, False
    
    # 检测问题
    report = prevention_system.detect_blank_issues(text)
    
    if not report.patterns_found:
        return text, False
    
    # 应用修复
    fixed_text = prevention_system.apply_prevention_fix(text)
    
    # 更新报告
    report.fixed_text = fixed_text
    report.fix_applied = True
    
    logger.info(f"空白问题已修复: '{text}' -> '{fixed_text}'")
    
    return fixed_text, True

def validate_translation_before_save(original: str, translation: str) -> Tuple[str, List[str]]:
    """
    保存前验证翻译质量
    返回: (最终翻译, 问题列表)
    """
    is_valid, issues = prevention_system.validate_translation_quality(original, translation)
    
    if not is_valid:
        logger.warning(f"翻译质量问题: {issues}")
        
        # 尝试修复
        fixed_translation, was_fixed = check_and_fix_blank_issues(translation)
        
        if was_fixed:
            # 重新验证
            is_valid_after_fix, remaining_issues = prevention_system.validate_translation_quality(original, fixed_translation)
            return fixed_translation, remaining_issues
        else:
            return translation, issues
    
    return translation, []

def enable_monitoring():
    """启用监控"""
    prevention_system.monitoring_enabled = True
    logger.info("空白问题监控已启用")

def disable_monitoring():
    """禁用监控"""
    prevention_system.monitoring_enabled = False
    logger.info("空白问题监控已禁用")

def get_prevention_statistics():
    """获取预防系统统计"""
    return prevention_system.get_statistics()

def save_monitoring_report(filepath: str = None):
    """保存监控报告"""
    if filepath is None:
        filepath = f"blank_terminology_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    prevention_system.save_report(filepath)
    return filepath

# 装饰器：自动应用空白检查
def auto_fix_blanks(func):
    """装饰器：自动检查和修复空白问题"""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        # 如果结果是字符串，检查空白问题
        if isinstance(result, str):
            fixed_result, was_fixed = check_and_fix_blank_issues(result)
            if was_fixed:
                logger.info(f"装饰器自动修复: {func.__name__}")
            return fixed_result
        
        return result
    
    return wrapper

if __name__ == "__main__":
    # 测试预防系统
    test_cases = [
        '在Vision OS", 2中，包含像停靠播放和空间视频这样的惊人体验。',
        '我是 ","团队的媒体应用工程师。',
        '快速预览", 提供了两个应用程序接口 接口 接口。',
        '正常的翻译文本，没有问题。',
    ]
    
    print("🛡️ 测试预防系统")
    print("=" * 50)
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {test_text}")
        
        # 检测问题
        report = prevention_system.detect_blank_issues(test_text)
        print(f"问题模式: {report.patterns_found}")
        
        # 修复问题
        if report.patterns_found:
            fixed_text = prevention_system.apply_prevention_fix(test_text)
            print(f"修复结果: {fixed_text}")
        else:
            print("✅ 无问题")
    
    # 显示统计信息
    print(f"\n📊 统计信息:")
    stats = prevention_system.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}") 