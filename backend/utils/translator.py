# -*- coding: utf-8 -*-
"""
字幕翻译：使用本地 Ollama 模型进行专业字幕翻译
"""
import os, requests, srt, tempfile, logging, json, sys
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

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
        logger.info(f"正在使用模型 {OLLAMA_MODEL} 进行翻译...")
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

# 全局常量：提示词与分隔符
DELIMITER = "|||"
SYSTEM_PROMPT = (
    "You are a professional bilingual subtitle translator. "
    "Translate each English subtitle line into concise, natural Simplified Chinese. "
    "Guidelines:\n"
    "1) Preserve meaning, tone, and named entities.\n"
    "2) Keep each translation ≤20 Chinese characters if possible.\n"
    "3) Do NOT merge, split, or omit lines.\n"
    "4) Output the SAME number of lines in the SAME order.\n"
    f"5) Format exactly: <index>{DELIMITER}<translation> (no extra spaces).\n"
    "6) Return nothing else—no explanations, no original text."
)

def translate_subtitle_batch(subs, batch_size=5):  # 减小批次大小
    """
    将字幕分批翻译，每批处理固定数量的字幕
    """
    translated_subs = []
    
    for i in range(0, len(subs), batch_size):
        batch = subs[i:i + batch_size]
        start_idx = i + 1            # 全局序号起点（保持原顺序）
        batch_text = "\n".join(
            f"{start_idx + j}{DELIMITER}{s.content.replace(DELIMITER, ' ')}"
            for j, s in enumerate(batch)
        )
        
        logger.info(f"开始翻译批次 {i//batch_size + 1}，包含 {len(batch)} 条字幕")
        logger.debug(f"批次内容:\n{batch_text}")
        
        prompt = (
            "以下字幕已按行编号，格式 <编号>{0}<英文内容>。\n"
            "请逐行翻译为简体中文，遵守：\n"
            "• 不增删或合并行；\n"
            "• 译文口语、自然，保留专有名词；\n"
            "• 每行尽量不超过 20 个汉字；\n"
            f"• 仅输出 <编号>{0}<译文>，不要输出英文和其他说明。\n\n"
            "字幕：\n{1}"
        ).format(DELIMITER, batch_text)
        
        try:
            # 使用本地 Ollama 进行对话
            assistant_content = chat_with_ollama(SYSTEM_PROMPT, prompt)
            translated_lines = assistant_content.strip().split('\n')
            
            logger.debug(f"翻译结果:\n{assistant_content}")
            
            # 将 API 输出解析成 {index: translation}
            mapping = {}
            for line in translated_lines:
                if not line.strip():
                    continue
                if DELIMITER not in line:
                    logger.warning(f"跳过格式不正确的行: {line}")
                    continue
                try:
                    idx_str, zh = line.split(DELIMITER, 1)
                    idx = int(idx_str.strip())
                    if idx in mapping:
                        logger.warning(f"重复的序号 {idx}，使用最新的翻译")
                    mapping[idx] = zh.strip()
                    logger.debug(f"成功解析序号 {idx}: {zh.strip()}")
                except ValueError as e:
                    logger.error(f"解析序号失败: {line}, 错误: {str(e)}")

            # 按原序号写回 batch，每行保留"中文↩原文"双行格式
            for j, sub in enumerate(batch, start=start_idx):
                zh = mapping.get(j)
                if zh:
                    sub.content = f"{zh}\n{sub.content}"
                    logger.debug(f"序号 {j} 翻译成功: {zh}")
                else:
                    logger.warning(f'缺少序号 {j} 的翻译，保留原文')
                translated_subs.append(sub)
                
        except Exception as e:
            logger.error(f"翻译批次 {i//batch_size + 1} 失败: {str(e)}", exc_info=True)
            # 如果翻译失败，保持原文
            translated_subs.extend(batch)
    
    return translated_subs

def translate_srt_to_zh(srt_path: str) -> str:
    """
    将 SRT 字幕文件翻译成中文
    
    Args:
        srt_path: SRT 文件路径
        
    Returns:
        str: 翻译后的 SRT 文件路径
    """
    try:
        # 读取字幕文件
        with open(srt_path, "r", encoding="utf-8") as fp:
            subs = list(srt.parse(fp.read()))
            
        logger.info(f"开始翻译字幕，共 {len(subs)} 条")
        
        # 分批翻译字幕
        translated_subs = translate_subtitle_batch(subs)
        
        # 生成翻译后的字幕文件
        zh_srt = srt.compose(translated_subs)
        zh_path = tempfile.mktemp(suffix=".zh.srt")
        
        with open(zh_path, "w", encoding="utf-8") as fp:
            fp.write(zh_srt)
                
        logger.info(f"字幕翻译完成，已保存到: {zh_path}")
        return zh_path 
            
    except Exception as e:
        logger.error(f"字幕翻译失败: {str(e)}")
        raise Exception(f"字幕翻译失败: {str(e)}")