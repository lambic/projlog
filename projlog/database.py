from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import config
from contextlib import contextmanager
#  
db_connect_str = config.SQLALCHEMY_DATABASE_URI
engine = create_engine(db_connect_str, convert_unicode=True)
Session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))


Base = declarative_base()
Base.query = Session.query_property()


def init_db():
    # import all modules here that might define models so that
    # they will be registered properly on the metadata.  Otherwise
    # you will have to import them first before calling init_db()
    from projlog import models
    Base.metadata.create_all(bind=engine)

 
    

        


