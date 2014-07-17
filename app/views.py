from app import app, db, login_manager
from sqlalchemy.sql.expression import insert
import os
from functools import wraps
from forms import *
from flask import render_template, flash, redirect , Flask, url_for, request, g, session
from flask_login import login_user, logout_user, login_required, current_user, LoginManager
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from models import  FriendRequest, friendships, Notification, Post, Project
import config
from file_lib import *
import time, base64, urllib, json, hmac
from hashlib import sha1
from werkzeug.utils import secure_filename
import boto
from PIL import Image
from flask_wtf.csrf import CsrfProtect
csrf = CsrfProtect()


def notification_viewed(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'nid' in request.args:
            nid = request.args.get('nid')
            notif = db.session.query(Notification).get(nid) # @UndefinedVariable
            if not notif.seen:
                notif.seen=True
                db.session.add(notif)# @UndefinedVariable
                db.session.commit()# @UndefinedVariable
        return f(*args, **kwargs)
    return decorated_function
        

@app.route('/sign_s3_upload/')
def sign_s3():
    
    folder = config.S3_BUCKET_FOLDER

    object_name = request.args.get('s3_object_name')
    mime_type = request.args.get('s3_object_type')

    expires = int(time.time()+10)
    amz_headers = "x-amz-acl:public-read"

    put_request = "PUT\n\n%s\n%d\n%s\n/%s/%s" % (mime_type, expires, amz_headers, config.AWS_S3_BUCKET, object_name)

    signature = base64.encodestring(hmac.new(config.AWS_SECRET_ACCESS_KEY, put_request, sha1).digest())
    signature = urllib.quote_plus(signature.strip())

    url = get_s3_url(object_name)

    return json.dumps({
        'signed_request': '%s?AWSAccessKeyId=%s&Expires=%d&Signature=%s' % (url, config.AWS_ACCESS_KEY_ID, expires, signature),
         'url': url
      })
    
@csrf.error_handler
def csrf_error(reason):
    return render_template('csrf_error.html', reason=reason), 400


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(user_id)  # @UndefinedVariable

@app.before_request
def before_request():
    g.user=None
    if current_user.is_authenticated():
        g.user = current_user
    
@app.route('/')
def index():
    if current_user is None or not current_user.is_active():
        return landing_page()
    posts = current_user.posts_followed()
    user_projects = current_user.projects
    return render_template('news_feed.html', posts=posts, 
                           projects=user_projects)

def landing_page():
    login_form = LoginForm()
    signup_form = SignupForm()
    return render_template('landing_page.html', login_form=login_form, signup_form=signup_form)


@app.route('/login', methods = ['GET','POST'])
def login():
    if current_user is not None and current_user.is_active():
        return redirect(url_for('index'))
    form = LoginForm()
    if request.method == 'POST' and form.validate_on_submit():
        login_user(form.user, remember=form.remember_me.data)
        return redirect(request.args.get("next") or url_for("index"))
    return render_template('login.html', 
        title = 'Login',
        login_form = form)
    
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('You have logged out')
    return redirect(url_for("index"))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if request.method == 'POST' and form.validate_on_submit():
        user = User(form.username.data, form.email.data,
                form.password.data)
        flash('Creating account')
        #try:
        db.session.add(user)  # @UndefinedVariable
        db.session.commit()  # @UndefinedVariable
        #except:
        #   db.session.rollback()  # @UndefinedVariable
        login_user(user, remember=True)
        return redirect(url_for('edit_profile', status='first'))
    return render_template('signup.html', signup_form=form)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile(status=None):
    user=current_user
    form = ProfileForm()
    previous_page = config.ROOT_URL
    form.old_username = user.username
    profile_pic_url = user.get_profile_pic_url()
    
    temp_file_name = user.username
    if request.method == 'POST':
        if form.validate_on_submit():
            user.username = form.username.data
            user.first_name = form.first_name.data
            user.last_name = form.last_name.data
            user.location = form.location.data
            user.gender = form.gender.data
            user.about = form.about.data
            user.privacy = form.privacy.data
            file = request.files['profile_pic']
            filename = secure_filename(file.filename)
            if file and allowed_file(filename):
                (file_id, file_extension) = os.path.splitext(filename)
                filename = user.get_profile_pic_filename(file_extension)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename) 
                file.save(filepath)
                #user.set_profile_pic(filepath)
                conn = boto.connect_s3(config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY)
                bucket=conn.get_bucket(config.AWS_S3_BUCKET)
                for size, dims in config.PROFILE_PIC_SIZES.iteritems():
                    pic = resize_and_crop(filepath, dims)
                    #pic = resize_image(filepath, width=config.PROFILE_PIC_WIDTH)
                    pic_filename=size.lower()+'/'+filename
                    key_pic = bucket.new_key(pic_filename)
                    key_pic.set_contents_from_file(pic)  
                    key_pic.set_acl('public-read')
                os.remove(filepath) 
            else:
                return "no file"        
            db.session.add(user)  # @UndefinedVariable
            db.session.commit()  # @UndefinedVariable
        else:
            return "form did not validate"
    else:
        form = ProfileForm(username=user.username, 
                           first_name=user.first_name, last_name=user.last_name,
                            location=user.location,
                            gender=user.gender,
                            about=user.about,
                            privacy=user.get_privacy())

    return render_template('edit_profile.html', 
                           form=form, status=status, user=user, 
                           previous_page=previous_page, 
                           profile_pic_url=profile_pic_url, 
                           file_name=temp_file_name)

