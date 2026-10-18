"""Shared inspection choices; removing a choice never changes saved results."""
import hashlib
from typing import Literal

from fastapi import Depends, HTTPException
from sqlalchemy import Boolean, Column, String, Text, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Base, Record

DEFAULTS = {'result': ['符合', '不符合'], 'conclusion': ['合格', '不合格']}
Kind = Literal['result', 'conclusion']


class InspectionOption(Base):
    __tablename__ = 'inspection_options'
    kind = Column(String(20), primary_key=True)
    key = Column(String(64), primary_key=True)
    name = Column(Text, nullable=False)
    hidden = Column(Boolean, nullable=False, default=False, server_default='false')


def option_values(kind, name):
    return {'kind': kind, 'key': hashlib.sha256(name.encode()).hexdigest(), 'name': name}


def remember_inspection_options(session, items):
    values = {(kind, item.get(kind, '').strip()) for item in items for kind in DEFAULTS}
    for kind, name in sorted(values):
        if name and name not in DEFAULTS[kind]:
            session.execute(insert(InspectionOption).values(**option_values(kind, name)).on_conflict_do_nothing())


def choices(session, kind):
    options = list(session.scalars(select(InspectionOption).where(InspectionOption.kind == kind)))
    hidden = {option.name for option in options if option.hidden}
    names = {option.name for option in options if not option.hidden}
    for items in session.scalars(select(Record.items)):
        names.update(item.get(kind, '').strip() for item in items)
    return DEFAULTS[kind] + sorted(names.difference(DEFAULTS[kind]).difference(hidden).difference({''}))


def register_inspection_option_routes(app, db, current_user):
    @app.get('/api/inspection-options/{kind}')
    def list_options(kind: Kind, user=Depends(current_user), session: Session = Depends(db)):
        return choices(session, kind)

    def change(kind, name, hidden, session):
        name = name.strip()
        if not name or (hidden and name in DEFAULTS[kind]):
            raise HTTPException(422, '只能删除自定义历史选项' if hidden else '选项内容不能为空')
        session.execute(insert(InspectionOption).values(**option_values(kind, name), hidden=hidden)
                        .on_conflict_do_update(index_elements=['kind', 'key'], set_={'hidden': hidden}))
        session.commit()
        return choices(session, kind)

    @app.post('/api/inspection-options/{kind}')
    def add_option(kind: Kind, name: str, user=Depends(current_user), session: Session = Depends(db)):
        return change(kind, name, False, session)

    @app.delete('/api/inspection-options/{kind}')
    def delete_option(kind: Kind, name: str, user=Depends(current_user), session: Session = Depends(db)):
        return change(kind, name, True, session)
