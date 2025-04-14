from nonebot.plugin import PluginMetadata
import aiohttp
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
import subprocess
import asyncio
import time
import sys
import re
from datetime import datetime, timedelta
import traceback

from nonebot import on_command, get_bot, require
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageSegment
from nonebot.log import logger

# 导入Selenium相关库
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from PIL import Image
import io

from .config import plugin_config

# 确保 nonebot_plugin_apscheduler 已加载
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="steam_talk",
    description="获取Steam游戏列表并使用AI生成毒舌分析",
    usage="/steam分析 [Steam ID或个人主页链接]",
    config=None,
)

# 设置Chrome驱动路径
DRIVER_PATH = r"D:\tools\chromedriver.exe"  # 请修改为你的chromedriver路径

# 获取插件目录路径
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(PLUGIN_DIR, "template.html")
DATA_DIR = os.path.join(PLUGIN_DIR, "data")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 创建命令处理器
steam_analyze = on_command("steam分析", aliases={"steam锐评", "steam毒舌"}, priority=5, block=True)
test_ai = on_command("测试AI", aliases={"testai", "ai测试"}, priority=5, block=True)

# 任务队列与状态跟踪
MAX_QUEUE_SIZE = 10
analysis_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
processing_task = None
processing_or_queued_ids: Set[str] = set() # 用于跟踪正在处理或排队的Steam ID
ADMIN_ID = 1814741500

# 向管理员发送错误消息
async def send_error_to_admin(bot: Bot, error_msg: str, traceback_info: str = None):
    """将错误信息私信发送给管理员"""
    admin_id = ADMIN_ID  # 管理员QQ号
    full_error = f"Steam分析插件出错:\n{error_msg}"
    if traceback_info:
        full_error += f"\n\n详细错误信息:\n{traceback_info}"
    
    try:
        await bot.send_private_msg(user_id=admin_id, message=full_error)
        logger.info(f"已将错误信息发送给管理员")
    except Exception as e:
        logger.error(f"向管理员发送错误信息失败: {str(e)}")

# 获取Steam游戏列表
async def get_steam_games(steam_id: str) -> Dict[str, Any]:
    """获取指定Steam ID的游戏列表"""
    url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        "key": plugin_config.steam_api_key,
        "steamid": steam_id,
        "include_appinfo": "true",
        "format": "json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Steam API请求失败: {response.status}")

# 获取用户信息
async def get_user_info(steam_id: str) -> Dict[str, Any]:
    """获取指定Steam ID的用户信息"""
    url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": plugin_config.steam_api_key,
        "steamids": steam_id
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                players = data.get("response", {}).get("players", [])
                if players:
                    return players[0]
                else:
                    raise Exception("未找到该Steam用户信息")
            else:
                raise Exception(f"Steam API请求失败: {response.status}")

