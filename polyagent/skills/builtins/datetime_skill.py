"""Datetime utils skill — 获取时间、计算日期差、格式化时间戳。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from polyagent.tools.base import Tool, ToolResult

metadata = {
    "name": "datetime_utils",
    "version": "1.0.0",
    "description": "日期时间工具：获取当前时间、计算日期差、格式化时间戳",
    "author": "PolyAgent",
}


class CurrentTimeArgs(BaseModel):
    tz: str = Field("Asia/Shanghai", description="时区，如 Asia/Shanghai, UTC")


class DateDiffArgs(BaseModel):
    start: str = Field(..., description="开始日期，格式 YYYY-MM-DD")
    end: str = Field(..., description="结束日期，格式 YYYY-MM-DD")


class FormatTimestampArgs(BaseModel):
    timestamp: float = Field(..., description="Unix 时间戳（秒）")
    format: str = Field("%Y-%m-%d %H:%M:%S", description="输出格式，如 %Y-%m-%d %H:%M:%S")


class CurrentTime(Tool):
    name = "current_time"
    description = "获取当前的日期和时间（默认北京时间）"
    args_model = CurrentTimeArgs

    async def run(self, args: CurrentTimeArgs) -> ToolResult:
        now = datetime.now(timezone.utc)
        cn = now.strftime("%Y-%m-%d %H:%M:%S")
        return ToolResult(output=f"当前 UTC 时间: {cn}（时区: {args.tz}）")


class DateDiff(Tool):
    name = "date_diff"
    description = "计算两个日期之间的天数差"
    args_model = DateDiffArgs

    async def run(self, args: DateDiffArgs) -> ToolResult:
        from datetime import date

        try:
            d1 = date.fromisoformat(args.start)
            d2 = date.fromisoformat(args.end)
        except ValueError as exc:
            return ToolResult(output=f"日期格式错误: {exc}", error=True)
        delta = abs((d2 - d1).days)
        return ToolResult(output=f"{args.start} 到 {args.end} 相差 {delta} 天")


class FormatTimestamp(Tool):
    name = "format_timestamp"
    description = "将 Unix 时间戳格式化为可读日期时间字符串"
    args_model = FormatTimestampArgs

    async def run(self, args: FormatTimestampArgs) -> ToolResult:
        try:
            dt = datetime.fromtimestamp(args.timestamp, tz=timezone.utc)
        except (ValueError, OSError) as exc:
            return ToolResult(output=f"时间戳无效: {exc}", error=True)
        return ToolResult(output=dt.strftime(args.format))


def get_tools():
    return [CurrentTime(), DateDiff(), FormatTimestamp()]
