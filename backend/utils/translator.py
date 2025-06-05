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

def extract_terminology(srt_path: str) -> Dict[str, str]:
    """
    从字幕中提取专业术语和专有名词，生成双语术语库
    """
    try:
        # 读取字幕内容
        with open(srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
        
        # 合并所有字幕文本
        all_text = " ".join([sub.content for sub in subs])
        
        system_prompt = (
            "You are a terminology extraction expert. Extract technical terms, proper nouns, "
            "brand names, and specialized vocabulary from the given English subtitle text. "
            "Return a JSON object with English terms as keys and their Chinese translations as values. "
            "Focus on:\n"
            "1) Technical terms and jargon\n"
            "2) Proper nouns (names, places, companies)\n"
            "3) Brand names and product names\n"
            "4) Specialized vocabulary\n"
            "5) Acronyms and abbreviations\n"
            "Return only the JSON object, no explanations."
        )
        
        user_prompt = f"Extract terminology from this subtitle text:\n\n{all_text[:2000]}"  # 限制长度
        
        logger.info("正在提取术语库...")
        response = chat_with_ollama(system_prompt, user_prompt)
        
        # 尝试解析 JSON
        try:
            terminology = json.loads(response.strip())
            logger.info(f"成功提取 {len(terminology)} 个术语")
            return terminology
        except json.JSONDecodeError:
            logger.warning("术语提取返回的不是有效JSON，尝试从文本中提取")
            # 如果不是JSON，尝试从文本中提取术语对
            terminology = {}
            lines = response.strip().split('\n')
            for line in lines:
                if ':' in line and len(line.split(':')) == 2:
                    en, zh = line.split(':', 1)
                    terminology[en.strip().strip('"')] = zh.strip().strip('"')
            return terminology
            
    except Exception as e:
        logger.error(f"术语提取失败: {str(e)}")
        return {}

def smart_chinese_subtitle_split(text: str, max_chars: int = 20) -> List[str]:
    """
    智能中文字幕切分，避免一行过长和断句生硬，特别处理中英混合内容
    """
    if len(text) <= max_chars:
        return [text]
    
    # 预处理：识别英文单词和中文内容
    import re
    
    # 先尝试整体优化：如果包含英文单词，优先保持英文单词完整
    english_words = re.findall(r'[A-Za-z]+', text)
    
    # 中文标点符号切分优先级
    chinese_punctuation = ['。', '！', '？', '，', '；', '：', '、', '…', '——']
    
    # 尝试在中文标点符号处分割
    for punct in chinese_punctuation:
        if punct in text:
            # 找到所有标点位置
            punct_positions = [i for i, char in enumerate(text) if char == punct]
            if punct_positions:
                # 选择最接近中间且不会切断英文单词的标点位置
                mid_pos = len(text) // 2
                
                for pos in sorted(punct_positions, key=lambda x: abs(x - mid_pos)):
                    if pos < len(text) - 1:  # 确保不是最后一个字符
                        part1 = text[:pos + 1]
                        part2 = text[pos + 1:]
                        
                        # 检查是否切断了英文单词
                        cut_word = False
                        for word in english_words:
                            word_start = text.find(word)
                            word_end = word_start + len(word) if word_start != -1 else -1
                            if word_start <= pos < word_end:
                                cut_word = True
                                break
                        
                        # 检查分割后的长度是否合理且没有切断英文单词
                        if (len(part1) <= max_chars and len(part2) <= max_chars and 
                            len(part1) >= 3 and not cut_word):
                            return [part1.strip(), part2.strip()]
    
    # 如果没有合适的标点符号，尝试在词语边界分割，优先保护英文单词
    connectors = ['的', '了', '在', '和', '与', '或', '但', '而', '然后', '因为', '所以', '如果', '当', '从']
    
    for connector in connectors:
        connector_pos = text.find(connector)
        if connector_pos > 0 and connector_pos < len(text) - len(connector):
            split_pos = connector_pos + len(connector)
            part1 = text[:split_pos]
            part2 = text[split_pos:]
            
            # 检查是否切断了英文单词
            cut_word = False
            for word in english_words:
                word_start = text.find(word)
                word_end = word_start + len(word) if word_start != -1 else -1
                if word_start <= split_pos < word_end:
                    cut_word = True
                    break
            
            if (len(part1) <= max_chars and len(part2) <= max_chars and 
                len(part1) >= 5 and not cut_word):
                return [part1.strip(), part2.strip()]
    
    # 尝试在空格处分割（适用于中英混合）
    if ' ' in text:
        # 找到所有空格位置
        space_positions = [i for i, char in enumerate(text) if char == ' ']
        mid_pos = len(text) // 2
        
        # 选择最接近中间的空格位置
        for pos in sorted(space_positions, key=lambda x: abs(x - mid_pos)):
            part1 = text[:pos]
            part2 = text[pos + 1:]  # 跳过空格
            
            if len(part1) <= max_chars and len(part2) <= max_chars and len(part1) >= 3:
                return [part1.strip(), part2.strip()]
    
    # 最后手段：智能分割，确保不切断英文单词
    mid = len(text) // 2
    
    # 向前寻找合适的分割点
    for offset in range(min(10, mid // 2)):  # 增加搜索范围
        split_pos = mid - offset
        if split_pos > 5:
            # 检查这个位置是否在英文单词中间
            cut_word = False
            for word in english_words:
                word_start = text.find(word)
                word_end = word_start + len(word) if word_start != -1 else -1
                if word_start < split_pos < word_end:
                    cut_word = True
                    break
            
            if not cut_word:
                part1 = text[:split_pos]
                part2 = text[split_pos:]
                if len(part1) <= max_chars and len(part2) <= max_chars:
                    return [part1.strip(), part2.strip()]
    
    # 实在不行就强制分割，但尽量在非字母字符处分割
    for i in range(max_chars - 5, max_chars + 5):
        if i < len(text) and not text[i].isalpha():
            part1 = text[:i]
            part2 = text[i:]
            if len(part1) >= 5:
                return [part1.strip(), part2.strip()]
    
    # 最终兜底
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
                full_text = ''.join(line.strip() for line in lines)
                
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

def three_stage_translation(text: str, terminology: Dict[str, str] = None) -> str:
    """
    三阶段翻译：初译 -> 反思 -> 适配
    """
    # 构建术语库提示
    terminology_prompt = ""
    if terminology:
        term_list = "\n".join([f"- {en}: {zh}" for en, zh in terminology.items()])
        terminology_prompt = f"\n\nTerminology reference:\n{term_list}\n"
    
    # 一次性完成翻译，包含所有阶段的要求
    system_prompt = (
        "You are a professional subtitle translator. Translate the English subtitle to natural Simplified Chinese. "
        "IMPORTANT: Output ONLY the Chinese translation, no English text, no explanations, no options. "
        "Requirements:\n"
        "1) Output only Chinese characters\n"
        "2) Natural and colloquial translation\n"
        "3) For proper nouns (names, brands, products): either translate them to Chinese OR keep the original English, but NOT both\n"
        "4) If keeping English proper nouns, integrate them naturally into the Chinese sentence\n"
        "5) Avoid mixed language that creates awkward line breaks\n"
        "6) Single coherent translation only\n"
        + terminology_prompt
    )
    
    try:
        # 一次性完成翻译
        translation = chat_with_ollama(system_prompt, f"Translate to Chinese only:\n{text}")
        
        # 清理翻译结果，移除任何英文内容
        cleaned_translation = clean_translation_output(translation.strip())
        logger.debug(f"翻译结果: {cleaned_translation}")
        return cleaned_translation
        
    except Exception as e:
        logger.error(f"翻译失败: {str(e)}")
        # 回退到简单翻译
        return translate_simple(text, terminology)

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

    # Normalize spacing around English words in Chinese text
    # Add proper spacing around English words if they're embedded in Chinese
    current_text = re.sub(r'([\u4e00-\u9fff])([A-Za-z])', r'\1 \2', current_text)  # 中文后跟英文
    current_text = re.sub(r'([A-Za-z])([\u4e00-\u9fff])', r'\1 \2', current_text)  # 英文后跟中文
    
    # But avoid too many spaces around single words
    current_text = re.sub(r'\s+', ' ', current_text).strip()
    
    # Clean up excessive spacing around punctuation
    current_text = re.sub(r'\s+([，。！？；：、])', r'\1', current_text)  # Remove space before Chinese punctuation
    current_text = re.sub(r'([，。！？；：、])\s+', r'\1', current_text)   # Remove space after Chinese punctuation

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
        translation = chat_with_ollama(system_prompt, f"Translate: {text}")
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
            batch_text = "\n".join(
                f"{start_idx + j}{DELIMITER}{s.content.replace(DELIMITER, ' ')}"
                for j, s in enumerate(batch)
            )
            
            logger.info(f"批量翻译进度: {i//batch_size + 1}/{(len(subs) + batch_size - 1)//batch_size}")
            
            system_prompt = (
                "You are a professional bilingual subtitle translator. "
                "Translate each English subtitle line into concise, natural Simplified Chinese. "
                "IMPORTANT: Output ONLY Chinese characters, no English text, no explanations. "
                "Guidelines:\n"
                "1) Output only Chinese characters for the main translation\n"
                "2) For proper nouns (names, brands, products): either translate them completely to Chinese OR keep them in English, but integrate naturally\n"
                "3) Avoid creating mixed Chinese-English text that breaks awkwardly\n"
                "4) Do NOT merge, split, or omit lines\n"
                "5) Output the SAME number of lines in the SAME order\n"
                f"6) Format exactly: <index>{DELIMITER}<Chinese_translation_only>\n"
                "7) No explanations, no options, no mixed language fragments\n"
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
                        mapping[idx] = zh.strip()
                    except ValueError:
                        continue
                
                # 应用翻译结果
                for j, sub in enumerate(batch, start=start_idx):
                    zh = mapping.get(j)
                    if zh:
                        # 清理翻译结果，只保留中文翻译
                        cleaned_zh = clean_translation_output(zh)
                        
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

def translate_srt_to_zh(srt_path: str, use_smart_split: bool = True, use_three_stage: bool = True, extract_terms: bool = True) -> str:
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
            terminology = extract_terminology(srt_path)
        
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