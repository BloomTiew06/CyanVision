#!/usr/bin/env python
"""Malaysian public holidays 2025-2027 (federal + state) -> data_my/malaysia_public_holidays.csv

Transcribed from the official schedules of the Cabinet, Constitution and Inter-Governmental Relations
Division, Prime Minister's Department (https://www.kabinet.gov.my/hari-kelepasan-am/):
  2025: https://www.kabinet.gov.my/storage/2024/11/hka_2025.pdf
  2026: https://www.kabinet.gov.my/storage/2025/08/HKA-2026.pdf
  2027: FMM circular GI/15/2026 reproducing the same division's table
        https://www.fmm.org.my/uploads/files/fmm/20260828_144306_GI15%20-%202027%20Public%20Holiday%20National%20&%20State%20-%2027%20Aug.pdf
plus holidays announced after the gazette (type "Additional", with their own source).

One row per (date, holiday, state or federal territory). Columns follow the Favorita holidays_events.csv
format (date, type, locale, locale_name, description, transferred) so pipeline.py can read it as is:
locale is "National" when all 16 states/FTs observe that holiday on that date, else "Regional".

Not included: replacement days (cuti ganti) for holidays on a rest day. The rules differ by state weekend
and are not in the gazette tables. Dates marked subject_to_change depend on moon sighting.

Run:  python make_my_holidays.py
"""
from datetime import date
from pathlib import Path

import pandas as pd

STATES = ["Kuala Lumpur", "Labuan", "Putrajaya", "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan",
          "Pahang", "Perak", "Perlis", "Pulau Pinang", "Sabah", "Sarawak", "Selangor", "Terengganu"]
ALL = "1" * 16
ALL_BUT_SARAWAK = "1111111111111011"
SRC = {
    2025: "https://www.kabinet.gov.my/storage/2024/11/hka_2025.pdf",
    2026: "https://www.kabinet.gov.my/storage/2025/08/HKA-2026.pdf",
    2027: "https://www.fmm.org.my/uploads/files/fmm/20260828_144306_GI15%20-%202027%20Public%20Holiday"
          "%20National%20&%20State%20-%2027%20Aug.pdf",
}
MAJOR_FESTIVALS = {"cny", "cny_2", "hari_raya_puasa", "hari_raya_puasa_2", "hari_raya_puasa_3",
                   "hari_raya_puasa_additional", "hari_raya_haji", "hari_raya_haji_2", "deepavali", "christmas",
                   "gawai", "kaamatan"}

# State masks, one character per entry of STATES in order (1 = observed). Recurring patterns:
NEW_YEAR = "1110001111011110"      # not Johor, Kedah, Kelantan, Perlis, Terengganu
ISRAK = "0000100100100001"         # Kedah, N. Sembilan, Perlis, Terengganu
THAIPUSAM = "1011000101010010"     # KL, Putrajaya, Johor, N. Sembilan, Perak, Penang, Selangor
NUZUL = "1110010011110011"         # FTs, Kelantan, Pahang, Perak, Perlis, Penang, Selangor, Terengganu
FT = "1110000000000000"
CNY2_FED = "1111101111111110"      # federal everywhere except Kelantan, Terengganu (state holiday there)
KT_TR = "0000010000000001"
KD_PL = "0000100000100000"
JH_KD = "0001100000000000"


def only(*names):
    return "".join("1" if s in names else "0" for s in STATES)


