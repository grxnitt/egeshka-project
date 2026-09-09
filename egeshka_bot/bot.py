from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import json
from datetime import datetime, timedelta
from html import escape
from sqlalchemy import func, select

from .config import Settings
from .db import get_or_create_user
from .models import Event, Review, School, Teacher
from .scoring import QuizProfile, school_score


SUBJECTS = [
    "Русский",
    "Математика",
    "Обществознание",
    "Физика",
    "Химия",
    "Биология",
    "Информатика",
    "Английский",
    "История",
    "Литература",
]

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
    ("price_quality_score", "Цена/качество", 0.14),
)
CRITERIA_BY_KEY = {field: label for field, label, _ in CRITERIA}


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


class ReviewForm(StatesGroup):
    score = State()
    criterion_score = State()
    positive = State()
    negative = State()
    verification = State()


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def score_bar(value, width=5):
    filled = max(0, min(width, round(float(value) / 2)))
    return "●" * filled + "○" * (width - filled)


def school_professional_score(school):
    return sum(float(getattr(school, field, 0)) * weight for field, _, weight in CRITERIA) / 2


def school_criteria_text(school, user_stats=None):
    user_stats = user_stats or {}
    lines = ["📊 Оценка по критериям", "Проф. оценка + оценки учеников · итоговая шкала 0–10"]
    for field, label, weight in CRITERIA:
        value = float(getattr(school, field, 0))
        average, count = user_stats.get(field, (None, 0))
        if count:
            lines.append(f"{score_bar(value)} {label}: проф. {value / 2:.1f} + ученики {average:.1f} = {value / 2 + average:.1f}/10 · вес {weight:.0%}")
        else:
            lines.append(f"{score_bar(value)} {label}: проф. {value / 2:.1f} + ученики — · итог не рассчитан · вес {weight:.0%}")
    return "\n".join(lines)


def school_criteria_simple_text(school, user_stats=None):
    user_stats = user_stats or {}

    def number(value):
        return f"{float(value):.1f}".replace(".", ",")

    lines = ["📊 <b>Критерии школы</b>", "Итоговая оценка каждого критерия · шкала 0–10"]
    for field, label, _ in CRITERIA:
        value = float(getattr(school, field, 0))
        average, count = user_stats.get(field, (None, 0))
        if count:
            final_score = value / 2 + float(average)
            score_text = f"{number(final_score)}/10"
        else:
            score_text = f"{number(value)}/10 · пока без отзывов"
        lines.append(f"{score_bar(value)}  {label} · {score_text}")
    if not any(count for _, count in user_stats.values()):
        lines.append("\nПосле одобренных отзывов итог будет учитывать и оценки учеников.")
    return "\n".join(lines)


def menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Подобрать школу", callback_data="quiz")],
            [InlineKeyboardButton(text="⚖️ Сравнить школы", callback_data="compare")],
            [InlineKeyboardButton(text="👩‍🏫 Сравнить преподавателей", callback_data="teacher_compare_menu")],
            [InlineKeyboardButton(text="💬 Отзыв о школе", callback_data="review_school_menu"),
             InlineKeyboardButton(text="👩‍🏫 Отзыв о преподавателе", callback_data="review_teacher_menu")],
            [InlineKeyboardButton(text="📚 Школы", callback_data="schools"),
             InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
            [InlineKeyboardButton(text="📰 Канал", callback_data="channel")],
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
        f"<b>{e(hybrid_rating(school_professional_score(school) * 2, user_average, user_count))}</b>\n\n"
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
    rating = hybrid_rating(school_professional_score(school) * 2, user_average, user_count)
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
    title, body = sections.get(section, ("Раздел", "Информация пока не добавлена"))
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


def comparison_text(left, right, left_user_average=None, left_user_count=0, right_user_average=None, right_user_count=0, left_criteria_stats=None, right_criteria_stats=None):
    left_criteria_stats = left_criteria_stats or {}
    right_criteria_stats = right_criteria_stats or {}
    def comma(value):
        return f"{value:.1f}".replace(".", ",")

    def criterion(field, label, left_value, right_value):
        left_average, left_count = left_criteria_stats.get(field, (None, 0))
        right_average, right_count = right_criteria_stats.get(field, (None, 0))
        left_result = comma(left_value / 2 + left_average) if left_count else f"{comma(left_value)}*"
        right_result = comma(right_value / 2 + right_average) if right_count else f"{comma(right_value)}*"
        return f"{label}:  {left_result}  │  {right_result}"

    return (
        f"⚖️ Сравнение школ\n\n"
        f"{left.name}  │  {right.name}\n"
        f"Итоговые оценки по критериям · шкала 0–10\n\n"
        f"📊 Критерии\n"
        f"{criterion('teachers_score', 'Преподаватели', left.teachers_score, right.teachers_score)}\n"
        f"{criterion('practice_score', 'Практика и ДЗ', left.practice_score, right.practice_score)}\n"
        f"{criterion('feedback_score', 'Проверка', left.feedback_score, right.feedback_score)}\n"
        f"{criterion('curator_score', 'Кураторы', left.curator_score, right.curator_score)}\n"
        f"{criterion('platform_score', 'Платформа', left.platform_score, right.platform_score)}\n"
        f"{criterion('workload_score', 'Нагрузка', left.workload_score, right.workload_score)}\n"
        f"{criterion('price_quality_score', 'Цена/качество', left.price_quality_score, right.price_quality_score)}\n"
        f"⭐ Общий итог:  "
        f"{comma(school_professional_score(left) + left_user_average) if left_user_count else comma(school_professional_score(left) * 2) + '*'}  │  "
        f"{comma(school_professional_score(right) + right_user_average) if right_user_count else comma(school_professional_score(right) * 2) + '*'}\n"
        f"* Предварительный балл: пока без оценок учеников.\n\n"
        f"────────────\n💸 Цена\n"
        f"{left.name}:\n{left.price_text}\n\n"
        f"{right.name}:\n{right.price_text}\n\n"
        f"────────────\n🎓 Формат\n"
        f"{left.name}: {left.format_text}\n\n"
        f"{right.name}: {right.format_text}\n\n"
        f"────────────\n🧑‍🏫 Поддержка\n"
        f"{left.name}: {left.support_text}\n\n"
        f"{right.name}: {right.support_text}\n\n"
        f"────────────\n📝 Практика\n"
        f"{left.name}: {left.homework_text}\n\n"
        f"{right.name}: {right.homework_text}\n\n"
        f"────────────\n✅ Сильные стороны\n"
        f"{left.name}: {left.strengths}\n\n"
        f"{right.name}: {right.strengths}\n\n"
        f"────────────\n⚠️ Риски\n"
        f"{left.name}: {left.weaknesses}\n\n"
        f"{right.name}: {right.weaknesses}"
    )


def rating_methodology_text():
    return (
        "ℹ️ Как считается рейтинг\n\n"
        "Для школ и преподавателей каждый критерий получает две оценки:\n"
        "• профессиональная оценка ЕГЭшки — до 5 баллов;\n"
        "• средняя оценка учеников — до 5 баллов.\n\n"
        "Итог по критерию и общий рейтинг — сумма двух частей, максимум 10/10.\n"
        "Звёздочка означает предварительный балл: по критерию пока нет одобренных отзывов учеников."
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
            [InlineKeyboardButton(text=subject, callback_data=f"teacher_subject:{school_id}:{subject}")]
            for subject in subjects
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def global_teacher_subject_buttons(subjects):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"global_teacher_subject:{subject}")]
            for subject in subjects
        ] + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
    )


def review_teacher_subject_buttons(subjects):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subject, callback_data=f"review_teacher_subject:{subject}")]
            for subject in subjects
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


def _teacher_display_score(teacher, user_average=None, user_count=0):
    """Return a student-friendly teacher score on the shared 0–10 scale."""
    professional = max(0.0, min(5.0, float(teacher.rating) / 2))
    if user_average is not None and user_count:
        return f"{professional + max(0.0, min(5.0, float(user_average))):.1f}".replace(".", ","), False, user_count
    return f"{professional * 2:.1f}".replace(".", ","), True, 0