@app.route('/user/<username>')
@login_required
def user_page(username):
    user = User.query.filter_by(username=username).first()# @UndefinedVariable
    if user is not None:
        if user.is_viewable_by(current_user.id):
            projects = Project.query.filter_by(created_by=user.id).limit(config.PROJ_LIST_LIMIT)  # @UndefinedVariable
            return render_template('user_page.html', user=user, projects=projects)
        else: 
            request_sent = FriendRequest.query.filter_by(requester_id=current_user.id, requested_id=user.id).count() > 0 # @UndefinedVariable
            request_received = FriendRequest.query.filter_by(requester_id=user.id, requested_id=current_user.id).count() > 0 # @UndefinedVariable
            return render_template('user_page_private.html', user=user, request_sent=request_sent,request_received=request_received)
    else:
        return redirect(url_for('index'))
    
    
@app.route('/add_friend', methods=['POST'])
def add_friend():  
    form = FriendRequestForm()
    if form.validate_on_submit():
        if request.method =='POST':
            requester_id =request.form['requester_id']
            requested_id =request.form['requested_id']
        count = FriendRequest.query.filter_by(requester_id=requester_id, requested_id=requested_id).count()# @UndefinedVariable
        count_reverse = FriendRequest.query.filter_by(requester_id=requested_id, requested_id=requester_id).count()# @UndefinedVariable
        if count+count_reverse == 0:
            friend_request = FriendRequest(requester_id=requester_id, requested_id=requested_id)
            try:
                db.session.add(friend_request)# @UndefinedVariable
                db.session.commit()# @UndefinedVariable
            except:
                return "Error"
    else:
        return  render_template('add_friend_form.html',form=form)
    return "Success"

@app.route('/approve_friend', methods=['GET', 'POST'])
def approve_friend():  
    form = FriendApproveForm()
    if request.method =='POST' and form.validate_on_submit():
        requester_id = int(form.requester_id.data)
        requested_id = int(form.requested_id.data)
        approve_request = form.approve.data
        friend_request = FriendRequest.query.filter_by(requester_id=requester_id, requested_id=requested_id, ignored=False).first()# @UndefinedVariable
        if friend_request:
            if approve_request:
                ins1=friendships.insert().values(user_id=requester_id, friend_id=requested_id)# @UndefinedVariable
                ins2=friendships.insert().values(user_id=requested_id, friend_id=requester_id)# @UndefinedVariable
                db.engine.execute(ins1) #@UndefinedVariable
                db.engine.execute(ins2) #@UndefinedVariable
                friend_request.approved=True
            else:
                friend_request.approved=False
                friend_request.ignored=True
            db.session.add(friend_request)# @UndefinedVariable  
            db.session.commit()# @UndefinedVariable                 
        else:
            return  "Error: No Friend Request"
    #else:
#     requester_id = request.args['requested_id']
#     requested_id = request.args['requested_id']
#     approve_request = True#request.form['approve']
    return "Success"


@app.route('/friend_requests')
@login_required
@notification_viewed
def friend_requests():
    requests = FriendRequest.query.filter_by(requested_id=current_user.id, approved=False,ignored=False).limit(10)# @UndefinedVariable
    
    return render_template('friend_requests.html',friend_requests=requests)
    



@app.route('/user/<username>/profile_pic/')
@login_required
def user_profile_pic_page(username):   
    user = User.query.filter_by(username=username).first()# @UndefinedVariable
    if user is not None:
        return render_template('user_profile_pic.html', user=user)
    else:
        redirect(url_for('index'))
        
        
        