# (month, day, gazette weekday, holiday_key, description, level, mask, subject_to_change)
# level: federal = Hari Kelepasan Am Persekutuan (P/N), state = Negeri (N/S), additional = announced later
H = {
    2025: [
        (1, 1, "Wed", "new_year", "New Year's Day", "state", NEW_YEAR, False),
        (1, 14, "Tue", "ruler_birthday", "Birthday of Yang di-Pertuan Besar Negeri Sembilan", "state", only("Negeri Sembilan"), False),
        (1, 27, "Mon", "israk_mikraj", "Israk and Mikraj", "state", ISRAK, False),
        (1, 29, "Wed", "cny", "Chinese New Year", "federal", ALL, False),
        (1, 30, "Thu", "cny_2", "Chinese New Year (2nd day)", "federal", CNY2_FED, False),
        (1, 30, "Thu", "cny_2", "Chinese New Year (2nd day)", "state", KT_TR, False),
        (2, 1, "Sat", "ft_day", "Federal Territory Day", "state", FT, False),
        (2, 11, "Tue", "thaipusam", "Thaipusam", "state", THAIPUSAM, False),
        (2, 20, "Thu", "state_day", "Declaration of Independence Day (Melaka)", "state", only("Melaka"), False),
        (3, 2, "Sun", "awal_ramadan", "Awal Ramadan", "state", JH_KD, True),
        (3, 4, "Tue", "ruler_installation", "Anniversary of Installation of Sultan of Terengganu", "state", only("Terengganu"), False),
        (3, 18, "Tue", "nuzul_quran", "Nuzul Al-Quran", "state", NUZUL, False),
        (3, 23, "Sun", "ruler_birthday", "Birthday of Sultan of Johor", "state", only("Johor"), False),
        (3, 31, "Mon", "hari_raya_puasa", "Hari Raya Aidilfitri", "federal", ALL, True),
        (4, 1, "Tue", "hari_raya_puasa_2", "Hari Raya Aidilfitri (2nd day)", "federal", ALL, True),
        (4, 2, "Wed", "hari_raya_puasa_3", "Hari Raya Aidilfitri (3rd day)", "state", only("Melaka"), False),
        (4, 18, "Fri", "good_friday", "Good Friday", "state", only("Sabah", "Sarawak"), False),
        (4, 26, "Sat", "ruler_birthday", "Birthday of Sultan of Terengganu", "state", only("Terengganu"), False),
        (5, 1, "Thu", "labour_day", "Labour Day", "federal", ALL, False),
        (5, 12, "Mon", "wesak", "Wesak Day", "federal", ALL, False),
        (5, 17, "Sat", "ruler_birthday", "Birthday of Raja of Perlis", "state", only("Perlis"), False),
        (5, 22, "Thu", "hol", "Hol of Almarhum Sultan Ahmad Shah (Pahang)", "state", only("Pahang"), False),
        (5, 30, "Fri", "kaamatan", "Harvest Festival (Pesta Kaamatan)", "state", only("Labuan", "Sabah"), False),
        (5, 31, "Sat", "kaamatan", "Harvest Festival (Pesta Kaamatan, 2nd day)", "state", only("Labuan", "Sabah"), False),
        (6, 1, "Sun", "gawai", "Gawai Dayak", "state", only("Sarawak"), False),
        (6, 2, "Mon", "gawai", "Gawai Dayak (2nd day)", "state", only("Sarawak"), False),
        (6, 2, "Mon", "agong_birthday", "Birthday of the Yang di-Pertuan Agong", "federal", ALL, False),
        (6, 6, "Fri", "arafah", "Arafah Day", "state", KT_TR, False),
        (6, 7, "Sat", "hari_raya_haji", "Hari Raya Aidiladha (Haji)", "federal", ALL, True),
        (6, 8, "Sun", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "federal", KT_TR, True),
        (6, 8, "Sun", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "state", KD_PL, True),
        (6, 22, "Sun", "ruler_birthday", "Birthday of Sultan of Kedah", "state", only("Kedah"), False),
        (6, 27, "Fri", "awal_muharram", "Awal Muharram (Maal Hijrah)", "federal", ALL, False),
        (7, 7, "Mon", "state_day", "George Town World Heritage City Day", "state", only("Pulau Pinang"), False),
        (7, 12, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Pulau Pinang", "state", only("Pulau Pinang"), False),
        (7, 22, "Tue", "state_day", "Sarawak Independence Day", "state", only("Sarawak"), False),
        (7, 30, "Wed", "ruler_birthday", "Birthday of Sultan of Pahang", "state", only("Pahang"), False),
        (7, 31, "Thu", "hol", "Hol of Almarhum Sultan Iskandar (Johor)", "state", only("Johor"), False),
        (8, 24, "Sun", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Melaka", "state", only("Melaka"), False),
        (8, 31, "Sun", "national_day", "National Day (Hari Merdeka)", "federal", ALL, False),
        (9, 5, "Fri", "maulidur_rasul", "Prophet Muhammad's Birthday (Maulidur Rasul)", "federal", ALL, False),
        (9, 15, "Mon", "malaysia_day_additional", "Additional holiday for Malaysia Day", "additional", ALL, False),
        (9, 16, "Tue", "malaysia_day", "Malaysia Day", "federal", ALL, False),
        (9, 29, "Mon", "ruler_birthday", "Birthday of Sultan of Kelantan", "state", only("Kelantan"), False),
        (9, 30, "Tue", "ruler_birthday", "Birthday of Sultan of Kelantan (2nd day)", "state", only("Kelantan"), False),
        (10, 4, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sabah", "state", only("Sabah"), False),
        (10, 11, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sarawak", "state", only("Sarawak"), False),
        (10, 20, "Mon", "deepavali", "Deepavali", "federal", ALL_BUT_SARAWAK, True),
        (11, 7, "Fri", "ruler_birthday", "Birthday of Sultan of Perak", "state", only("Perak"), False),
        (12, 11, "Thu", "ruler_birthday", "Birthday of Sultan of Selangor", "state", only("Selangor"), False),
        (12, 24, "Wed", "christmas_eve", "Christmas Eve", "state", only("Sabah"), False),
        (12, 25, "Thu", "christmas", "Christmas Day", "federal", ALL, False),
    ],
    2026: [
        (1, 1, "Thu", "new_year", "New Year's Day", "state", NEW_YEAR, False),
        (1, 14, "Wed", "ruler_birthday", "Birthday of Yang di-Pertuan Besar Negeri Sembilan", "state", only("Negeri Sembilan"), False),
        (1, 17, "Sat", "israk_mikraj", "Israk and Mikraj", "state", ISRAK, False),
        (2, 1, "Sun", "ft_day", "Federal Territory Day", "state", FT, False),
        (2, 1, "Sun", "thaipusam", "Thaipusam", "state", THAIPUSAM, False),
        (2, 17, "Tue", "cny", "Chinese New Year", "federal", ALL, False),
        (2, 18, "Wed", "cny_2", "Chinese New Year (2nd day)", "federal", CNY2_FED, False),
        (2, 18, "Wed", "cny_2", "Chinese New Year (2nd day)", "state", KT_TR, False),
        (2, 19, "Thu", "awal_ramadan", "Awal Ramadan", "state", JH_KD, True),
        (2, 20, "Fri", "state_day", "Declaration of Independence Day (Melaka)", "state", only("Melaka"), False),
        (3, 4, "Wed", "ruler_installation", "Anniversary of Installation of Sultan of Terengganu", "state", only("Terengganu"), False),
        (3, 7, "Sat", "nuzul_quran", "Nuzul Al-Quran", "state", NUZUL, False),
        (3, 20, "Fri", "hari_raya_puasa_additional", "Additional holiday for Hari Raya Aidilfitri", "additional", ALL, False),
        (3, 21, "Sat", "hari_raya_puasa", "Hari Raya Aidilfitri", "federal", ALL, True),
        (3, 22, "Sun", "hari_raya_puasa_2", "Hari Raya Aidilfitri (2nd day)", "federal", ALL, True),
        (3, 23, "Mon", "ruler_birthday", "Birthday of Sultan of Johor", "state", only("Johor"), False),
        (3, 23, "Mon", "hari_raya_puasa_3", "Hari Raya Aidilfitri (3rd day)", "state", only("Melaka"), False),
        (3, 30, "Mon", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sabah", "state", only("Sabah"), False),
        (4, 3, "Fri", "good_friday", "Good Friday", "state", only("Sabah", "Sarawak"), False),
        (4, 26, "Sun", "ruler_birthday", "Birthday of Sultan of Terengganu", "state", only("Terengganu"), False),
        (5, 1, "Fri", "labour_day", "Labour Day", "federal", ALL, False),
        (5, 17, "Sun", "ruler_birthday", "Birthday of Raja of Perlis", "state", only("Perlis"), False),
        (5, 22, "Fri", "hol", "Hol of Almarhum Sultan Ahmad Shah (Pahang)", "state", only("Pahang"), False),
        (5, 26, "Tue", "arafah", "Arafah Day", "state", KT_TR, False),
        (5, 27, "Wed", "hari_raya_haji", "Hari Raya Aidiladha (Haji)", "federal", ALL, True),
        (5, 28, "Thu", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "federal", KT_TR, True),
        (5, 28, "Thu", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "state", KD_PL, True),
        (5, 30, "Sat", "kaamatan", "Harvest Festival (Pesta Kaamatan)", "state", only("Labuan", "Sabah"), False),
        (5, 31, "Sun", "kaamatan", "Harvest Festival (Pesta Kaamatan, 2nd day)", "state", only("Labuan", "Sabah"), False),
        (5, 31, "Sun", "wesak", "Wesak Day", "federal", ALL, False),
        (6, 1, "Mon", "agong_birthday", "Birthday of the Yang di-Pertuan Agong", "federal", ALL, False),
        (6, 1, "Mon", "gawai", "Gawai Dayak", "state", only("Sarawak"), False),
        (6, 2, "Tue", "gawai", "Gawai Dayak (2nd day)", "state", only("Sarawak"), False),
        (6, 17, "Wed", "awal_muharram", "Awal Muharram (Maal Hijrah)", "federal", ALL, False),
        (6, 21, "Sun", "ruler_birthday", "Birthday of Sultan of Kedah", "state", only("Kedah"), False),
        (7, 7, "Tue", "state_day", "George Town World Heritage City Day", "state", only("Pulau Pinang"), False),
        (7, 11, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Pulau Pinang", "state", only("Pulau Pinang"), False),
        (7, 21, "Tue", "hol", "Hol of Almarhum Sultan Iskandar (Johor)", "state", only("Johor"), False),
        (7, 22, "Wed", "state_day", "Sarawak Independence Day", "state", only("Sarawak"), False),
        (7, 31, "Fri", "ruler_birthday", "Birthday of Sultan of Pahang", "state", only("Pahang"), False),
        (8, 24, "Mon", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Melaka", "state", only("Melaka"), False),
        (8, 25, "Tue", "maulidur_rasul", "Prophet Muhammad's Birthday (Maulidur Rasul)", "federal", ALL, False),
        (8, 31, "Mon", "national_day", "National Day (Hari Merdeka)", "federal", ALL, False),
        (9, 1, "Tue", "state_special", "Selangor state holiday (SUKMA 2026)", "additional", only("Selangor"), False),
        (9, 16, "Wed", "malaysia_day", "Malaysia Day", "federal", ALL, False),
        (9, 29, "Tue", "ruler_birthday", "Birthday of Sultan of Kelantan", "state", only("Kelantan"), False),
        (9, 30, "Wed", "ruler_birthday", "Birthday of Sultan of Kelantan (2nd day)", "state", only("Kelantan"), False),
        (10, 10, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sarawak", "state", only("Sarawak"), False),
        (10, 25, "Sun", "state_special", "Silver Jubilee of the Sultan of Selangor's reign", "additional", only("Selangor"), False),
        (11, 6, "Fri", "ruler_birthday", "Birthday of Sultan of Perak", "state", only("Perak"), False),
        (11, 8, "Sun", "deepavali", "Deepavali", "federal", ALL_BUT_SARAWAK, True),
        (12, 11, "Fri", "ruler_birthday", "Birthday of Sultan of Selangor", "state", only("Selangor"), False),
        (12, 24, "Thu", "christmas_eve", "Christmas Eve", "state", only("Sabah"), False),
        (12, 25, "Fri", "christmas", "Christmas Day", "federal", ALL, False),
    ],
    2027: [
        (1, 1, "Fri", "new_year", "New Year's Day", "state", NEW_YEAR, False),
        (1, 6, "Wed", "israk_mikraj", "Israk and Mikraj", "state", ISRAK, False),
        (1, 14, "Thu", "ruler_birthday", "Birthday of Yang di-Pertuan Besar Negeri Sembilan", "state", only("Negeri Sembilan"), False),
        (1, 22, "Fri", "thaipusam", "Thaipusam", "state", THAIPUSAM, False),
        (2, 1, "Mon", "ft_day", "Federal Territory Day", "state", FT, False),
        (2, 6, "Sat", "cny", "Chinese New Year", "federal", ALL, False),
        (2, 7, "Sun", "cny_2", "Chinese New Year (2nd day)", "federal", CNY2_FED, False),
        (2, 7, "Sun", "cny_2", "Chinese New Year (2nd day)", "state", KT_TR, False),
        (2, 8, "Mon", "awal_ramadan", "Awal Ramadan", "state", JH_KD, True),
        (2, 20, "Sat", "state_day", "Declaration of Independence Day (Melaka)", "state", only("Melaka"), False),
        (2, 24, "Wed", "nuzul_quran", "Nuzul Al-Quran", "state", NUZUL, False),
        (3, 4, "Thu", "ruler_installation", "Anniversary of Installation of Sultan of Terengganu", "state", only("Terengganu"), False),
        (3, 10, "Wed", "hari_raya_puasa", "Hari Raya Aidilfitri", "federal", ALL, True),
        (3, 11, "Thu", "hari_raya_puasa_2", "Hari Raya Aidilfitri (2nd day)", "federal", ALL, True),
        (3, 12, "Fri", "hari_raya_puasa_3", "Hari Raya Aidilfitri (3rd day)", "state", only("Melaka"), True),
        (3, 23, "Tue", "ruler_birthday", "Birthday of Sultan of Johor", "state", only("Johor"), False),
        (3, 26, "Fri", "good_friday", "Good Friday", "state", only("Sabah", "Sarawak"), False),
        (3, 30, "Tue", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sabah", "state", only("Sabah"), False),
        (4, 26, "Mon", "ruler_birthday", "Birthday of Sultan of Terengganu", "state", only("Terengganu"), False),
        (5, 1, "Sat", "labour_day", "Labour Day", "federal", ALL, False),
        (5, 16, "Sun", "arafah", "Arafah Day", "state", KT_TR, False),
        (5, 17, "Mon", "ruler_birthday", "Birthday of Raja of Perlis", "state", only("Perlis"), False),
        (5, 17, "Mon", "hari_raya_haji", "Hari Raya Aidiladha (Haji)", "federal", ALL, True),
        (5, 18, "Tue", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "federal", KT_TR, True),
        (5, 18, "Tue", "hari_raya_haji_2", "Hari Raya Aidiladha (2nd day)", "state", KD_PL, True),
        (5, 20, "Thu", "wesak", "Wesak Day", "federal", ALL, False),
        (5, 22, "Sat", "hol", "Hol of Almarhum Sultan Ahmad Shah (Pahang)", "state", only("Pahang"), False),
        (5, 30, "Sun", "kaamatan", "Harvest Festival (Pesta Kaamatan)", "state", only("Labuan", "Sabah"), False),
        (5, 31, "Mon", "kaamatan", "Harvest Festival (Pesta Kaamatan, 2nd day)", "state", only("Labuan", "Sabah"), False),
        (6, 1, "Tue", "gawai", "Gawai Dayak", "state", only("Sarawak"), False),
        (6, 2, "Wed", "gawai", "Gawai Dayak (2nd day)", "state", only("Sarawak"), False),
        (6, 6, "Sun", "awal_muharram", "Awal Muharram (Maal Hijrah)", "federal", ALL, False),
        (6, 7, "Mon", "agong_birthday", "Birthday of the Yang di-Pertuan Agong", "federal", ALL, False),
        (6, 20, "Sun", "ruler_birthday", "Birthday of Sultan of Kedah", "state", only("Kedah"), False),
        (7, 7, "Wed", "state_day", "George Town World Heritage City Day", "state", only("Pulau Pinang"), False),
        (7, 10, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Pulau Pinang", "state", only("Pulau Pinang"), False),
        (7, 11, "Sun", "hol", "Hol of Almarhum Sultan Iskandar (Johor)", "state", only("Johor"), False),
        (7, 22, "Thu", "state_day", "Sarawak Independence Day", "state", only("Sarawak"), False),
        (7, 30, "Fri", "ruler_birthday", "Birthday of Sultan of Pahang", "state", only("Pahang"), False),
        (8, 15, "Sun", "maulidur_rasul", "Prophet Muhammad's Birthday (Maulidur Rasul)", "federal", ALL, False),
        (8, 24, "Tue", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Melaka", "state", only("Melaka"), False),
        (8, 31, "Tue", "national_day", "National Day (Hari Merdeka)", "federal", ALL, False),
        (9, 16, "Thu", "malaysia_day", "Malaysia Day", "federal", ALL, False),
        (9, 29, "Wed", "ruler_birthday", "Birthday of Sultan of Kelantan", "state", only("Kelantan"), False),
        (9, 30, "Thu", "ruler_birthday", "Birthday of Sultan of Kelantan (2nd day)", "state", only("Kelantan"), False),
        (10, 9, "Sat", "ruler_birthday", "Birthday of Yang di-Pertua Negeri Sarawak", "state", only("Sarawak"), False),
        (10, 28, "Thu", "deepavali", "Deepavali", "federal", ALL_BUT_SARAWAK, True),
        (11, 5, "Fri", "ruler_birthday", "Birthday of Sultan of Perak", "state", only("Perak"), False),
        (12, 11, "Sat", "ruler_birthday", "Birthday of Sultan of Selangor", "state", only("Selangor"), False),
        # The FMM table prints "24 Thu"; 24 Dec 2027 is a Friday (Christmas Eve is the 24th by definition).
        (12, 24, "Fri", "christmas_eve", "Christmas Eve", "state", only("Sabah"), False),
        (12, 25, "Sat", "christmas", "Christmas Day", "federal", ALL, False),
        (12, 26, "Sun", "israk_mikraj", "Israk and Mikraj", "state", ISRAK, False),
    ],
}
# Holidays announced after the gazette, keyed by (year, month, day).
ADDITIONAL_SRC = {
    (2025, 9, 15): "https://www.fmm.org.my/Articles/Details/Branch_Circulars-@-Declaration_of_Public_Holiday_on_September_15,_2025_",
    (2026, 3, 20): "https://berita.rtm.gov.my/?p=581444",
    (2026, 9, 1): "https://www.fmm.org.my/article/circulars/fmm-selangor-kuala-lumpur-advisory-selangor-state-public-holiday-september-1-2026-sklb282026",
    (2026, 10, 25): "https://www.fmm.org.my/article/circulars/fmm-selangor-kuala-lumpur-advisory-declaration-of-state-holiday-sultan-of-selangor-25th-silver-jubilee-october-25-2026-sklb302026",
}


def build():
    rows = []
    for year, entries in H.items():
        for m, d, dow, key, desc, level, mask, stc in entries:
            day = date(year, m, d)
            assert day.strftime("%a") == dow, f"{day}: gazette says {dow}, calendar says {day:%a} ({desc})"
            assert len(mask) == 16 and set(mask) <= {"0", "1"}, f"bad mask for {day} {desc}"
            src = ADDITIONAL_SRC[(year, m, d)] if level == "additional" else SRC[year]
            for state, on in zip(STATES, mask):
                if on == "1":
                    rows.append({"date": day.isoformat(), "weekday": dow, "type": "Additional" if level == "additional" else "Holiday",
                                 "locale_name": state, "description": desc, "holiday_key": key, "level": level,
                                 "major_festival": key in MAJOR_FESTIVALS, "subject_to_change": stc,
                                 "transferred": False, "source": src})
    df = pd.DataFrame(rows)
    assert not df.duplicated(["date", "holiday_key", "locale_name"]).any(), "duplicate holiday rows"
    n_states = df.groupby(["date", "holiday_key"])["locale_name"].transform("nunique")
    df.insert(3, "locale", (n_states == len(STATES)).map({True: "National", False: "Regional"}))
    return df.sort_values(["date", "description", "locale_name"]).reset_index(drop=True)


if __name__ == "__main__":
    out = Path(__file__).parent / "data_my" / "malaysia_public_holidays.csv"
    out.parent.mkdir(exist_ok=True)
    df = build()
    df.to_csv(out, index=False)
    nat = df[df["locale"] == "National"].drop_duplicates(["date", "holiday_key"])
    print(f"Wrote {out} ({len(df)} rows, {df['date'].nunique()} dates)")
    for y in sorted(H):
        print(f"  {y}: {nat['date'].str.startswith(str(y)).sum()} nationwide holiday dates, "
              f"{df.loc[df['date'].str.startswith(str(y)), 'date'].nunique()} dates in at least one state")
