"""Exam identities shared by bot, export and website. Legacy index order is stable."""
SUBJECTS = ["Русский", "Математика профильная", "Обществознание", "Физика", "Химия", "Биология", "Информатика", "Английский", "История", "Литература", "География", "Математика базовая"]
MATH_BOTH = "Математика профильная / Математика базовая"
BASE_SCHOOL_SOURCES = {
    "Умскул": "https://umschool.net/courses/",
    "100балльный репетитор": "https://100points.ru/course/basic-math-ege-baza-otdyha-s-matemanei/",
    "Сотка": "https://sotkaonline.ru/ege/10class/matematika/baza",
    "Фоксфорд": "https://foxford.ru/courses/17242/landing",
    "Вебиум": "https://webium.ru/courses/bazovaya-matematika-ege-osnova/",
    "99 Баллов": "https://99ballov.ru/courses/159",
    "Турбо ЕГЭ": "https://egeturbo.ru/kursy-ege-i-oge",
    "ЕГЭLand": "https://el-ed.ru/",
    "СМИТАП": "https://smitup.ru/ege-math",
    "PARTA": "https://onlineparta.ru/",
    "Skysmart": "https://skysmart.ru/courses/ege/matematika-bazovyj-uroven",
    "StudyCats": "https://studycats.ru/courses",
}

def teacher_exam_subject(school, name, subject):
    if subject not in ("Математика", "Математика профильная"):
        return subject
    if (school, name) == ("Умскул", "Данир Баев"):
        return "Математика ОГЭ"
    if (school, name) in {("Умскул", "Надежда Ковалевская"), ("Турбо ЕГЭ", "Катя"), ("Турбо ЕГЭ", "Саша")}:
        return "Математика базовая"
    if (school, name) in {("100балльный репетитор", "МатемАня"), ("Вебиум", "Эйджей Гаусс"), ("Фоксфорд", "Нина Максимова")}:
        return MATH_BOTH
    return "Математика профильная"

def target_options(subject):
    return [(f"Оценка {n}", str(n)) for n in (3, 4, 5)] if subject == "математика базовая" else [(s, s) for s in ("60+", "70+", "80+", "90+")]


def split_teacher_subjects(subjects):
    return sorted({part for subject in subjects for part in subject.split(" / ")})

def subject_token(subject):
    return {"Математика профильная": "math-profile", "Математика базовая": "math-base"}.get(subject, subject)

def subject_from_token(token):
    return {"math-profile": "Математика профильная", "math-base": "Математика базовая", "Математика": "Математика профильная"}.get(token, token)
