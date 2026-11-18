# Christ the King Daramombe High School — FindIt

Smart lost-and-found for school. Flask + SQLite + HTML/CSS, no special hardware.

## Run
```
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000 (other devices on the same Wi-Fi: http://YOUR-LAPTOP-IP:5000).

Before Open Day set your own secrets:
```
export STAFF_PASSWORD="something-only-you-know"
export SECRET_KEY="any-long-random-text"
```
Default staff password is `daramombe2026`. Change it.

## Open Day demo (2 minutes)
1. Log in at **Staff**, click **Reset demo** (clean slate with a few background items).
2. As a student: **I lost something** → Calculator, Black, Library, today → submit. Note the code.
3. As staff: **Register found item** → Calculator, Black, Library, today.
4. Open **Check my report** with the code: a "Strong match" appears.
5. Staff dashboard → **Mark returned**.

Tip: open the student page on a phone and the staff page on the laptop.

## How matching works
Category must match. Then points: same colour +25 (Multicolour +8), same location +20,
date closeness up to +15. Base 40. Shown from 50%; 80+ Strong, 65+ Likely.
Students only see category, colour, place and date of found items, never who found them
or who lost things.