# 解析Steam自定义URL
async def resolve_vanity_url(vanity_url: str) -> str:
    """解析Steam自定义URL为SteamID"""
    url = f"http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
    params = {
        "key": plugin_config.steam_api_key,
        "vanityurl": vanity_url
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                result = data.get("response", {})
                if result.get("success") == 1:
                    steam_id = result.get("steamid")
                    if steam_id:
                        return steam_id
                    else:
                        raise Exception("无法获取SteamID，API返回结果异常")
                else:
                    error_code = result.get("message", "未知错误")
                    raise Exception(f"自定义URL解析失败: {error_code}")
            else:
                raise Exception(f"Steam API请求失败: {response.status}")

def build_api_url() -> str:
    """构建完整的API URL"""
    api_url = plugin_config.ai_api_base
    
    # 检查URL是否已经包含了chat/completions路径
    if "chat/completions" not in api_url:
        # 如果不包含且不以/结尾，添加/
        if not api_url.endswith("/"):
            api_url += "/"
        # 添加chat/completions路径
        api_url += "chat/completions"
    
    return api_url

# 生成游戏分析
async def generate_game_analysis(games_data: Dict[str, Any], user_info: Optional[Dict[str, Any]] = None) -> Tuple[str, int, int, int]:
    """根据游戏列表数据生成毒舌分析，并返回分析文本、prompt_tokens, completion_tokens, total_tokens"""
    # 提取游戏信息
    games = games_data.get("response", {}).get("games", [])
    if not games:
        return "未找到任何游戏数据", 0, 0, 0
    
    # 按游戏时长排序
    games.sort(key=lambda x: x.get("playtime_forever", 0), reverse=True)
    
    # 准备游戏列表文本
    games_text = "\n".join([f"- {game.get('name', '未知游戏')}: {game.get('playtime_forever', 0)//60}小时" 
                           for game in games[:15]])  # 取前15个游戏
    
    # 获取用户名称
    username = "该用户"
    if user_info:
        username = user_info.get("personaname", "该用户")
    
    # 获取当前日期
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 构建AI提示
    prompt = f"""基于用户"{username}"的Steam游戏库数据（包含游戏名称、时长），请生成一篇毒舌幽默向的锐评报告。要求：

风格：犀利吐槽为主，结合互联网流行梗、夸张比喻，语言风格参考'老湿吐槽'或'阴阳师文学'，避免脏话但保持'阴阳怪气'；

结构：分点总结用户'迷惑行为'（如喜加一、二次元浓度、硬核打脸等），每点需结合具体游戏数据；

游戏品味：对用户进行进行总体评价，分析用户的游戏风格/品味；

游戏推荐：结合用户的游戏库，推荐一些可能会让他"上头"的游戏，或者可能会让他"上头"的游戏类型。

彩蛋：发现矛盾点/与众不同的点并玩梗，结尾用反鸡汤式总结；

格式：支持Markdown格式，可以使用**加粗**、*斜体*、## 二级标题、- 列表等Markdown语法增强表现力和可读性；

今天是{current_date}，请以今天的日期为基准。
接下来会提供一个游戏列表，每行格式为 "- {{游戏名称}}: {{游玩时长}}"

游戏列表：
{games_text}

总游戏数量：{len(games)}

请用中文生成分析，字数在300字左右，尽量使用Markdown语法来突出重点和结构。"""

    # 调用AI接口
    headers = {
        "Authorization": f"Bearer {plugin_config.ai_api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": plugin_config.ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1000,
        # "stream": True # 可选：如果需要流式输出，可以开启，但需要修改处理逻辑
    }
    
    # 获取API URL
    api_url = build_api_url()
    logger.debug(f"请求AI API URL: {api_url}")
    
    analysis_text = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    try:
        timeout = aiohttp.ClientTimeout(total=120)  # 设置更长的超时时间，例如120秒
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    analysis_text = result["choices"][0]["message"]["content"]
                    usage_data = result.get("usage")
                    if usage_data:
                        prompt_tokens = usage_data.get("prompt_tokens", 0)
                        completion_tokens = usage_data.get("completion_tokens", 0)
                        total_tokens = usage_data.get("total_tokens", 0)
                    logger.info(f"AI调用成功，Tokens: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
                else:
                    error_text = await response.text()
                    raise Exception(f"AI API请求失败: {response.status}, {error_text}")
    except asyncio.TimeoutError:
        logger.error("AI API请求超时")
        raise Exception("AI API请求超时，请稍后重试")
    except Exception as e:
        logger.error(f"调用AI API时出错: {str(e)}")
        raise

    return analysis_text, prompt_tokens, completion_tokens, total_tokens

# 生成HTML模板
def generate_html_template(steam_id: str, analysis: str, user_info: Optional[Dict[str, Any]] = None, group_id: str = "", token_info: Dict[str, int] = None, ai_model: str = "") -> str:
    """生成分析报告的HTML页面，包含Token和模型信息"""
    # 准备模板变量
    username = steam_id
    avatar_url = ""
    profile_url = f"https://steamcommunity.com/profiles/{steam_id}"
    avatar_html = ""
    current_date = time.strftime("%Y年%m月%d日")
    
    if user_info:
        username = user_info.get("personaname", steam_id)
        avatar_url = user_info.get("avatarfull", "")
        if avatar_url:
            avatar_html = f'<img class="avatar" src="{avatar_url}" alt="{username}">'
    
    # 准备群号信息
    group_info = f"来自群：{group_id}" if group_id else ""
    
    # 准备Token和模型信息
    token_html = ""
    if token_info:
        prompt_tokens = token_info.get("prompt", 0)
        completion_tokens = token_info.get("completion", 0)
        total_tokens = token_info.get("total", 0)
        token_html = f"Model: {ai_model} | Tokens: {total_tokens} (P: {prompt_tokens}, C: {completion_tokens})"

    # 读取HTML模板
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            template = f.read()
        logger.debug("成功加载HTML模板")
    except Exception as e:
        logger.error(f"加载HTML模板失败: {str(e)}")
        # 使用默认模板
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Steam游戏锐评 - {{username}}</title>
            <style>
                body {font-family: 'Microsoft YaHei', sans-serif; background-color: #1b2838; color: #c7d5e0;}
                .container {background-color: #2a475e; padding: 20px; border-radius: 10px;}
                h1 {color: #66c0f4; text-align: center;}
                .analysis {line-height: 1.8;}
                .footer {margin-top: 20px; text-align: center; font-size: 12px; color: #8f98a0;}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Steam游戏锐评</h1>
                <div class="user-info">
                    {{avatar_html}}
                    <div>
                        <div class="username">{{username}}</div>
                        <div class="profile-link"><a href="{{profile_url}}">Steam个人资料</a></div>
                    </div>
                </div>
                <div class="analysis">{{analysis}}</div>
                <div class="footer">由AI生成的游戏品味分析 · 仅供娱乐 · {{date}} {{group_info}}<br>{{token_info}}</div>
            </div>
        </body>
        </html>
        """
        logger.warning("使用默认HTML模板")
    
    # 替换模板变量
    html_content = template.replace("{{username}}", username)
    html_content = html_content.replace("{{profile_url}}", profile_url)
    html_content = html_content.replace("{{avatar_html}}", avatar_html)
    html_content = html_content.replace("{{analysis}}", analysis)
    html_content = html_content.replace("{{date}}", current_date)
    html_content = html_content.replace("{{group_info}}", group_info)
    html_content = html_content.replace("{{token_info}}", token_html)
    
    return html_content

# 添加HTML转图片功能
async def html_to_image(html_path: str, qq_id: str) -> str:
    """使用Selenium将HTML转换为图片"""
    try:
        # 使用特定目录保存图片
        output_dir = Path(os.path.join(DATA_DIR, qq_id))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        img_path = str(output_dir / f"analysis_{timestamp}.png")
        
        logger.debug(f"开始将HTML转换为图片: {html_path} -> {img_path}")
        
        options = Options()
        options.add_argument('--headless')  # 无头模式
        options.add_argument('--disable-gpu')
        options.add_argument('--force-device-scale-factor=2')  # 提高清晰度
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--hide-scrollbars')  # 隐藏滚动条
        options.add_argument('--window-size=850,1500')  # 设置更大的初始窗口高度以确保能完整显示内容
        
        logger.info(f"启动Selenium，ChromeDriver路径: {DRIVER_PATH}")
        try:
            driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
            driver.set_page_load_timeout(30)  # 设置页面加载超时时间
            driver.get("file://" + os.path.abspath(html_path))
            
            # 等待页面加载和Markdown渲染完成
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.container'))
            )
            # 额外等待Markdown渲染和可能的动态内容加载
            await asyncio.sleep(2)
            logger.debug("页面加载完成")
            
            # 确保页面上的脚本执行完毕
            driver.execute_script("return document.readyState") == "complete"
            
            # 获取容器元素的实际尺寸
            container = driver.find_element(By.CSS_SELECTOR, '.container')
            container_rect = driver.execute_script('''
                var rect = arguments[0].getBoundingClientRect();
                return {
                    height: rect.height,
                    width: rect.width,
                    top: rect.top,
                    left: rect.left
                };
            ''', container)
            
            # 设置窗口大小以适应容器的实际尺寸加上边距
            padding = 40
            width = int(container_rect['width']) + padding * 2
            height = int(container_rect['height']) + padding * 2
            
            # 确保整个容器（包括页脚）都在视图内
            driver.set_window_size(width, height)
            logger.debug(f"设置窗口大小为: {width}x{height}")
            
            # 等待页面调整后重新渲染
            await asyncio.sleep(1)
            
            # 使用JS确保页面不滚动
            driver.execute_script("window.scrollTo(0, 0);")
            
            # 确认footer完全在视图内（再次确认，因为窗口大小可能改变了元素位置）
            is_footer_visible = driver.execute_script('''
                var containerRect = arguments[0].getBoundingClientRect();
                var footerRect = arguments[1].getBoundingClientRect();
                var viewHeight = window.innerHeight;
                // 检查容器底部是否在视口内
                return containerRect.bottom <= viewHeight;
            ''', container, driver.find_element(By.CSS_SELECTOR, '.footer'))
            
            if not is_footer_visible:
                # 如果容器底部不完全可见，可能内容过长，需要调整窗口高度
                new_height = int(container_rect['height']) + padding * 2 + 50 # 增加一些额外空间
                driver.set_window_size(width, new_height)
                logger.debug(f"调整窗口大小以显示完整容器: {width}x{new_height}")
                await asyncio.sleep(1)
            
            # 直接对页面内的容器元素截图，确保包含页脚
            container = driver.find_element(By.CSS_SELECTOR, '.container')
            screenshot = container.screenshot_as_png
            
            # 保存截图
            with open(img_path, "wb") as f:
                f.write(screenshot)
            logger.info(f"图片生成成功: {img_path}")
            
            # 同时保存分析数据以便追溯
            html_copy_path = str(output_dir / f"analysis_{timestamp}.html")
            with open(html_copy_path, "w", encoding="utf-8") as f:
                with open(html_path, "r", encoding="utf-8") as source:
                    f.write(source.read())
            logger.debug(f"已保存HTML副本: {html_copy_path}")
            
            # 保存游戏分析内容
            text_copy_path = str(output_dir / f"analysis_{timestamp}.txt")
            with open(text_copy_path, "w", encoding="utf-8") as f:
                # 从HTML中提取分析文本
                with open(html_path, "r", encoding="utf-8") as source:
                    html_content = source.read()
                    analysis_match = re.search(r'<div class="analysis" id="analysis-content">\s*(.*?)\s*</div>', html_content, re.DOTALL)
                    if analysis_match:
                        analysis_text = analysis_match.group(1).strip()
                        f.write(analysis_text)
                    else:
                        f.write("无法从HTML中提取分析文本")
            logger.debug(f"已保存纯文本分析: {text_copy_path}")
            
            return img_path
        except Exception as e:
            logger.error(f"截图失败: {str(e)}")
            return ""
        finally:
            try:
                driver.quit()
                logger.debug("Selenium驱动已关闭")
            except:
                pass
    except Exception as e:
        logger.error(f"创建图片文件失败: {str(e)}")
        return ""

# 启动时检查工具是否安装
def check_tools():
    """检查必要的工具是否已安装"""
    # 检查HTML模板是否存在
    if not os.path.exists(TEMPLATE_PATH):
        logger.warning(f"未找到HTML模板: {TEMPLATE_PATH}")
        logger.info("将使用默认模板")
    
    # 检查chromedriver是否存在
    if not os.path.exists(DRIVER_PATH):
        logger.warning(f"未找到ChromeDriver: {DRIVER_PATH}")
        logger.info("请下载适合你Chrome版本的ChromeDriver: https://chromedriver.chromium.org/downloads")
        return False
    
    # 尝试初始化Chrome，验证驱动是否正常工作
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
        driver.quit()
        logger.info("ChromeDriver检查通过")
        return True
    except Exception as e:
        logger.error(f"ChromeDriver测试失败: {str(e)}")
        logger.info("请确保已安装Chrome浏览器且ChromeDriver版本与Chrome版本匹配")
        return False

# 后台处理任务
async def process_analysis_queue():
    global processing_task, processing_or_queued_ids
    logger.info("启动Steam分析后台处理任务...")
    while True:
        bot: Bot = None
        event: Event = None
        steam_id: str = None
        task_steam_id: str = None # 记录当前处理的任务ID
        try:
            # 从队列中获取任务
            bot, event, task_steam_id = await analysis_queue.get()
            qq_id = event.get_user_id()
            group_id = getattr(event, "group_id", "") or ""
            
            # logger.info(f"开始处理Steam ID {task_steam_id} 的分析任务") # 不再发送此消息
            
            # 输出配置信息，便于调试（隐藏API密钥的部分信息）
            api_key_safe = plugin_config.ai_api_key[:6] + "*****" if plugin_config.ai_api_key else "未设置"
            logger.debug(f"当前配置 - API基础URL: {plugin_config.ai_api_base}, 模型: {plugin_config.ai_model}, API密钥: {api_key_safe}")

            user_info = None
            try:
                # 获取用户信息
                logger.debug(f"正在获取用户信息，SteamID: {task_steam_id}")
                user_info = await get_user_info(task_steam_id)
                logger.info(f"获取到用户信息: {user_info.get('personaname', '未知')}")
            except Exception as e:
                error_msg = f"获取用户信息失败: {str(e)}"
                logger.warning(error_msg)
                await send_error_to_admin(bot, error_msg)
                # 继续执行，不因为用户信息获取失败而中断流程
                
            # 获取游戏数据
            logger.debug(f"正在获取游戏列表，SteamID: {task_steam_id}")
            games_data = await get_steam_games(task_steam_id)
            games_count = len(games_data.get("response", {}).get("games", []))
            logger.info(f"获取到游戏数量: {games_count}")
            
            # 生成分析
            logger.debug(f"正在生成游戏分析，SteamID: {task_steam_id}")
            analysis, p_tokens, c_tokens, t_tokens = await generate_game_analysis(games_data, user_info)
            logger.info(f"生成分析完成，长度: {len(analysis)}")
            token_info = {"prompt": p_tokens, "completion": c_tokens, "total": t_tokens}
            
            # 生成HTML
            logger.debug(f"正在生成HTML报告，SteamID: {task_steam_id}")
            html_content = generate_html_template(task_steam_id, analysis, user_info, str(group_id), token_info, plugin_config.ai_model)
            
            # 保存原始HTML文件
            output_dir = Path(os.path.join(DATA_DIR, "_temp"))
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"temp_{task_steam_id}.html"
            
            # 写入HTML文件
            logger.debug(f"正在保存临时HTML文件: {output_file}")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            # 保存原始游戏数据
            games_data_path = Path(os.path.join(DATA_DIR, qq_id))
            games_data_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            games_data_file = games_data_path / f"games_data_{timestamp}.json"
            
            with open(games_data_file, "w", encoding="utf-8") as f:
                json.dump(games_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"已保存游戏数据: {games_data_file}")
            
            # 尝试将HTML转换为图片
            img_path = await html_to_image(str(output_file.absolute()), qq_id)
            
            if img_path and os.path.exists(img_path):
                # 使用生成的图片，采用绝对路径和参考newbooth插件的方式
                logger.debug(f"使用生成的图片: {img_path}")
                await bot.send(event=event, message=MessageSegment.reply(event.message_id) + MessageSegment.image(file=f'file:///{os.path.abspath(img_path)}'))
            else:
                # 截图失败，这里不提供纯文本备选方案，而是提示安装所需工具
                error_msg = "HTML转图片失败，缺少必要的工具"
                logger.error(error_msg)
                trace_info = traceback.format_exc()
                await send_error_to_admin(bot, error_msg, trace_info)
                await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "分析失败：图片生成错误，请联系管理员。")
            
            logger.info(f"Steam分析完成并发送，SteamID: {task_steam_id}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"处理Steam分析任务时发生错误: {error_msg}")
            
            # 提供更友好的错误信息，但不透露详细错误
            user_friendly_msg = "分析失败，请稍后再试或联系管理员。"
            
            if "Steam API请求失败" in error_msg:
                user_friendly_msg = "分析失败：无法获取Steam游戏数据，可能是ID错误或该用户的游戏库不公开。请检查ID是否正确，或者确认用户已将游戏库设为公开。"
            elif "未找到任何游戏数据" in error_msg:
                user_friendly_msg = "分析失败：未找到游戏数据，该用户可能没有游戏或游戏库不公开。"
            elif "AI API请求失败" in error_msg or "Invalid variable" in error_msg or "No such file or directory" in error_msg or "AI API请求超时" in error_msg:
                user_friendly_msg = "分析失败：生成分析时出错，请稍后再试或联系管理员。"
            
            if bot and event: # 确保bot和event对象存在
                await bot.send(event=event, message=MessageSegment.reply(event.message_id) + user_friendly_msg)
            
            # 对于调试目的，发送详细错误信息给管理员
            trace_info = traceback.format_exc()
            if bot: # 确保bot对象存在
                await send_error_to_admin(bot, error_msg, trace_info)
        
        finally:
            if task_steam_id in processing_or_queued_ids:
                processing_or_queued_ids.remove(task_steam_id)
                logger.debug(f"已将 Steam ID {task_steam_id} 从跟踪集合中移除")
            analysis_queue.task_done() # 标记任务完成

# 启动后台任务
@scheduler.scheduled_job("interval", seconds=1, misfire_grace_time=60)
async def _start_processing_task():
    global processing_task
    if processing_task is None or processing_task.done():
        processing_task = asyncio.create_task(process_analysis_queue())

@steam_analyze.handle()
async def handle_steam_analyze(bot: Bot, event: Event):
    # 获取QQ号和群号
    qq_id = event.get_user_id()
    group_id = getattr(event, "group_id", "") or ""
    
    args = event.get_plaintext().split()
    if len(args) < 2:
        await bot.send(event=event, message="请提供Steam ID或个人主页链接。例如：\n/steam分析 7656119xxxxxxxxx\n/steam分析 https://steamcommunity.com/id/用户名")
        return
    
    # 获取用户输入
    user_input = args[1]
    steam_id = None
    
    # 处理不同格式的输入
    parsing_error_msg = None
    try:
        if user_input.startswith("https://steamcommunity.com/"):
            # 如果是Steam个人主页链接
            logger.info(f"检测到Steam个人主页链接: {user_input}")
            # await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "正在解析Steam个人主页链接...") # 移除中间消息
            if "/profiles/" in user_input:
                profile_id = user_input.split("/profiles/")[1].split("/")[0].strip()
                steam_id = profile_id
                logger.debug(f"从个人主页链接提取到SteamID: {steam_id}")
            elif "/id/" in user_input:
                custom_url = user_input.split("/id/")[1].split("/")[0].strip()
                logger.debug(f"从个人主页链接提取到自定义URL: {custom_url}")
                try:
                    steam_id = await resolve_vanity_url(custom_url)
                    logger.debug(f"已将自定义URL解析为SteamID: {steam_id}")
                except Exception as e:
                    error_msg = f"解析自定义URL失败: {str(e)}"
                    logger.error(error_msg)
                    await send_error_to_admin(bot, error_msg)
                    parsing_error_msg = "无法解析Steam个人主页URL，请直接使用Steam ID。"
            else:
                error_msg = f"无法从链接中提取SteamID: {user_input}"
                logger.error(error_msg)
                await send_error_to_admin(bot, error_msg)
                parsing_error_msg = "无法从提供的链接中提取Steam ID，请使用其他格式。"
        else:
            # 否则认为是Steam ID
            steam_id = user_input
            # 检查是否是有效的Steam64位ID（通常以7656119开头）
            if not steam_id.startswith("7656119") or not steam_id.isdigit() or len(steam_id) != 17:
                logger.warning(f"输入的Steam ID格式可能不正确: {steam_id}")
                await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "您输入的Steam ID格式可能不正确（应是17位数字且以7656119开头），但仍会尝试查询...")
                # 继续尝试，但已经警告用户
    except Exception as e:
        error_msg = f"处理输入时出错: {str(e)}"
        logger.error(error_msg)
        trace_info = traceback.format_exc()
        await send_error_to_admin(bot, error_msg, trace_info)
        parsing_error_msg = "处理您的输入时遇到错误，请检查格式或联系管理员。"

    if parsing_error_msg:
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + parsing_error_msg)
        return
    
    if not steam_id:
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "未能成功识别Steam ID或链接，请检查输入格式。")
        return

    # 检查是否已在队列中或正在处理
    if steam_id in processing_or_queued_ids:
        # (可选) 尝试获取精确位置比较复杂，简单提示已在队列中
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + f"该Steam ID ({steam_id}) 的分析请求已在队列中或正在处理，请耐心等待。")
        return

    # 检查队列是否已满
    if analysis_queue.full():
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + f"当前队列已满({MAX_QUEUE_SIZE}/{MAX_QUEUE_SIZE})，请稍后再试。")
        return

    # 将任务添加到队列和跟踪集合
    try:
        processing_or_queued_ids.add(steam_id) # 先添加到集合
        await analysis_queue.put((bot, event, steam_id))
        queue_pos = analysis_queue.qsize()
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + f"您的Steam分析请求已加入队列(当前共 {queue_pos} 个任务)，请耐心等待~")
        logger.info(f"用户 {qq_id} 的Steam分析请求 (ID: {steam_id}) 已加入队列，位置: {queue_pos}")
    except asyncio.QueueFull:
        processing_or_queued_ids.remove(steam_id) # 如果添加队列失败，从集合中移除
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + f"当前队列已满({MAX_QUEUE_SIZE}/{MAX_QUEUE_SIZE})，请稍后再试。")
    except Exception as e:
        if steam_id in processing_or_queued_ids: # 添加失败时移除
            processing_or_queued_ids.remove(steam_id)
        error_msg = f"添加任务到队列时出错: {str(e)}"
        logger.error(error_msg)
        trace_info = traceback.format_exc()
        await send_error_to_admin(bot, error_msg, trace_info)
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "添加任务到队列时出错，请联系管理员。")


@test_ai.handle()
async def handle_test_ai(bot: Bot, event: Event):
    """处理AI测试命令"""
    # 获取QQ号
    qq_id = event.get_user_id()
    
    # 检查是否为管理员
    if qq_id != str(ADMIN_ID):
        await bot.send(event=event, message="抱歉，只有管理员才能使用此命令。")
        return
    
    # 始终先回复一条消息确认收到命令
    await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "收到AI测试命令，正在处理...")
    
    try:
        result = await test_ai_api()
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + result)
    except Exception as e:
        error_msg = f"AI测试失败: {str(e)}"
        trace_info = traceback.format_exc()
        logger.error(f"{error_msg}\n{trace_info}")
        await send_error_to_admin(bot, error_msg, trace_info)
        await bot.send(event=event, message=MessageSegment.reply(event.message_id) + "AI测试出错，请联系管理员。")

# 简单的AI测试函数
async def test_ai_api() -> str:
    """测试AI API的连接和响应"""
    headers = {
        "Authorization": f"Bearer {plugin_config.ai_api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": plugin_config.ai_model,
        "messages": [{"role": "user", "content": "你好，请回复一句简短的话来测试连接"}],
        "temperature": 0.7,
        "max_tokens": 50
    }
    
    # 获取API URL
    api_url = build_api_url()
    logger.debug(f"测试AI API，请求URL: {api_url}")
    
    try:
        timeout = aiohttp.ClientTimeout(total=30) # 测试接口超时设置短一些
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(api_url, headers=headers, json=data) as response:
                status = response.status
                response_text = await response.text()
                logger.debug(f"AI API响应状态: {status}, 响应内容: {response_text}")
                
                if status == 200:
                    try:
                        result = json.loads(response_text)
                        return f"API测试成功! 响应: {result['choices'][0]['message']['content']}"
                    except (json.JSONDecodeError, KeyError) as e:
                        return f"API响应格式错误: {str(e)}\n响应内容: {response_text[:100]}..."
                else:
                    return f"API请求失败，状态码: {status}\n响应内容: {response_text}"
    except asyncio.TimeoutError:
        logger.error("AI API测试请求超时")
        raise Exception("AI API测试请求超时")
    except Exception as e:
        logger.error(f"调用AI API测试时出错: {str(e)}")
        raise

# 插件加载时执行检查
check_tools()

# 启动时确保后台任务已运行
# asyncio.create_task(process_analysis_queue()) # 改用scheduler启动

logger.info("Steam Talk插件加载完成")

