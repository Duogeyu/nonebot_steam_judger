from nonebot import get_driver
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Steam Talk Plugin Config"""
    steam_api_key: str = Field(default="", description="Steam Web API密钥")
    ai_api_key: str = Field(default="", description="AI接口的API密钥")
    ai_api_base: str = Field(default="", description="AI接口的完整URL")
    ai_model: str = Field(default="deepseek-v3-0324", description="使用的AI模型")

global_config = get_driver().config
plugin_config = Config.model_validate({
    "steam_api_key": getattr(global_config, "steam_api_key", Config().steam_api_key),
    "ai_api_key": getattr(global_config, "ai_api_key", Config().ai_api_key),
    "ai_api_base": getattr(global_config, "ai_api_base", Config().ai_api_base),
    "ai_model": getattr(global_config, "ai_model", Config().ai_model),
})
