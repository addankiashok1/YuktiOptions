# YuktiOptions

A full-stack options trading simulation platform for paper-trading, strategy testing, and learning options mechanics — without risking real capital.

---

## Tech Stack

| Layer     | Technology                  |
|-----------|-----------------------------|
| Backend   | Python · FastAPI · SQLAlchemy |
| Frontend  | React · TypeScript · Vite    |
| Database  | PostgreSQL                   |
| Cache     | Redis                        |
| Container | Docker · Docker Compose      |

---

## Project Structure

```
YuktiOptions/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── auth.py          # JWT authentication
│   │   ├── db.py            # Database session
│   │   ├── deps.py          # Shared dependencies
│   │   └── routers/         # API route modules
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api.ts
│   │   └── main.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node 18+
- Docker & Docker Compose

### 1. Clone & configure

```bash
git clone https://github.com/your-org/YuktiOptions.git
cd YuktiOptions
cp .env.example .env        # fill in DB_URL, SECRET_KEY, REDIS_URL
```

### 2. Run with Docker

```bash
docker compose up --build
```

### 3. Run locally (without Docker)

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

### Endpoints

| Service  | URL                    |
|----------|------------------------|
| API      | http://localhost:8000  |
| API docs | http://localhost:8000/docs |
| Frontend | http://localhost:5173  |

---

## Environment Variables

Copy `.env.example` and set the following:

```
DATABASE_URL=postgresql://user:password@localhost:5432/yuktioptions
SECRET_KEY=your-secret-key
REDIS_URL=redis://localhost:6379
```

---

## License

MIT
