Clone the repository

git clone https://github.com/valentino-strebel/24_quizly_backend
cd 24_quizly_backend/core

Create and activate a virtual environment

# On Linux/Mac

python -m venv venv
source venv/bin/activate

# (optional) upgrade pip

python -m pip install --upgrade pip

# On Windows (PowerShell)

python -m venv venv
venv\Scripts\Activate
python -m pip install --upgrade pip

Install dependencies

pip install -r requirements.txt

Create your .env file

The project reads environment variables from core/.env (same folder as manage.py).

# from 24_quizly_backend/core

cp env.template .env

Generate a secret key and set DJANGO_SECRET_KEY in .env:

python - <<'PY'
import secrets; print(secrets.token_urlsafe(64))
PY

Leave the default SQLite settings as-is to run locally.

Ensure DJANGO_DEBUG=1 and DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

The provided CORS/CSRF defaults already allow a frontend on http://localhost:3000.

Apply database migrations

python manage.py migrate

Create a superuser (for admin access)

python manage.py createsuperuser

Run the development server

python manage.py runserver

The server starts at http://127.0.0.1:8000/

Access the project

App: http://127.0.0.1:8000/

Admin: http://127.0.0.1:8000/admin/
