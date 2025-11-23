from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

db = SQLAlchemy(app)

# ---------------- Models ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=False)  # login key
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'farmer' or 'labour'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    work_type = db.Column(db.String(200))
    days = db.Column(db.Integer, default=1)
    stay_info = db.Column(db.String(300))
    wage = db.Column(db.String(50))
    location = db.Column(db.String(200))
    contact = db.Column(db.String(50))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    # status 'open'/'assigned'/'confirmed'/'closed'
    status = db.Column(db.String(30), default='open')

class ViewNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    labour_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    seen = db.Column(db.Boolean, default=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChangeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    labour_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    requested_days = db.Column(db.Integer, nullable=True)
    requested_wage = db.Column(db.String(50), nullable=True)
    requested_stay = db.Column(db.String(300), nullable=True)
    message = db.Column(db.Text)
    status = db.Column(db.String(30), default='pending')  # pending/accepted/rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    labour_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    accepted_by_farmer = db.Column(db.Boolean, default=False)
    confirmed_by_labour = db.Column(db.Boolean, default=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- Helpers ----------------
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

@app.before_request
def init_db():
    # create DB only if missing
    if not os.path.exists("database.db"):
        db.create_all()

# ---------------- Routes ----------------
@app.route('/')
def index():
    return render_template('index.html', user=current_user())

# ---------- Registration & Login (Farmer) ----------
@app.route('/farmer/register', methods=['GET', 'POST'])
def farmer_register():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = request.form['password']
        if User.query.filter_by(phone=phone).first():
            flash('Phone already registered')
            return redirect(url_for('farmer_register'))
        hashed = generate_password_hash(password)
        user = User(name=name, phone=phone, password_hash=hashed, role='farmer')
        db.session.add(user)
        db.session.commit()
        flash('Registered! Please login.')
        return redirect(url_for('farmer_login'))
    return render_template('farmer_register.html')

@app.route('/farmer/login', methods=['GET', 'POST'])
def farmer_login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        user = User.query.filter_by(phone=phone, role='farmer').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = 'farmer'
            return redirect(url_for('farmer_dashboard'))
        flash('Invalid credentials')
    return render_template('farmer_login.html')

# ---------- Registration & Login (Labour) ----------
@app.route('/labour/register', methods=['GET', 'POST'])
def labour_register():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = request.form['password']
        if User.query.filter_by(phone=phone).first():
            flash('Phone already registered')
            return redirect(url_for('labour_register'))
        hashed = generate_password_hash(password)
        user = User(name=name, phone=phone, password_hash=hashed, role='labour')
        db.session.add(user)
        db.session.commit()
        flash('Registered! Please login.')
        return redirect(url_for('labour_login'))
    return render_template('labour_register.html')

@app.route('/labour/login', methods=['GET', 'POST'])
def labour_login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        user = User.query.filter_by(phone=phone, role='labour').first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = 'labour'
            return redirect(url_for('labour_dashboard'))
        flash('Invalid credentials')
    return render_template('labour_login.html')

# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------- Farmer Dashboard ----------
@app.route('/farmer/dashboard')
def farmer_dashboard():
    user = current_user()
    if not user or user.role != 'farmer':
        return redirect(url_for('farmer_login'))
    jobs = Job.query.filter_by(farmer_id=user.id).order_by(Job.date_posted.desc()).all()

    # prepare detailed views and change requests for this farmer's jobs
    views = ViewNotification.query.join(Job, ViewNotification.job_id == Job.id)\
        .filter(Job.farmer_id == user.id).order_by(ViewNotification.viewed_at.desc()).all()
    # expand labour info for templates
    view_details = []
    for v in views:
        labour = User.query.get(v.labour_id)
        view_details.append({'view': v, 'labour': labour})

    change_reqs = ChangeRequest.query.join(Job, ChangeRequest.job_id == Job.id)\
        .filter(Job.farmer_id == user.id).order_by(ChangeRequest.requested_at.desc()).all()

    assignments = Assignment.query.join(Job, Assignment.job_id == Job.id)\
        .filter(Job.farmer_id == user.id).order_by(Assignment.assigned_at.desc()).all()

    return render_template('farmer_dashboard.html', user=user, jobs=jobs,
                           view_details=view_details, change_reqs=change_reqs, assignments=assignments)

# ---------- Post Job ----------
@app.route('/farmer/post_job', methods=['GET', 'POST'])
def post_job():
    user = current_user()
    if not user or user.role != 'farmer':
        return redirect(url_for('farmer_login'))
    if request.method == 'POST':
        title = request.form['title']
        work_type = request.form.get('work_type')
        days = int(request.form.get('days') or 1)
        stay_info = request.form.get('stay_info')
        wage = request.form.get('wage')
        location = request.form.get('location')
        contact = request.form.get('contact')
        job = Job(farmer_id=user.id, title=title, work_type=work_type, days=days,
                  stay_info=stay_info, wage=wage, location=location, contact=contact)
        db.session.add(job)
        db.session.commit()
        flash('Job posted')
        return redirect(url_for('farmer_dashboard'))
    return render_template('post_job.html', user=user)

# ---------- Labour Dashboard ----------
@app.route('/labour/dashboard')
def labour_dashboard():
    user = current_user()
    if not user or user.role != 'labour':
        return redirect(url_for('labour_login'))
    jobs = Job.query.filter(Job.status!='closed').order_by(Job.date_posted.desc()).all()
    assignments = Assignment.query.filter_by(labour_id=user.id).all()
    return render_template('labour_dashboard.html', user=user, jobs=jobs, assignments=assignments)

# ---------- View job (labour views creates a view notification with labour details) ----------
@app.route('/job/<int:job_id>')
def job_view(job_id):
    user = current_user()
    job = Job.query.get_or_404(job_id)
    farmer = User.query.get(job.farmer_id)

    # store view notification with labour details if labour is logged in
    if user and user.role == 'labour':
        existing = ViewNotification.query.filter_by(job_id=job_id, labour_id=user.id).first()
        if not existing:
            v = ViewNotification(job_id=job_id, labour_id=user.id)
            db.session.add(v)
            db.session.commit()

    # get change requests for this job
    change_reqs = ChangeRequest.query.filter_by(job_id=job_id).order_by(ChangeRequest.requested_at.desc()).all()
    return render_template('job_view.html', job=job, farmer=farmer, user=user, change_reqs=change_reqs)

# ---------- Labour requests change or contact ----------
@app.route('/job/<int:job_id>/request_change', methods=['POST'])
def request_change(job_id):
    user = current_user()
    if not user or user.role != 'labour':
        flash('Please login as labour to request changes')
        return redirect(url_for('labour_login'))
    requested_days = request.form.get('requested_days')
    requested_wage = request.form.get('requested_wage')
    requested_stay = request.form.get('requested_stay')
    message = request.form.get('message', '')
    cr = ChangeRequest(
        job_id=job_id,
        labour_id=user.id,
        requested_days=int(requested_days) if requested_days else None,
        requested_wage=requested_wage if requested_wage else None,
        requested_stay=requested_stay if requested_stay else None,
        message=message
    )
    db.session.add(cr)
    db.session.commit()
    flash('Change request sent to farmer')
    return redirect(url_for('job_view', job_id=job_id))

# ---------- Farmer reviews change request ----------
@app.route('/change/<int:change_id>/decide', methods=['POST'])
def decide_change(change_id):
    user = current_user()
    if not user or user.role != 'farmer':
        return redirect(url_for('farmer_login'))
    cr = ChangeRequest.query.get_or_404(change_id)
    decision = request.form.get('decision')  # 'accept' or 'reject'
    if decision == 'accept':
        cr.status = 'accepted'
        # create assignment if not exists
        assign = Assignment.query.filter_by(job_id=cr.job_id, labour_id=cr.labour_id).first()
        if not assign:
            assign = Assignment(job_id=cr.job_id, labour_id=cr.labour_id, accepted_by_farmer=True)
            db.session.add(assign)
        else:
            assign.accepted_by_farmer = True
        # apply the requested changes to job (optional: override job fields)
        job = Job.query.get(cr.job_id)
        if cr.requested_days:
            job.days = cr.requested_days
        if cr.requested_wage:
            job.wage = cr.requested_wage
        if cr.requested_stay:
            job.stay_info = cr.requested_stay
        job.status = 'assigned'
        db.session.commit()
        flash('Change accepted and labour assigned (awaiting labour confirmation).')
    else:
        cr.status = 'rejected'
        db.session.commit()
        flash('Change request rejected.')
    return redirect(url_for('farmer_dashboard'))

# ---------- Farmer accepts labour directly (no change request) ----------
@app.route('/assign/<int:job_id>/<int:labour_id>', methods=['POST'])
def assign_labour(job_id, labour_id):
    user = current_user()
    if not user or user.role != 'farmer':
        return redirect(url_for('farmer_login'))
    assign = Assignment.query.filter_by(job_id=job_id, labour_id=labour_id).first()
    if not assign:
        assign = Assignment(job_id=job_id, labour_id=labour_id, accepted_by_farmer=True)
        db.session.add(assign)
    else:
        assign.accepted_by_farmer = True
    job = Job.query.get(job_id)
    job.status = 'assigned'
    db.session.commit()
    flash('Labour accepted for job. Waiting for labour confirmation.')
    return redirect(url_for('farmer_dashboard'))

# ---------- Labour confirms assignment ----------
@app.route('/assignment/<int:assign_id>/confirm', methods=['POST'])
def confirm_assignment(assign_id):
    user = current_user()
    if not user or user.role != 'labour':
        return redirect(url_for('labour_login'))
    assign = Assignment.query.get_or_404(assign_id)
    if assign.labour_id != user.id:
        flash('Not allowed')
        return redirect(url_for('labour_dashboard'))
    assign.confirmed_by_labour = True
    # if both accepted & confirmed -> mark job confirmed
    job = Job.query.get(assign.job_id)
    if assign.accepted_by_farmer and assign.confirmed_by_labour:
        job.status = 'confirmed'
    db.session.commit()
    flash('You confirmed the assignment.')
    return redirect(url_for('labour_dashboard'))

# ---------- Farmer notifications page (with labour details) ----------
@app.route('/farmer/notifications')
def farmer_notifications():
    user = current_user()
    if not user or user.role != 'farmer':
        return redirect(url_for('farmer_login'))

    # Labour views with full labour details
    views = ViewNotification.query.join(Job, ViewNotification.job_id == Job.id) \
        .filter(Job.farmer_id == user.id) \
        .order_by(ViewNotification.viewed_at.desc()) \
        .all()

    view_list = []
    for v in views:
        labour = User.query.get(v.labour_id)
        job = Job.query.get(v.job_id)
        view_list.append({
            'view': v,
            'labour': labour,
            'job': job
        })

    # Change requests with labour details
    change_reqs_raw = ChangeRequest.query.join(Job, ChangeRequest.job_id == Job.id) \
        .filter(Job.farmer_id == user.id) \
        .order_by(ChangeRequest.requested_at.desc()) \
        .all()

    change_reqs = []
    for cr in change_reqs_raw:
        labour = User.query.get(cr.labour_id)
        change_reqs.append({
            'id': cr.id,
            'job_id': cr.job_id,
            'requested_days': cr.requested_days,
            'requested_wage': cr.requested_wage,
            'requested_stay': cr.requested_stay,
            'message': cr.message,
            'status': cr.status,
            'requested_at': cr.requested_at,
            'labour_name': labour.name,
            'labour_phone': labour.phone
        })

    return render_template(
        'notifications.html',
        user=user,
        views=view_list,
        change_reqs=change_reqs
    )

# ---------------- Run ----------------
if __name__ == '__main__':
    app.run(debug=True)
