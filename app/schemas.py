from typing import Literal
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)


class UserCreate(Credentials):
    role: Literal["admin", "user"] = "user"


class UserChange(Input):
    role: Literal["admin", "user"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class LedgerInput(Input):
    name: str = Field(min_length=1, max_length=31)

    @field_validator("name")
    @classmethod
    def valid_sheet_name(cls, value):
        if any(c in value for c in "[]:*?/\\") or value.startswith("'") or value.endswith("'") or any(ord(c) < 32 for c in value):
            raise ValueError("公司名称不能含 Excel 工作表禁止使用的字符")
        return value


class RecordFields(Input):
    arrival_date: date | None = Field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Shanghai")).date())
    material_name: str = ""
    production_dates: list[date] = Field(default_factory=list)
    specification: str = ""
    company_name: str = ""
    address: str = ""
    contact: str = ""
    address_source: Literal["", "supplier", "manufacturer"] = ""
    contact_source: Literal["", "supplier", "manufacturer"] = ""
    shelf_life: str = ""
    received_quantity: str = ""
    certificates: str = ""
    sensory: str = ""
    sampling_items: str = ""
    notes: str = ""


class InspectionItem(Input):
    name: str = ""
    standard: str = ""
    unit: str = ""
    result: str = ""
    conclusion: str = ""


class ReportFields(Input):
    packaging: str = ""
    basis: str = ""
    inspection_date: date | None = None
    internal_report: str = ""
    conclusion: str = ""
    inspector: str = ""
    approver: str = ""


class RecordCreate(Input):
    recognition_job_id: int | None = None
    fields: RecordFields = Field(default_factory=RecordFields)
    material_id: int | None = None
    scheme_id: int | None = None
    items: list[InspectionItem] | None = None
    report: ReportFields = Field(default_factory=ReportFields)
    image_ids: list[int] = Field(default_factory=list, max_length=40)


class VersionInput(Input):
    version: int = Field(ge=1)


class RecordChange(VersionInput):
    recognition_job_id: int | None = None
    fields: RecordFields | None = None
    items: list[InspectionItem] | None = None
    report: ReportFields | None = None
    image_ids: list[int] | None = Field(default=None, max_length=40)
    material_id: int | None = None
    scheme_id: int | None = None


class MaterialInput(Input):
    name: str = Field(min_length=1, max_length=200)
    model: str = ""
    aliases: str = ""


class StandardItem(Input):
    name: str = ""
    standard: str = ""
    unit: str = ""


class SchemeInput(Input):
    material_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    items: list[StandardItem] = Field(default_factory=list)


class ExportInput(Input):
    record_ids: list[int] = Field(min_length=1, max_length=500)
    include_pending: bool = False
    template_base64: str | None = Field(default=None, max_length=14_000_000)


class PartnerInput(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["supplier", "manufacturer"]
    address: str = ""
    contact: str = ""


class RecognitionInput(Input):
    image_ids: list[int] = Field(min_length=1, max_length=40)
    cloud_enabled: bool = True


class CloudSettingInput(Input):
    api_key: str = Field(max_length=2000)
