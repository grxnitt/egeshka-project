from egeshka_bot.teacher_copy import teacher_description


def test_removes_source_led_intro() -> None:
    source = "Профиль школы и Telegram‑канал: подготовка с 2013 года, 73 стобалльника, каждый второй ученик сдаёт на 70+; это заявленные преподавателем показатели."
    assert teacher_description(source) == "Подготовка с 2013 года, 73 стобалльника, каждый второй ученик сдаёт на 70+."


def test_keeps_useful_channel_content_without_naming_source() -> None:
    source = "Официальный каталог: 69 стобалльников. В подтверждённом Telegram-канале — открытые стримы и разборы вариантов; показатели опубликованы школой."
    assert teacher_description(source) == "69 стобалльников. Публикует открытые стримы и разборы вариантов."
