from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest
from .teacher_copy import teacher_description
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import asyncio
import json
from datetime import datetime, timedelta
from html import escape
from sqlalchemy import func, select

from .config import Settings
from .db import SCHOOL_REVIEW_SLUGS, delete_user_data, get_or_create_user
from .models import Course, Event, Review, ReviewCriterionScore, School, Teacher
from .scoring import QuizProfile, school_score


from .subjects import SUBJECTS, MATH_BOTH, target_options, split_teacher_subjects, subject_token, subject_from_token


PRIORITIES = {
    "teacher": "преподаватели",
    "practice": "практика",
    "curator": "куратор",
    "platform": "платформа",
    "price": "цена",
}

PRIORITY_LABELS = {
    "teacher": "Сильные преподаватели",
    "practice": "Практика и домашние задания",
    "curator": "Куратор и поддержка",
    "platform": "Удобная платформа",
    "price": "Доступная цена",
}

CRITERIA = (
    ("teachers_score", "Преподаватели", 0.24),
    ("practice_score", "Практика и ДЗ", 0.16),
    ("feedback_score", "Проверка и обратная связь", 0.14),
    ("curator_score", "Кураторы", 0.14),
    ("platform_score", "Платформа", 0.10),
    ("workload_score", "Нагрузка и темп", 0.08),
    ("organization_score", "Организация обучения", 0.14),
)
CRITERIA_BY_KEY = {field: label for field, label, _ in CRITERIA}
LEGACY_CRITERIA_KEYS = {"price_quality_score": "organization_score"}

# These are deliberately kept separate from the school criteria.  We collect
# the parts that a student can fairly assess after studying with a teacher,
# without inventing an "expert" sub-score where the public source does not
# support one yet.
TEACHER_CRITERIA = (
    ("explanation", "Объяснение материала"),
    ("practice", "Практика и разбор ошибок"),
    ("atmosphere", "Атмосфера и вовлечённость"),
    ("structure", "Структура и темп занятий"),
    ("exam_value", "Польза для экзамена"),
)
TEACHER_CRITERIA_BY_KEY = {field: label for field, label in TEACHER_CRITERIA}
REVIEW_CRITERIA_BY_KEY = {**CRITERIA_BY_KEY, **TEACHER_CRITERIA_BY_KEY, "price_quality_score": "Организация обучения (старый отзыв)"}
SCHOOL_BY_REVIEW_SLUG = {slug: name for name, slug in SCHOOL_REVIEW_SLUGS.items()}


class Quiz(StatesGroup):
    subject = State()
    budget = State()
    current_level = State()
    target = State()
    curator = State()
    workload = State()
    first_priority = State()
    second_priority = State()
    control = State()


class Compare(StatesGroup):
    first = State()
    second = State()


class TeacherCompare(StatesGroup):
    subject = State()
    first = State()
    second = State()


class CourseCompare(StatesGroup):
    first = State()
    second = State()


class ReviewForm(StatesGroup):
    score = State()
    criterion_score = State()
    positive = State()
    negative = State()
    verification = State()


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def profile_from_payload(payload: str):
    """Parse the deep-link payload produced by the site's quiz
    (`q_<subjectIndex>_<budget>_<level>_<target>_<curator>_<workload>_<priority1>_<priority2>_<control>`)
    into the same QuizProfile the bot's own /quiz builds, so a student who
    finished the quiz on the site lands on a result computed by the exact
    same formula instead of answering everything again.
    """
    try:
        _, subject_index, budget, level, target, curator, workload, priority1, priority2, control = payload.split("_")
        site_subjects = [item.lower() for item in SUBJECTS]
        priorities = tuple(value for value in (priority1, priority2) if value != "none")
        return QuizProfile(
            subject=site_subjects[int(subject_index)],
            budget=int(budget) or None,
            current_level=level,
            target=int(target),
            curator_need=int(curator),
            workload=int(workload),
            control_need=int(control),
            priorities=priorities,
        )
    except (ValueError, IndexError):
        return None


def teacher_subject_variants(subject: str) -> tuple[str, ...]:
    """Course catalogue uses exam names; teacher catalogues sometimes spell them out."""
    aliases = {
        "Английский": "Английский язык",
        "Русский": "Русский язык",
        "Математика": "Математика профильная",
    }
    return tuple(dict.fromkeys((subject, aliases.get(subject, subject), *([MATH_BOTH] if subject in ("Математика профильная", "Математика базовая") else []))))


def score_bar(value, width=5):
    filled = max(0, min(width, round(float(value) / 2)))
    return "●" * filled + "○" * (width - filled)


def school_professional_score(school):
    return sum(float(getattr(school, field, 0)) * weight for field, _, weight in CRITERIA)


def blend_rating(editorial, user_average=None, user_count=0):
    """Blend an editorial 0–10 score with a 0–10 average of confirmed student
    reviews. Below 3 reviews the editorial score stands alone (preliminary).
    From 3 reviews the student average is blended in with a weight that
    grows with review_count, so it becomes noticeable after a handful of
    reviews rather than only after several dozen; the result still counts
    as preliminary (marked with *) until 10 reviews.
    """
    editorial = max(0.0, min(10.0, float(editorial)))
    if user_average is None or user_count < 3:
        return round(editorial, 1), True
    weight = user_count / (user_count + 5)
    user_score = max(0.0, min(10.0, float(user_average)))
    blended = editorial * (1 - weight) + user_score * weight
    return round(blended, 1), user_count < 10


def school_criteria_text(school, user_stats=None):
    user_stats = user_stats or {}
    lines = ["📊 Оценка по критериям", "Редакция + отзывы учеников · итоговая шкала 0–10"]
    for field, label, weight in CRITERIA:
        value = float(getattr(school, field, 0))
        average, count = user_stats.get(field, (None, 0))
        blended, preliminary = blend_rating(value, average, count)
        if count:
            marker = "*" if preliminary else ""
            lines.append(f"{score_bar(blended)} {label}: {blended:.1f}/10{marker} · вес {weight:.0%}")
        else:
            lines.append(f"{score_bar(value)} {label}: {value:.1f}/10 · пока без отзывов · вес {weight:.0%}")
    return "\n".join(lines)


def school_criteria_simple_text(school, user_stats=None):
    user_stats = user_stats or {}

    def number(value):
        return f"{float(value):.1f}".replace(".", ",")

    lines = ["📊 <b>Критерии школы</b>", "Итоговая оценка каждого критерия · шкала 0–10"]
    for field, label, _ in CRITERIA:
        value = float(getattr(school, field, 0))
        average, count = user_stats.get(field, (None, 0))
        blended, preliminary = blend_rating(value, average, count)
        score_text = f"{number(blended)}/10" + (" · предварительно" if preliminary else "")
        lines.append(f"{score_bar(blended)}  {label} · {score_text}")
    if not any(count for _, count in user_stats.values()):
        lines.append("\nОценка станет комбинированной, когда появятся одобренные отзывы учеников.")
    return "\n".join(lines)


def menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Подобрать школу", callback_data="quiz")],
            [InlineKeyboardButton(text="⚖️ Сравнить школы", callback_data="compare")],
            [InlineKeyboardButton(text="👩‍🏫 Сравнить преподавателей", callback_data="teacher_compare_menu")],
            [InlineKeyboardButton(text="💬 Отзыв о школе", callback_data="review_school_menu"),
             InlineKeyboardButton(text="👩‍🏫 Отзыв о преподавателе", callback_data="review_teacher_menu")],
            [InlineKeyboardButton(text="📚 Найти курс по предмету", callback_data="courses"),
             InlineKeyboardButton(text="🏫 Школы", callback_data="schools")],
            [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
            [InlineKeyboardButton(text="📰 Канал", callback_data="channel")],
            [InlineKeyboardButton(text="🔐 Мои данные", callback_data="my_data")],
        ]
    )


def options(items, prefix, with_back=True):
    footer = []
    if with_back:
        footer.append([InlineKeyboardButton(text="← Назад", callback_data="quiz_back")])
    footer.append([InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"{prefix}:{value}")]
            for text, value in items
        ]
        + footer
    )


def school_buttons(rows, prefix):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=row.name, callback_data=f"{prefix}:{row.id}")]
            for row in rows
        ]
        + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def course_subject_buttons(subjects):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"course_subject:{subject}")]
            for subject in subjects
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def course_buttons(rows, prefix="course", exclude_id=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row.school_name} · {row.subject}", callback_data=f"{prefix}:{row.id}")]
            for row in rows if row.id != exclude_id
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def _course_tariffs_text(course):
    try:
        tariffs = json.loads(course.tariffs_json or "[]")
    except json.JSONDecodeError:
        tariffs = []
    if not tariffs:
        return "Тарифы и детали зависят от предмета. Открой официальный источник перед оплатой."
    return "\n".join(
        f"• <b>{escape(item['name'])}</b> — от {money(int(item['price']))} руб./мес\n  {escape(item['details'])}"
        for item in tariffs
    )


def course_subject_profile(teachers):
    count = len(teachers)
    names = ", ".join(teacher.name for teacher in teachers)
    if count >= 4:
        return (
            f"У ЕГЭ Мэтча есть карточки {count} преподавателей: {names}. "
            "По предмету есть выбор — сначала сравни преподавателей и проверь, кто ведёт твой набор."
        )
    if count >= 2:
        return (
            f"У ЕГЭ Мэтча есть карточки {count} преподавателей: {names}. "
            "Можно открыть карточки и сравнить опыт, результаты и отзывы."
        )
    if count == 1:
        return (
            f"В открытых источниках подтверждён один профиль: {names}. "
            "Перед оплатой проверь на странице набора, кто ведёт курс сейчас."
        )
    return (
        "В открытом каталоге школы не найден подтверждённый профиль преподавателя по этому предмету. "
        "Перед оплатой проверь ведущего на странице выбранного набора."
    )


def course_card(course, school, teachers):
    checked = course.verified_at.strftime("%d.%m.%Y") if course.verified_at else "дата не указана"
    return (
        f"📚 <b>{escape(course.name)}</b>\n"
        f"🏫 {escape(school.name)}\n\n"
        f"💸 <b>Цена</b>\n{escape(course.price_text)}\n\n"
        f"🎓 <b>Формат</b>\n{escape(course.format_text)}\n\n"
        f"🧑‍🏫 <b>Поддержка</b>\n{escape(course.support_text)}\n\n"
        f"📝 <b>Практика</b>\n{escape(course.practice_text)}\n\n"
        f"👩‍🏫 <b>Что по предмету</b>\n{escape(course_subject_profile(teachers))}\n\n"
        f"🎯 <b>Кому может подойти</b>\n{escape(school.fit_text)}\n\n"
        f"🔎 <b>Что проверить перед оплатой</b>\n"
        "Кто ведёт выбранный набор, полную стоимость всех месяцев или блоков и состав поддержки в твоём тарифе.\n\n"
        f"🔎 <b>Данные проверены</b>: {checked}\n"
        f"Источник: {escape(course.source_url)}"
    )


