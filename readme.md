# nonebot_steam_judger AI 游戏库锐评Nonebot插件

AI 游戏库锐评 nonebot_steam_judger是一个Nonebot插件，可以获取用户的Steam游戏库数据，并使用AI生成毒舌风格的游戏品味分析。

## 功能介绍

- 从Steam获取用户游戏列表及游玩时长数据
- 使用AI生成犀利吐槽风格的游戏品味分析
- 将分析内容以精美图片形式发送

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

## 注意事项

1. 用户的Steam游戏库必须设为公开才能获取数据
2. 由于使用了队列处理，当请求较多时可能需要排队等待
3. 分析图片会保存在插件目录下的`data`文件夹中

## 特别感谢

- [Steam-Judger](https://github.com/kutius/steam-judger) - 提供灵感的项目
- [Steam Web API](https://developer.valvesoftware.com/wiki/Steam_Web_API)
- [NoneBot2](https://v2.nonebot.dev/)
- [Selenium](https://www.selenium.dev/)

