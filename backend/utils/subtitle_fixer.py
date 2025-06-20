# -*- coding: utf-8 -*-
"""
字幕修复工具：修复翻译后字幕中的专有名词空白问题
"""
import re
import srt
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# 不翻译的术语列表（保持原样）
NO_TRANSLATE_TERMS = {
    'MCp', 'MCP', 'API', 'SDK', 'IDE', 'GitHub', 'Docker', 'Kubernetes', 'DevOps', 
    'UI', 'UX', 'JSON', 'XML', 'HTTP', 'HTTPS', 'SSL', 'TLS', 'OAuth', 'JWT',
    'CORS', 'WebSocket', 'CDN', 'DNS', 'Redis', 'MongoDB', 'PostgreSQL', 'MySQL',
    'SQLite', 'NoSQL', 'CRM', 'ERP', 'CMS', 'GDPR', 'CCPA', 'IPO', 'CEO', 'CTO',
    'CFO', 'CMO', 'COO', 'CPO', 'VP', 'GM', 'PM', 'PO', 'BA', 'DA', 'SRE',
    'vibe coding'
}

# 常见的空白模式和对应的可能术语
BLANK_PATTERN_FIXES = {
    # 苹果生态系统 - 针对实际问题优化
    r'Vision\s*OS["\']?\s*,?\s*2': 'visionOS 2',
    r'Vision\s*Pro["\']?\s*,?\s*2': 'Vision Pro 2', 
    r'在\s*Vision\s*OS["\']?\s*,?\s*(\d+)': r'在visionOS \1',
    r'在\s*Vision\s*Pro["\']?\s*,?\s*(\d+)': r'在Vision Pro \1',
    r'visionOS["\']?\s*,?\s*(\d+)': r'visionOS \1',
    
    # 修复引号和逗号的问题
    r'Vision\s*OS["\']?\s*,': 'visionOS',
    r'Vision\s*Pro["\']?\s*,': 'Vision Pro',
    r'([A-Za-z]+)["\']?\s*,\s*(\d+)': r'\1 \2',  # 通用的 "名称", 数字 模式
    
    # 原有规则优化
    r'\b",\s*2\b': 'Vision Pro 2',
    r'\b",\s*26\b': 'visionOS 26',  
    r'\b",\s*2023\b': 'WWDC 2023',
    r'\b",\s*2024\b': 'WWDC 2024',
    r'\b",\s*23\b': 'WWDC23',
    r'\b",\s*24\b': 'WWDC24',
    
    # QuickLook相关
    r'快速预览["\']?\s*,?': 'QuickLook',
    r'QLPreviewController': 'QLPreviewController',
    
    # API和框架
    r'\b",",\b': 'AVPlayer',
    r'\b",\s*框架\b': 'RealityKit框架',
    r'应用程序接口\s*接口\s*接口': 'API',
    r'应用程序接口\s*接口': 'API',
    r'\bAPI\s*接口': 'API',
    
    # 更精确的模式匹配
    r'\b",\s*应用程序\b': 'Vision Pro应用程序',
    r'在\s*",\s*中': '在Vision Pro中',
    r'在\s*",\s*上': '在Vision Pro上',
    r'使用\s*",': '使用RealityKit',
    r'\b媒体\s*",': '媒体播放器',
    r'\b体验控制器': 'AVExperienceController',
    
    # 处理多余的标点符号
    r'([A-Za-z]+)["\']?\s*,\s*(["\']?)': r'\1',  # 移除名称后的引号逗号
    r'["\']?\s*,\s*([A-Za-z]+)': r'\1',  # 移除前面的引号逗号
    
    # 通用模式
    r'",\s*团队': '苹果团队',
    r'我是\s*",': '我是苹果',
    r'在\s*",\s*(?=[\u4e00-\u9fff])': '在苹果',
    r'\b",\s*空间': 'Vision Pro空间',
    r'\b沉浸式\s*",': '沉浸式体验',
    r'\b",\s*视频': '空间视频',
    r'\b",\s*的': '苹果的',
    r'\b",\s*和\s*",': '苹果和谷歌',
    r'\b",\s*或\s*",': 'iPhone或iPad',
    
    # 清理残留的空白引号和逗号
    r'\s*",\s*': ' ',
    r'\s*,"\s*': ' ',
    r'"\s*,\s*': ' ',
}

