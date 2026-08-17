from typing import Any, Literal

from pydantic import BaseModel, Field


class RequirementSchema(BaseModel):
    property_usage: str = Field(default="", description="房地产用途，如住宅、商铺、办公、工业厂房")
    area: float | None = Field(default=None, description="建筑面积，单位平方米；未知则为空")
    location: str = Field(default="", description="区位或项目位置；未知则为空")
    rights_type: str = Field(default="", description="权利类型，如商品房、国有建设用地使用权等")
    valuation_purpose: str = Field(default="", description="估价目的，如买卖参考、抵押、投资测算")
    valuation_date: str = Field(default="", description="估价时点；未知则为空")
    layout: str = Field(default="", description="户型，例如三房两厅")
    building_age: float | None = Field(default=None, description="房龄，单位年")
    orientation: str = Field(default="", description="朝向")
    floor: str = Field(default="", description="楼层")
    decoration: str = Field(default="", description="装修状况")
    known_data: dict[str, Any] = Field(default_factory=dict, description="已知数据，金额单位统一为元，比例统一为小数")
    missing_data: list[str] = Field(default_factory=list, description="缺失但影响估价的数据")


class MethodPlanSchema(BaseModel):
    methods: list[Literal["market_comparison", "income", "cost"]] = Field(
        default_factory=list,
        description="估价方法队列，按执行顺序排列",
    )
    params: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="各方法已知参数，金额单位统一为元，百分比统一为小数",
    )


class ComputationItem(BaseModel):
    method: str
    tool: str = ""
    result: str = ""
    source: str = ""
    value: float | None = None
    missing: list[str] = Field(default_factory=list)


class ReportSchema(BaseModel):
    question: str
    property_info: dict[str, Any] = Field(default_factory=dict)
    valuation_purpose: str = ""
    valuation_date: str = ""
    methods: list[str] = Field(default_factory=list)
    computations: list[ComputationItem] = Field(default_factory=list)
    verification: str = ""
    missing_data: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    report_markdown: str = ""
