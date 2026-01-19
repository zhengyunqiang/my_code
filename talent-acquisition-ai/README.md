# Talent Acquisition AI System

A production-grade, AI-powered talent acquisition system built with **LangGraph** orchestration and **Qwen (千问)** LLM integration.

## 🎯 Overview

This system automates the entire recruitment pipeline through four intelligent phases:

1. **Requirement Analysis & JD Generation** - Multi-modal input processing with RAG-enhanced context
2. **Intelligent Screening & Automation** - Semantic matching + RPA automated communication
3. **Interview Feedback & Optimization** - Automated feedback collection with JD dynamic tuning
4. **Onboarding & Talent Asset Management** - Complete onboarding workflows with talent pool

## ✨ Key Features

### Phase 1: Smart JD Generation
- 📝 Multi-modal input support (chat logs, documents, voice-to-text)
- 🔍 RAG-powered context injection from project history
- ❓ Intelligent clarification with 5-10 key questions
- 📄 Professional JD generation with keyword extraction

### Phase 2: AI-Powered Screening
- 🎯 Semantic matching beyond simple keywords
- 🤖 RPA automation for Boss Zhipin (Boss直聘) platform
- 📋 Resume standardization with privacy protection
- 🏆 Automated candidate ranking and scoring

### Phase 3: Feedback Loop Optimization
- ⏰ Automated feedback reminder system
- 📊 JD performance analysis based on interview outcomes
- 🔄 Dynamic JD optimization suggestions
- 📈 Continuous improvement through feedback analytics

### Phase 4: Talent Management
- ✅ Complete onboarding workflow tracking
- 👥 Automated talent profile generation
- 🔍 Intelligent talent pool search
- 💡 AI-powered talent recommendations

## 🛠️ Tech Stack

- **Backend Framework**: FastAPI
- **Orchestration**: LangGraph
- **LLM**: Qwen / DashScope API
- **Database**: PostgreSQL with Async SQLAlchemy
- **Cache**: Redis
- **Task Queue**: Celery
- **Monitoring**: Prometheus + Sentry
- **Automation**: Playwright (RPA)

## 📦 Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Qwen API Key

### Setup Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd talent-acquisition-ai
```

2. **Install dependencies**
```bash
pip install poetry
poetry install
```

3. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Initialize database**
```bash
python -m database.migrations.init reset
```

5. **Start the application**
```bash
./scripts/start_dev.sh
```

Or manually:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 🔑 Configuration

Key environment variables (see `.env.example`):

```env
# Qwen API
QWEN_API_KEY=your-qwen-api-key-here

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/talent_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# Boss Zhipin RPA (Optional)
BOSS_USERNAME=your-username
BOSS_PASSWORD=your-password
```

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **Health Check**: http://localhost:8000/health

### Core API Endpoints

#### JD Generation
```bash
# Create JD request
POST /api/v1/jd/requests

# Analyze requirement
GET /api/v1/jd/requests/{request_id}/analyze

# Submit clarifications
POST /api/v1/jd/requests/{request_id}/clarify

# Generate final JD
POST /api/v1/jd/requests/{request_id}/generate
```

#### Candidate Screening
```bash
# Upload and process resume
POST /api/v1/resumes/upload

# Batch screening
POST /api/v1/screening/batch

# Get ranked candidates
GET /api/v1/jobs/{job_id}/candidates
```

#### Talent Pool
```bash
# Search talent pool
POST /api/v1/talent/search

# Get recommendations
GET /api/v1/jobs/{job_id}/recommendations
```

## 🔄 Workflow Example

Complete recruitment workflow using LangGraph:

```python
from app.workflows.recruitment_graph import workflow_executor, RecruitmentState

# Initialize state
state = RecruitmentState(
    request_id="unique-id",
    phase="jd_generation",
    # ... other fields
)

# Execute complete workflow
final_state = await workflow_executor.execute_complete_workflow(state)
```

## 🧪 Testing

```bash
# Run unit tests
pytest tests/unit

# Run integration tests
pytest tests/integration

# Run with coverage
pytest --cov=app --cov-report=html
```

## 📊 Monitoring

- **Metrics**: http://localhost:8000/metrics (Prometheus)
- **Logs**: Check `./logs` directory
- **Sentry**: Configure DSN in `.env` for error tracking

## 🚀 Deployment

### Docker Deployment

```bash
docker-compose up -d
```

### Production Considerations

1. Use environment-specific configuration
2. Enable SSL/TLS
3. Configure proper CORS
4. Set up log aggregation
5. Configure database backups
6. Enable rate limiting
7. Use production WSGI server (Gunicorn)

## 📁 Project Structure

```
talent-acquisition-ai/
├── app/
│   ├── agents/           # LangGraph agents
│   ├── api/              # API routes
│   ├── core/             # Core functionality
│   ├── models/           # Database & Pydantic models
│   ├── services/         # Business logic
│   ├── utils/            # Utilities
│   └── workflows/        # LangGraph workflows
├── database/
│   └── migrations/       # DB migrations
├── tests/
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
├── docs/                # Documentation
├── scripts/             # Utility scripts
└── static/              # Static files
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📝 License

This project is proprietary software. All rights reserved.

## 👥 Authors

- **Your Name** - Initial work

## 🙏 Acknowledgments

- Qwen (千问) team for the excellent LLM API
- LangGraph team for the workflow orchestration framework
- FastAPI team for the amazing web framework