# 上下文相关的修复规则
CONTEXT_FIXES = [
    # 基于上下文的智能修复
    {
        'pattern': r'我是\s*",\s*团队的',
        'replacement': '我是苹果团队的',
        'context': ['苹果', '开发', '工程师']
    },
    {
        'pattern': r'在\s*",\s*26',
        'replacement': '在visionOS 26',
        'context': ['visionOS', '系统', '版本']
    },
    {
        'pattern': r'使用\s*",\s*框架',
        'replacement': '使用RealityKit框架',
        'context': ['RealityKit', '3D', '渲染']
    },
    {
        'pattern': r'快速预览",',
        'replacement': 'QuickLook',
        'context': ['预览', '媒体', '应用程序接口']
    }
]

def merge_inline_linebreaks(text: str) -> str:
    """Merge line breaks that split words or short phrases.

    This specifically targets cases such as:
        "V\nS\nCode" -> "VS Code"
        "Hello\nWorld" -> "Hello World"
        "MC\np" -> "MCp"
        "M\nC\nP" -> "MCP"
    It replaces newline characters that are between two non-punctuation characters
    with a single space.
    """
    if not text or "\n" not in text:
        return text

    # 1) 英文字母或数字被换行打断的情况（包括MCp、MCP等术语）
    text = re.sub(r"([A-Za-z0-9])\n+([A-Za-z0-9])", r"\1\2", text)
    
    # 2) 英文与中文或其他字符被换行分隔，例如 "Code\n开发"
    text = re.sub(r"([A-Za-z0-9])\n+([^\s])", r"\1 \2", text)
    
    # 3) 中文与英文之间的换行，例如 "开发\nCode"
    text = re.sub(r"([\u4e00-\u9fff])\n+([A-Za-z0-9])", r"\1 \2", text)
    
    # 4) 处理特殊情况：NO_TRANSLATE_TERMS 里的术语被拆分的情况（大小写不敏感）
    for term in NO_TRANSLATE_TERMS:
        if len(term) > 1:
            # 构造大小写不敏感的正则，允许术语被任意数量\n拆分
            pattern = r''
            for ch in term:
                pattern += f'[{ch.lower()}{ch.upper()}]\\n*'
            pattern = r'\b' + pattern.rstrip('\\n*') + r'\b'
            text = re.sub(pattern, term, text, flags=re.IGNORECASE)
    
    # 5) 处理连续的英文字母被换行分隔的情况
    text = re.sub(r"([A-Z])\n+([A-Z])", r"\1\2", text)  # 大写字母之间
    text = re.sub(r"([a-z])\n+([a-z])", r"\1\2", text)  # 小写字母之间
    text = re.sub(r"([A-Z])\n+([a-z])", r"\1\2", text)  # 大写+小写字母之间

    return text

def collapse_linebreaks(text: str, max_lines: int = 2) -> str:
    """Collapse excessive line breaks in subtitle text.

    Args:
        text: Original subtitle text possibly containing many '\n'.
        max_lines: The maximum number of lines allowed. If the text has more
            than this number of non-empty lines, they will be merged into one.

    Returns:
        Text with line breaks collapsed to at most *max_lines*.
    """
    if not text:
        return text

    # Strip each line and filter out empty lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > max_lines:
        return " ".join(lines)  # Merge into a single line separated by spaces
    return "\n".join(lines)

