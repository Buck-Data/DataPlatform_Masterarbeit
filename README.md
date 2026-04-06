# Scrap Data Platform

Prototyp einer Datenplattform fuer Metallschrottkreislaufsysteme im Rahmen einer Masterarbeit.

GitHub-Repository: https://github.com/Buck-Data/DataPlatform_Masterarbeit

## Stack

- Streamlit
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Casbin

## Projektstart

Am einfachsten per Docker:

```bash
docker-compose up --build
```

Danach erreichbar unter:

- Streamlit: `http://localhost:8501`
- FastAPI Docs: `http://localhost:8000/docs`

## Nutzung durch Dritte

Wenn du das Projekt jemand anderem zur Verfügung stellen willst, ist der einfachste Ablauf:

1. Repository klonen

```bash
git clone <REPO-URL>
cd <REPO-ORDNER>
```

2. Docker installieren

Benötigt wird eine lokale Docker-Installation, z. B. Docker Desktop.

3. Projekt starten

```bash
docker-compose up --build
```

Danach ist die Anwendung erreichbar unter:

- Streamlit: `http://localhost:8501`
- FastAPI Docs: `http://localhost:8000/docs`

Hinweise:

- Python, PostgreSQL und Alembic müssen lokal nicht separat installiert werden.
- Die Datenbank wird automatisch mit Docker gestartet.
- Migrationen und Seed-Daten werden beim Start des API-Containers automatisch ausgeführt.

Für spätere Starts reicht in der Regel:

```bash
docker-compose up
```

Wenn alles vollständig zurückgesetzt werden soll, inklusive Datenbankdaten:

```bash
docker-compose down -v
docker-compose up --build
```

## Lokaler Start ohne Docker

Voraussetzung: laufende PostgreSQL-Datenbank.

```bash
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
streamlit run app/main.py
```

In einem zweiten Terminal:

```bash
uvicorn app.api.main:app --reload
```

## Wichtige Variable

```bash
DATABASE_URL=postgresql://scrap_user:scrap_pass@localhost:5432/scrap_platform
```

## Hinweis zum Deployment

Das Projekt besteht aktuell aus Streamlit, FastAPI und PostgreSQL. 
Fuer Streamlit Community Cloud reicht das Repo daher nicht allein aus, dafuer braeuchte es zusaetzlich ein extern gehostetes Backend und eine externe Datenbank.
