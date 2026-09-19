import asyncio
from types import SimpleNamespace

from sqlalchemy import select
from egeshka_bot.bot import global_teacher_subject_buttons, review_teacher_subject_buttons, teacher_subject_buttons, teacher_subject_variants
from egeshka_bot.db import SEED, TEACHERS, init_db
from egeshka_bot.models import Teacher, Course
from egeshka_bot.scoring import school_score
from egeshka_bot.subjects import SUBJECTS, MATH_BOTH, target_options
from test_scoring import profile


def test_math_levels_are_independent_hard_filters():
    school = SimpleNamespace(**{k:v for k,v in SEED[-1].items()})
    assert school_score(school, profile('математика базовая'))[0] == -1
    assert school_score(school, profile('математика профильная'))[0] >= 0
    assert all('математика' not in s['subjects'].split(',') for s in SEED)
    assert 'География' in SUBJECTS
    assert SUBJECTS[1] == 'Математика профильная'  # old site_1 links retain meaning
    assert SUBJECTS[11] == 'Математика базовая'


def test_base_targets_and_teacher_routing():
    assert [value for _, value in target_options('математика базовая')] == ['3', '4', '5']
    assert target_options('география')[-1] == ('90+', '90+')
    assert 'Математика базовая' not in teacher_subject_variants('Математика профильная')
    assert MATH_BOTH in teacher_subject_variants('Математика базовая')
    subjects = {t[2] for t in TEACHERS}
    for keyboard in (global_teacher_subject_buttons(subjects), review_teacher_subject_buttons(subjects), teacher_subject_buttons(subjects, 16)):
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        assert all(len(button.callback_data.encode()) <= 64 for button in buttons)
        assert any(button.text == 'Математика базовая' for button in buttons)
        assert not any(button.text == MATH_BOTH for button in buttons)


def test_subject_migration_preserves_existing_teacher_ids(tmp_path):
    async def check():
        url = f'sqlite+aiosqlite:///{tmp_path / "catalog.db"}'
        engine, factory = await init_db(url)
        async with factory() as session:
            teacher = (await session.execute(select(Teacher).where(Teacher.name == 'Надежда Ковалевская'))).scalar_one()
            teacher_id = teacher.id
            teacher.subject = 'Математика'
            await session.commit()
        await engine.dispose()
        engine, factory = await init_db(url)
        async with factory() as session:
            teachers = (await session.execute(select(Teacher).where(Teacher.name == 'Надежда Ковалевская'))).scalars().all()
            assert len(teachers) == 1
            assert teachers[0].id == teacher_id
            assert teachers[0].subject == 'Математика базовая'
            courses = (await session.execute(select(Course).where(Course.subject == 'Математика базовая'))).scalars().all()
            assert courses and all(c.price_from == 0 for c in courses)
        await engine.dispose()
    asyncio.run(check())
