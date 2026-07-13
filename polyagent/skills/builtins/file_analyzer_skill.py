"""File analyzer skill — 分析文件统计信息。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from polyagent.tools.base import Tool, ToolResult

metadata = {
    "name": "file_analyzer",
    "version": "1.0.0",
    "description": "分析文件：统计行数/字数/大小，检测编码格式",
    "author": "PolyAgent",
}


class AnalyzeFileArgs(BaseModel):
    path: str = Field(..., description="要分析的文件的路径")
    max_bytes: int = 1048576  # 1MB


class AnalyzeFile(Tool):
    name = "analyze_file"
    description = "分析文件的统计信息：大小、行数、字数、编码格式等"
    args_model = AnalyzeFileArgs

    async def run(self, args: AnalyzeFileArgs) -> ToolResult:
        p = Path(args.path)
        if not p.is_file():
            return ToolResult(output=f"文件不存在: {p}", error=True)

        try:
            raw = p.read_bytes()
        except OSError as exc:
            return ToolResult(output=f"读取失败: {exc}", error=True)

        size = len(raw)
        size_str = _fmt_size(size)

        # Try to detect encoding
        detected_enc = _detect_encoding(raw[:4096])
        try:
            text = raw.decode(detected_enc or "utf-8", errors="replace")
            lines = text.splitlines()
            line_count = len(lines)
            char_count = len(text)
            word_count = len(text.split())
            # Count non-empty lines
            non_empty = sum(1 for line in lines if line.strip())
        except Exception:
            line_count = char_count = word_count = non_empty = 0
            text = ""

        return ToolResult(
            output=(
                f"📄 {p.name}\n"
                f"   大小: {size_str} ({size} bytes)\n"
                f"   行数: {line_count} (非空: {non_empty})\n"
                f"   字数: {char_count}\n"
                f"   词数: {word_count}\n"
                f"   编码: {detected_enc or 'unknown'}"
            )
        )


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _detect_encoding(head: bytes) -> str | None:
    # Simple heuristic (not chardet, to keep deps minimal)
    try:
        head.decode("utf-8")
        return "UTF-8"
    except UnicodeDecodeError:
        pass
    try:
        head.decode("gbk")
        return "GBK"
    except UnicodeDecodeError:
        pass
    try:
        head.decode("shift-jis")
        return "Shift-JIS"
    except UnicodeDecodeError:
        pass
    return None


def get_tools() -> list[AnalyzeFile]:
    return [AnalyzeFile()]
