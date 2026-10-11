from dataclasses import dataclass

VERSION = "apx240-safe-v1"
DANGERS = ("烟雾", "冒烟", "焦味", "异常高温", "剧烈振动", "金属摩擦声", "部件松脱")
FORBIDDEN = (
    "短接安全门",
    "绕过报警",
    "绕过安全门",
    "带电插拔",
    "带电拆线",
    "带压拆装",
    "徒手触碰加热",
    "徒手接触加热",
)
ISOLATION_ACTIONS = ("打开防护罩", "清除夹料", "检查线路", "接触加热组件")


@dataclass(frozen=True)
class SafetyRule:
    rule_id: str
    page: int
    requirement: str


RULES = (
    SafetyRule("SAFE-01", 3, "出现危险征兆时立即停机并升级专家。"),
    SafetyRule("SAFE-02", 3, "防护罩、夹料、线路或加热组件操作前断电、锁定挂牌并释放残余能量。"),
    SafetyRule("SAFE-03", 3, "禁止绕过保护、带电插拔及徒手触碰加热部件。"),
    SafetyRule("SAFE-04", 3, "回路、拆线、绝缘测试、伺服等维修须相应授权人员。"),
    SafetyRule("SAFE-05", 3, "无知识覆盖、证据矛盾或风险不明时停止进一步操作并升级专家。"),
)