def course_card_keyboard(course_id, source_url=None):
    rows = [
        [InlineKeyboardButton(text="💸 Тарифы", callback_data=f"course_section:{course_id}:tariffs")],
    ]
    if source_url:
        rows.append([InlineKeyboardButton(text="🌐 Перейти на сайт школы", url=source_url)])
    rows += [
        [InlineKeyboardButton(text="👩‍🏫 Преподаватели предмета", callback_data=f"course_teachers:{course_id}")],
        [InlineKeyboardButton(text="⚖️ Сравнить с курсом другой школы", callback_data=f"course_compare:{course_id}")],
        [InlineKeyboardButton(text="💬 Оставить отзыв о школе", callback_data=f"review_course_school:{course_id}")],
        [InlineKeyboardButton(text="← К курсам по предметам", callback_data="courses")],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def course_compare_keyboard(left_id, right_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Цена и тарифы", callback_data=f"course_compare_section:{left_id}:{right_id}:price")],
        [InlineKeyboardButton(text="🎓 Формат и нагрузка", callback_data=f"course_compare_section:{left_id}:{right_id}:format")],
        [InlineKeyboardButton(text="🧑‍🏫 Поддержка и практика", callback_data=f"course_compare_section:{left_id}:{right_id}:learning")],
        [InlineKeyboardButton(text="👩‍🏫 Преподаватели", callback_data=f"course_compare_section:{left_id}:{right_id}:teachers")],
        [InlineKeyboardButton(text="← К карточке курса", callback_data=f"course:{left_id}")],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def course_compare_teachers_keyboard(left, right, left_school, right_school):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👩‍🏫 Преподаватели: {left_school.name}", callback_data=f"course_teachers:{left.id}")],
        [InlineKeyboardButton(text=f"👩‍🏫 Преподаватели: {right_school.name}", callback_data=f"course_teachers:{right.id}")],
        [InlineKeyboardButton(text="← К сравнению курсов", callback_data=f"course_compare_result:{left.id}:{right.id}")],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def course_compare_text(left, right, left_school, right_school):
    left_price = f"от {money(left.price_from)} руб." if left.price_from else "цену уточняй в карточке"
    right_price = f"от {money(right.price_from)} руб." if right.price_from else "цену уточняй в карточке"
    return (
        "⚖️ <b>Сравнение курсов</b>\n\n"
        f"📚 {escape(left.subject)}\n\n"
        f"<b>{escape(left_school.name)}</b>\n{escape(left.name)} · {left_price}\n\n"
        f"<b>{escape(right_school.name)}</b>\n{escape(right.name)} · {right_price}\n\n"
        "Открой нужный раздел, чтобы сравнить только цену, формат, поддержку или преподавателей."
    )


def course_compare_section_text(left, right, left_school, right_school, section, left_teachers=(), right_teachers=()):
    if section == "price":
        return (
            "💸 <b>Цена и тарифы</b>\n\n"
            f"<b>{escape(left_school.name)}</b>\n{escape(left.price_text)}\n\n"
            f"{_course_tariffs_text(left)}\n\n────────────\n\n"
            f"<b>{escape(right_school.name)}</b>\n{escape(right.price_text)}\n\n"
            f"{_course_tariffs_text(right)}"
        )
    if section == "format":
        return (
            "🎓 <b>Формат и нагрузка</b>\n\n"
            f"<b>{escape(left_school.name)}</b>\n{escape(left.format_text)}\n\n────────────\n\n"
            f"<b>{escape(right_school.name)}</b>\n{escape(right.format_text)}"
        )
    if section == "learning":
        return (
            "🧑‍🏫 <b>Поддержка и практика</b>\n\n"
            f"<b>{escape(left_school.name)}</b>\nПоддержка: {escape(left.support_text)}\n\nПрактика: {escape(left.practice_text)}"
            f"\n\n────────────\n\n"
            f"<b>{escape(right_school.name)}</b>\nПоддержка: {escape(right.support_text)}\n\nПрактика: {escape(right.practice_text)}"
        )
    if section == "teachers":
        left_names = ", ".join(t.name for t in left_teachers) or "подтверждённые профили не найдены в открытом каталоге"
        right_names = ", ".join(t.name for t in right_teachers) or "подтверждённые профили не найдены в открытом каталоге"
        return (
            "👩‍🏫 <b>Преподаватели по предмету</b>\n\n"
            f"<b>{escape(left_school.name)}</b>\n{escape(left_names)}\n\n────────────\n\n"
            f"<b>{escape(right_school.name)}</b>\n{escape(right_names)}\n\n"
            "Перед оплатой проверь, кто ведёт именно выбранный набор: состав может меняться."
        )
    return "Раздел недоступен. Вернись к карточке курса."


def priority_keyboard(first_priority=None):
    rows = []
    for value, label in PRIORITIES.items():
        if value == first_priority:
            continue
        rows.append([InlineKeyboardButton(text=PRIORITY_LABELS[value], callback_data=f"priority:{value}")])
    rows.append([InlineKeyboardButton(text="Пропустить второй приоритет", callback_data="priority:none")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="quiz_back")])
    rows.append([InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def school_card(school, user_average=None, user_count=0, criteria_stats=None):
    divider = "────────────"
    e = escape
    return (
        f"🏫 <b>{e(school.name)}</b>\n\n{e(school.description)}\n\n"
        f"{divider}\n📚 <b>Предметы</b>\n{e(school.subjects.replace(',', ', '))}\n\n"
        f"{divider}\n{school_criteria_text(school, criteria_stats)}\n"
        f"<b>{e(hybrid_rating(school_professional_score(school), user_average, user_count))}</b>\n\n"
        f"{divider}\n🎯 <b>Кому подходит</b>\n{e(school.fit_text)}\n\n"
        f"{divider}\n💸 <b>Цена и тарифы</b>\n{e(school.price_text or f'от {money(school.monthly_price_from)} руб./мес')}\n\n"
        f"{divider}\n📈 <b>Результаты и баллы</b>\n{e(school.results_text)}\n\n"
        f"{divider}\n🎓 <b>Формат</b>\n{e(school.format_text)}\n\n"
        f"{divider}\n🧑‍🏫 <b>Поддержка</b>\n{e(school.support_text)}\n\n"
        f"{divider}\n📝 <b>Практика</b>\n{e(school.homework_text)}\n\n"
        f"{divider}\n✅ <b>Сильные стороны</b>\n{e(school.strengths)}\n\n"
        f"{divider}\n⚠️ <b>Риски и жалобы</b>\n{e(school.weaknesses)}\n\n"
        f"{divider}\n💬 <b>Отзывы</b>\n{e(school.review_summary)}\n\n"
        f"{divider}\n🔎 <b>Источники</b>\n{e(school.price_comment)}\n<i>Тип данных: {e(school.evidence_types)}</i>\n\n"
        f"🌐 <b>Сайт:</b> {e(school.official_url)}"
    )


def school_overview(school, user_average=None, user_count=0):
    e = escape
    rating = hybrid_rating(school_professional_score(school), user_average, user_count)
    return (
        f"🏫 <b>{e(school.name)}</b>\n\n"
        f"{e(school.description)}\n\n"
        f"📚 <b>Предметы</b>\n{e(school.subjects.replace(',', ', '))}\n\n"
        f"⭐ <b>Оценка</b>\n{e(rating)}\n\n"
        f"✅ <b>Сильные стороны</b>\n{e(school.strengths)}\n\n"
        f"💸 <b>Цена от</b>\n{e(school.price_text or f'от {money(school.monthly_price_from)} руб./мес')}"
    )


def school_section_text(school, section, criteria_stats=None):
    e = escape
    sections = {
        "price": ("💸 Цена и тарифы", school.price_text or f"от {money(school.monthly_price_from)} руб./мес"),
        "format": ("🎓 Формат", school.format_text),
        "support": ("🧑‍🏫 Поддержка", school.support_text),
        "practice": ("📝 Практика и ДЗ", school.homework_text),
        "strengths": ("✅ Сильные стороны", school.strengths),
        "risks": ("⚠️ Риски и жалобы", school.weaknesses),
        "results": ("📈 Результаты и баллы", school.results_text),
    }
    if section == "criteria":
        return school_criteria_simple_text(school, criteria_stats)
    title, body = sections.get(section, ("Раздел", "Информация для этого раздела не найдена"))
    return f"{title}\n\n{e(body)}"


def card_keyboard(school_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💸 Цена", callback_data=f"school_section:{school_id}:price"),
             InlineKeyboardButton(text="🎓 Формат", callback_data=f"school_section:{school_id}:format")],
            [InlineKeyboardButton(text="🧑‍🏫 Поддержка", callback_data=f"school_section:{school_id}:support"),
             InlineKeyboardButton(text="📝 Практика", callback_data=f"school_section:{school_id}:practice")],
            [InlineKeyboardButton(text="📊 Критерии", callback_data=f"school_section:{school_id}:criteria"),
             InlineKeyboardButton(text="⚠️ Риски", callback_data=f"school_section:{school_id}:risks")],
            [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data=f"review_school:{school_id}")],
            [InlineKeyboardButton(text="⭐ Оценить критерий", callback_data=f"review_criteria:{school_id}")],
            [InlineKeyboardButton(text="⚖️ Сравнить с другой школой", callback_data=f"compare_with:{school_id}")],
            [InlineKeyboardButton(text="👩‍🏫 Посмотреть преподавателей", callback_data=f"teachers:{school_id}")],
            [InlineKeyboardButton(text="📰 Новости и разборы ЕГЭ", callback_data="channel")],
            [InlineKeyboardButton(text="← Вернуться к каталогу", callback_data="schools")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
        ]
    )


def school_total_score(school, user_average=None, user_count=0):
    """A display score on the shared 0–10 scale and a preliminary flag."""
    return blend_rating(school_professional_score(school), user_average, user_count)


def criterion_total(value, stats, field):
    average, count = (stats or {}).get(field, (None, 0))
    return blend_rating(value, average, count)


def comparison_text(left, right, left_user_average=None, left_user_count=0, right_user_average=None, right_user_count=0, left_criteria_stats=None, right_criteria_stats=None):
    """Short first screen. Details live behind focused buttons."""
    left_total, left_preliminary = school_total_score(left, left_user_average, left_user_count)
    right_total, right_preliminary = school_total_score(right, right_user_average, right_user_count)

    def score(value, preliminary):
        return f"{value:.1f}".replace(".", ",") + "/10" + ("*" if preliminary else "")

    return (
        "⚖️ <b>Сравнение школ</b>\n\n"
        f"{escape(left.name)}  │  {escape(right.name)}\n\n"
        "⭐ <b>Итоговый рейтинг</b>\n"
        f"{escape(left.name)} — <b>{score(left_total, left_preliminary)}</b>\n"
        f"{escape(right.name)} — <b>{score(right_total, right_preliminary)}</b>\n\n"
        "Открой нужный раздел: там только данные по одной теме, без длинной сводки.\n"
        "* Предварительный балл: нет одобренных отзывов учеников."
    )


def comparison_section_text(left, right, section, left_stats=None, right_stats=None):
    left_stats = left_stats or {}
    right_stats = right_stats or {}

    def comma(value):
        return f"{value:.1f}".replace(".", ",")

    if section == "criteria":
        lines = [
            "📊 <b>Критерии</b>",
            f"{escape(left.name)}  │  {escape(right.name)}",
            "Шкала 0–10\n",
        ]
        has_preliminary = False
        for field, label, _ in CRITERIA:
            left_value, left_preliminary = criterion_total(getattr(left, field), left_stats, field)
            right_value, right_preliminary = criterion_total(getattr(right, field), right_stats, field)
            has_preliminary = has_preliminary or left_preliminary or right_preliminary
            lines.append(
                f"{escape(label)}\n{comma(left_value)}/10{'*' if left_preliminary else ''}  │  "
                f"{comma(right_value)}/10{'*' if right_preliminary else ''}"
            )
        if has_preliminary:
            lines.append("\n* Предварительный балл: нет одобренных отзывов учеников.")
        return "\n\n".join(lines)

    sections = {
        "price": ("💸 <b>Цена и тарифы</b>", "price_text"),
        "format": ("🎓 <b>Формат</b>", "format_text"),
        "support": ("🧑‍🏫 <b>Поддержка</b>", "support_text"),
        "practice": ("📝 <b>Практика</b>", "homework_text"),
        "strengths": ("✅ <b>Сильные стороны</b>", "strengths"),
        "risks": ("⚠️ <b>Риски и жалобы</b>", "weaknesses"),
    }
    title, attribute = sections.get(section, ("Раздел", "description"))
    return (
        f"{title}\n\n"
        f"<b>{escape(left.name)}</b>\n{escape(getattr(left, attribute))}\n\n"
        f"────────────\n\n"
        f"<b>{escape(right.name)}</b>\n{escape(getattr(right, attribute))}"
    )


def comparison_keyboard(left_id, right_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Все критерии", callback_data=f"compare_section:{left_id}:{right_id}:criteria")],
        [InlineKeyboardButton(text="💸 Цена", callback_data=f"compare_section:{left_id}:{right_id}:price"),
         InlineKeyboardButton(text="🎓 Формат", callback_data=f"compare_section:{left_id}:{right_id}:format")],
        [InlineKeyboardButton(text="🧑‍🏫 Поддержка", callback_data=f"compare_section:{left_id}:{right_id}:support"),
         InlineKeyboardButton(text="📝 Практика", callback_data=f"compare_section:{left_id}:{right_id}:practice")],
        [InlineKeyboardButton(text="✅ Сильные стороны", callback_data=f"compare_section:{left_id}:{right_id}:strengths"),
         InlineKeyboardButton(text="⚠️ Риски", callback_data=f"compare_section:{left_id}:{right_id}:risks")],
        [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:compare")],
        [InlineKeyboardButton(text="📰 Новости и разборы ЕГЭ", callback_data="channel")],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def rating_methodology_text():
    return (
        "ℹ️ Как считается рейтинг\n\n"
        "<b>Школы:</b> сначала редакционная оценка по семи критериям — шкала 0–10. С трёх подтверждённых отзывов "
        "в неё подмешивается оценка учеников: её вес растёт с числом отзывов и становится заметным уже после "
        "5–10 отзывов, а не только после нескольких десятков — это специально сделано так, чтобы у небольших школ "
        "тоже был реальный шанс повлиять на свою оценку отзывами.\n\n"
        "<b>Преподаватели:</b> оценку ставят только подтверждённые ученики по пяти критериям — от 1 до 10 каждый: "
        "понятность объяснений, практика и разбор ошибок, атмосфера, структура и темп, польза для ЕГЭ. "
        "Итог до 10 — среднее этих пяти оценок.\n\n"
        "Оценка появляется после трёх подтверждённых отзывов и помечается как предварительная (*), пока их меньше десяти. "
        "Неподтверждённые отзывы можно читать после модерации, но они не меняют рейтинг."
    )


def teacher_buttons(rows, school_id, include_compare=True):
    footer = []
    if include_compare:
        footer.append([InlineKeyboardButton(text="⚖️ Сравнить преподавателей", callback_data=f"teacher_compare:{school_id}")])
    footer.extend([
            [InlineKeyboardButton(text="← Вернуться к школе", callback_data=f"school:{school_id}")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
        ])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row.name} · {row.subject}", callback_data=f"teacher:{row.id}")]
            for row in rows
        ] + footer
    )


def teacher_subject_buttons(subjects, school_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"teacher_subject:{school_id}:{subject_token(subject)}")]
            for subject in split_teacher_subjects(subjects)
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def global_teacher_subject_buttons(subjects):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"global_teacher_subject:{subject_token(subject)}")]
            for subject in split_teacher_subjects(subjects)
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def review_teacher_subject_buttons(subjects):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"review_teacher_subject:{subject_token(subject)}")]
            for subject in split_teacher_subjects(subjects)
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def global_teacher_buttons(rows, first_id=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row.name} · {row.school_name}", callback_data=f"teacher:{row.id}")]
            for row in rows if row.id != first_id
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def review_teacher_buttons(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{row.name} · {row.school_name}", callback_data=f"review_teacher_pick:{row.id}")]
            for row in rows
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def teacher_rating_from_criteria(stats):
    """Return the student-only /10 rating and number of verified reviews."""
    values = [float(average) for average, count in stats.values() if average is not None and count]
    counts = [int(count) for _average, count in stats.values() if count]
    if len(values) != len(TEACHER_CRITERIA) or not counts:
        return None, 0
    return round(sum(values) / len(values), 1), min(counts)


def teacher_rating_text(stats):
    average, count = teacher_rating_from_criteria(stats)
    if average is None or count < 3:
        return "Оценка учеников: пока не сформирована\nНужно минимум 3 подтверждённых отзыва"
    marker = "*" if count < 10 else ""
    return f"Оценка учеников: {average:.1f}/10{marker}\nПодтверждённых отзывов: {count}".replace(".", ",")


def teacher_compare_text(
    left,
    right,
    school=None,
    left_stats=None,
    right_stats=None,
):
    school_line = f"🏫 {school.name}" if school else f"🏫 {left.school_name} и {right.school_name}"
    left_school_name = school.name if school else left.school_name
    right_school_name = school.name if school else right.school_name
    left_rating = teacher_rating_text(left_stats or {})
    right_rating = teacher_rating_text(right_stats or {})
    return (
        f"⚖️ Сравнение преподавателей\n\n"
        f"{school_line}\n"
        f"📚 {left.subject}\n\n"
        f"👩‍🏫 {left.name} ({left_school_name})\n⭐ {left_rating}\n\n"
        f"👩‍🏫 {right.name} ({right_school_name})\n⭐ {right_rating}\n\n"
        "Открой карточку преподавателя, если хочешь посмотреть биографию, результаты и ссылки."
    )


def teacher_compare_keyboard(left, right, school_id=None):
    rows = [
        [InlineKeyboardButton(text=f"👩‍🏫 {left.name}", callback_data=f"teacher:{left.id}"),
         InlineKeyboardButton(text=f"👩‍🏫 {right.name}", callback_data=f"teacher:{right.id}")],
        [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:teacher_compare")],
    ]
    if school_id:
        rows.append([InlineKeyboardButton(text="← Преподаватели школы", callback_data=f"teachers:{school_id}")])
        rows.append([InlineKeyboardButton(text="← Карточка школы", callback_data=f"school:{school_id}")])
    rows.append([InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hybrid_rating(editorial_out_of_10, user_average=None, user_count=0):
    editorial = max(0.0, min(10.0, float(editorial_out_of_10)))
    if user_average is None or user_count < 3:
        user_line = (
            f"Пользовательская оценка: {float(user_average):.1f}/10 ({user_count} отзывов)"
            if user_average is not None
            else "Пользовательская оценка: нет данных"
        )
        return (
            f"Редакционная оценка: {editorial:.1f}/10\n"
            f"{user_line}\n"
            f"Итог: {editorial:.1f}/10* — нужно 3 подтверждённых отзыва"
        )
    blended, preliminary = blend_rating(editorial, user_average, user_count)
    marker = "*" if preliminary else ""
    return (
        f"Редакционная оценка: {editorial:.1f}/10\n"
        f"Пользовательская оценка: {max(0.0, min(10.0, float(user_average))):.1f}/10 ({user_count} отзывов)\n"
        f"Итог: {blended:.1f}/10{marker}"
    )


def rating_medal(position):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, "▫️")


def rating_entry(position, school, user_average, user_count):
    def n(value):
        return f"{value:.1f}".replace(".", ",")

    total_score, preliminary = school_total_score(school, user_average, user_count)
    score_suffix = f" · {user_count} подтверждённых отзывов" if user_count else ""
    if preliminary:
        score_suffix += "*"
    score_text = n(total_score)
    return (
        f"{rating_medal(position)} <b>{escape(school.name)}</b>\n"
        f"⭐ <b>{score_text}/10{score_suffix}</b>\n"
        f"Критерии:\n"
        f"преподаватели {n(school.teachers_score)} · практика {n(school.practice_score)} · "
        f"проверка {n(school.feedback_score)} · кураторы {n(school.curator_score)}\n"
        f"платформа {n(school.platform_score)} · нагрузка {n(school.workload_score)} · "
        f"организация обучения {n(school.organization_score)}"
    )


def teacher_criteria_text(stats):
    if not any(count for _, count in stats.values()):
        return "📊 <b>По отзывам учеников</b>\nОценки отдельных аспектов появятся после одобренных отзывов."
    lines = ["📊 <b>Оценки учеников по критериям</b>", "Шкала 1–10"]
    for field, label in TEACHER_CRITERIA:
        average, count = stats.get(field, (None, 0))
        if count:
            lines.append(f"{escape(label)} — <b>{float(average):.1f}/10</b> · {count} оценок")
    return "\n".join(lines)


def teacher_card(teacher, school, criteria_stats=None):
    social = teacher.social_url or "Публичная ссылка на соцсеть не подтверждена"
    return (
        f"👩‍🏫 {teacher.name}\n\n"
        f"🏫 Школа: {school.name}\n"
        f"📚 Предмет: {teacher.subject}\n\n"
        f"⭐ {teacher_rating_text(criteria_stats or {})}\n\n"
        f"{teacher_criteria_text(criteria_stats or {})}\n\n"
        f"👤 О преподавателе\n{teacher_description(teacher.description)}\n\n"
        f"💬 Отзывы и сигналы\n{teacher.review_summary}\n\n"
        f"📱 Соцсеть\n{social}\n\n"
        f"🔎 Источник\n{teacher.source_url}\n"
        f"Тип данных: {teacher.evidence_type}"
    )


def review_score_keyboard():
    scores = range(1, 11)

    def label(score):
        return f"{score} / 10"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label(score), callback_data=f"review_score:{score}") for score in scores[index:index + 5]]
        for index in range(0, len(scores), 5)
    ] + [
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def criterion_score_keyboard():
    scores = range(1, 11)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(score), callback_data=f"criterion_score:{score}") for score in scores[index:index + 5]]
        for index in range(0, len(scores), 5)
    ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]])


