# Scrap Data Platform – Prototyp Masterarbeit

Prototyp für eine Datenplattform in Metallschrottkreislaufsystemen.
Implementiert vier ausgewählte Anforderungen aus einem 19-Punkte-Katalog.

## Schnellstart

```bash
docker-compose up --build
```

Nach dem Start (ca. 30–60 Sekunden):
- **Streamlit-App:** http://localhost:8501
- **FastAPI-Docs:** http://localhost:8000/docs

## Anforderungen (implementiert)

| ID | Bezeichnung | Seite |
|----|-------------|-------|
| F3 | Chemische Zusammensetzung mit Grenzwertwarnung | Chemische Analyse |
| F8 | Logistik- und Abholkoordination | Logistikkoordination |
| F2 | Digitaler Materialpass (versioniert) | Materialpass |
| T2+O1 | Datensouveränität via ABAC (Casbin) | Materialpass |

## Demo-Rollen

Der Rollenumschalter befindet sich in der Sidebar.

| Rolle | Organisation | Sieht |
|-------|-------------|-------|
| Metallverarbeiter | Müller Metallverarbeitung GmbH | Basisinfos, Bezugsquelle, Preis |
| Händler | Schrotthandel Bauer & Söhne | Basisinfos, Grenzwertstatus |
| Stahlwerk | Süddeutsche Stahlwerke AG | Chemische Details, EAF-Kompatibilität |

## Struktur

```
app/
├── main.py                    # Streamlit Startseite
├── pages/
│   ├── 1_Chargenübersicht.py
│   ├── 2_Materialpass.py      # ABAC-Kerndemo
│   ├── 3_Chemische_Analyse.py
│   └── 4_Logistikkoordination.py
├── auth/session.py            # Rollensimulation
├── abac/
│   ├── engine.py              # Casbin-Wrapper
│   ├── abac_model.conf        # ABAC-Modell
│   └── abac_policy.csv        # Zugriffsrichtlinien
├── db/
│   ├── models.py              # SQLAlchemy-Modelle (9 Entitäten)
│   ├── session.py
│   └── seed.py                # Testdaten
├── services/                  # Business-Logik
└── api/main.py                # FastAPI (separat)
alembic/                       # Datenbankmigrationen
docker-compose.yml
```

## Lokale Entwicklung (ohne Docker)

```bash
# PostgreSQL lokal starten, dann:
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
streamlit run app/main.py
# In einem zweiten Terminal:
uvicorn app.api.main:app --reload
```

## Umgebungsvariablen

| Variable | Standard |
|----------|---------|
| DATABASE_URL | postgresql://scrap_user:scrap_pass@localhost:5432/scrap_platform |

## Seed-Daten

5 Schrottchargen (E1, E6, E8, E3C, ECS01), davon:
- SB-2024-0002: Cu = 0,38 % (Grenzwert 0,30 %) → Warnung aktiv
- SB-2024-0003: Cu = 0,52 % → EAF-Kompatibilität "nicht geeignet"
- SB-2024-0001: Alle Werte im Normalbereich, zertifiziert
