# is2108-PP35
Hello Prof :D

DeLaundry - IS2108 Pair Project
Group number: 35

GROUP MEMBERS

Member 1 (Group Leader)
Full name: Phee Hong En, Chrio
Student number: A0321866Y
Email: e1524773@u.nus.edu
Contact number: 8251 1722

Member 2
Full name: Matt Tan Yong
Student number: A0320966Y
Email: e1523873@u.nus.edu
Contact number: 9147 3557


FULL DEMO VIDEO
YouTube link: https://youtu.be/7CQUtty9WPc

RUNNING THE APPLICATION (WINDOWS POWERSHELL)

Use Python 3.12. Run the following from the extracted project root,
which contains requirements.txt and the Delaundry folder:

py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd Delaundry
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000

Open http://127.0.0.1:8000/accounts/login/ (the root URL is not the home page).
Customer registration: http://127.0.0.1:8000/accounts/register/
Worker registration: http://127.0.0.1:8000/accounts/worker/register/
Worker login: http://127.0.0.1:8000/accounts/worker/login/
Staff login: http://127.0.0.1:8000/adminpanel/login/

Use the superuser username and password for staff login. Entries are case sensitive, and ensure that passwords are minimally 8 characters long.

Customers and workers register separately with different @u.nus.edu email addresses. You may consider using e1234567@u.nus.edu and e7654321@u.nus.edu as dummy accounts.

Choose the same hall for the customer and worker to demonstrate acceptance.
Staff must approve the worker before the worker can accept new tasks.

Migrations seed the fixed halls, laundry rooms and machines.
An internet connection is needed to load the Bootstrap stylesheet.
Delivery proof requires a valid JPEG or PNG (maximum 5 MB and 12 megapixels).

OPTIONAL LOCAL DEMO CLOCK FOR SIMULATED RUNS

The normal web application uses real time. Demo mode uses a separate database and uploads for each named session, and allows time-dependent stages, such as washing, drying, and return, to be demonstrated without waiting for the 30-minute cycles. You do NOT need to change your computer clock.

In the active virtual environment, from the Delaundry directory, run:

$env:DELAUNDRY_DEMO = "1"
$env:DELAUNDRY_DEMO_SESSION = "demo1"
python manage.py demo_clock set "2026-11-16 09:45"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000

Initialize the clock before migrating a fresh demo database. Register fresh
customer and worker accounts; normal accounts are not copied to demo mode.
Book and accept the 10:00-12:00 window before advancing the clock.

In a SECOND terminal, activate the same virtual environment, enter the
Delaundry directory and select the same session:

$env:DELAUNDRY_DEMO = "1"
$env:DELAUNDRY_DEMO_SESSION = "demo1"
python manage.py demo_clock show

Run each following command only when ready for that stage, refreshing the
website after changing the time. Here's an example:

python manage.py demo_clock set "2026-11-16 10:00"
Then record collection and start washing.

python manage.py demo_clock set "2026-11-16 10:30"
Then finish washing and start drying.

python manage.py demo_clock set "2026-11-16 11:00"
Then finish drying and submit delivery proof.

Time remains frozen until advanced. Use a new session name in both terminals for a fresh demonstration. Use separate browser profiles to keep customer, worker and staff logged in simultaneously.

To return to normal mode, stop the demo server and run in each terminal:

Remove-Item Env:DELAUNDRY_DEMO -ErrorAction SilentlyContinue
Remove-Item Env:DELAUNDRY_DEMO_SESSION -ErrorAction SilentlyContinue

Then, in the server terminal:

python manage.py migrate
python manage.py runserver 127.0.0.1:8000
