from __future__ import annotations

from typing import Any


SOURCE_DOCUMENTS = [
    {
        "source": "市场数据_武汉基准地价.md",
        "title": "武汉市中心城区城镇建设用地基准地价标准（2023）",
        "publisher": "武汉市人民政府",
        "url": "https://3g.wuhan.gov.cn/zwgk/xxgk/zfwj/szfwj/202407/t20240705_2425353.shtml",
    },
    {
        "source": "市场数据_武汉住宅价格指数.md",
        "title": "70个大中城市商品住宅销售价格变动情况",
        "publisher": "国家统计局",
        "url": "https://www.stats.gov.cn/sj/zxfb/202501/t20250117_1958323.html",
    },
]

# 行政区只用于选择代表级别。具体宗地应以官方基准地价图定位。
DISTRICT_GRADES = {
    "江岸区": 1,
    "江汉区": 1,
    "硚口区": 2,
    "汉阳区": 2,
    "武昌区": 1,
    "青山区": 3,
    "洪山区": 2,
    "东西湖区": 4,
    "汉南区": 5,
    "蔡甸区": 5,
    "江夏区": 4,
    "黄陂区": 5,
    "新洲区": 6,
    "东湖高新区": 2,
    "武汉经开区": 3,
}

LAND_PRICES_2023 = {
    "住宅": [10800, 8690, 6820, 5400, 4350, 3430, 2580, 1920],
    "商铺": [9100, 7230, 5650, 4380, 3340, 2530, 1910, 1370],
    "办公": [7400, 5830, 4490, 3560, 2770, 2210, 1590, 1140],
    "工业厂房": [2200, 1670, 1250, 905, 600, 600, 600, 600],
}

SECONDHAND_YOY = {
    2019: 0.985,
    2020: 1.002,
    2021: 1.022,
    2022: 0.939,
    2023: 0.946,
    2024: 0.897,
}

ASSUMPTIONS = {
    "住宅": {"replacement_unit": 3500.0, "cap_rate": 0.04, "useful_life": 50},
    "商铺": {"replacement_unit": 5000.0, "cap_rate": 0.055, "useful_life": 40},
    "办公": {"replacement_unit": 4500.0, "cap_rate": 0.05, "useful_life": 50},
    "工业厂房": {"replacement_unit": 3000.0, "cap_rate": 0.06, "useful_life": 40},
}

SUPPORTED_YEARS = tuple(range(2019, 2025))


def preset_options() -> dict[str, Any]:
    return {
        "districts": list(DISTRICT_GRADES),
        "years": list(SUPPORTED_YEARS),
        "property_usages": list(LAND_PRICES_2023),
        "sources": SOURCE_DOCUMENTS,
    }


def build_wuhan_preset(
    district: str,
    year: int,
    property_usage: str,
    area: float | None = None,
    building_age: float | None = None,
) -> dict[str, Any]:
    if district not in DISTRICT_GRADES:
        raise ValueError("暂不支持该武汉区域。")
    if year not in SUPPORTED_YEARS:
        raise ValueError(f"数据年份仅支持 {SUPPORTED_YEARS[0]}—{SUPPORTED_YEARS[-1]}。")
    if property_usage not in LAND_PRICES_2023:
        raise ValueError("暂不支持该物业用途。")
    if area is not None and area <= 0:
        raise ValueError("建筑面积必须大于 0。")
    if building_age is not None and building_age < 0:
        raise ValueError("房龄不能小于 0。")

    grade = DISTRICT_GRADES[district]
    market_factor = _market_factor(year)
    official_land_unit = LAND_PRICES_2023[property_usage][grade - 1]
    assumption = ASSUMPTIONS[property_usage]
    replacement_unit = assumption["replacement_unit"]
    cap_rate = assumption["cap_rate"]

    # 房屋单价不是官方发布值，只是把官方楼面地价与可编辑建造成本假设组合后的初测值。
    comparable_price = round((official_land_unit + replacement_unit) * 1.08 * market_factor, -1)
    land_value = round(official_land_unit * market_factor * area, -2) if area else None
    replacement_cost = round(replacement_unit * area, -2) if area else None
    depreciation_rate = min((building_age or 0) / assumption["useful_life"], 0.8)
    depreciation = round(replacement_cost * depreciation_rate, -2) if replacement_cost is not None else None
    net_income = round(comparable_price * area * cap_rate, -2) if area else None

    fields = {
        "comparable_price": _field(comparable_price, "公式推导", "官方楼面地价 + 重置单价假设，并按武汉二手住宅指数换算"),
        "net_income": _field(net_income, "公式推导", "模型总价 × 可编辑资本化率"),
        "cap_rate": _field(cap_rate, "估值假设", "按物业用途设置的初始值，正式估价应由市场租售比或安全利率加风险调整确定"),
        "land_value": _field(land_value, "公式推导", "2023 官方代表级别基准地价 × 面积 × 年份系数"),
        "replacement_cost": _field(replacement_cost, "估值假设", "可编辑重置单价 × 建筑面积"),
        "depreciation": _field(depreciation, "公式推导", "重置成本 × min(房龄/经济寿命, 80%)"),
    }
    return {
        "district": district,
        "year": year,
        "property_usage": property_usage,
        "representative_grade": grade,
        "market_factor": round(market_factor, 4),
        "official_land_unit": official_land_unit,
        "fields": fields,
        "sources": SOURCE_DOCUMENTS,
        "warnings": [
            "行政区代表级别不是宗地级地价认定，具体项目应按官方基准地价图定位。",
            "可比单价、净收益、资本化率、重置成本和折旧均含模型推导或估值假设，应用前必须复核。",
        ],
    }


def _market_factor(year: int) -> float:
    levels = {2018: 1.0}
    for current_year in sorted(SECONDHAND_YOY):
        levels[current_year] = levels[current_year - 1] * SECONDHAND_YOY[current_year]
    return levels[year] / levels[2023]


def _field(value: float | None, evidence: str, basis: str) -> dict[str, Any]:
    return {"value": value, "evidence": evidence, "basis": basis}
