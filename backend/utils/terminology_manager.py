# -*- coding: utf-8 -*-
"""
术语库管理工具
提供术语库的增删改查、导入导出、一致性检查等功能
"""
import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class TerminologyManager:
    """术语库管理器"""
    
    def __init__(self, terminology_file: str = "terminology.json"):
        self.terminology_file = terminology_file
        self.terminology = self._load_terminology()
    
    def _load_terminology(self) -> Dict[str, str]:
        """加载术语库"""
        if os.path.exists(self.terminology_file):
            try:
                with open(self.terminology_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载术语库失败: {str(e)}")
                return {}
        return {}
    
    def save_terminology(self) -> bool:
        """保存术语库"""
        try:
            # 创建备份
            if os.path.exists(self.terminology_file):
                backup_file = f"{self.terminology_file}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename(self.terminology_file, backup_file)
            
            # 保存术语库
            with open(self.terminology_file, 'w', encoding='utf-8') as f:
                json.dump(self.terminology, f, ensure_ascii=False, indent=2, sort_keys=True)
            
            logger.info(f"术语库已保存: {len(self.terminology)} 个术语")
            return True
        except Exception as e:
            logger.error(f"保存术语库失败: {str(e)}")
            return False
    
    def add_term(self, english: str, chinese: str) -> bool:
        """添加术语"""
        if not english or not chinese:
            logger.warning("英文术语和中文翻译都不能为空")
            return False
        
        english = english.strip()
        chinese = chinese.strip()
        
        if english in self.terminology:
            logger.info(f"术语已存在，更新翻译: {english} -> {chinese}")
        else:
            logger.info(f"添加新术语: {english} -> {chinese}")
        
        self.terminology[english] = chinese
        return True
    
    def remove_term(self, english: str) -> bool:
        """删除术语"""
        if english in self.terminology:
            removed_chinese = self.terminology.pop(english)
            logger.info(f"删除术语: {english} -> {removed_chinese}")
            return True
        else:
            logger.warning(f"术语不存在: {english}")
            return False
    
    def update_term(self, english: str, chinese: str) -> bool:
        """更新术语翻译"""
        if english not in self.terminology:
            logger.warning(f"术语不存在: {english}")
            return False
        
        old_chinese = self.terminology[english]
        self.terminology[english] = chinese
        logger.info(f"更新术语翻译: {english} -> {old_chinese} => {chinese}")
        return True
    
    def search_terms(self, keyword: str) -> Dict[str, str]:
        """搜索术语"""
        keyword = keyword.lower()
        results = {}
        
        for en, zh in self.terminology.items():
            if (keyword in en.lower() or keyword in zh.lower()):
                results[en] = zh
        
        return results
    
    def get_all_terms(self) -> Dict[str, str]:
        """获取所有术语"""
        return self.terminology.copy()
    
    def import_from_file(self, file_path: str, overwrite: bool = False) -> Tuple[int, int]:
        """从文件导入术语库"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_terms = json.load(f)
            
            added_count = 0
            updated_count = 0
            
            for en, zh in imported_terms.items():
                if en in self.terminology:
                    if overwrite:
                        self.terminology[en] = zh
                        updated_count += 1
                else:
                    self.terminology[en] = zh
                    added_count += 1
            
            logger.info(f"导入术语库完成: 新增 {added_count} 个，更新 {updated_count} 个")
            return added_count, updated_count
            
        except Exception as e:
            logger.error(f"导入术语库失败: {str(e)}")
            return 0, 0
    
    def export_to_file(self, file_path: str, keywords: Optional[List[str]] = None) -> bool:
        """导出术语库到文件"""
        try:
            export_terms = self.terminology
            
            # 如果指定了关键词，只导出相关术语
            if keywords:
                export_terms = {}
                for keyword in keywords:
                    matching_terms = self.search_terms(keyword)
                    export_terms.update(matching_terms)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_terms, f, ensure_ascii=False, indent=2, sort_keys=True)
            
            logger.info(f"导出术语库完成: {len(export_terms)} 个术语")
            return True
            
        except Exception as e:
            logger.error(f"导出术语库失败: {str(e)}")
            return False
    
    def import_from_csv(self, file_path: str, overwrite: bool = False) -> Tuple[int, int]:
        """从CSV文件导入术语库"""
        try:
            import csv
            added_count = 0
            updated_count = 0
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # 跳过标题行
                next(reader, None)
                
                for row in reader:
                    if len(row) >= 2:
                        en, zh = row[0].strip(), row[1].strip()
                        if en and zh:
                            if en in self.terminology:
                                if overwrite:
                                    self.terminology[en] = zh
                                    updated_count += 1
                            else:
                                self.terminology[en] = zh
                                added_count += 1
            
            logger.info(f"从CSV导入术语库完成: 新增 {added_count} 个，更新 {updated_count} 个")
            return added_count, updated_count
            
        except Exception as e:
            logger.error(f"从CSV导入术语库失败: {str(e)}")
            return 0, 0
    
    def export_to_csv(self, file_path: str, keywords: Optional[List[str]] = None) -> bool:
        """导出术语库到CSV文件"""
        try:
            import csv
            export_terms = self.terminology
            
            # 如果指定了关键词，只导出相关术语
            if keywords:
                export_terms = {}
                for keyword in keywords:
                    matching_terms = self.search_terms(keyword)
                    export_terms.update(matching_terms)
            
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['English', 'Chinese'])  # 标题行
                
                for en, zh in sorted(export_terms.items()):
                    writer.writerow([en, zh])
            
            logger.info(f"导出术语库到CSV完成: {len(export_terms)} 个术语")
            return True
            
        except Exception as e:
            logger.error(f"导出术语库到CSV失败: {str(e)}")
            return False
    
    def validate_terminology(self) -> List[str]:
        """验证术语库，返回问题列表"""
        issues = []
        
        for en, zh in self.terminology.items():
            # 检查空值
            if not en.strip():
                issues.append("发现空的英文术语")
            if not zh.strip():
                issues.append(f"术语 '{en}' 的中文翻译为空")
            
            # 检查异常字符
            if len(en) > 100:
                issues.append(f"英文术语过长: {en[:50]}...")
            if len(zh) > 50:
                issues.append(f"中文翻译过长: {en} -> {zh[:20]}...")
            
            # 检查自我翻译
            if en.lower() == zh.lower():
                issues.append(f"自我翻译: {en}")
            
            # 检查重复值
            duplicate_terms = [k for k, v in self.terminology.items() if v == zh and k != en]
            if duplicate_terms:
                issues.append(f"重复翻译 '{zh}': {en}, {', '.join(duplicate_terms)}")
        
        return issues
    
    def clean_terminology(self) -> int:
        """清理术语库，删除无效术语"""
        issues = self.validate_terminology()
        cleaned_count = 0
        
        # 删除空值术语
        to_remove = []
        for en, zh in self.terminology.items():
            if not en.strip() or not zh.strip() or en.lower() == zh.lower():
                to_remove.append(en)
        
        for en in to_remove:
            self.terminology.pop(en, None)
            cleaned_count += 1
        
        logger.info(f"清理术语库完成: 删除 {cleaned_count} 个无效术语")
        return cleaned_count
    
    def get_statistics(self) -> Dict[str, any]:
        """获取术语库统计信息"""
        stats = {
            "total_terms": len(self.terminology),
            "avg_english_length": 0,
            "avg_chinese_length": 0,
            "longest_english_term": "",
            "longest_chinese_term": "",
            "categories": {}
        }
        
        if self.terminology:
            english_lengths = [len(en) for en in self.terminology.keys()]
            chinese_lengths = [len(zh) for zh in self.terminology.values()]
            
            stats["avg_english_length"] = sum(english_lengths) / len(english_lengths)
            stats["avg_chinese_length"] = sum(chinese_lengths) / len(chinese_lengths)
            
            # 找最长的术语
            longest_en = max(self.terminology.keys(), key=len)
            longest_zh = max(self.terminology.values(), key=len)
            stats["longest_english_term"] = longest_en
            stats["longest_chinese_term"] = longest_zh
            
            # 简单分类统计
            tech_count = sum(1 for en in self.terminology.keys() 
                           if any(word in en.lower() for word in ['api', 'software', 'system', 'data', 'tech']))
            business_count = sum(1 for en in self.terminology.keys() 
                               if any(word in en.lower() for word in ['business', 'market', 'sales', 'revenue']))
            brand_count = sum(1 for en in self.terminology.keys() 
                            if en[0].isupper() and ' ' not in en)
            
            stats["categories"] = {
                "technology": tech_count,
                "business": business_count,
                "brands": brand_count,
                "others": len(self.terminology) - tech_count - business_count - brand_count
            }
        
        return stats

# 使用示例和测试函数
def create_sample_terminology_file():
    """创建示例术语库文件"""
    sample_terms = {
        "API": "应用程序接口",
        "Machine Learning": "机器学习",
        "Deep Learning": "深度学习",
        "Artificial Intelligence": "人工智能",
        "Database": "数据库",
        "Algorithm": "算法",
        "Framework": "框架",
        "Cloud Computing": "云计算",
        "Big Data": "大数据",
        "Internet of Things": "物联网"
    }
    
    with open("sample_terminology.json", 'w', encoding='utf-8') as f:
        json.dump(sample_terms, f, ensure_ascii=False, indent=2)
    
    print("示例术语库文件已创建: sample_terminology.json")

if __name__ == "__main__":
    # 测试术语库管理器
    manager = TerminologyManager("test_terminology.json")
    
    # 添加一些测试术语
    manager.add_term("API", "应用程序接口")
    manager.add_term("Machine Learning", "机器学习")
    manager.add_term("Deep Learning", "深度学习")
    
    # 保存术语库
    manager.save_terminology()
    
    # 获取统计信息
    stats = manager.get_statistics()
    print(f"术语库统计: {stats}")
    
    # 搜索术语
    results = manager.search_terms("learning")
    print(f"搜索结果: {results}")
    
    # 验证术语库
    issues = manager.validate_terminology()
    if issues:
        print(f"发现问题: {issues}")
    else:
        print("术语库验证通过") 