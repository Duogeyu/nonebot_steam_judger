# nonebot_steam_judger 插件

nonebot_steam_judger是一个OneBot插件，可以获取用户的Steam游戏库数据，并使用AI生成毒舌风格的游戏品味分析。通过解析用户的游戏时长和偏好，生成一份犀利幽默的评价报告，以图片形式呈现。

## 效果展示

![Steam游戏锐评示例](https://github.com/Duogeyu/nonebot_steam_judger/blob/cbfea2d8828a511986832db606f2a1db917182a9/data/1814741500/analysis_20250414_200422.png)

## 功能介绍

- **Steam游戏数据获取**：从Steam API获取用户的游戏列表及详细游玩时长数据
- **AI分析生成**：使用大语言模型生成犀利吐槽风格的游戏品味分析
- **美观报告展示**：将分析内容转换为精美图片形式发送
- **队列处理机制**：使用异步队列处理请求，避免高并发时的问题
- **缓存结果保存**：保存分析结果，支持追溯历史分析
- **多种输入格式**：支持Steam ID、自定义URL和个人主页链接多种输入方式

## 技术实现

- 使用Selenium将HTML渲染为图片，支持Markdown格式的分析内容
- 异步处理Steam API请求，提高响应速度
- 使用任务队列避免并发请求对API的压力
- 集成OpenAI兼容接口，支持多种AI模型
- 错误处理和管理员通知机制，确保插件稳定运行

## 安装方法

1. 确保已安装[NoneBot2](https://v2.nonebot.dev/)和[OneBot适配器](https://github.com/nonebot/adapter-onebot)
2. 将插件目录复制到你的NoneBot2项目的`plugins`目录下
3. 在`.env`文件中添加这个插件名称：

```
PLUGINS=["nonebot_steam_judger"]
```

## 必要依赖

- Python 3.8+
- Chrome浏览器
- ChromeDriver (与Chrome版本对应)
- nonebot_plugin_apscheduler
- selenium
- aiohttp
- Pillow

## 安装依赖

```bash
pip install nonebot-plugin-apscheduler selenium aiohttp pillow
```

## 配置说明

在`.env`文件中添加以下配置：

```
# Steam API密钥
STEAM_API_KEY=你的Steam_API密钥

# AI相关配置
AI_API_BASE=你的AI接口地址
AI_API_KEY=你的AI接口密钥
AI_MODEL=AI模型名称
```

## ChromeDriver配置

在插件的`__init__.py`文件中修改ChromeDriver路径：

```python
DRIVER_PATH = r"D:\tools\chromedriver.exe"  # 请修改为你的chromedriver路径
```

确保ChromeDriver版本与你的Chrome浏览器版本匹配。

## 使用方法

### 普通用户

- `/steam分析 [Steam ID或个人主页链接]` - 获取Steam游戏分析
- 支持的输入格式:
  - Steam ID: `7656119xxxxxxxxx`
  - Steam个人主页: `https://steamcommunity.com/id/用户名`
  - Steam个人主页: `https://steamcommunity.com/profiles/7656119xxxxxxxxx`

### 管理员命令

- `/测试AI` - 测试AI接口连接状态

## 分析内容特点

AI生成的分析报告通常包含以下内容：

- **游戏品味总结**：基于用户游戏库特点的概括性评价
- **游玩时间分析**：重点关注游玩时间最长的游戏
- **游戏类型偏好**：分析用户偏好的游戏类型和风格
- **有趣的发现**：发掘用户游戏库中独特或有趣的特点
- **游戏推荐**：根据用户现有游戏偏好推荐可能感兴趣的游戏

分析以犀利幽默的风格呈现，使用Markdown格式增强可读性，最终转换为精美图片。

## 私有化部署

如需私有化部署，建议：

1. 使用国内可访问的AI接口，如DeepSeek等
2. 确保服务器环境支持Chrome和ChromeDriver的运行
3. 对于图片渲染，可根据需要调整HTML模板中的样式

## 注意事项

1. 用户的Steam游戏库必须设为公开才能获取数据
2. 由于使用了队列处理，当请求较多时可能需要排队等待
3. 分析图片会保存在插件目录下的`data`文件夹中
4. 请确保AI模型有足够的token容量处理较长的游戏列表
5. ChromeDriver版本必须与Chrome浏览器版本匹配，否则会导致图片生成失败

## 自定义与扩展

### 自定义HTML模板

可以编辑`template.html`文件来修改分析报告的外观和样式：

- 修改配色方案
- 调整布局和字体
- 添加自定义元素或品牌标识

### 自定义AI提示词

可以编辑`__init__.py`中的`generate_game_analysis`函数，修改AI提示词来改变分析风格：

- 更改分析的风格和语气
- 添加新的分析维度
- 调整分析内容的长度和结构

## 特别感谢

- [Steam-Judger](https://github.com/kutius/steam-judger) - 提供灵感的项目
- [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- [NoneBot2](https://v2.nonebot.dev/)
- [Selenium](https://www.selenium.dev/)

