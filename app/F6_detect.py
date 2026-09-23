"""F6 起火点识别：统计全景图中"碳化黑/深褐"像素占比，找出最可能的起火点位。

纯函数模块，不依赖 FastAPI / Blender，可独立在容器或本机运行。
"""
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel

# ---- 颜色阈值常量（HSV 空间，OpenCV 8bit 取值范围：H 0-179, S/V 0-255） ----
BLACK_V_MAX = 70    # 炭化纯黑：亮度低于该值即视为烧焦
BROWN_H_MIN = 5     # 深褐焦痕色相下限
BROWN_H_MAX = 30    # 深褐焦痕色相上限
BROWN_S_MIN = 60    # 深褐焦痕最低饱和度（排除偏灰墙面）
BROWN_V_MIN = 40    # 深褐焦痕最低亮度（排除纯黑阴影区）
BROWN_V_MAX = 130   # 深褐焦痕最高亮度（排除正常木色/亮橙色）


class PointBurnStat(BaseModel):
    """单个点位的烧痕统计。"""

    point_id: int
    burn_ratio: float


class IgnitionResult(BaseModel):
    """F6 输出：起火点 ID 与各点位统计明细。"""

    ignition_point: int
    max_ratio: float
    stats: list[PointBurnStat]


def build_burn_mask(image_bgr: NDArray[np.uint8]) -> NDArray[np.bool_]:
    """构造二值掩码：True 表示"碳化黑/深褐"像素。"""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h: NDArray[np.uint8] = hsv[:, :, 0]
    s: NDArray[np.uint8] = hsv[:, :, 1]
    v: NDArray[np.uint8] = hsv[:, :, 2]

    black_mask: NDArray[np.bool_] = v <= BLACK_V_MAX
    brown_mask: NDArray[np.bool_] = (
        (h >= BROWN_H_MIN)
        & (h <= BROWN_H_MAX)
        & (s >= BROWN_S_MIN)
        & (v >= BROWN_V_MIN)
        & (v <= BROWN_V_MAX)
    )
    return black_mask | brown_mask


def calc_burn_ratio(image_bgr: NDArray[np.uint8]) -> float:
    """返回图像中烧痕像素占比（0.0 ~ 1.0）。"""
    if image_bgr.size == 0:
        return 0.0
    mask = build_burn_mask(image_bgr)
    return float(mask.sum()) / float(mask.size)


def load_pano(image_dir: Path, point_id: int, ext: str = ".jpg") -> NDArray[np.uint8]:
    """按点位 ID 读取对应全景图，读取失败直接抛错。"""
    image_path = image_dir / f"{point_id}{ext}"
    image: NDArray[np.uint8] | None = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")
    return image


def find_ignition_point(image_dir: Path, point_ids: Sequence[int]) -> IgnitionResult:
    """遍历点位图片，返回烧痕占比最高的点位作为起火点。"""
    stats: list[PointBurnStat] = []
    for point_id in point_ids:
        image = load_pano(image_dir, point_id)
        ratio = calc_burn_ratio(image)
        stats.append(PointBurnStat(point_id=point_id, burn_ratio=ratio))

    best = max(stats, key=lambda s: s.burn_ratio)
    return IgnitionResult(
        ignition_point=best.point_id,
        max_ratio=best.burn_ratio,
        stats=stats,
    )