def teacher_compare_text(
    left,
    right,
    school=None,
    left_user_average=None,
    left_user_count=0,
    right_user_average=None,
    right_user_count=0,
):
    school_line = f"🏫 {school.name}" if school else f"🏫 {left.school_name} и {right.school_name}"
    left_school_name = school.name if school else left.school_name
    right_school_name = school.name if school else right.school_name
    left_score, left_preliminary, _ = _teacher_display_score(left, left_user_average, left_user_count)
    right_score, right_preliminary, _ = _teacher_display_score(right, right_user_average, right_user_count)
    left_marker = "*" if left_preliminary else ""
    right_marker = "*" if right_preliminary else ""
    left_reviews = f"💬 Одобренных отзывов: {left_user_count}" if left_user_count else "💬 Пока нет одобренных отзывов"
    right_reviews = f"💬 Одобренных отзывов: {right_user_count}" if right_user_count else "💬 Пока нет одобренных отзывов"
    preliminary_note = "\n* Предварительный балл — без одобренных отзывов учеников." if left_preliminary or right_preliminary else ""
    return (
        f"⚖️ Сравнение преподавателей\n\n"
        f"{school_line}\n"
        f"📚 {left.subject}\n\n"
        f"👩‍🏫 {left.name} ({left_school_name}) · ⭐ {left_score}/10{left_marker}\n"
        f"{left.description}\n"
        f"{left_reviews}\n\n"
        f"👩‍🏫 {right.name} ({right_school_name}) · ⭐ {right_score}/10{right_marker}\n"
        f"{right.description}\n"
        f"{right_reviews}{preliminary_note}"
    )


def hybrid_rating(professional_out_of_10, user_average=None, user_count=0):
    professional = max(0.0, min(5.0, float(professional_out_of_10) / 2))
    if user_average is None or user_count == 0:
        return (
            f"Профессиональная оценка: {professional:.1f}/5\n"
            "Пользовательская оценка: пока нет данных\n"
            "Итог: не рассчитан — нужны одобренные отзывы"
        )
    total = professional + max(0.0, min(5.0, float(user_average)))
    return (
        f"Профессиональная оценка: {professional:.1f}/5\n"
        f"Пользовательская оценка: {float(user_average):.1f}/5 ({user_count} отзывов)\n"
        f"Итог: {total:.1f}/10"
    )


def rating_medal(position):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, "▫️")


def rating_entry(position, school, user_average, user_count):
    def n(value):
        return f"{value:.1f}".replace(".", ",")

    professional = school_professional_score(school)
    if user_count:
        total_score = professional + user_average
        score_suffix = f" · {user_count} отзывов"
    else:
        total_score = professional * 2
        score_suffix = "*"
    score_text = n(total_score)
    return (
        f"{rating_medal(position)} <b>{escape(school.name)}</b>\n"
        f"⭐ <b>{score_text}/10{score_suffix}</b>\n"
        f"Критерии:\n"
        f"преподаватели {n(school.teachers_score)} · практика {n(school.practice_score)} · "
        f"проверка {n(school.feedback_score)} · кураторы {n(school.curator_score)}\n"
        f"платформа {n(school.platform_score)} · нагрузка {n(school.workload_score)} · "
        f"цена/качество {n(school.price_quality_score)}"
    )


def teacher_card(teacher, school, user_average=None, user_count=0):
    social = teacher.social_url or "Публичная ссылка на соцсеть не подтверждена"
    return (
        f"👩‍🏫 {teacher.name}\n\n"
        f"🏫 Школа: {school.name}\n"
        f"📚 Предмет: {teacher.subject}\n\n"
        f"⭐ Оценка ЕГЭшки\n{hybrid_rating(teacher.rating, user_average, user_count)}\n\n"
        f"👤 О преподавателе\n{teacher.description}\n\n"
        f"💬 Отзывы и сигналы\n{teacher.review_summary}\n\n"
        f"📱 Соцсеть\n{social}\n\n"
        f"🔎 Источник\n{teacher.source_url}\n"
        f"Тип данных: {teacher.evidence_type}"
    )


def review_score_keyboard():
    scores = (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)

    def label(score):
        return f"{score:g}".replace(".", ",") + " / 5"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label(score), callback_data=f"review_score:{score}") for score in scores[index:index + 3]]
        for index in range(0, len(scores), 3)
    ] + [
        [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
    ])


