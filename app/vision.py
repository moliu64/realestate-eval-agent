from __future__ import annotations

import base64
import io
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.config import load_config


def describe_image(image_bytes_or_base64: bytes | str, prompt: str = "请描述图片中的房地产估价相关信息。") -> str:
    config = load_config()
    if not config.vision_api_key:
        raise RuntimeError("未配置 VISION_API_KEY，无法解析图片；请在 .env 中配置通义千问 VL。")

    if isinstance(image_bytes_or_base64, bytes):
        encoded = base64.b64encode(image_bytes_or_base64).decode("ascii")
    else:
        encoded = image_bytes_or_base64.split(",", 1)[-1]

    model = ChatOpenAI(
        model=config.vision_model,
        api_key=config.vision_api_key,
        base_url=config.vision_base_url,
        temperature=0,
        timeout=config.llm_timeout_seconds,
        max_retries=1,
    )
    response = model.invoke([
        HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        ])
    ])
    content = response.content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content).strip()
    return str(content).strip()


def describe_image_file(path: str | Path, prompt: str = "请提取图片中的房地产估价相关信息，包含可见的户型、面积、房龄、价格、日期和趋势数据；无法确认的内容请标注不确定。") -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("图片入库需要安装 Pillow：pip install -r requirements.txt") from exc

    source = Path(path)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((1600, 1600))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    return describe_image(buffer.getvalue(), prompt)
