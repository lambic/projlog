from app.models import User
from app import db
import unittest

class CreateUser(unittest.TestCase):
    u = User(username='max',email='maxlambert@gmail.com', password='Cyclone1')
    db.session.add(u)# @UndefinedVariable
    db.session.commit(u)# @UndefinedVariable
    
    
class TestCase(unittest.TestCase):
    #...
    def test_follow(self):
        u1 = User(nickname = 'john', email = 'john@example.com')
        u2 = User(nickname = 'susan', email = 'susan@example.com')
        db.session.add(u1)  # @UndefinedVariable
        db.session.add(u2)  # @UndefinedVariable
        db.session.commit()  # @UndefinedVariable
        assert u1.unfollow(u2) == None
        u = u1.follow(u2)
        db.session.add(u)# @UndefinedVariable
        db.session.commit()# @UndefinedVariable
        assert u1.follow(u2) == None
        assert u1.is_following(u2)
        assert u1.followed.count() == 1
        assert u1.followed.first().nickname == 'susan'
        assert u2.followers.count() == 1
        assert u2.followers.first().nickname == 'john'
        u = u1.unfollow(u2)
        assert u != None
        db.session.add(u)# @UndefinedVariable
        db.session.commit()# @UndefinedVariable
        assert u1.is_following(u2) == False
        assert u1.followed.count() == 0
        assert u2.followers.count() == 0