def criterion_score_keyboard():
    scores = (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{score:g}".replace(".", ","), callback_data=f"criterion_score:{score}") for score in scores[index:index + 3]]
        for index in range(0, len(scores), 3)
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
        parts = [f"⭐ {review.score:.1f}/5"]
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
    ))).scalars().all()
    for review in dedicated:
        if review.criterion in values:
            values[review.criterion].append(review.score)
    overall = (await session.execute(select(Review).where(
        Review.school_id == school_id,
        Review.teacher_id.is_(None),
        Review.criterion.is_(None),
        Review.moderation_status == "approved",
    ))).scalars().all()
    for review in overall:
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
            target += f" · критерий «{CRITERIA_BY_KEY.get(review.criterion, review.criterion)}»"
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
                f"{CRITERIA_BY_KEY.get(key, key)}: {float(value):g}/5" for key, value in criteria.items()
            ) + "\n\n"
        text = (
            f"Новый отзыв №{review.id} о {target}. Оценка: {review.score:.1f}/5\n\n"
            f"{criteria_text}"
            f"Понравилось:\n{positive}\n\n"
            f"Не понравилось:\n{negative}\n\n"
            f"Подтверждение обучения: {proof}\n"
            f"Одобрить отзыв: /approve_review {review.id}\n"
            f"Отклонить: /reject_review {review.id}"
        )
        if review.proof_file_id:
            text += f"\nПодтвердить обучение: /verify_review {review.id}"
        for admin_id in settings.admin_id_set:
            await bot.send_message(admin_id, text)
            if review.proof_file_id:
                caption = f"Файл подтверждения для отзыва №{review.id}"
                if review.proof_file_type == "photo":
                    await bot.send_photo(admin_id, review.proof_file_id, caption=caption)
                else:
                    await bot.send_document(admin_id, review.proof_file_id, caption=caption)

    @dp.message(CommandStart())
    async def start(message: Message):
        await track(message.from_user.id, "start")
        async with session_factory() as session:
            await get_or_create_user(session, message.from_user.id)
        await message.answer(
            "Привет! Я ЕГЭшка — помогу выбрать школу и преподавателя для ЕГЭ. Здесь можно пройти подбор, посмотреть оценки по критериям, сравнить школы и преподавателей и оставить свой отзыв.",
            reply_markup=menu(),
        )

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
            await call.message.edit_text("Вопрос 2 из 8 · Сколько готов тратить в месяц?", reply_markup=options([("До 3 000 ₽", "3000"), ("3 000–5 000 ₽", "5000"), ("5 000–8 000 ₽", "8000"), ("Больше 8 000 ₽", "12000"), ("Пока не определился", "0")], "budget"))
        elif current == "Quiz:target":
            await state.set_state(Quiz.current_level)
            await call.message.edit_text("Вопрос 3 из 8 · Как оцениваешь свою базу?", reply_markup=options([("Начинаю почти с нуля", "low"), ("Что-то знаю, нужна система", "middle"), ("База хорошая, хочу усилить результат", "high")], "level"))
        elif current == "Quiz:curator":
            await state.set_state(Quiz.target)
            await call.message.edit_text("Вопрос 4 из 8 · На какой результат ориентируешься?", reply_markup=options([(item, item) for item in ["60+", "70+", "80+", "90+"]], "target"))
        elif current == "Quiz:workload":
            await state.set_state(Quiz.curator)
            await call.message.edit_text("Вопрос 5 из 8 · Какая поддержка тебе нужна?", reply_markup=options([("Разберусь сам", "1"), ("Хочу иногда задавать вопросы", "2"), ("Нужен регулярный контроль", "3"), ("Без куратора легко всё откладываю", "4")], "curator"))
        elif current == "Quiz:first_priority":
            await state.set_state(Quiz.workload)
            await call.message.edit_text("Вопрос 6 из 8 · Сколько нагрузки тебе подходит?", reply_markup=options([("Небольшая нагрузка, без перегруза", "1"), ("Умеренный темп", "2"), ("Готов заниматься много", "3"), ("Максимум практики ради результата", "4")], "workload"))
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
        subject = call.data.split(":", 1)[1]
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher.id, Teacher.name, Teacher.subject, School.name.label("school_name"))
                .join(School, School.id == Teacher.school_id)
                .where(Teacher.subject == subject, Teacher.is_active == True)
                .order_by(Teacher.rating.desc(), Teacher.name)
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
        await state.update_data(review_school_id=school_id, review_teacher_id=None, review_criterion=criterion)
        if criterion is None:
            await state.update_data(review_criteria_scores={}, review_criteria_index=0)
            await state.set_state(ReviewForm.criterion_score)
            await call.message.edit_text(
                "Сначала оцени критерии школы по очереди.\n\n"
                "1/7 · Преподаватели\nВыбери оценку от 1 до 5:",
                reply_markup=criterion_score_keyboard(),
            )
        else:
            await state.set_state(ReviewForm.score)
            subject = f"критерий «{CRITERIA_BY_KEY[criterion]}»"
            await call.message.edit_text(f"Оцени {subject} от 1 до 5 с шагом 0,5. Отзыв будет опубликован только после модерации.", reply_markup=review_score_keyboard())
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
        await state.update_data(review_school_id=teacher.school_id, review_teacher_id=teacher_id, review_criterion=None)
        await state.set_state(ReviewForm.score)
        await call.message.edit_text(f"Оцени преподавателя {teacher.name} от 1 до 5 с шагом 0,5. Отзыв будет опубликован только после модерации.", reply_markup=review_score_keyboard())
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
        field, label, _ = CRITERIA[index]
        scores[field] = float(call.data.split(":")[1])
        if index + 1 < len(CRITERIA):
            next_field, next_label, _ = CRITERIA[index + 1]
            await state.update_data(review_criteria_scores=scores, review_criteria_index=index + 1)
            await call.message.edit_text(
                f"{index + 2}/7 · {next_label}\nВыбери оценку от 1 до 5:",
                reply_markup=criterion_score_keyboard(),
            )
        else:
            await state.update_data(review_criteria_scores=scores)
            await state.set_state(ReviewForm.score)
            await call.message.edit_text(
                "Все критерии оценены.\n\nТеперь поставь общую оценку школе от 1 до 5:",
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
            await session.commit()
            review_id = review.id
            school = await session.get(School, data["review_school_id"])
            teacher = await session.get(Teacher, data["review_teacher_id"]) if data.get("review_teacher_id") else None
        await state.update_data(review_id=review_id)
        await state.set_state(ReviewForm.verification)
        await track(message.from_user.id, "review_submitted", {"review_id": review_id})
        await message.answer(
            "Отзыв сохранён и отправлен на модерацию.\n\n"
            "Хочешь подтвердить, что действительно учился в этой школе? Можно отправить скриншот личного кабинета, чека или договора. Это необязательно.",
            reply_markup=review_verification_keyboard(),
        )

    @dp.callback_query(ReviewForm.verification, F.data == "review_proof:no")
    async def review_proof_skip(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await notify_review_for_moderation(call.bot, int(data["review_id"]))
        await state.clear()
        await call.message.edit_text("Хорошо, отзыв останется без подтверждения.", reply_markup=menu())
        await call.answer()

    @dp.callback_query(ReviewForm.verification, F.data == "review_proof:yes")
    async def review_proof_start(call: CallbackQuery, state: FSMContext):
        await call.message.edit_text(
            "Пришли одним сообщением фото или файл подтверждения.\n\n"
            "Подойдут скриншот личного кабинета, чек, договор или другое подтверждение обучения. Лишние персональные данные можно закрыть.",
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
            await session.commit()
            school = await session.get(School, review.school_id)
            teacher = await session.get(Teacher, review.teacher_id) if review.teacher_id else None
        await notify_review_for_moderation(message.bot, review.id)
        await state.clear()
        await message.answer("Подтверждение получено и отправлено на проверку.", reply_markup=menu())

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
            await session.commit()
        await message.answer("Отзыв опубликован.")

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
            await session.commit()
        await message.answer("Обучение подтверждено. Теперь можно опубликовать отзыв командой /approve_review ID")

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
                f"{CRITERIA_BY_KEY.get(key, key)}: {float(value):g}/5" for key, value in criteria.items()
            )
        await message.answer(
            f"Отзыв №{review.id} о {target}\n"
            f"Оценка: {review.score:.1f}/5\n"
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
        await message.answer("\n".join(lines) if rows else "За последние 30 дней событий пока нет.")

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
            await session.commit()
        await message.answer("Отзыв отклонён.")

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
            "Вопрос 2 из 8 · Сколько готов тратить в месяц?",
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
            "Вопрос 3 из 8 · Как оцениваешь свою базу?",
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
            "Вопрос 4 из 8 · На какой результат ориентируешься?",
            reply_markup=options([(item, item) for item in ["60+", "70+", "80+", "90+"]], "target"),
        )
        await call.answer()

    @dp.callback_query(Quiz.target, F.data.startswith("target:"))
    async def target(call: CallbackQuery, state: FSMContext):
        await state.update_data(target=int(call.data.split(":")[1].replace("+", "")))
        await state.set_state(Quiz.curator)
        await call.message.edit_text(
            "Вопрос 5 из 8 · Какая поддержка тебе нужна?",
            reply_markup=options(
                [
                    ("Разберусь сам", "1"),
                    ("Хочу иногда задавать вопросы", "2"),
                    ("Нужен регулярный контроль", "3"),
                    ("Без куратора легко всё откладываю", "4"),
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
            "Вопрос 6 из 8 · Сколько нагрузки тебе подходит?",
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
            "Вопрос 8 из 8 · Как тебе удобнее не откладывать учёбу?",
            reply_markup=options(
                [
                    ("Сам планирую и выполняю", "1"),
                    ("Нужны напоминания", "2"),
                    ("Нужны проверки и дедлайны", "3"),
                    ("Нужен жёсткий контроль", "4"),
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
        rows = await active_schools(session_factory)
        ranked = [
            (score, reasons, school)
            for school in rows
            for score, reasons in [school_score(school, profile)]
            if score >= 0
        ]
        ranked.sort(key=lambda item: item[0], reverse=True)
        top = ranked[:3]
        lines = []
        for index, (score, reasons, school) in enumerate(top, 1):
            reason_text = ", ".join(reasons) if reasons else "хорошее совпадение по анкете"
            lines.append(f"{index}. {school.name} — {score:.0f}%\nПочему: {reason_text}\n💸 {school.price_text}")
        text = "Результат подбора\n\n" + "\n\n".join(lines)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Карточка: {school.name}", callback_data=f"school:{school.id}")]
                for _, _, school in top
            ]
            + [[InlineKeyboardButton(text="📰 Новости и разборы ЕГЭ", callback_data="channel")]]
            + [[InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")]]
        )
        await state.clear()
        await track(call.from_user.id, "quiz_completed", {"subject": data.get("subject")})
        await call.message.edit_text(text, reply_markup=keyboard)
        await call.answer()

    @dp.callback_query(F.data == "schools")
    async def schools(call: CallbackQuery):
        rows = await active_schools(session_factory)
        await call.message.edit_text("📚 Каталог школ\n\nВыбери школу, чтобы открыть её карточку:", reply_markup=school_buttons(rows, "school"))
        await call.answer()

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
                select(Teacher).where(Teacher.school_id == school_id, Teacher.is_active == True).order_by(Teacher.rating.desc(), Teacher.name)
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
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher).where(Teacher.school_id == int(school_id), Teacher.subject == subject, Teacher.is_active == True).order_by(Teacher.rating.desc(), Teacher.name)
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
                    select(Teacher.id, Teacher.name, Teacher.subject, Teacher.rating, School.name.label("school_name"))
                    .join(School, School.id == Teacher.school_id)
                    .where(Teacher.subject == data["subject"], Teacher.id != first_id, Teacher.is_active == True)
                    .order_by(Teacher.rating.desc(), Teacher.name)
                )).all()
            await state.update_data(first_id=first_id)
            await state.set_state(TeacherCompare.second)
            await call.message.edit_text("Теперь выбери второго преподавателя:", reply_markup=global_teacher_buttons(rows, first_id))
            await call.answer()
            return
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher).where(Teacher.school_id == data["school_id"], Teacher.subject == data["subject"], Teacher.id != first_id, Teacher.is_active == True).order_by(Teacher.rating.desc(), Teacher.name)
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
                left_user_average, left_user_count = await approved_review_stats(session, left.school_id, left.id)
                right_user_average, right_user_count = await approved_review_stats(session, right.school_id, right.id)
            left.school_name = left_school.name
            right.school_name = right_school.name
            await state.clear()
            await call.message.edit_text(
                teacher_compare_text(left, right, left_user_average=left_user_average, left_user_count=left_user_count, right_user_average=right_user_average, right_user_count=right_user_count),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:teacher_compare")],
                    [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                ]),
            )
            await call.answer()
            return
        async with session_factory() as session:
            left = await session.get(Teacher, data["first_id"])
            right = await session.get(Teacher, int(call.data.split(":")[1]))
            school = await session.get(School, data["school_id"])
            left_user_average, left_user_count = await approved_review_stats(session, left.school_id, left.id)
            right_user_average, right_user_count = await approved_review_stats(session, right.school_id, right.id)
        await state.clear()
        await call.message.edit_text(
            teacher_compare_text(left, right, school, left_user_average, left_user_count, right_user_average, right_user_count),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:teacher_compare")],
                [InlineKeyboardButton(text="← Преподаватели школы", callback_data=f"teachers:{school.id}")],
                [InlineKeyboardButton(text="← Карточка школы", callback_data=f"school:{school.id}")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
        )
        await call.answer()

    @dp.callback_query(F.data.startswith("teacher:"))
    async def teacher(call: CallbackQuery):
        teacher_id = int(call.data.split(":")[1])
        async with session_factory() as session:
            item = await session.get(Teacher, teacher_id)
            school = await session.get(School, item.school_id)
            user_reviews = await approved_reviews_text(session, school.id, item.id)
            user_average, user_count = await approved_review_stats(session, school.id, item.id)
        await call.message.edit_text(
            teacher_card(item, school, user_average, user_count) + user_reviews,
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
        subject = call.data.split(":", 1)[1]
        async with session_factory() as session:
            rows = (await session.execute(
                select(Teacher.id, Teacher.name, Teacher.subject, Teacher.rating, School.name.label("school_name"))
                .join(School, School.id == Teacher.school_id)
                .where(Teacher.subject == subject, Teacher.is_active == True)
                .order_by(Teacher.rating.desc(), Teacher.name)
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
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ℹ️ Как считается рейтинг", callback_data="rating_methodology:compare")],
                [InlineKeyboardButton(text="📰 Новости и разборы ЕГЭ", callback_data="channel")],
                [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
            ]),
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
        )
        await call.answer()

    @dp.callback_query(F.data == "rating")
    async def rating(call: CallbackQuery):
        async with session_factory() as session:
            rows = (await session.execute(select(School).where(School.is_active == True))).scalars().all()
            stats = {}
            for item in rows:
                stats[item.id] = await approved_review_stats(session, item.id)
            rows.sort(key=school_professional_score, reverse=True)
        await call.message.edit_text(
            "🏆 <b>Рейтинг школ</b>\n"
            "Первые три места отмечены медалями. Пока пользовательских отзывов мало, порядок основан на профессиональной оценке.\n\n"
            + "\n────────────\n".join(
                rating_entry(index, item, stats[item.id][0], stats[item.id][1])
                for index, item in enumerate(rows, 1)
            )
            + "\n\n<i>Профессиональная часть — аналитика ЕГЭшки по открытым данным.\n"
            "Пользовательская часть учитывает только одобренные отзывы в боте.</i>",
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
            "Новости, разборы ЕГЭ и поступление — в канале ЕГЭшка.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Открыть канал ЕГЭшки", url=settings.channel_url)],
                    [InlineKeyboardButton(text="⌂ Главное меню", callback_data="menu")],
                ]
            ),
        )
        await call.answer()


async def run(settings: Settings):
    from .db import init_db

    _, session_factory = await init_db(settings.database_url)
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    await setup(dp, session_factory, settings)
    await dp.start_polling(bot)