def fix_blank_terminology_in_text(text: str, context_history: List[str] = None) -> str:
    """
    修复单行文本中的空白专有名词
    按优先级顺序应用修复规则
    """
    if not text or not text.strip():
        return text
    
    fixed_text = text
    original_text = text
    
    logger.debug(f"开始修复文本: '{original_text}'")
    
    # 第一轮：精确匹配特定的问题模式
    priority_fixes = [
        (r'Vision\s*OS["\']?\s*,?\s*2\b', 'visionOS 2'),
        (r'Vision\s*Pro["\']?\s*,?\s*2\b', 'Vision Pro 2'),
        (r'在\s*Vision\s*OS["\']?\s*,?\s*(\d+)', r'在visionOS \1'),
        (r'在\s*Vision\s*Pro["\']?\s*,?\s*(\d+)', r'在Vision Pro \1'),
        (r'visionOS["\']?\s*,?\s*(\d+)', r'visionOS \1'),
        (r'应用程序接口\s*接口\s*接口', 'API'),
        (r'应用程序接口\s*接口', 'API'),
    ]
    
    for pattern, replacement in priority_fixes:
        if re.search(pattern, fixed_text, re.IGNORECASE):
            before = fixed_text
            fixed_text = re.sub(pattern, replacement, fixed_text, flags=re.IGNORECASE)
            if before != fixed_text:
                logger.debug(f"优先级修复: '{before}' -> '{fixed_text}'")
    
    # 第二轮：应用基本模式修复
    for pattern, replacement in BLANK_PATTERN_FIXES.items():
        if re.search(pattern, fixed_text, re.IGNORECASE):
            before = fixed_text
            fixed_text = re.sub(pattern, replacement, fixed_text, flags=re.IGNORECASE)
            if before != fixed_text:
                logger.debug(f"基本修复: '{before}' -> '{fixed_text}'")
    
    # 第三轮：应用上下文相关修复
    if context_history:
        context_text = ' '.join(context_history[-5:])  # 使用最近5条字幕作为上下文
        
        for fix_rule in CONTEXT_FIXES:
            pattern = fix_rule['pattern']
            replacement = fix_rule['replacement']
            context_keywords = fix_rule['context']
            
            # 检查上下文是否匹配
            if any(keyword.lower() in context_text.lower() for keyword in context_keywords):
                if re.search(pattern, fixed_text, re.IGNORECASE):
                    before = fixed_text
                    fixed_text = re.sub(pattern, replacement, fixed_text, flags=re.IGNORECASE)
                    if before != fixed_text:
                        logger.debug(f"上下文修复: '{before}' -> '{fixed_text}'")
    
    # 第四轮：处理连续的空白模式
    cleanup_patterns = [
        (r'",\s*",', 'iPhone和iPad'),
        (r'",\s*和\s*",', 'RealityKit和ARKit'),
        (r'例如\s*",', '例如SwiftUI'),
        (r'([A-Za-z]+)["\']?\s*,\s*(["\']?)', r'\1'),  # 移除名称后的引号逗号
        (r'["\']?\s*,\s*([A-Za-z]+)', r'\1'),  # 移除前面的引号逗号
    ]
    
    for pattern, replacement in cleanup_patterns:
        if re.search(pattern, fixed_text):
            before = fixed_text
            fixed_text = re.sub(pattern, replacement, fixed_text)
            if before != fixed_text:
                logger.debug(f"清理修复: '{before}' -> '{fixed_text}'")
    
    # 第五轮：最终清理
    # 清理残留的独立空白引号
    final_cleanup = [
        (r'\s*",\s*', ' '),
        (r'\s*,"\s*', ' '),
        (r'"\s*,\s*', ' '),
        (r'\s+', ' '),  # 多个空格合并为一个
    ]
    
    for pattern, replacement in final_cleanup:
        fixed_text = re.sub(pattern, replacement, fixed_text)
    
    fixed_text = fixed_text.strip()

    # 第五点五：合并行内英文换行
    fixed_text = merge_inline_linebreaks(fixed_text)

    # 第六轮：归并多余换行，避免播放器竖排
    fixed_text = collapse_linebreaks(fixed_text, max_lines=2)

    if fixed_text != original_text:
        logger.info(f"修复完成: '{original_text}' -> '{fixed_text}'")
    
    return fixed_text

