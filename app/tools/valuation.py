from langchain_core.tools import tool
from pydantic import BaseModel, Field


def _money(value: float) -> str:
    return f"{value:.2f}"


class MarketComparisonInput(BaseModel):
    comparable_price: float = Field(description="可比实例成交单价，单位为元/平方米")
    transaction_adj: float = Field(default=1.0, description="交易情况修正系数，默认 1.0")
    date_adj: float = Field(default=1.0, description="交易日期修正系数，默认 1.0")
    location_adj: float = Field(default=1.0, description="区位状况修正系数，默认 1.0")
    physical_adj: float = Field(default=1.0, description="实物状况修正系数，默认 1.0")
    rights_adj: float = Field(default=1.0, description="权益状况修正系数，默认 1.0")
    area: float = Field(description="估价对象建筑面积，单位为平方米")


class IncomeApproachInput(BaseModel):
    net_income: float = Field(description="年度稳定净收益，单位为元；例如 60 万元应填 600000")
    cap_rate: float = Field(description="资本化率，小数形式；例如 5% 应填 0.05")


class CostApproachInput(BaseModel):
    land_value: float = Field(description="土地价值，单位为元")
    replacement_cost: float = Field(description="建筑物重置成本，单位为元")
    depreciation: float = Field(description="建筑物折旧，单位为元")


@tool(args_schema=MarketComparisonInput)
def calc_market_comparison(
    comparable_price: float,
    area: float,
    transaction_adj: float = 1.0,
    date_adj: float = 1.0,
    location_adj: float = 1.0,
    physical_adj: float = 1.0,
    rights_adj: float = 1.0,
) -> str:
    """适用于交易案例可比的房地产，计算市场比较法修正单价和总价。"""
    unit_price = (
        comparable_price
        * transaction_adj
        * date_adj
        * location_adj
        * physical_adj
        * rights_adj
    )
    total_value = unit_price * area
    return (
        "市场比较法计算结果：\n"
        f"修正单价 = {_money(comparable_price)} × {_money(transaction_adj)} × "
        f"{_money(date_adj)} × {_money(location_adj)} × {_money(physical_adj)} × "
        f"{_money(rights_adj)} = {_money(unit_price)} 元/平方米\n"
        f"总价 = {_money(unit_price)} × {_money(area)} = {_money(total_value)} 元"
    )


@tool(args_schema=IncomeApproachInput)
def calc_income_approach(net_income: float, cap_rate: float) -> str:
    """适用于可持续产生稳定收益的房地产，按收益法计算资本化价值。"""
    if cap_rate <= 0:
        return "收益法计算错误：资本化率必须大于 0，且应使用小数形式，例如 5% 填 0.05。"

    value = net_income / cap_rate
    return (
        "收益法计算结果：\n"
        f"房地产价值 = 年度稳定净收益 ÷ 资本化率 = {_money(net_income)} ÷ "
        f"{_money(cap_rate)} = {_money(value)} 元"
    )


@tool(args_schema=CostApproachInput)
def calc_cost_approach(land_value: float, replacement_cost: float, depreciation: float) -> str:
    """适用于成本资料充分或交易案例较少的房地产，计算成本法价值。"""
    value = land_value + replacement_cost - depreciation
    return (
        "成本法计算结果：\n"
        f"房地产价值 = 土地价值 + 建筑物重置成本 - 建筑物折旧 = "
        f"{_money(land_value)} + {_money(replacement_cost)} - {_money(depreciation)} "
        f"= {_money(value)} 元"
    )
