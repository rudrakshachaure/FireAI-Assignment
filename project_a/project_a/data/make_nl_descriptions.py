"""Writes data/nl_descriptions_50.jsonl. Gold = structured input, or needs_clarification + acceptable fields.
Run: python -m project_a.data.make_nl_descriptions"""
from __future__ import annotations

import json
from pathlib import Path


def G(gross, age="<60", basic=0, hra=0, rent=0, metro=False, ps=False, c80=0, nps=0, ds=0, dp=0, hl=0):
    return {"gross_salary": gross, "basic_plus_da": basic, "hra_received": hra, "rent_paid_annual": rent, "metro": metro,
            "age_band": age, "parent_senior": ps, "sec_80c": c80, "sec_80ccd_1b": nps, "sec_80d_self": ds,
            "sec_80d_parents": dp, "home_loan_interest": hl}


def Q(*fields):
    return {"needs_clarification": True, "fields": list(fields)}


E = [  # (style, text, gold)
 ("formal", "I am a salaried employee, 32 years old. My annual gross salary is Rs 18,00,000. I have invested Rs 1,50,000 in ELSS and PPF. I have no other deductions.", G(1800000, c80=150000)),
 ("hinglish", "meri salary 18 lakh saalana hai, 40k rent har mahine deta hu Pune mein. basic 9 lakh, HRA 3.6 lakh saal ka. umar 29. koi investment nahi hai.", G(1800000, basic=900000, hra=360000, rent=480000)),
 ("terse", "gross 12L, age 45, no investments, no loans.", G(1200000, age="<60")),
 ("units", "Salary 1.8 cr per annum, I'm 50. 80C maxed, NPS 50k extra, health insurance premium 25000 for me.", G(18000000, c80=150000, nps=50000, ds=25000)),
 ("formal", "Annual salary Rs 15,00,000, age 38. I pay Rs 1,20,000 rent a year in Mumbai, HRA received is Rs 1,80,000, basic is Rs 6,00,000. 80C is 1.5 lakh.", G(1500000, basic=600000, hra=180000, rent=120000, metro=True, c80=150000)),
 ("terse", "9L gross, 26yo, nothing invested.", G(900000)),
 ("senior", "I'm 62, gross salary 14 lakh per year. 80D 40k for myself. No other deductions.", G(1400000, age="60-79", ds=40000)),
 ("homeloan", "Gross salary 25 lakh annually, 41 years old, home loan interest 2.4 lakh per year on a self occupied house, 80C 1.5 lakh.", G(2500000, c80=150000, hl=240000)),
 ("monthly", "monthly gross 1.5 lakh, age 34, no deductions", G(1800000)),
 ("units", "I earn 24 LPA, age 31, put 50k in NPS (80CCD1B) and 1 lakh total in 80C.", G(2400000, c80=100000, nps=50000)),
 ("senior", "Age 71. Gross salary 8.5 lakh a year. Medical insurance 50,000 for self. Nothing else.", G(850000, age="60-79", ds=50000)),
 ("parents", "Age 55, annual salary 32L. I pay health insurance of 45,000 for my parents (age 68) and 20,000 for myself. 80C 1,50,000.", G(3200000, c80=150000, ds=20000, dp=45000, ps=True)),
 ("hra", "Gross 40,00,000 per year, age 44, rent 15,000 per month in Delhi, HRA 2,40,000 per year, basic 16,00,000 per year. 80C 1.5L.", G(4000000, basic=1600000, hra=240000, rent=180000, metro=True, c80=150000)),
 ("formal", "I am 36 years of age with an annual gross salary of INR 21,60,000. I do not have any tax-saving investments or loans.", G(2160000)),
 ("rambling", "so basically last year I switched jobs, new job gives like 16 lakh gross annual, I'm 33, honestly I haven't invested anything at all, no loans either.", G(1600000)),
 ("parents", "gross 60L pa, age 48, 80C 1.5L, NPS 50k, 80D 25k for self, 50k for parents (father is 72), home loan interest 1.8L", G(6000000, c80=150000, nps=50000, ds=25000, dp=50000, ps=True, hl=180000)),
 ("terse", "5.5 lakh salary a year, 23 years old, no investments.", G(550000)),
 ("units", "I'm 28, gross 7,50,000 yearly, 80C total 1.5L (PPF+ELSS), nothing else.", G(750000, c80=150000)),
 ("hinglish", "meri salary 22 lakh saalana hai, umar 35, 80C mein poora 1.5 lakh bhara hai, baaki kuch nahi.", G(2200000, c80=150000)),
 ("units", "Gross 3 crore per annum, age 52, no deductions claimed.", G(30000000)),
 ("monthly", "Monthly basic 50k, monthly HRA 20k, monthly gross 1.2 lakh, rent 30k per month in Chennai, age 30, no investments.", G(1440000, basic=600000, hra=240000, rent=360000, metro=True)),
 ("terse", "age 29, 11 lakh gross a year, nothing to claim.", G(1100000)),
 ("hra", "I am 41. Gross salary is Rs. 28,50,000 p.a. 80C is 1,50,000. Rent 25,000 pm in Bangalore, HRA 1,20,000 pa, basic 11,40,000 pa.", G(2850000, basic=1140000, hra=120000, rent=300000, c80=150000)),
 ("formal", "Annual gross 19.5 lakh, age 37, 80D self 25k and 80C 1.5 lakh. Nothing else.", G(1950000, c80=150000, ds=25000)),
 ("terse", "14L, 40y, nil deductions", G(1400000)),
 ("senior", "I am 83 years old, annual salary 12 lakh, I pay 40k premium for self. No other deductions.", G(1200000, age="80+", ds=40000)),
 ("homeloan", "gross 17 lakhs per year, im 27, home loan interest 1.2 lakh self occupied, no other investments", G(1700000, hl=120000)),
 ("parents", "30 lakh gross a year, 46 years, 80C 1.5 lakh, 80CCD(1B) 50k, 80D self 25k, parents 50k (mom is 63)", G(3000000, c80=150000, nps=50000, ds=25000, dp=50000, ps=True)),
 ("terse", "salary 6,00,000 per annum, age 24, I live with my parents, no rent, no investments.", G(600000)),
 ("hra", "Gross annual salary 13 lakh. I'm 39. Rent 20,000 per month in Hyderabad, HRA 96000 yearly, basic 5.2 lakh yearly, 80C 80k. Nothing else.", G(1300000, basic=520000, hra=96000, rent=240000, c80=80000)),
 ("homeloan", "age 58, gross 45L annually, no investments but home loan interest of 2L.", G(4500000, hl=200000)),
 ("units", "annual gross 10,00,000, age 30, 80C 1 lakh, no other deductions", G(1000000, c80=100000)),
 ("units", "My gross salary is 2 crore per year. Age 47. 80C 1.5L, nothing else.", G(20000000, c80=150000)),
 ("parents", "my parents are senior citizens and I pay 60k premium for them. gross 30L a year, age 45, 80C 1.5L, nothing else.", G(3000000, c80=150000, dp=60000, ps=True)),
 # ---- should trigger a clarifying question ----
 ("ambiguity", "I earn 85000", Q("gross_salary")),
 ("ambiguity", "my CTC is 20 lakh, age 30, no investments", Q("gross_salary")),
 ("hinglish", "meri salary 18 lakh hai, 40k rent deta hu Pune mein", Q("age_band", "rent_paid", "hra_received", "basic_plus_da", "deductions")),
 ("missing", "I'm 30 and earn 15L gross a year. I pay 20k rent in Mumbai.", Q("rent_paid", "hra_received", "basic_plus_da", "deductions")),
 ("contradiction", "gross 18L, age 33, I live in a metro city (Pune), rent 30k per month, HRA 1.8 lakh a year, basic 7.2 lakh a year, no investments", Q("metro")),
 ("contradiction", "My 80C is maxed out but also I haven't invested anything. Gross 12L a year, age 35.", Q("sec_80c")),
 ("ambiguity", "I pay 30k a year for my parents' medical insurance. Gross 20L a year, age 40, 80C 1.5L, nothing else.", Q("parent_senior")),
 ("missing", "Salary 18L a year", Q("age_band", "deductions")),
 ("missing", "I'm 29, gross 14 lakh a year.", Q("deductions")),
 ("contradiction", "I earn 12L a year, no wait my total comes to 15L a year, age 30, no investments", Q("gross_salary")),
 ("contradiction", "Rent is 50 lakh a year, salary 8 lakh a year, age 30, no investments, HRA 2L, basic 4L, Delhi.", Q("rent_paid")),
 ("missing", "Salary 20L a year, age 34, HRA 2.4L, I rent in Bangalore, no investments", Q("basic_plus_da", "rent_paid")),
 ("hinglish", "Bhai 1.5L per month milti hai CTC", Q("gross_salary", "age_band", "deductions")),
 ("vague", "I earn 25 lakh a year and I'm 40 and I have some investments", Q("deductions", "sec_80c")),
 ("ambiguity", "I get 1.2 lakh a month plus 3 lakh bonus yearly, age 31, no investments", Q("gross_salary")),
 ("ambiguity", "Total package 45 lakh a year, 50 years old, 80C 1.5L, nothing else", Q("gross_salary")),
]
assert len(E) == 50 and sum(1 for e in E if "needs_clarification" in e[2]) >= 15

if __name__ == "__main__":
    out = Path(__file__).parent / "nl_descriptions_50.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for i, (style, text, gold) in enumerate(E, 1):
            f.write(json.dumps({"id": f"nl{i:02d}", "style": style, "text": text, "gold": gold}, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(E)} rows)")