def review_verification_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Да, прикрепить подтверждение", callback_data="review_proof:yes")],
        [InlineKeyboardButton(text="Пропустить", callback_data="review_proof:no")],
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def criterion_buttons(school_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"review_criterion_select:{school_id}:{field}")]
            for field, label, _ in CRITERIA
        ] + [
            [InlineKeyboardButton(text="← Карточка школы", callback_data=f"school:{school_id}")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
        ]
    )


async def active_schools(session_factory):
    async with session_factory() as session:
        return (
            await session.execute(select(School).where(School.is_active == True).order_by(School.name))
        ).scalars().all()


async def build_quiz_result(session_factory, profile: QuizProfile):
    rows = await active_schools(session_factory)
    ranked = [
        (score, reasons, school)
        for school in rows
        for score, reasons in [school_score(school, profile)]
        if score >= 0
    ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    top = ranked[:3]
    subject_name = next((item for item in SUBJECTS if item.lower() == profile.subject), profile.subject.title())
    if not top:
        text = (
            f"🎯 <b>Подбор по предмету: {escape(subject_name)}</b>\n\n"
            "По этому предмету пока нет подходящих школ в каталоге. Загляни в общий рейтинг или попробуй другой предмет."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
        ])
        return text, keyboard
    top_school_ids = [school.id for _, _, school in top]
    async with session_factory() as session:
        subject_courses = (await session.execute(
            select(Course).where(Course.subject == subject_name, Course.is_active == True)
        )).scalars().all()
        subject_teachers = (await session.execute(
            select(Teacher).where(
                Teacher.school_id.in_(top_school_ids),
                Teacher.subject.in_(teacher_subject_variants(subject_name)),
                Teacher.is_active == True,
            )
        )).scalars().all()
        teacher_lines = {}
        for school_id in top_school_ids:
            school_teachers = [t for t in subject_teachers if t.school_id == school_id]
            teacher_lines[school_id] = None
            if not school_teachers:
                continue
            rated = []
            for teacher in school_teachers:
                stats = await approved_teacher_criteria_stats(session, school_id, teacher.id)
                average, _count = teacher_rating_from_criteria(stats)
                if average is not None:
                    rated.append((average, teacher.name))
            if rated:
                rated.sort(reverse=True)
                best_average, best_name = rated[0]
                extra = f" (лучший из {len(school_teachers)})" if len(school_teachers) > 1 else ""
                teacher_lines[school_id] = f"👩‍🏫 {best_name} — {best_average:.1f}/10{extra}"
            else:
                names = ", ".join(t.name for t in school_teachers[:3])
                teacher_lines[school_id] = f"👩‍🏫 {names} — оценки пока формируются"
    course_by_school = {course.school_id: course for course in subject_courses}
    lines = []
    for index, (score, reasons, school) in enumerate(top, 1):
        reason_text = ", ".join(reasons) if reasons else "хорошее совпадение по анкете"
        course = course_by_school.get(school.id)
        price = course.price_text if course else school.price_text
        line = f"{index}. {school.name} — {score:.0f}% совпадение\nПочему: {reason_text}\n💸 {price}"
        if teacher_lines.get(school.id):
            line += f"\n{teacher_lines[school.id]}"
        lines.append(line)
    text = (
        f"🎯 <b>Подбор по предмету: {escape(subject_name)}</b>\n\n"
        "Мы отобрали школы по твоим ответам. Открой карточку курса: там формат, тарифы и преподаватели именно по предмету.\n\n"
        + "\n\n".join(escape(line) for line in lines)
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"Курс: {school.name}",
                callback_data=f"course:{course_by_school[school.id].id}" if school.id in course_by_school else f"school:{school.id}",
            )]
            for _, _, school in top
        ]
        + [[InlineKeyboardButton(text="📰 Новости и разборы ЕГЭ", callback_data="channel")]]
        + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )
    return text, keyboard