@app.route('/post', methods=['GET', 'POST'])      
def post():
    form = PostForm()
    if request.method =='POST' and form.validate_on_submit():
        project_id = int(form.project_id)
        project = Project.query.get(project_id) # @UndefinedVariable
        if current_user.id == project.created_by:
            post = Post(created_by=current_user.id,
                        project=project.id,
                        text=form.text
                        )
            file = request.files['project_id']
            if file:
                filename = secure_filename(file.filename)
                (file_id, file_extension) = os.path.splitext(filename)
                filename = generate_filename(file_extension)
                post.pic_id=filename
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename) 
                file.save(filepath)
                #user.set_profile_pic(filepath)
                conn = boto.connect_s3(config.AWS_ACCESS_KEY_ID, config.AWS_SECRET_ACCESS_KEY)
                bucket=conn.get_bucket(config.AWS_S3_BUCKET)
                for size, dims in config.POST_PIC_SIZE.iteritems():
                    pic = resize_and_crop(filepath, dims)
                    #pic = resize_image(filepath, width=config.PROFILE_PIC_WIDTH)
                    pic_filename=size.lower()+'/'+filename
                    key_pic = bucket.new_key(pic_filename)
                    key_pic.set_contents_from_file(pic)  
                    key_pic.set_acl('public-read')
                os.remove(filepath) 
            else:
                return "no file"        
            db.session.add(post)  # @UndefinedVariable
            db.session.commit()  # @UndefinedVariable
        else:
            redirect(url_for('index'))
    return render_template('post.html',form=form)
            
        
@app.route('/project/<project_id>/<slug>/edit')
@login_required
def edit_project(project_id):
    project = Project.query.get(int(project_id))  # @UndefinedVariable
    form = ProjectEditForm()
    if request.method == 'POST' and project.created_by == current_user.id and form.validate_on_submit() :
        project.name = form.project_name
        project.goal = form.goal
        project.privacy_mode = form.privacy
        db.session.add(project)  # @UndefinedVariable
        db.session.commit()  # @UndefinedVariable
    return render_template('edit_project.html', project=project)

@app.route('/create_project', methods=['GET', 'POST'])
@login_required
def create_project():
    form =ProjectCreateForm()
    form.user=current_user
    previous_page = config.ROOT_URL
    if request.method == 'POST' and form.validate_on_submit():
        project = Project(project_name=form.project_name.data, 
                          goal=form.goal.data, 
                          privacy=form.privacy.data,
                          created_by=current_user.id)
        db.session.add(project)  # @UndefinedVariable
        db.session.commit()  # @UndefinedVariable
        project.get_url()
        db.session.add(project)  # @UndefinedVariable
        db.session.commit() # @UndefinedVariable
        return redirect(project.get_url())
    
    return render_template('create_project.html', form=form, previous_page=previous_page)
    
@app.route('/project/<project_id>/<slug>/')
@login_required
def project_page(project_id, slug):
    project = Project.query.get(project_id) # @UndefinedVariable
    viewable=project.is_viewable_by(current_user.id)
    return render_template('project_page.html', project=project,  viewable=viewable)


@app.route('/follow/<username>')
def follow(username):
    user = User.query.filter_by(username= username).first()  # @UndefinedVariable
    if user == None:
        flash('User ' + username + ' not found.')
        return redirect(url_for('index'))
    if user == g.user:
        flash('You can\'t follow yourself!')
        return redirect(url_for('user', username = username))
    u = g.user.follow(user)
    if u is None:
        flash('Cannot follow ' + username + '.')
        return redirect(url_for('user', username = username))
    session.add(u)
    session.commit()
    flash('You are now following ' + username + '!')
    return redirect(url_for('user', username = username))

@app.route('/unfollow/<username>')
def unfollow(username):
    user = User.query.filter_by(User.username == username).first()  # @UndefinedVariable
    if user == None:
        flash('User ' + username + ' not found.')
        return redirect(url_for('index'))
    if user == g.user:
        flash('You can\'t unfollow yourself!')
        return redirect(url_for('user', username = username))
    u = g.user.unfollow(user)
    if u is None:
        flash('Cannot unfollow ' + username + '.')
        return redirect(url_for('user', username = username))
    session.add(u)
    session.commit()
    flash('You have stopped following ' + username + '.')
    return redirect(url_for('user', username = username))

# 
# 
# 
# def edit_profile():
#     
#     if request.method == 'POST':
#         file = request.files['profile_pic']
#         if file and allowed_file(file.filename):
#             filename = secure_filename(file.filename)
#             conn = S3Connection('credentials', '')
#             bucket = conn.create_bucket('bucketname')
#             k = Key(bucket)
#             k.key = 'foobar'
#             k.set_contents_from_string(file.readlines())
#             return "Success!"