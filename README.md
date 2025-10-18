Clone the repository

<pre> ```bash 
git clone https://github.com/valentino-strebel/24_quizly_backend
cd 24_quizly_backend/core
```</pre>

Create and activate a virtual environment

<pre> ```bash 

# On Linux/Mac

python -m venv venv
source venv/bin/activate

# (optional) upgrade pip

python -m pip install --upgrade pip
```</pre>
<pre> ```bash 

# On Windows (PowerShell)

python -m venv venv
venv\Scripts\Activate
python -m pip install --upgrade pip
```</pre>

Install dependencies

<pre> ```bash 

pip install -r requirements.txt
```</pre>

Create your .env file

The project reads environment variables from core/.env (same folder as manage.py).

<pre> ```bash 

# from 24_quizly_backend/core

cp env.template .env
```</pre>

Generate a secret key and set DJANGO_SECRET_KEY in .env:

<pre> ```bash 

python - <<'PY'
import secrets; print(secrets.token_urlsafe(64))
PY
```</pre>

Leave the default SQLite settings as-is to run locally.

Ensure DJANGO_DEBUG=1 and DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

The provided CORS/CSRF defaults already allow a frontend on http://localhost:3000.

Apply database migrations

<pre> ```bash 

python manage.py migrate
```</pre>

Create a superuser (for admin access)

<pre> ```bash 

python manage.py createsuperuser
```</pre>

Run the development server

<pre> ```bash 
python manage.py runserver
 ``` </pre>

The server starts at http://127.0.0.1:8000/

Access the project

App: http://127.0.0.1:8000/

Admin: http://127.0.0.1:8000/admin/