def fix_blank_terminology_in_srt(srt_path: str) -> str:
    """
    修复SRT文件中的空白专有名词问题
    
    Args:
        srt_path: 输入的SRT文件路径
        
    Returns:
        str: 修复后的SRT文件路径
    """
    try:
        # 读取SRT文件
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        subs = list(srt.parse(srt_content))
        context_history = []
        fixed_count = 0
        
        logger.info(f"开始修复字幕文件: {srt_path}")
        
        for i, sub in enumerate(subs):
            original_content = sub.content
            
            # 修复当前字幕
            fixed_content = fix_blank_terminology_in_text(original_content, context_history)
            
            if fixed_content != original_content:
                sub.content = fixed_content
                fixed_count += 1
                logger.debug(f"字幕 {i+1}: '{original_content}' -> '{fixed_content}'")
            
            # 更新上下文历史
            context_history.append(fixed_content)
            if len(context_history) > 10:  # 保留最近10条作为上下文
                context_history.pop(0)
        
        # 生成修复后的文件
        fixed_srt_path = srt_path.replace('.srt', '_fixed.srt')
        with open(fixed_srt_path, 'w', encoding='utf-8') as f:
            f.write(srt.compose(subs))
        
        logger.info(f"修复完成: 共修复 {fixed_count} 条字幕，输出到 {fixed_srt_path}")
        return fixed_srt_path
        
    except Exception as e:
        logger.error(f"修复字幕文件失败: {str(e)}")
        return srt_path

def analyze_blank_patterns(srt_path: str) -> Dict[str, int]:
    """
    分析SRT文件中的空白模式，用于改进修复规则
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        subs = list(srt.parse(srt_content))
        
        # 统计空白模式
        blank_patterns = {}
        
        for sub in subs:
            content = sub.content
            
            # 查找各种空白模式
            patterns = [
                r'",\s*\w+',  # ", 词汇"
                r'\w+\s*",',  # "词汇 ,"
                r'",\s*",',   # ", ,"
                r'",\s*\d+',  # ", 数字"
                r'在\s*",',   # "在 ,"
                r'使用\s*",', # "使用 ,"
                r'我是\s*",', # "我是 ,"
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    blank_patterns[match] = blank_patterns.get(match, 0) + 1
        
        # 按频率排序
        sorted_patterns = dict(sorted(blank_patterns.items(), key=lambda x: x[1], reverse=True))
        
        logger.info(f"发现 {len(sorted_patterns)} 种空白模式:")
        for pattern, count in list(sorted_patterns.items())[:10]:
            logger.info(f"  '{pattern}': {count} 次")
        
        return sorted_patterns
        
    except Exception as e:
        logger.error(f"分析空白模式失败: {str(e)}")
        return {}

def suggest_terminology_additions(srt_path: str) -> Dict[str, str]:
    """
    基于空白模式建议新的术语库条目
    """
    patterns = analyze_blank_patterns(srt_path)
    suggestions = {}
    
    # 基于常见空白模式推测可能的术语
    for pattern in patterns.keys():
        if '", 2' in pattern:
            suggestions['Vision Pro 2'] = 'Vision Pro 2'
        elif '", 26' in pattern:
            suggestions['visionOS 26'] = 'visionOS 26'
        elif 'API' in pattern:
            suggestions['API'] = '应用程序接口'
        elif '快速预览' in pattern:
            suggestions['QuickLook'] = 'QuickLook'
        # 可以继续添加更多模式识别逻辑
    
    return suggestions

if __name__ == "__main__":
    # 测试修复功能
    import sys
    if len(sys.argv) > 1:
        srt_file = sys.argv[1]
        print(f"修复字幕文件: {srt_file}")
        
        # 分析空白模式
        print("\n分析空白模式:")
        analyze_blank_patterns(srt_file)
        
        # 修复文件
        print(f"\n开始修复:")
        fixed_file = fix_blank_terminology_in_srt(srt_file)
        print(f"修复完成: {fixed_file}")
        
        # 建议新术语
        print(f"\n建议新增术语:")
        suggestions = suggest_terminology_additions(srt_file)
        for en, zh in suggestions.items():
            print(f"  {en}: {zh}")
    else:
        print("用法: python subtitle_fixer.py <srt_file_path>") 