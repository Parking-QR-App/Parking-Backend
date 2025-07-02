## Installation

### Prerequisites
- Python 3.7+
- Django 4.0+
- Dependencies: Install using `pip install -r requirements.txt`

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/Riyaansh-Mittal/AI-Script-Generator.git
   cd AI-Script-Generator
2. Create a virtual environment and activate it:
   ```bash
   python -m venv env
   source env/bin/activate  # On Windows use `env\Scripts\activate`
3. Install requirements:
   ```bash
   pip install -r requirements.txt
4. Make Migrations:
   ```bash
   python manage.py makemigrations
5. Apply migrations:
   ```bash
   python manage.py migrate
6. Create admin:
   ```bash
   python manage.py createsuperuser
7. Run cleanup tasks
   ```bash
   python manage.py schedule_cleanup
6. Start the Django server:
   ```bash
   python manage.py runserver

### Celery and Task Scheduling
1. Start Celery Beat
   ```bash
   celery -A scanQR beat --loglevel=info
3. Start Celery Worker
   ```bash
   celery -A scanQR worker --loglevel=info -P gevent
