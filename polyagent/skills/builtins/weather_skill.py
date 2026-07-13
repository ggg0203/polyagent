"""Weather skill — 查询城市天气（模拟演示）。"""

from __future__ import annotations

import random

from pydantic import BaseModel

from polyagent.tools.base import Tool, ToolResult

metadata = {
    "name": "weather",
    "version": "1.0.0",
    "description": "查询任意城市的实时天气",
    "author": "PolyAgent",
}

CITIES = {
    "北京": ("晴", 28),
    "上海": ("多云", 26),
    "深圳": ("小雨", 30),
    "广州": ("阵雨", 29),
    "杭州": ("阴", 24),
    "成都": ("晴", 27),
    "武汉": ("多云转晴", 25),
    "南京": ("晴", 23),
    "东京": ("晴", 22),
    "纽约": ("多云", 18),
    "伦敦": ("小雨", 14),
    "巴黎": ("晴", 20),
}


class WeatherArgs(BaseModel):
    city: str = "北京"


class GetWeather(Tool):
    name = "get_weather"
    description = "查询指定城市的当前天气状况"
    args_model = WeatherArgs

    async def run(self, args: WeatherArgs) -> ToolResult:
        if args.city in CITIES:
            condition, temp = CITIES[args.city]
        else:
            # Unknown city — simulate
            condition = random.choice(["晴", "多云", "阴", "小雨", "阵雨"])
            temp = random.randint(10, 35)
        return ToolResult(output=f"{args.city}：{condition}，{temp}°C")


def get_tools() -> list[GetWeather]:
    return [GetWeather()]
