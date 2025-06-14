# -*- coding: utf-8 -*-
"""
网络术语搜索模块
当遇到不确定的术语翻译时，自动搜索获取准确翻译
"""
import os
import re
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WebTerminologySearcher:
    """网络术语搜索器"""
    
    def __init__(self, cache_file: str = "terminology_search_cache.json", cache_days: int = 30):
        self.cache_file = cache_file
        self.cache_days = cache_days
        self.search_cache = self._load_cache()
        
        # 搜索API配置
        self.search_engines = {
            "bing": {
                "url": "https://api.bing.microsoft.com/v7.0/search",
                "key": os.getenv("BING_SEARCH_API_KEY"),
                "enabled": bool(os.getenv("BING_SEARCH_API_KEY"))
            },
            "serper": {
                "url": "https://google.serper.dev/search",
                "key": os.getenv("SERPER_API_KEY"),
                "enabled": bool(os.getenv("SERPER_API_KEY"))
            }
        }
        
        # 搜索配置
        self.max_results = 5
        self.timeout = 10
        self.rate_limit_delay = 1  # 搜索间隔（秒）
        self.last_search_time = 0
        
        # 可信翻译来源
        self.trusted_sources = [
            "wikipedia.org",
            "baidu.com", 
            "zhihu.com",
            "jianshu.com",
            "csdn.net",
            "stackoverflow.com",
            "github.com",
            "microsoft.com",
            "google.com",
            "apple.com",
            "amazon.com"
        ]
    
    def _load_cache(self) -> Dict:
        """加载搜索缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # 清理过期缓存
                current_time = datetime.now()
                cleaned_cache = {}
                
                for key, value in cache_data.items():
                    if 'timestamp' in value:
                        cache_time = datetime.fromisoformat(value['timestamp'])
                        if current_time - cache_time < timedelta(days=self.cache_days):
                            cleaned_cache[key] = value
                
                logger.info(f"加载术语搜索缓存: {len(cleaned_cache)} 条记录")
                return cleaned_cache
                
            except Exception as e:
                logger.error(f"加载搜索缓存失败: {str(e)}")
        
        return {}
    
    def _save_cache(self):
        """保存搜索缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.search_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存搜索缓存失败: {str(e)}")
    
    def _get_cache_key(self, term: str) -> str:
        """生成缓存键"""
        return hashlib.md5(term.lower().encode()).hexdigest()
    
    def _rate_limit(self):
        """速率限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_search_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            time.sleep(sleep_time)
        
        self.last_search_time = time.time()
    
    def _search_bing(self, query: str) -> List[Dict]:
        """使用Bing搜索API"""
        if not self.search_engines["bing"]["enabled"]:
            return []
        
        try:
            headers = {
                "Ocp-Apim-Subscription-Key": self.search_engines["bing"]["key"],
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            params = {
                "q": query,
                "count": self.max_results,
                "mkt": "zh-CN",
                "responseFilter": "Webpages"
            }
            
            self._rate_limit()
            response = requests.get(
                self.search_engines["bing"]["url"], 
                headers=headers, 
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for item in data.get("webPages", {}).get("value", []):
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "source": "bing"
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Bing搜索失败: {str(e)}")
        
        return []
    
    def _search_serper(self, query: str) -> List[Dict]:
        """使用Serper Google搜索API"""
        if not self.search_engines["serper"]["enabled"]:
            return []
        
        try:
            headers = {
                "X-API-KEY": self.search_engines["serper"]["key"],
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": query,
                "gl": "cn",
                "hl": "zh-cn",
                "num": self.max_results
            }
            
            self._rate_limit()
            response = requests.post(
                self.search_engines["serper"]["url"],
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for item in data.get("organic", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "source": "serper"
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Serper搜索失败: {str(e)}")
        
        return []
    
    def _fallback_search(self, query: str) -> List[Dict]:
        """备用搜索方法（爬虫）"""
        try:
            # 简单的DuckDuckGo搜索
            search_url = f"https://duckduckgo.com/html/?q={quote(query)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            self._rate_limit()
            response = requests.get(search_url, headers=headers, timeout=self.timeout)
            
            if response.status_code == 200:
                # 简单解析搜索结果
                import re
                results = []
                
                # 提取搜索结果标题和链接
                pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(pattern, response.text)
                
                for url, title in matches[:self.max_results]:
                    results.append({
                        "title": title.strip(),
                        "url": url,
                        "snippet": "",
                        "source": "duckduckgo"
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"备用搜索失败: {str(e)}")
        
        return []
    
    def search_term_translation(self, english_term: str) -> List[Dict]:
        """搜索术语翻译"""
        # 检查缓存
        cache_key = self._get_cache_key(english_term)
        if cache_key in self.search_cache:
            logger.debug(f"使用缓存结果: {english_term}")
            return self.search_cache[cache_key].get("results", [])
        
        # 构建搜索查询
        queries = [
            f'"{english_term}" 中文翻译',
            f'"{english_term}" 是什么意思',
            f'"{english_term}" 中文 含义',
            f'{english_term} translation Chinese'
        ]
        
        all_results = []
        
        # 尝试不同的搜索引擎
        for query in queries[:2]:  # 限制查询数量
            # 优先使用付费API
            results = self._search_serper(query)
            if not results:
                results = self._search_bing(query)
            if not results:
                results = self._fallback_search(query)
            
            all_results.extend(results)
            
            if len(all_results) >= self.max_results:
                break
        
        # 去重并过滤
        unique_results = []
        seen_urls = set()
        
        for result in all_results:
            url = result.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 缓存结果
        self.search_cache[cache_key] = {
            "term": english_term,
            "results": unique_results[:self.max_results],
            "timestamp": datetime.now().isoformat()
        }
        
        self._save_cache()
        logger.info(f"搜索术语翻译完成: {english_term}, 找到 {len(unique_results)} 个结果")
        
        return unique_results[:self.max_results]
    
    def extract_translation_from_results(self, english_term: str, search_results: List[Dict]) -> Optional[str]:
        """从搜索结果中提取翻译"""
        if not search_results:
            return None
        
        # 收集所有文本内容
        all_text = ""
        for result in search_results:
            all_text += f" {result.get('title', '')} {result.get('snippet', '')}"
        
        # 使用正则表达式提取可能的中文翻译
        patterns = [
            # "term" 中文翻译是 "翻译"
            rf'"{re.escape(english_term)}"[^"]*?(?:中文翻译|翻译|含义|意思)[^"]*?(?:是|为|：|:)[^"]*?"([^"]*?)"',
            rf'"{re.escape(english_term)}"[^"]*?(?:中文翻译|翻译|含义|意思)[^"]*?(?:是|为|：|:)([^，。；！？\n]*)',
            # term（翻译）
            rf'{re.escape(english_term)}[（(]([^）)]*?)[）)]',
            # 中文词汇在文本中的模式
            rf'(?:是|为|叫做|称为|指|即)([^，。；！？\n]*?{english_term}|{english_term}[^，。；！？\n]*?)',
        ]
        
        candidate_translations = set()
        
        for pattern in patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    for m in match:
                        if m.strip():
                            candidate_translations.add(m.strip())
                else:
                    if match.strip():
                        candidate_translations.add(match.strip())
        
        # 过滤和评分候选翻译
        valid_translations = []
        
        for translation in candidate_translations:
            # 基本过滤
            if (len(translation) > 20 or len(translation) < 2 or 
                translation.lower() == english_term.lower() or
                not re.search(r'[\u4e00-\u9fff]', translation)):
                continue
            
            # 计算可信度得分
            score = 0
            
            # 长度合理性
            if 2 <= len(translation) <= 10:
                score += 2
            
            # 中文字符比例
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', translation))
            if chinese_chars / len(translation) > 0.7:
                score += 2
            
            # 是否来自可信来源
            for result in search_results:
                if translation in result.get('title', '') or translation in result.get('snippet', ''):
                    for trusted_source in self.trusted_sources:
                        if trusted_source in result.get('url', ''):
                            score += 3
                            break
            
            valid_translations.append((translation, score))
        
        # 返回得分最高的翻译
        if valid_translations:
            valid_translations.sort(key=lambda x: x[1], reverse=True)
            best_translation = valid_translations[0][0]
            logger.info(f"提取到最佳翻译: {english_term} -> {best_translation}")
            return best_translation
        
        return None
    
    def search_and_translate(self, english_term: str) -> Optional[str]:
        """搜索并获取术语翻译"""
        try:
            # 搜索相关结果
            search_results = self.search_term_translation(english_term)
            
            if not search_results:
                logger.warning(f"未找到搜索结果: {english_term}")
                return None
            
            # 从结果中提取翻译
            translation = self.extract_translation_from_results(english_term, search_results)
            
            if translation:
                logger.info(f"网络搜索翻译成功: {english_term} -> {translation}")
                return translation
            else:
                logger.warning(f"无法从搜索结果中提取翻译: {english_term}")
                return None
                
        except Exception as e:
            logger.error(f"网络搜索翻译失败: {english_term}, 错误: {str(e)}")
            return None
    
    def batch_search_uncertain_terms(self, uncertain_terms: List[str]) -> Dict[str, str]:
        """批量搜索不确定的术语"""
        results = {}
        
        for term in uncertain_terms:
            translation = self.search_and_translate(term)
            if translation:
                results[term] = translation
            
            # 避免过快请求
            time.sleep(0.5)
        
        return results

def detect_uncertain_terms(text: str, existing_terminology: Dict[str, str]) -> List[str]:
    """
    检测文本中可能需要搜索的不确定术语
    """
    # 提取可能的专业术语
    potential_terms = []
    
    # 大写开头的单词或短语（可能是专有名词）
    capitalized_words = re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', text)
    potential_terms.extend(capitalized_words)
    
    # 全大写的缩写
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
    potential_terms.extend(acronyms)
    
    # 技术相关的词汇模式
    tech_patterns = [
        r'\b\w*(?:API|SDK|IDE|OS|UI|UX|AI|ML|DL|IoT|AR|VR)\w*\b',
        r'\b\w*(?:software|hardware|database|algorithm|framework)\w*\b',
        r'\b\w*(?:cloud|server|network|security|crypto)\w*\b'
    ]
    
    for pattern in tech_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        potential_terms.extend(matches)
    
    # 过滤已知术语和常见词汇
    uncertain_terms = []
    common_words = {'The', 'This', 'That', 'With', 'For', 'And', 'But', 'Not', 'You', 'All', 'Can', 'Had', 'Her', 'Was', 'One', 'Our', 'Out', 'Day', 'Get', 'Has', 'Him', 'His', 'How', 'Its', 'New', 'Now', 'Old', 'See', 'Two', 'Way', 'Who', 'Boy', 'Did', 'Man', 'Men', 'Put', 'Say', 'She', 'Too', 'Use'}
    
    for term in potential_terms:
        if (term not in existing_terminology and 
            term not in common_words and 
            len(term) > 2 and 
            not term.isdigit()):
            uncertain_terms.append(term)
    
    # 去重
    uncertain_terms = list(set(uncertain_terms))
    
    return uncertain_terms

# 全局搜索器实例
web_searcher = WebTerminologySearcher()

def enhance_terminology_with_web_search(text: str, existing_terminology: Dict[str, str], 
                                      max_search_terms: int = 5) -> Dict[str, str]:
    """
    使用网络搜索增强术语库
    """
    if not any(engine["enabled"] for engine in web_searcher.search_engines.values()):
        logger.warning("未配置搜索API，跳过网络搜索")
        return existing_terminology
    
    # 检测不确定的术语
    uncertain_terms = detect_uncertain_terms(text, existing_terminology)
    
    if not uncertain_terms:
        logger.info("未发现需要搜索的不确定术语")
        return existing_terminology
    
    # 限制搜索数量
    search_terms = uncertain_terms[:max_search_terms]
    logger.info(f"发现 {len(uncertain_terms)} 个不确定术语，将搜索前 {len(search_terms)} 个")
    
    # 批量搜索
    search_results = web_searcher.batch_search_uncertain_terms(search_terms)
    
    # 合并到现有术语库
    enhanced_terminology = existing_terminology.copy()
    enhanced_terminology.update(search_results)
    
    if search_results:
        logger.info(f"网络搜索新增 {len(search_results)} 个术语翻译")
        for en, zh in search_results.items():
            logger.info(f"  {en} -> {zh}")
    
    return enhanced_terminology 