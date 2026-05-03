from sqlalchemy import Boolean, Column, ForeignKey,Integer,String

from .database import Base

class Ourdata(Base):
    __tablename__='emailid'

    shipping_id = Column(Integer, primary_key=True, index=True)
    id=Column(String,index=True)