def _proof_admin_copies(review) -> list:
    try:
        copies = json.loads(review.proof_admin_messages or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [tuple(item) for item in copies if isinstance(item, (list, tuple)) and len(item) == 2]


async def erase_review_proof(bot, review) -> int:
    """Forget the proof file and delete its copies in admin chats.

    Returns how many admin copies could not be deleted (Telegram only lets a bot
    delete its own messages younger than 48 hours). Only the ``verified`` flag stays.
    """
    failed = 0
    for chat_id, message_id in _proof_admin_copies(review):
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            failed += 1
    review.proof_file_id = None
    review.proof_file_type = None
    review.proof_delete_after = None
    review.proof_admin_messages = None
    return failed


PROOF_MANUAL_DELETE_NOTE = (
    "\n\nКопию файла в этом чате бот удалить не смог (прошло больше 48 часов). Удали сообщение с файлом вручную."
)


async def approved_reviews_text(session, school_id, teacher_id=None, criterion=None):
    query = select(Review).where(Review.school_id == school_id, Review.moderation_status == "approved")
    if teacher_id is None:
        query = query.where(Review.teacher_id.is_(None))
    else:
        query = query.where(Review.teacher_id == teacher_id)
    query = query.where(Review.criterion == criterion)
    reviews = (await session.execute(query.order_by(Review.created_at.desc()).limit(5))).scalars().all()
    if not reviews:
        return ""
    lines = ["\n\n💬 Отзывы пользователей"]
    for review in reviews:
        parts = [f"⭐ {review.score:.1f}/10 · {'✅ подтверждённый' if review.verified else 'без подтверждения'}"]
        if review.text_positive:
            parts.append(f"Плюсы: {escape(review.text_positive)}")
        if review.text_negative:
            parts.append(f"Минусы: {escape(review.text_negative)}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


async def approved_review_stats(session, school_id, teacher_id=None, criterion=None):
    query = select(func.avg(Review.score), func.count(Review.id)).where(
        Review.school_id == school_id,
        Review.moderation_status == "approved",
        Review.verified == True,
    )
    if teacher_id is None:
        query = query.where(Review.teacher_id.is_(None))
    else:
        query = query.where(Review.teacher_id == teacher_id)
    query = query.where(Review.criterion == criterion)
    average, count = (await session.execute(query)).one()
    return (float(average) if average is not None else None, int(count or 0))


async def approved_school_criteria_stats(session, school_id):
    values = {field: [] for field, _, _ in CRITERIA}
    dedicated = (await session.execute(select(Review).where(
        Review.school_id == school_id,
        Review.teacher_id.is_(None),
        Review.criterion.is_not(None),
        Review.moderation_status == "approved",
        Review.verified == True,
    ))).scalars().all()
    for review in dedicated:
        criterion = LEGACY_CRITERIA_KEYS.get(review.criterion, review.criterion)
        if criterion in values:
            values[criterion].append(review.score)
    overall = (await session.execute(select(Review).where(
        Review.school_id == school_id,
        Review.teacher_id.is_(None),
        Review.criterion.is_(None),
        Review.moderation_status == "approved",
        Review.verified == True,
    ))).scalars().all()
    for review in overall:
        try:
            scores = json.loads(review.criteria_json or "{}")
        except json.JSONDecodeError:
            scores = {}
        for field, score in scores.items():
            field = LEGACY_CRITERIA_KEYS.get(field, field)
            if field in values:
                values[field].append(float(score))
    return {field: (sum(items) / len(items) if items else None, len(items)) for field, items in values.items()}


async def approved_teacher_criteria_stats(session, school_id, teacher_id):
    values = {field: [] for field, _ in TEACHER_CRITERIA}
    reviews = (await session.execute(select(Review).where(
        Review.school_id == school_id,
        Review.teacher_id == teacher_id,
        Review.criterion.is_(None),
        Review.moderation_status == "approved",
        Review.verified == True,
    ))).scalars().all()
    for review in reviews:
        try:
            scores = json.loads(review.criteria_json or "{}")
        except json.JSONDecodeError:
            scores = {}
        for field, score in scores.items():
            if field in values:
                values[field].append(float(score))
    return {field: (sum(items) / len(items) if items else None, len(items)) for field, items in values.items()}


async def setup(dp: Dispatcher, session_factory, settings: Settings):
    async def track(telegram_id: int, event_name: str, metadata=None):
        async with session_factory() as session:
            session.add(Event(
                telegram_id=telegram_id,
                event_name=event_name,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            ))
            await session.commit()

    async def review_guard(telegram_id: int, school_id: int, teacher_id=None, criterion=None):
        async with session_factory() as session:
            user = await get_or_create_user(session, telegram_id)
            query = select(Review).where(
                Review.user_id == user.id,
                Review.school_id == school_id,
                Review.teacher_id == teacher_id,
                Review.criterion == criterion,
            ).order_by(Review.created_at.desc())
            existing = (await session.execute(query)).scalars().first()
            if existing:
                return "Ты уже отправлял отзыв об этом объекте. Повторные оценки не учитываются, чтобы защитить рейтинг от накрутки."
            since = datetime.utcnow() - timedelta(hours=24)
            recent_count = await session.scalar(
                select(func.count(Review.id)).where(Review.user_id == user.id, Review.created_at >= since)
            )
            if int(recent_count or 0) >= 3:
                return "За сутки можно отправить не больше трёх отзывов. Это ограничение защищает рейтинг от массовой накрутки."
        return None

    async def notify_review_for_moderation(bot: Bot, review_id: int):
        async with session_factory() as session:
            review = await session.get(Review, review_id)
            if not review:
                return
            school = await session.get(School, review.school_id)
            teacher = await session.get(Teacher, review.teacher_id) if review.teacher_id else None
        target = f"преподавателе {teacher.name}" if teacher else f"школе {school.name}"
        if review.criterion:
            target += f" · критерий «{REVIEW_CRITERIA_BY_KEY.get(review.criterion, review.criterion)}»"
        positive = review.text_positive or "—"
        negative = review.text_negative or "—"
        proof = "приложено" if review.proof_file_id else "не приложено"
        try:
            criteria = json.loads(review.criteria_json or "{}")
        except json.JSONDecodeError:
            criteria = {}
        criteria_text = ""
        if criteria:
            criteria_text = "\n\nОценки критериев:\n" + "\n".join(
                f"{REVIEW_CRITERIA_BY_KEY.get(key, key)}: {float(value):g}/10" for key, value in criteria.items()
            ) + "\n\n"
        delete_note = ""
        if review.proof_file_id:
            delete_note = "\nФайл удалится сразу после решения (одобрить, подтвердить или отклонить)."
            if review.proof_delete_after:
                delete_note += f" Если решения не будет, не позже {review.proof_delete_after.strftime('%d.%m.%Y')}."
        text = (
            f"Новый отзыв №{review.id} о {target}. Оценка: {review.score:.1f}/10\n\n"
            f"{criteria_text}"
            f"Понравилось:\n{positive}\n\n"
            f"Не понравилось:\n{negative}\n\n"
            f"Подтверждение обучения: {proof}{delete_note}\n"
            f"Одобрить отзыв: /approve_review {review.id}\n"
            f"Отклонить: /reject_review {review.id}"
        )
        if review.proof_file_id:
            text += f"\nПодтвердить обучение: /verify_review {review.id}"
        proof_copies = []
        for admin_id in settings.admin_id_set:
            await bot.send_message(admin_id, text)
            if review.proof_file_id:
                caption = f"Файл подтверждения для отзыва №{review.id}"
                if review.proof_file_type == "photo":
                    sent = await bot.send_photo(admin_id, review.proof_file_id, caption=caption)
                else:
                    sent = await bot.send_document(admin_id, review.proof_file_id, caption=caption)
                proof_copies.append([admin_id, sent.message_id])
        if proof_copies:
            async with session_factory() as session:
                stored = await session.get(Review, review_id)
                if stored:
                    stored.proof_admin_messages = json.dumps(proof_copies)
                    await session.commit()

    @dp.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        payload = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
        if payload == "delete_data":
            await state.clear()
            await message.answer(
                "🔐 <b>Твои данные</b>\n\n"
                "Можно удалить профиль в ЕГЭ Мэтче, отправленные отзывы, оценки по критериям, ссылки на подтверждения и историю действий в боте. "
                "После удаления вклад этих отзывов исчезнет из пользовательской части рейтинга.\n\n"
                "Сообщения в самом чате Telegram управляются приложением Telegram и в базу ЕГЭ Мэтча не входят.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Удалить мои данные", callback_data="delete_data_request")],
                    [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                ]),
                parse_mode=ParseMode.HTML,
            )
            return
        await track(message.from_user.id, "start")
        async with session_factory() as session:
            await get_or_create_user(session, message.from_user.id)
        if payload.startswith("review_"):
            school_name = SCHOOL_BY_REVIEW_SLUG.get(payload.removeprefix("review_"))
            if school_name:
                async with session_factory() as session:
                    school = (await session.execute(select(School).where(
                        School.name == school_name,
                        School.is_active.is_(True),
                    ))).scalar_one_or_none()
                if school:
                    await state.clear()
                    await track(message.from_user.id, "review_deeplink_opened", {"school_id": school.id})
                    await message.answer(
                        f"Отзыв о школе «{school.name}»\n\nОцени весь опыт обучения: занятия, практику, проверку работ, поддержку, платформу и организацию курса.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Оставить отзыв о школе", callback_data=f"review_school:{school.id}")],
                            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                        ]),
                    )
                    return
        if payload.startswith("q_"):
            profile = profile_from_payload(payload)
            if profile:
                await state.clear()
                await track(message.from_user.id, "quiz_started", {"source": "site"})
                text, keyboard = await build_quiz_result(session_factory, profile)
                await track(message.from_user.id, "quiz_completed", {"subject": profile.subject, "source": "site"})
                await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                return
        await message.answer(
            "Привет! Я ЕГЭ Мэтч — помогу выбрать школу и преподавателя для ЕГЭ. Здесь можно пройти подбор, посмотреть оценки по критериям, сравнить школы и преподавателей и оставить свой отзыв.",
            reply_markup=menu(),
        )

    async def show_data_controls(message: Message, edit: bool = False):
        text_value = (
            "🔐 <b>Твои данные</b>\n\n"
            "Здесь можно удалить профиль в ЕГЭ Мэтче, отправленные отзывы, оценки по критериям, ссылки на подтверждения и историю действий в боте. "
            "После удаления вклад этих отзывов исчезнет из пользовательской части рейтинга.\n\n"
            "Сообщения в самом чате Telegram управляются приложением Telegram и в базу ЕГЭ Мэтча не входят."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Удалить мои данные", callback_data="delete_data_request")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
        ])
        if edit:
            await message.edit_text(text_value, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            await message.answer(text_value, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    @dp.message(Command("delete_data"))
    async def delete_data_command(message: Message, state: FSMContext):
        await state.clear()
        await show_data_controls(message)

    @dp.callback_query(F.data == "my_data")
    async def my_data(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await show_data_controls(call.message, edit=True)
        await call.answer()

    @dp.callback_query(F.data == "delete_data_request")
    async def delete_data_request(call: CallbackQuery):
        await call.message.edit_text(
            "<b>Удалить все данные без возможности восстановления?</b>\n\n"
            "Будут удалены профиль, отзывы, поставленные оценки, ссылки на подтверждения и история действий. "
            "Если позже снова открыть бота, будет создан новый пустой профиль.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Да, удалить всё", callback_data="delete_data_confirm")],
                [InlineKeyboardButton(text="Отмена", callback_data="menu")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data == "delete_data_confirm")
    async def delete_data_confirm(call: CallbackQuery, state: FSMContext):
        await state.clear()
        async with session_factory() as session:
            result = await delete_user_data(session, call.from_user.id)
        if result["users"] or result["reviews"] or result["events"]:
            text_value = "Данные удалены. Профиль, отзывы, оценки, ссылки на подтверждения и история действий больше не хранятся в базе ЕГЭ Мэтча."
        else:
            text_value = "В базе ЕГЭ Мэтча уже нет данных, связанных с твоим Telegram-профилем."
        await call.message.edit_text(
            text_value,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Начать заново", callback_data="menu")],
            ]),
        )
        await call.answer("Готово")

    @dp.callback_query(F.data == "menu")
    async def to_menu(call: CallbackQuery, state: FSMContext):
        await state.clear()
        try:
            await call.message.edit_text("Главное меню", reply_markup=menu())
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error):
                raise
        await call.answer()

    @dp.callback_query(F.data == "review_school_menu")
    async def review_school_menu(call: CallbackQuery):
        rows = await active_schools(session_factory)
        await call.message.edit_text("💬 Отзыв о школе\n\nВыбери школу:", reply_markup=school_buttons(rows, "review_school_select"))
        await call.answer()

    @dp.callback_query(F.data == "quiz_back")
    async def quiz_back(call: CallbackQuery, state: FSMContext):
        current = await state.get_state()
        data = await state.get_data()
        if current == "Quiz:subject" or current is None:
            await state.clear()
            await call.message.edit_text("Главное меню", reply_markup=menu())
        elif current == "Quiz:budget":
            await state.set_state(Quiz.subject)
            await call.message.edit_text("Вопрос 1 из 8 · Какой предмет сдаёшь?", reply_markup=options([(item, item.lower()) for item in SUBJECTS], "subject"))
        elif current == "Quiz:current_level":
            await state.set_state(Quiz.budget)
            await call.message.edit_text("Вопрос 2 из 8 · Сколько готов тратить на подготовку в месяц?", reply_markup=options([("До 3 000 ₽", "3000"), ("3 000–5 000 ₽", "5000"), ("5 000–8 000 ₽", "8000"), ("Больше 8 000 ₽", "12000"), ("Пока не определился", "0")], "budget"))
        elif current == "Quiz:target":
            await state.set_state(Quiz.current_level)
            await call.message.edit_text("Вопрос 3 из 8 · Как оцениваешь свои знания по предмету сейчас?", reply_markup=options([("Начинаю почти с нуля", "low"), ("Что-то знаю, нужна система", "middle"), ("База хорошая, хочу усилить результат", "high")], "level"))
        elif current == "Quiz:curator":
            await state.set_state(Quiz.target)
            await call.message.edit_text("Вопрос 4 из 8 · На какой балл ЕГЭ ориентируешься?", reply_markup=options(target_options((await state.get_data()).get("subject")), "target"))
        elif current == "Quiz:workload":
            await state.set_state(Quiz.curator)
            await call.message.edit_text("Вопрос 5 из 8 · Нужен ли тебе куратор, который следит за прогрессом?", reply_markup=options([("Справлюсь сам, куратор не нужен", "1"), ("Иногда хочу спросить куратора", "2"), ("Нужен регулярный контроль куратора", "3"), ("Без куратора я всё откладываю", "4")], "curator"))
        elif current == "Quiz:first_priority":
            await state.set_state(Quiz.workload)
            await call.message.edit_text("Вопрос 6 из 8 · Какой темп подготовки тебе подходит?", reply_markup=options([("Небольшая нагрузка, без перегруза", "1"), ("Умеренный темп", "2"), ("Готов заниматься много", "3"), ("Максимум практики ради результата", "4")], "workload"))
        elif current == "Quiz:second_priority":
            await state.set_state(Quiz.first_priority)
            await call.message.edit_text("Вопрос 7 из 8 · Что для тебя важнее всего? Выбери главный приоритет.", reply_markup=priority_keyboard())
        elif current == "Quiz:control":
            await state.set_state(Quiz.second_priority)
            await call.message.edit_text("Дополнительный приоритет · Можно выбрать ещё один пункт.", reply_markup=priority_keyboard(data.get("first_priority")))
        await call.answer()

    @dp.callback_query(F.data == "review_teacher_menu")
    async def review_teacher_menu(call: CallbackQuery):
        async with session_factory() as session:
            subjects = (await session.execute(
                select(Teacher.subject).where(Teacher.is_active == True).distinct().order_by(Teacher.subject)
            )).scalars().all()
        await call.message.edit_text(
            "💬 Отзыв о преподавателе\n\nСначала выбери предмет:",
            reply_markup=review_teacher_subject_buttons(subjects),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("review_school_select:"))
    async def review_school_select(call: CallbackQuery, state: FSMContext):
        school_id = int(call.data.split(":")[1])
        await review_school_start(call, state, school_id=school_id)

    @dp.callback_query(F.data.startswith("review_criteria:"))
    async def review_criteria(call: CallbackQuery):
        school_id = int(call.data.split(":")[1])
        await call.message.edit_text("⭐ Оцени отдельный аспект школы:\n\nВыбери критерий:", reply_markup=criterion_buttons(school_id))
        await call.answer()

    @dp.callback_query(F.data.startswith("review_criterion_select:"))
    async def review_criterion_select(call: CallbackQuery, state: FSMContext):
        _, school_id, criterion = call.data.split(":", 2)
        await review_school_start(call, state, school_id=int(school_id), criterion=criterion)

    @dp.callback_query(F.data.startswith("review_teacher_subject:"))
    async def global_teacher_subject_review(call: CallbackQuery):
        subject = subject_from_token(call.data.split(":", 1)[1])
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher.id, Teacher.name, Teacher.subject, School.name.label("school_name"))
                .join(School, School.id == Teacher.school_id)
                .where(Teacher.subject.in_(teacher_subject_variants(subject)), Teacher.is_active == True)
                .order_by(Teacher.name)
            )).all()
        await call.message.edit_text(
            f"💬 Отзыв о преподавателе · {subject}\n\nВыбери преподавателя:",
            reply_markup=review_teacher_buttons(rows),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("review_teacher_pick:"))
    async def review_teacher_pick(call: CallbackQuery, state: FSMContext):
        teacher_id = int(call.data.split(":")[1])
        await review_teacher_start(call, state, teacher_id=teacher_id)

    @dp.callback_query(F.data.startswith("review_school:"))
    async def review_school_start(call: CallbackQuery, state: FSMContext, school_id=None, criterion=None):
        school_id = school_id or int(call.data.split(":")[1])
        blocked = await review_guard(call.from_user.id, school_id, criterion=criterion)
        if blocked:
            await call.message.edit_text(blocked, reply_markup=menu())
            await call.answer()
            return
        await state.update_data(review_school_id=school_id, review_teacher_id=None, review_criterion=criterion, review_kind="school")
        if criterion is None:
            await state.update_data(review_criteria_scores={}, review_criteria_index=0)
            await state.set_state(ReviewForm.criterion_score)
            await call.message.edit_text(
                "Сначала оцени критерии школы по очереди.\n\n"
                "1/7 · Преподаватели\nВыбери оценку от 1 до 10:",
                reply_markup=criterion_score_keyboard(),
            )
        else:
            await state.set_state(ReviewForm.score)
            subject = f"критерий «{CRITERIA_BY_KEY[criterion]}»"
            await call.message.edit_text(f"Оцени {subject} от 1 до 10. Отзыв будет опубликован только после модерации.", reply_markup=review_score_keyboard())
        await call.answer()

    @dp.callback_query(F.data.startswith("review_teacher:"))
    async def review_teacher_start(call: CallbackQuery, state: FSMContext, teacher_id=None):
        teacher_id = teacher_id or int(call.data.split(":")[1])
        async with session_factory() as session:
            teacher = await session.get(Teacher, teacher_id)
        blocked = await review_guard(call.from_user.id, teacher.school_id, teacher_id, criterion=None)
        if blocked:
            await call.message.edit_text(blocked, reply_markup=menu())
            await call.answer()
            return
        await state.update_data(
            review_school_id=teacher.school_id,
            review_teacher_id=teacher_id,
            review_criterion=None,
            review_kind="teacher",
            review_criteria_scores={},
            review_criteria_index=0,
        )
        await state.set_state(ReviewForm.criterion_score)
        await call.message.edit_text(
            f"Сначала оцени преподавателя {teacher.name} по пяти понятным аспектам.\n\n"
            "1/5 · Объяснение материала\nВыбери оценку от 1 до 10:",
            reply_markup=criterion_score_keyboard(),
        )
        await call.answer()

    @dp.callback_query(ReviewForm.score, F.data.startswith("review_score:"))
    async def review_score(call: CallbackQuery, state: FSMContext):
        await state.update_data(review_score=float(call.data.split(":")[1]))
        await state.set_state(ReviewForm.positive)
        await call.message.edit_text("Что было полезно или понравилось? Напиши одним сообщением. Можно написать «пропустить».")
        await call.answer()

    @dp.callback_query(ReviewForm.criterion_score, F.data.startswith("criterion_score:"))
    async def review_criterion_score(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        index = int(data.get("review_criteria_index", 0))
        scores = dict(data.get("review_criteria_scores", {}))
        criteria = TEACHER_CRITERIA if data.get("review_kind") == "teacher" else CRITERIA
        field, label, *_ = criteria[index]
        scores[field] = float(call.data.split(":")[1])
        if index + 1 < len(criteria):
            next_field, next_label, *_ = criteria[index + 1]
            await state.update_data(review_criteria_scores=scores, review_criteria_index=index + 1)
            await call.message.edit_text(
                f"{index + 2}/{len(criteria)} · {next_label}\nВыбери оценку от 1 до 10:",
                reply_markup=criterion_score_keyboard(),
            )
        else:
            if data.get("review_kind") == "teacher":
                await state.update_data(
                    review_criteria_scores=scores,
                    review_score=sum(scores.values()) / len(scores),
                )
                await state.set_state(ReviewForm.positive)
                await call.message.edit_text(
                    "Все пять критериев оценены. Итог посчитаем автоматически как их среднее.\n\n"
                    "Что было полезно или понравилось? Напиши одним сообщением. Можно написать «пропустить»."
                )
            else:
                await state.update_data(review_criteria_scores=scores)
                await state.set_state(ReviewForm.score)
                await call.message.edit_text(
                    "Все критерии оценены.\n\nТеперь поставь общую оценку школе от 1 до 10:",
                    reply_markup=review_score_keyboard(),
                )
        await call.answer()

    @dp.message(ReviewForm.positive)
    async def review_positive(message: Message, state: FSMContext):
        await state.update_data(review_positive="" if message.text.lower().strip() == "пропустить" else message.text.strip())
        await state.set_state(ReviewForm.negative)
        await message.answer("Что было неудобно или не понравилось? Напиши одним сообщением. Можно написать «пропустить».")

    @dp.message(ReviewForm.negative)
    async def review_negative(message: Message, state: FSMContext):
        data = await state.get_data()
        negative = "" if message.text.lower().strip() == "пропустить" else message.text.strip()
        blocked = await review_guard(
            message.from_user.id,
            data["review_school_id"],
            data.get("review_teacher_id"),
            data.get("review_criterion"),
        )
        if blocked:
            await state.clear()
            await message.answer(blocked, reply_markup=menu())
            return
        async with session_factory() as session:
            user = await get_or_create_user(session, message.from_user.id)
            review = Review(
                user_id=user.id,
                school_id=data["review_school_id"],
                teacher_id=data.get("review_teacher_id"),
                criterion=data.get("review_criterion"),
                criteria_json=json.dumps(data.get("review_criteria_scores", {}), ensure_ascii=False),
                score=data["review_score"],
                text_positive=data.get("review_positive", ""),
                text_negative=negative,
            )
            session.add(review)
            await session.flush()
            for criterion, score in data.get("review_criteria_scores", {}).items():
                session.add(ReviewCriterionScore(
                    review_id=review.id,
                    criterion=LEGACY_CRITERIA_KEYS.get(criterion, criterion),
                    score=float(score),
                ))
            await session.commit()
            review_id = review.id
            school = await session.get(School, data["review_school_id"])
            teacher = await session.get(Teacher, data["review_teacher_id"]) if data.get("review_teacher_id") else None
        await state.update_data(review_id=review_id)
        await state.set_state(ReviewForm.verification)
        await track(message.from_user.id, "review_submitted", {"review_id": review_id})
        await message.answer(
            "Отзыв сохранён.\n\n"
            "Можно подтвердить, что ты действительно учился в этой школе. Это необязательно. "
            "Подтверждённые отзывы влияют на оценку, отзывы без подтверждения публикуются с пометкой и в оценку не входят.\n\n"
            "После выбора «прикрепить» или «пропустить» отзыв попадёт в очередь.",
            reply_markup=review_verification_keyboard(),
        )

    @dp.callback_query(ReviewForm.verification, F.data == "review_proof:no")
    async def review_proof_skip(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await notify_review_for_moderation(call.bot, int(data["review_id"]))
        await state.clear()
        await call.message.edit_text("Хорошо, отзыв отправлен без подтверждения. После проверки он появится с пометкой и не повлияет на оценку.", reply_markup=menu())
        await call.answer()

    @dp.callback_query(ReviewForm.verification, F.data == "review_proof:yes")
    async def review_proof_start(call: CallbackQuery, state: FSMContext):
        await call.message.edit_text(
            "Пришли одним сообщением скриншот или фото, на котором видно только название школы или курса и дату. "
            "Подойдёт личный кабинет, чек или договор.\n\n"
            "⚠️ Перед отправкой закрой:\n"
            "• ФИО и фото профиля\n"
            "• e-mail и телефон\n"
            "• адрес\n"
            "• номер договора, заказа и банковской карты\n"
            "• любые другие личные данные\n\n"
            "Файл не публикуется, его увидит только модератор. После проверки мы сразу удалим файл, "
            "в базе останется только отметка «подтверждён». Своё сообщение с файлом в этом чате можешь удалить сам.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Пропустить", callback_data="review_proof:no")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
        )
        await call.answer()

    async def save_review_proof(message: Message, file_id: str, file_type: str, state: FSMContext):
        data = await state.get_data()
        review_id = data.get("review_id")
        if not review_id:
            await message.answer("Не нашёл отзыв для подтверждения. Попробуй отправить отзыв ещё раз.", reply_markup=menu())
            await state.clear()
            return
        async with session_factory() as session:
            review = await session.get(Review, int(review_id))
            if not review:
                await message.answer("Не нашёл отзыв для подтверждения.", reply_markup=menu())
                await state.clear()
                return
            review.proof_file_id = file_id
            review.proof_file_type = file_type
            review.proof_consent = True
            review.proof_delete_after = datetime.utcnow() + timedelta(days=7)
            await session.commit()
            school = await session.get(School, review.school_id)
            teacher = await session.get(Teacher, review.teacher_id) if review.teacher_id else None
        await notify_review_for_moderation(message.bot, review.id)
        await state.clear()
        await message.answer("Подтверждение получено. Отзыв на проверке, файл удалим сразу после решения.", reply_markup=menu())

    @dp.message(ReviewForm.verification, F.photo)
    async def review_proof_photo(message: Message, state: FSMContext):
        await save_review_proof(message, message.photo[-1].file_id, "photo", state)

    @dp.message(ReviewForm.verification, F.document)
    async def review_proof_document(message: Message, state: FSMContext):
        await save_review_proof(message, message.document.file_id, "document", state)

    @dp.message(ReviewForm.verification)
    async def review_proof_invalid(message: Message):
        await message.answer("Отправь фото или файл. Можно также нажать «Пропустить».")

    @dp.message(Command("approve_review"))
    async def approve_review(message: Message):
        if message.from_user.id not in settings.admin_id_set:
            return
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Формат: /approve_review ID")
            return
        async with session_factory() as session:
            review = await session.get(Review, int(parts[1]))
            if not review:
                await message.answer("Отзыв не найден.")
                return
            review.moderation_status = "approved"
            failed = await erase_review_proof(message.bot, review)
            await session.commit()
        await message.answer("Отзыв опубликован." + (PROOF_MANUAL_DELETE_NOTE if failed else ""))

    @dp.message(Command("verify_review"))
    async def verify_review(message: Message):
        if message.from_user.id not in settings.admin_id_set:
            return
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Формат: /verify_review ID")
            return
        async with session_factory() as session:
            review = await session.get(Review, int(parts[1]))
            if not review:
                await message.answer("Отзыв не найден.")
                return
            if not review.proof_file_id:
                await message.answer("У этого отзыва нет приложенного подтверждения.")
                return
            review.verified = True
            failed = await erase_review_proof(message.bot, review)
            await session.commit()
        await message.answer(
            "Обучение подтверждено, файл удалён. Теперь можно опубликовать отзыв командой /approve_review ID"
            + (PROOF_MANUAL_DELETE_NOTE if failed else "")
        )

    @dp.message(Command("review"))
    async def read_review(message: Message):
        if message.from_user.id not in settings.admin_id_set:
            return
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Формат: /review ID")
            return
        async with session_factory() as session:
            review = await session.get(Review, int(parts[1]))
            if not review:
                await message.answer("Отзыв не найден.")
                return
            school = await session.get(School, review.school_id)
            teacher = await session.get(Teacher, review.teacher_id) if review.teacher_id else None
        target = f"преподавателе {teacher.name}" if teacher else f"школе {school.name}"
        proof = "приложено" if review.proof_file_id else "нет"
        try:
            criteria = json.loads(review.criteria_json or "{}")
        except json.JSONDecodeError:
            criteria = {}
        criteria_text = ""
        if criteria:
            criteria_text = "\n\nОценки критериев:\n" + "\n".join(
                f"{CRITERIA_BY_KEY.get(key, key)}: {float(value):g}/10" for key, value in criteria.items()
            )
        await message.answer(
            f"Отзыв №{review.id} о {target}\n"
            f"Оценка: {review.score:.1f}/10\n"
            f"Статус: {review.moderation_status}\n"
            f"Подтверждение: {proof}\n\n"
            f"{criteria_text}"
            f"Понравилось:\n{review.text_positive or '—'}\n\n"
            f"Не понравилось:\n{review.text_negative or '—'}"
        )

    @dp.message(Command("funnel"))
    async def funnel(message: Message):
        if message.from_user.id not in settings.admin_id_set:
            return
        since = datetime.utcnow() - timedelta(days=30)
        async with session_factory() as session:
            rows = (await session.execute(
                select(Event.event_name, func.count(Event.id), func.count(func.distinct(Event.telegram_id)))
                .where(Event.created_at >= since)
                .group_by(Event.event_name)
            )).all()
        labels = {
            "start": "Открыли бота",
            "quiz_started": "Начали подбор",
            "quiz_completed": "Завершили подбор",
            "school_opened": "Открыли карточку школы",
            "school_comparison_completed": "Завершили сравнение школ",
            "channel_cta_clicked": "Нажали на канал",
        }
        lines = ["Воронка за последние 30 дней", ""]
        for event_name, events_count, users_count in rows:
            lines.append(f"{labels.get(event_name, event_name)}: {users_count} пользователей · {events_count} действий")
        await message.answer("\n".join(lines) if rows else "За последние 30 дней событий нет.")

    @dp.message(Command("reject_review"))
    async def reject_review(message: Message):
        if message.from_user.id not in settings.admin_id_set:
            return
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("Формат: /reject_review ID")
            return
        async with session_factory() as session:
            review = await session.get(Review, int(parts[1]))
            if not review:
                await message.answer("Отзыв не найден.")
                return
            review.moderation_status = "rejected"
            failed = await erase_review_proof(message.bot, review)
            await session.commit()
        await message.answer("Отзыв отклонён." + (PROOF_MANUAL_DELETE_NOTE if failed else ""))

    @dp.callback_query(F.data == "quiz")
    async def quiz_start(call: CallbackQuery, state: FSMContext):
        await track(call.from_user.id, "quiz_started")
        await state.set_state(Quiz.subject)
        await call.message.edit_text(
            "Вопрос 1 из 8 · Какой предмет сдаёшь?",
            reply_markup=options([(item, item.lower()) for item in SUBJECTS], "subject"),
        )
        await call.answer()

    @dp.callback_query(Quiz.subject, F.data.startswith("subject:"))
    async def subject(call: CallbackQuery, state: FSMContext):
        await state.update_data(subject=call.data.split(":", 1)[1])
        await state.set_state(Quiz.budget)
        await call.message.edit_text(
            "Вопрос 2 из 8 · Сколько готов тратить на подготовку в месяц?",
            reply_markup=options(
                [
                    ("До 3 000 ₽", "3000"),
                    ("3 000–5 000 ₽", "5000"),
                    ("5 000–8 000 ₽", "8000"),
                    ("Больше 8 000 ₽", "12000"),
                    ("Пока не определился", "0"),
                ],
                "budget",
            ),
        )
        await call.answer()

    @dp.callback_query(Quiz.budget, F.data.startswith("budget:"))
    async def budget(call: CallbackQuery, state: FSMContext):
        await state.update_data(budget=int(call.data.split(":")[1]) or None)
        await state.set_state(Quiz.current_level)
        await call.message.edit_text(
            "Вопрос 3 из 8 · Как оцениваешь свои знания по предмету сейчас?",
            reply_markup=options(
                [
                    ("Начинаю почти с нуля", "low"),
                    ("Что-то знаю, нужна система", "middle"),
                    ("База хорошая, хочу усилить результат", "high"),
                ],
                "level",
            ),
        )
        await call.answer()

    @dp.callback_query(Quiz.current_level, F.data.startswith("level:"))
    async def current_level(call: CallbackQuery, state: FSMContext):
        await state.update_data(current_level=call.data.split(":")[1])
        await state.set_state(Quiz.target)
        await call.message.edit_text(
            "Вопрос 4 из 8 · На какой балл ЕГЭ ориентируешься?",
            reply_markup=options(target_options((await state.get_data()).get("subject")), "target"),
        )
        await call.answer()

    @dp.callback_query(Quiz.target, F.data.startswith("target:"))
    async def target(call: CallbackQuery, state: FSMContext):
        await state.update_data(target=int(call.data.split(":")[1].replace("+", "")))
        await state.set_state(Quiz.curator)
        await call.message.edit_text(
            "Вопрос 5 из 8 · Нужен ли тебе куратор, который следит за прогрессом?",
            reply_markup=options(
                [
                    ("Справлюсь сам, куратор не нужен", "1"),
                    ("Иногда хочу спросить куратора", "2"),
                    ("Нужен регулярный контроль куратора", "3"),
                    ("Без куратора я всё откладываю", "4"),
                ],
                "curator",
            ),
        )
        await call.answer()

    @dp.callback_query(Quiz.curator, F.data.startswith("curator:"))
    async def curator(call: CallbackQuery, state: FSMContext):
        await state.update_data(curator=int(call.data.split(":")[1]))
        await state.set_state(Quiz.workload)
        await call.message.edit_text(
            "Вопрос 6 из 8 · Какой темп подготовки тебе подходит?",
            reply_markup=options(
                [
                    ("Небольшая нагрузка, без перегруза", "1"),
                    ("Умеренный темп", "2"),
                    ("Готов заниматься много", "3"),
                    ("Максимум практики ради результата", "4"),
                ],
                "workload",
            ),
        )
        await call.answer()

    @dp.callback_query(Quiz.workload, F.data.startswith("workload:"))
    async def workload(call: CallbackQuery, state: FSMContext):
        await state.update_data(workload=int(call.data.split(":")[1]))
        await state.set_state(Quiz.first_priority)
        await call.message.edit_text(
            "Вопрос 7 из 8 · Что для тебя важнее всего? Выбери главный приоритет.",
            reply_markup=priority_keyboard(),
        )
        await call.answer()

    @dp.callback_query(Quiz.first_priority, F.data.startswith("priority:"))
    async def first_priority(call: CallbackQuery, state: FSMContext):
        priority = call.data.split(":")[1]
        await state.update_data(first_priority=priority)
        await state.set_state(Quiz.second_priority)
        await call.message.edit_text(
            "Дополнительный приоритет · Можно выбрать ещё один пункт.",
            reply_markup=priority_keyboard(priority),
        )
        await call.answer()

    @dp.callback_query(Quiz.second_priority, F.data.startswith("priority:"))
    async def second_priority(call: CallbackQuery, state: FSMContext):
        priority = call.data.split(":")[1]
        await state.update_data(second_priority=None if priority == "none" else priority)
        await state.set_state(Quiz.control)
        await call.message.edit_text(
            "Вопрос 8 из 8 · Как у тебя с самодисциплиной в подготовке?",
            reply_markup=options(
                [
                    ("Отлично — планирую и делаю сам", "1"),
                    ("Хорошо, но нужны напоминания", "2"),
                    ("Слабо — нужны проверки и дедлайны", "3"),
                    ("Совсем никак без жёсткого контроля", "4"),
                ],
                "control",
            ),
        )
        await call.answer()

    @dp.callback_query(Quiz.control, F.data.startswith("control:"))
    async def control(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        priorities = tuple(
            value
            for value in (data.get("first_priority"), data.get("second_priority"))
            if value
        )
        profile = QuizProfile(
            subject=data["subject"],
            budget=data["budget"],
            current_level=data["current_level"],
            target=data["target"],
            curator_need=data["curator"],
            workload=data["workload"],
            control_need=int(call.data.split(":")[1]),
            priorities=priorities,
        )
        text, keyboard = await build_quiz_result(session_factory, profile)
        await state.clear()
        await track(call.from_user.id, "quiz_completed", {"subject": data.get("subject")})
        await call.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        await call.answer()

    @dp.callback_query(F.data == "schools")
    async def schools(call: CallbackQuery):
        rows = await active_schools(session_factory)
        await call.message.edit_text("📚 Каталог школ\n\nВыбери школу, чтобы открыть её карточку:", reply_markup=school_buttons(rows, "school"))
        await call.answer()

    @dp.callback_query(F.data == "courses")
    async def courses(call: CallbackQuery):
        async with session_factory() as session:
            subjects = (await session.execute(
                select(Course.subject).where(Course.is_active == True).distinct().order_by(Course.subject)
            )).scalars().all()
        await call.message.edit_text(
            "📚 <b>Найти курс по предмету</b>\n\n"
            "Выбери предмет — покажем, как он устроен в разных школах: формат, цена, поддержка и преподаватели. "
            "Так проще сравнить именно нужную подготовку, а не школу целиком.",
            reply_markup=course_subject_buttons(subjects),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_subject:"))
    async def course_subject(call: CallbackQuery):
        subject = subject_from_token(call.data.split(":", 1)[1])
        async with session_factory() as session:
            rows = (await session.execute(
                select(Course, School.name.label("school_name"))
                .join(School, School.id == Course.school_id)
                .where(Course.subject == subject, Course.is_active == True)
                .order_by(School.name)
            )).all()
        courses_with_school = []
        for course, school_name in rows:
            course.school_name = school_name
            courses_with_school.append(course)
        await call.message.edit_text(
            f"📚 Курсы ЕГЭ · {subject}\n\nВыбери вариант, чтобы увидеть формат, тарифы и преподавателей именно по предмету:",
            reply_markup=course_buttons(courses_with_school),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course:"))
    async def course(call: CallbackQuery):
        course_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            item = await session.get(Course, course_id)
            school = await session.get(School, item.school_id)
            teachers = (await session.execute(
                select(Teacher).where(
                    Teacher.school_id == item.school_id,
                    Teacher.subject.in_(teacher_subject_variants(item.subject)),
                    Teacher.is_active == True,
                ).order_by(Teacher.name)
            )).scalars().all()
        await track(call.from_user.id, "course_opened", {"course_id": course_id, "subject": item.subject})
        await call.message.edit_text(
            course_card(item, school, teachers),
            reply_markup=course_card_keyboard(item.id, item.source_url),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_section:"))
    async def course_section(call: CallbackQuery):
        _, course_id, section = call.data.split(":", 2)
        async with session_factory() as session:
            item = await session.get(Course, int(course_id))
        if section == "tariffs":
            text = f"💸 <b>Тарифы</b>\n\n{_course_tariffs_text(item)}\n\n🔎 Данные проверены: {item.verified_at.strftime('%d.%m.%Y') if item.verified_at else 'дата не указана'}"
        else:
            text = "Раздел недоступен. Вернись к карточке курса."
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Карточка курса", callback_data=f"course:{item.id}")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_teachers:"))
    async def course_teachers(call: CallbackQuery):
        course_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            item = await session.get(Course, course_id)
            rows = (await session.execute(
                select(Teacher).where(
                    Teacher.school_id == item.school_id,
                    Teacher.subject.in_(teacher_subject_variants(item.subject)),
                    Teacher.is_active == True,
                ).order_by(Teacher.name)
            )).scalars().all()
        if not rows:
            await call.message.edit_text(
                "В открытом каталоге школы нет подтверждённых профилей преподавателей по этому предмету. Открой официальный источник курса и проверь ведущего выбранного набора.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="← Карточка курса", callback_data=f"course:{course_id}")],
                    [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                ]),
            )
        else:
            await call.message.edit_text(
                f"👩‍🏫 Преподаватели · {item.subject}\n\nЭто найденные публичные профили школы. Перед покупкой проверь, ведёт ли преподаватель выбранный набор.",
                reply_markup=teacher_buttons(rows, item.school_id, include_compare=True),
            )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_compare:"))
    async def course_compare_start(call: CallbackQuery, state: FSMContext):
        first_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            first = await session.get(Course, first_id)
            rows = (await session.execute(
                select(Course, School.name.label("school_name"))
                .join(School, School.id == Course.school_id)
                .where(
                    Course.subject == first.subject,
                    Course.id != first.id,
                    Course.is_active == True,
                )
                .order_by(School.name)
            )).all()
        options_for_compare = []
        for item, school_name in rows:
            item.school_name = school_name
            options_for_compare.append(item)
        await state.update_data(course_first_id=first_id)
        await state.set_state(CourseCompare.second)
        await call.message.edit_text(
            f"⚖️ Сравнение курсов · {first.subject}\n\nВыбери курс другой школы:",
            reply_markup=course_buttons(options_for_compare, prefix="course_compare_second", exclude_id=first_id),
        )
        await call.answer()

    @dp.callback_query(CourseCompare.second, F.data.startswith("course_compare_second:"))
    async def course_compare_second(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        left_id = int(data["course_first_id"])
        right_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            left = await session.get(Course, left_id)
            right = await session.get(Course, right_id)
            left_school = await session.get(School, left.school_id)
            right_school = await session.get(School, right.school_id)
        await state.clear()
        await track(call.from_user.id, "course_comparison_completed", {"left_id": left_id, "right_id": right_id})
        await call.message.edit_text(
            course_compare_text(left, right, left_school, right_school),
            reply_markup=course_compare_keyboard(left.id, right.id),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_compare_result:"))
    async def course_compare_result(call: CallbackQuery):
        _, left_id, right_id = call.data.split(":", 2)
        async with session_factory() as session:
            left = await session.get(Course, int(left_id))
            right = await session.get(Course, int(right_id))
            left_school = await session.get(School, left.school_id)
            right_school = await session.get(School, right.school_id)
        await call.message.edit_text(
            course_compare_text(left, right, left_school, right_school),
            reply_markup=course_compare_keyboard(left.id, right.id),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("course_compare_section:"))
    async def course_compare_section(call: CallbackQuery):
        _, left_id, right_id, section = call.data.split(":", 3)
        async with session_factory() as session:
            left = await session.get(Course, int(left_id))
            right = await session.get(Course, int(right_id))
            left_school = await session.get(School, left.school_id)
            right_school = await session.get(School, right.school_id)
            left_teachers = (await session.execute(select(Teacher).where(
                Teacher.school_id == left.school_id,
                Teacher.subject.in_(teacher_subject_variants(left.subject)),
                Teacher.is_active == True,
            ).order_by(Teacher.name))).scalars().all()
            right_teachers = (await session.execute(select(Teacher).where(
                Teacher.school_id == right.school_id,
                Teacher.subject.in_(teacher_subject_variants(right.subject)),
                Teacher.is_active == True,
            ).order_by(Teacher.name))).scalars().all()
        await call.message.edit_text(
            course_compare_section_text(left, right, left_school, right_school, section, left_teachers, right_teachers),
            reply_markup=(
                course_compare_teachers_keyboard(left, right, left_school, right_school)
                if section == "teachers"
                else course_compare_keyboard(left.id, right.id)
            ),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("review_course_school:"))
    async def review_course_school(call: CallbackQuery, state: FSMContext):
        course_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            item = await session.get(Course, course_id)
        await review_school_start(call, state, school_id=item.school_id)

    @dp.callback_query(F.data.startswith("school:"))
    async def school(call: CallbackQuery):
        await track(call.from_user.id, "school_opened", {"school_id": int(call.data.split(":")[1])})
        async with session_factory() as session:
            item = await session.get(School, int(call.data.split(":")[1]))
            user_reviews = await approved_reviews_text(session, item.id)
            user_average, user_count = await approved_review_stats(session, item.id)
            criteria_stats = await approved_school_criteria_stats(session, item.id)
        await call.message.edit_text(school_overview(item, user_average, user_count) + user_reviews, reply_markup=card_keyboard(item.id), parse_mode=ParseMode.HTML)
        await call.answer()

    @dp.callback_query(F.data.startswith("school_section:"))
    async def school_section(call: CallbackQuery):
        _, school_id, section = call.data.split(":", 2)
        async with session_factory() as session:
            item = await session.get(School, int(school_id))
            criteria_stats = await approved_school_criteria_stats(session, item.id) if section == "criteria" else None
        await call.message.edit_text(
            school_section_text(item, section, criteria_stats),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Карточка школы", callback_data=f"school:{item.id}")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("teachers:"))
    async def teachers(call: CallbackQuery):
        school_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            school = await session.get(School, school_id)
            rows = (await session.execute(
                select(Teacher).where(Teacher.school_id == school_id, Teacher.is_active == True).order_by(Teacher.name)
            )).scalars().all()
        await call.message.edit_text(
            f"👩‍🏫 Преподаватели школы {school.name}\n"
            f"Публично найдено профилей: {len(rows)}\n\n"
            "Выбери преподавателя, чтобы открыть его карточку:",
            reply_markup=teacher_buttons(rows, school_id),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("teacher_compare:"))
    async def teacher_compare_start(call: CallbackQuery, state: FSMContext):
        school_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            subjects = (await session.execute(
                select(Teacher.subject).where(Teacher.school_id == school_id, Teacher.is_active == True).distinct().order_by(Teacher.subject)
            )).scalars().all()
        await state.update_data(school_id=school_id)
        await state.set_state(TeacherCompare.subject)
        await call.message.edit_text("⚖️ Сравнение преподавателей\n\nСначала выбери предмет:", reply_markup=teacher_subject_buttons(subjects, school_id))
        await call.answer()

    @dp.callback_query(TeacherCompare.subject, F.data.startswith("teacher_subject:"))
    async def teacher_compare_subject(call: CallbackQuery, state: FSMContext):
        _, school_id, subject = call.data.split(":", 2)
        subject = subject_from_token(subject)
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher).where(Teacher.school_id == int(school_id), Teacher.subject.in_(teacher_subject_variants(subject)), Teacher.is_active == True).order_by(Teacher.name)
            )).scalars().all()
        await state.update_data(school_id=int(school_id), subject=subject)
        await state.set_state(TeacherCompare.first)
        await call.message.edit_text("Выбери первого преподавателя для сравнения:", reply_markup=teacher_buttons(rows, int(school_id), include_compare=False))
        await call.answer()

    @dp.callback_query(TeacherCompare.first, F.data.startswith("teacher:"))
    async def teacher_compare_first(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        first_id = int(call.data.split(":")[1])
        if data.get("global_compare"):
            async with session_factory() as session:
                rows = (await session.execute(
                    select(Teacher.id, Teacher.name, Teacher.subject, School.name.label("school_name"))
                    .join(School, School.id == Teacher.school_id)
                    .where(Teacher.subject.in_(teacher_subject_variants(data["subject"])), Teacher.id != first_id, Teacher.is_active == True)
                    .order_by(Teacher.name)
                )).all()
            await state.update_data(first_id=first_id)
            await state.set_state(TeacherCompare.second)
            await call.message.edit_text("Теперь выбери второго преподавателя:", reply_markup=global_teacher_buttons(rows, first_id))
            await call.answer()
            return
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher).where(Teacher.school_id == data["school_id"], Teacher.subject.in_(teacher_subject_variants(data["subject"])), Teacher.id != first_id, Teacher.is_active == True).order_by(Teacher.name)
            )).scalars().all()
        await state.update_data(first_id=first_id)
        await state.set_state(TeacherCompare.second)
        await call.message.edit_text("Теперь выбери второго преподавателя:", reply_markup=teacher_buttons(rows, data["school_id"], include_compare=False))
        await call.answer()

    @dp.callback_query(TeacherCompare.second, F.data.startswith("teacher:"))
    async def teacher_compare_second(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if data.get("global_compare"):
            async with session_factory() as session:
                left = await session.get(Teacher, data["first_id"])
                right = await session.get(Teacher, int(call.data.split(":")[1]))
                left_school = await session.get(School, left.school_id)
                right_school = await session.get(School, right.school_id)
                left_stats = await approved_teacher_criteria_stats(session, left.school_id, left.id)
                right_stats = await approved_teacher_criteria_stats(session, right.school_id, right.id)
            left.school_name = left_school.name
            right.school_name = right_school.name
            await state.clear()
            await call.message.edit_text(
                teacher_compare_text(left, right, left_stats=left_stats, right_stats=right_stats),
                reply_markup=teacher_compare_keyboard(left, right),
            )
            await call.answer()
            return
        async with session_factory() as session:
            left = await session.get(Teacher, data["first_id"])
            right = await session.get(Teacher, int(call.data.split(":")[1]))
            school = await session.get(School, data["school_id"])
            left_stats = await approved_teacher_criteria_stats(session, left.school_id, left.id)
            right_stats = await approved_teacher_criteria_stats(session, right.school_id, right.id)
        await state.clear()
        await call.message.edit_text(
            teacher_compare_text(left, right, school, left_stats, right_stats),
            reply_markup=teacher_compare_keyboard(left, right, school.id),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("teacher:"))
    async def teacher(call: CallbackQuery):
        teacher_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            item = await session.get(Teacher, teacher_id)
            school = await session.get(School, item.school_id)
            user_reviews = await approved_reviews_text(session, school.id, item.id)
            criteria_stats = await approved_teacher_criteria_stats(session, school.id, item.id)
        await call.message.edit_text(
            teacher_card(item, school, criteria_stats) + user_reviews,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Оставить отзыв о преподавателе", callback_data=f"review_teacher:{item.id}")],
                [InlineKeyboardButton(text="← Все преподаватели", callback_data=f"teachers:{school.id}")],
                [InlineKeyboardButton(text="← Карточка школы", callback_data=f"school:{school.id}")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
        )
        await call.answer()

    @dp.callback_query(F.data == "compare")
    async def compare(call: CallbackQuery, state: FSMContext):
        rows = await active_schools(session_factory)
        await state.set_state(Compare.first)
        await call.message.edit_text("⚖️ Сравнение школ\n\nВыбери первую школу:", reply_markup=school_buttons(rows, "compare_first"))
        await call.answer()

    @dp.callback_query(F.data == "teacher_compare_menu")
    async def teacher_compare_menu(call: CallbackQuery, state: FSMContext):
        async with session_factory() as session:
            subjects = (await session.execute(
                select(Teacher.subject).where(Teacher.is_active == True).distinct().order_by(Teacher.subject)
            )).scalars().all()
        await state.set_state(TeacherCompare.subject)
        await state.update_data(global_compare=True)
        await call.message.edit_text("👩‍🏫 Сравнение преподавателей\n\nВыбери предмет — можно сравнить преподавателей из разных школ:", reply_markup=global_teacher_subject_buttons(subjects))
        await call.answer()

    @dp.callback_query(TeacherCompare.subject, F.data.startswith("global_teacher_subject:"))
    async def global_teacher_compare_subject(call: CallbackQuery, state: FSMContext):
        subject = subject_from_token(call.data.split(":", 1)[1])
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher.id, Teacher.name, Teacher.subject, School.name.label("school_name"))
                .join(School, School.id == Teacher.school_id)
                .where(Teacher.subject.in_(teacher_subject_variants(subject)), Teacher.is_active == True)
                .order_by(Teacher.name)
            )).all()
        await state.update_data(global_compare=True, subject=subject)
        await state.set_state(TeacherCompare.first)
        await call.message.edit_text("Выбери первого преподавателя:", reply_markup=global_teacher_buttons(rows))
        await call.answer()

    @dp.callback_query(F.data.startswith("teacher_compare_school:"))
    async def teacher_compare_school(call: CallbackQuery, state: FSMContext):
        school_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            subjects = (await session.execute(
                select(Teacher.subject).where(Teacher.school_id == school_id, Teacher.is_active == True).distinct().order_by(Teacher.subject)
            )).scalars().all()
        await state.update_data(school_id=school_id)
        await state.set_state(TeacherCompare.subject)
        await call.message.edit_text("Выбери предмет для сравнения:", reply_markup=teacher_subject_buttons(subjects, school_id))
        await call.answer()

    @dp.callback_query(F.data.startswith("compare_with:"))
    async def compare_with(call: CallbackQuery, state: FSMContext):
        first_id = int(call.data.split(":")[1])
        rows = [row for row in await active_schools(session_factory) if row.id != first_id]
        await state.update_data(first_id=first_id)
        await state.set_state(Compare.second)
        await call.message.edit_text("Первая школа выбрана. С какой сравнить?", reply_markup=school_buttons(rows, "compare_second"))
        await call.answer()

    @dp.callback_query(Compare.first, F.data.startswith("compare_first:"))
    async def compare_first(call: CallbackQuery, state: FSMContext):
        first_id = int(call.data.split(":")[1])
        rows = [row for row in await active_schools(session_factory) if row.id != first_id]
        await state.update_data(first_id=first_id)
        await state.set_state(Compare.second)
        await call.message.edit_text("Теперь выбери вторую школу:", reply_markup=school_buttons(rows, "compare_second"))
        await call.answer()

    @dp.callback_query(Compare.second, F.data.startswith("compare_second:"))
    async def compare_second(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        async with session_factory() as session:
            left = await session.get(School, int(data["first_id"]))
            right = await session.get(School, int(call.data.split(":")[1]))
            left_user_average, left_user_count = await approved_review_stats(session, left.id)
            right_user_average, right_user_count = await approved_review_stats(session, right.id)
            left_criteria_stats = await approved_school_criteria_stats(session, left.id)
            right_criteria_stats = await approved_school_criteria_stats(session, right.id)
        await state.clear()
        await track(call.from_user.id, "school_comparison_completed", {"left_id": left.id, "right_id": right.id})
        await call.message.edit_text(
            comparison_text(
                left, right, left_user_average, left_user_count,
                right_user_average, right_user_count,
                left_criteria_stats, right_criteria_stats,
            ),
            reply_markup=comparison_keyboard(left.id, right.id),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("compare_section:"))
    async def compare_section(call: CallbackQuery):
        _, left_id, right_id, section = call.data.split(":", 3)
        async with session_factory() as session:
            left = await session.get(School, int(left_id))
            right = await session.get(School, int(right_id))
            left_stats = await approved_school_criteria_stats(session, left.id) if section == "criteria" else None
            right_stats = await approved_school_criteria_stats(session, right.id) if section == "criteria" else None
        await call.message.edit_text(
            comparison_section_text(left, right, section, left_stats, right_stats),
            reply_markup=comparison_keyboard(left.id, right.id),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("rating_methodology:"))
    async def rating_methodology(call: CallbackQuery):
        origin = call.data.split(":", 1)[1]
        if origin == "rating":
            back_callback = "rating"
            back_label = "← Вернуться к рейтингу"
        elif origin == "teacher_compare":
            back_callback = "teacher_compare_menu"
            back_label = "← Вернуться к сравнению преподавателей"
        else:
            back_callback = "compare"
            back_label = "← Вернуться к сравнению"
        await call.message.edit_text(
            rating_methodology_text(),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=back_label, callback_data=back_callback)],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data == "rating")
    async def rating(call: CallbackQuery):
        async with session_factory() as session:
            rows = (await session.execute(select(School).where(School.is_active == True))).scalars().all()
            stats = {}
            for item in rows:
                stats[item.id] = await approved_review_stats(session, item.id)
            rows.sort(
                key=lambda item: school_total_score(item, stats[item.id][0], stats[item.id][1])[0],
                reverse=True,
            )
        await call.message.edit_text(
            "🏆 <b>Рейтинг школ</b>\n"
            "Первые три места отмечены медалями. Пока у школы меньше трёх подтверждённых отзывов, её балл отмечен звёздочкой как предварительный.\n\n"
            + "\n────────────\n".join(
                rating_entry(index, item, stats[item.id][0], stats[item.id][1])
                for index, item in enumerate(rows, 1)
            )
            + "\n\n<i>Профессиональная часть — аналитика ЕГЭ Мэтча по открытым данным.\n"
            "Пользовательская часть учитывает только одобренные и подтверждённые отзывы в боте.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:rating")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        await call.answer()

    @dp.callback_query(F.data == "channel")
    async def channel(call: CallbackQuery):
        await track(call.from_user.id, "channel_cta_clicked")
        await call.message.edit_text(
            "Новости, разборы ЕГЭ и поступление — в канале ЕГЭ Мэтч.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть канал ЕГЭ Мэтча", url=settings.channel_url)],
                    [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                ]
            ),
        )
        await call.answer()


async def run(settings: Settings):
    from .db import cleanup_expired_proofs, init_db

    engine, session_factory = await init_db(settings.database_url)
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    await setup(dp, session_factory, settings)

    async def proof_cleanup_loop():
        while True:
            await asyncio.sleep(24 * 60 * 60)
            await cleanup_expired_proofs(session_factory)

    cleanup_task = asyncio.create_task(proof_cleanup_loop())
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        await bot.session.close()
        await engine.dispose()
