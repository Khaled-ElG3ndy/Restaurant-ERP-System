"""ترقيم كوبونات حسني (2026-10-10): 10 أرقام = الفرع (2) + عشوائي (7) + رقم تحقق (Luhn).

أرقام فقط: لوحة الكاشير العربية لا تفسد الكود، وقارئ الباركود يقرأه. العشوائي يمنع تخمين
الكوبون التالي، ورقم التحقق يكشف أي رقم مكتوب غلط قبل البحث.
"""
import re
import secrets

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
CODE_LENGTH = 10


def luhn_digit(number):
    """رقم التحقق الذي يُلحق بـ number (نفس طريقة بطاقات البنوك)."""
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def luhn_valid(code):
    return len(code) > 1 and code.isdigit() and luhn_digit(code[:-1]) == code[-1]


def normalize_code(code):
    """«٢٠ ٤٨٢٧-٣٩١ ٦» → «2048273916»؛ الأكواد غير الرقمية (القديمة) تبقى كما هي بلا مسافات."""
    text = (code or "").strip().translate(ARABIC_DIGITS)
    compact = re.sub(r"[\s\-_.]", "", text)
    return compact if compact.isdigit() else text


def is_hosny_code(code):
    return len(code) == CODE_LENGTH and code.isdigit()


def generate_code(prefix, exists):
    prefix = (prefix or "90")[:2].rjust(2, "0")
    for _attempt in range(50):
        body = prefix + "".join(str(secrets.randbelow(10)) for _ in range(CODE_LENGTH - 3))
        code = body + luhn_digit(body)
        if not exists(code):
            return code
    raise RuntimeError("could not generate a unique coupon code")


def display_code(code):
    """2048273916 → «20 4827 391 6» للطباعة."""
    if not is_hosny_code(code):
        return code
    return f"{code[:2]} {code[2:6]} {code[6:9]} {code[9]}"
