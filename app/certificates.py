import hashlib
import re

from sqlalchemy import Column, String, Text, select
from sqlalchemy.dialects.postgresql import insert
from app.models import Base, Record

DEFAULTS = ['出厂检验报告', '检疫证', '肉品品质合格证', '进关检疫证', '报关单']


class CertificateOption(Base):
    __tablename__ = 'certificate_options'
    key = Column(String(64), primary_key=True)
    name = Column(Text, nullable=False)


def split_certificates(value):
    return list(dict.fromkeys(part.strip() for part in re.split(r'[、,，;；\n]+', value) if part.strip()))


def remember_certificates(session, value):
    for name in sorted(split_certificates(value)):
        session.execute(insert(CertificateOption).values(
            key=hashlib.sha256(name.encode()).hexdigest(), name=name).on_conflict_do_nothing())


def certificate_options(session):
    names = set(session.scalars(select(CertificateOption.name)))
    # Include records saved before this feature was introduced.
    for value in session.scalars(select(Record.fields['certificates'].as_string()).distinct()):
        names.update(split_certificates(value or ''))
    return DEFAULTS + sorted(names.difference(DEFAULTS))
