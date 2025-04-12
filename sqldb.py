from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, select, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pytz import timezone

est_timezone = timezone('US/Eastern')
datetime_est = datetime.now(est_timezone)

# Create an SQLite engine (a file named "app.db")
engine = create_engine("sqlite:///app.db", echo=True)
Base = declarative_base()

# Create a session

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    date_added = Column(DateTime, default=datetime_est)

    # Relationship to store subscription history
    subscriptions = relationship("SubscriptionHistory", back_populates="customer")


class SubscriptionHistory(Base):
    __tablename__ = "subscription_history"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    event = Column(String)  # e.g., "subscribed", "unsubscribed", etc.
    timestamp = Column(DateTime, default=datetime_est)
    stripe_active = Column(Integer, default=0)
    exists_on_plex = Column(Integer, default=0)
    current = Column(Boolean, default=True)
    end_date = Column(DateTime)

    customer = relationship("Customer", back_populates="subscriptions")


def add_subscription_history(customer_id, event, session, end_date=None):
    if event == "unsubscribe":
        # Update any previous history records for this customer to not be current
        stmt = select(SubscriptionHistory).where((SubscriptionHistory.customer_id ==
                                                 customer_id) & (SubscriptionHistory.current == True))
        result = session.execute(stmt)
        customer_record = result.scalar_one()
        if customer_record:
            customer_record.current = 0
        # Create and add the new record with current flag True
        new_history = SubscriptionHistory(customer_id=customer_id, event=event, stripe_active=0, exists_on_plex=0,
                                          current=True, end_date=end_date)
        session.add(new_history)
        session.commit()
    elif event == "subscription":
        history = SubscriptionHistory(customer_id=customer_id, event=event, stripe_active=1, exists_on_plex=1)
        session.add(history)
        session.commit()
    elif event == "update_subscription":
        current_status = current_plex_status(customer_id, session)
        current_status.current = 0
        new_history = SubscriptionHistory(customer_id=customer_id, event=event, stripe_active=0, exists_on_plex=0,
                                          current=True, end_date=end_date)
        session.add(new_history)
        session.commit()

    else:
        history = SubscriptionHistory(customer_id=customer_id, event=event, stripe_active=1, exists_on_plex=0)
        session.add(history)
        session.commit()

def add_customer(email, session):
    customer= find_customer(email,session)
    if not customer:
        new_customer = Customer(email=email)
        session.add(new_customer)
        session.commit()
    else:
        print("Customer already exists")

def find_customer(email, session):
    stmt = select(Customer).where(Customer.email == email)
    result = session.execute(stmt)
    customer_record = result.scalar_one_or_none()
    return customer_record


def current_plex_status(id, session):
    stmt = select(SubscriptionHistory).where((SubscriptionHistory.customer_id == id)
                                             & (SubscriptionHistory.current == 1))
    result = session.execute(stmt)

    customer_record = result.scalar_one_or_none()
    return customer_record

#newfinaltese@gmail.com


