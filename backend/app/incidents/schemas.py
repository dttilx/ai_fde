from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal[
        "set_temperature_c",
        "actual_temperature_c",
        "heating_current_a",
        "upstream_pressure_mpa",
        "device_pressure_mpa",
    ]
    value: float = Field(strict=True, allow_inf_nan=False)
    unit: Literal["C", "A", "MPa"]


class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_description: str = Field(min_length=1, max_length=5000)
    asset_id: str | None = None
    alarm_code: str | None = Field(default=None, pattern=r"^A\d{3}$")
    readings: list[Reading] = Field(default_factory=list, max_length=8)
    preheating_confirmed: StrictBool | None = None
    observations: dict[str, bool | str | None] = Field(default_factory=dict)
    observation_time: str | None = None

    @field_validator("observations")
    @classmethod
    def validate_observations(cls, value):
        booleans = {
            "smoke",
            "burning_smell",
            "abnormal_heat",
            "violent_vibration",
            "metal_friction",
            "loose_part",
            "continuous_leak_sound",
            "material_present",
            "door_closed",
            "door_alarm_persists_after_reclose",
            "visible_jam",
        }
        enums = {
            "p1_indicator_state": {"ON", "OFF", "UNKNOWN"},
            "panel_state": {"NORMAL", "ABNORMAL", "UNKNOWN"},
            "onset_phase": {"STARTUP", "RUNNING", "AFTER_CHANGEOVER", "UNKNOWN"},
        }
        for key, item in value.items():
            if item is None:
                continue
            if key in booleans and type(item) is bool:
                continue
            if key in enums and item in enums[key]:
                continue
            raise ValueError("Unsupported observation or value")
        return value
