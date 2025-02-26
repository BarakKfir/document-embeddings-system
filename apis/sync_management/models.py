
from sqlalchemy import Column, Integer, String, DateTime, Enum, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum
from datetime import datetime

Base = declarative_base()

class DocumentStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class SyncJob(Base):
    __tablename__ = 'sync_jobs'
    
    id = Column(Integer, primary_key=True)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class JobLog(Base):
    __tablename__ = 'job_logs'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)
    message = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Database connection
engine = create_engine('sqlite:///sync_management.db')
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables
Base.metadata.create_all(engine)
