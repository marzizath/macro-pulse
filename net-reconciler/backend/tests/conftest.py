import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.services.basiq_client import to_domain_transaction
from app.services.splitwise_client import to_domain_expense

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
MY_USER_ID = 10001


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def bank_sample():
    with open(os.path.join(FIXTURES_DIR, "bank_sample.json")) as f:
        raw = json.load(f)
    return [to_domain_transaction(t) for t in raw]


@pytest.fixture()
def bank_sample_raw():
    with open(os.path.join(FIXTURES_DIR, "bank_sample.json")) as f:
        return json.load(f)


@pytest.fixture()
def splitwise_sample():
    with open(os.path.join(FIXTURES_DIR, "splitwise_sample.json")) as f:
        raw = json.load(f)
    return [to_domain_expense(e, MY_USER_ID) for e in raw["expenses"]]


@pytest.fixture()
def splitwise_sample_raw():
    with open(os.path.join(FIXTURES_DIR, "splitwise_sample.json")) as f:
        return json.load(f)["expenses"]
