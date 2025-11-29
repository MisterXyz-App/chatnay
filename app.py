from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Konfigurasi
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Inisialisasi ekstensi
db = SQLAlchemy(app)
login_manager = LoginManager(app)
csrf = CSRFProtect(app)

# Konfigurasi Login Manager
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'

# Konfigurasi Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_picture = db.Column(db.String(500), default='https://res.cloudinary.com/dzfkklsza/image/upload/v1700000000/default_avatar.png')
    bio = db.Column(db.Text, default='')
    social_links = db.Column(db.Text, default='[]')
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_social_links(self):
        try:
            return json.loads(self.social_links)
        except:
            return []
    
    def set_social_links(self, links_list):
        self.social_links = json.dumps(links_list)
    
    def can_chat(self):
        return self.is_active and not self.is_blocked
    
    def is_online(self):
        if not self.last_seen:
            return False
        return self.last_seen > datetime.utcnow() - timedelta(minutes=5)
    
    def get_unread_count(self, sender_id):
        return Message.query.filter_by(
            sender_id=sender_id,
            receiver_id=self.id,
            is_read=False
        ).count()
    
    def __repr__(self):
        return f'<User {self.username}>'

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.String(500))
    media_type = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'media_url': self.media_url,
            'media_type': self.media_type,
            'is_read': self.is_read,
            'timestamp': self.timestamp.strftime('%H:%M'),
            'full_timestamp': self.timestamp.strftime('%d %b %Y %H:%M'),
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'sender_username': self.sender.username,
            'sender_profile_pic': self.sender.profile_picture
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context Processor untuk template
@app.context_processor
def utility_processor():
    return {
        'datetime': datetime,
        'now': datetime.utcnow,
        'timedelta': timedelta
    }

# Helper Functions
def upload_to_cloudinary(file, folder="chat_app"):
    try:
        file_extension = file.filename.lower().split('.')[-1]
        resource_type = "auto"
        
        if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            resource_type = "image"
        elif file_extension in ['mp4', 'avi', 'mov', 'wmv', 'mkv']:
            resource_type = "video"
        
        result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type=resource_type,
            quality="auto",
            fetch_format="auto"
        )
        
        return {
            'success': True,
            'url': result['secure_url'],
            'public_id': result['public_id'],
            'resource_type': resource_type
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Akses ditolak. Hanya admin yang dapat mengakses halaman ini.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def active_user_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_active:
            flash('Akun Anda tidak aktif. Silakan hubungi admin.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Update last seen before each request
@app.before_request
def update_last_seen():
    if current_user.is_authenticated and hasattr(current_user, 'id'):
        current_user.last_seen = datetime.utcnow()
        try:
            db.session.commit()
        except:
            db.session.rollback()

# Routes - Authentication
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([username, email, password, confirm_password]):
            flash('Semua field harus diisi!', 'error')
            return render_template('register.html')
        
        if len(username) < 3:
            flash('Username harus minimal 3 karakter!', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password harus minimal 6 karakter!', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Password tidak cocok!', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan!', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email sudah digunakan!', 'error')
            return render_template('register.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Akun Anda tidak aktif. Silakan hubungi admin.', 'error')
                return render_template('login.html')
            
            if user.is_blocked:
                flash('Akun Anda diblokir. Silakan hubungi admin.', 'error')
                return render_template('login.html')
            
            login_user(user, remember=remember)
            flash(f'Login berhasil! Selamat datang {user.username}', 'success')
            
            # Redirect ke halaman yang diminta sebelumnya atau dashboard
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

# Routes - Main & Chat
@app.route('/')
@login_required
@active_user_required
def dashboard():
    # Pastikan admin Nayla Asyifa ada
    ensure_admin_exists()
    
    if current_user.is_admin:
        # Admin melihat semua user kecuali dirinya sendiri
        users = User.query.filter(User.id != current_user.id).order_by(
            User.is_admin.desc(), User.username
        ).all()
    else:
        # User biasa hanya melihat admin dan user lain yang aktif
        users = User.query.filter(
            (User.id != current_user.id) &
            (User.is_active == True) &
            (User.is_blocked == False)
        ).order_by(User.is_admin.desc(), User.username).all()
    
    # Get unread counts for each user
    user_data = []
    for user in users:
        unread_count = current_user.get_unread_count(user.id)
        user_data.append({
            'user': user,
            'unread_count': unread_count
        })
    
    return render_template('dashboard.html', user_data=user_data)

def ensure_admin_exists():
    """Pastikan admin Nayla Asyifa selalu ada di database"""
    admin = User.query.filter_by(username='nayla_asyifa', is_admin=True).first()
    if not admin:
        admin = User(
            username='nayla_asyifa',
            email='nayla@example.com',
            is_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: nayla_asyifa / admin123")

@app.route('/chat/<int:user_id>')
@login_required
@active_user_required
def chat(user_id):
    target_user = User.query.get_or_404(user_id)
    
    # Cek apakah user bisa mengakses chat
    if not target_user.can_chat():
        flash('User tidak dapat dihubungi.', 'error')
        return redirect(url_for('dashboard'))
    
    # Ambil pesan antara current_user dan target_user
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    # Tandai pesan sebagai dibaca
    unread_messages = Message.query.filter(
        Message.receiver_id == current_user.id,
        Message.sender_id == user_id,
        Message.is_read == False
    ).all()
    
    for msg in unread_messages:
        msg.is_read = True
    
    db.session.commit()
    
    return render_template('chat.html', target_user=target_user, messages=messages)

@app.route('/send_message', methods=['POST'])
@login_required
@active_user_required
def send_message():
    try:
        receiver_id = request.form.get('receiver_id')
        content = request.form.get('content', '').strip()
        file = request.files.get('file')
        
        if not receiver_id:
            return jsonify({'success': False, 'error': 'Receiver ID diperlukan'})
        
        receiver = User.query.get(receiver_id)
        if not receiver or not receiver.can_chat():
            return jsonify({'success': False, 'error': 'User tidak dapat dihubungi'})
        
        # Validasi: minimal ada content atau file
        if not content and not (file and file.filename):
            return jsonify({'success': False, 'error': 'Pesan tidak boleh kosong'})
        
        media_url = None
        media_type = None
        public_id = None
        
        # Handle file upload
        if file and file.filename:
            # Validasi file size
            file.seek(0, 2)  # Seek to end to get size
            file_size = file.tell()
            file.seek(0)  # Reset seek position
            
            if file_size > 16 * 1024 * 1024:  # 16MB
                return jsonify({'success': False, 'error': 'File terlalu besar. Maksimal 16MB'})
            
            upload_result = upload_to_cloudinary(file)
            if upload_result['success']:
                media_url = upload_result['url']
                media_type = upload_result['resource_type']
                public_id = upload_result['public_id']
            else:
                return jsonify({'success': False, 'error': 'Gagal mengupload file: ' + upload_result['error']})
        
        # Buat pesan baru
        message = Message(
            content=content if content else None,
            media_url=media_url,
            media_type=media_type,
            sender_id=current_user.id,
            receiver_id=receiver_id
        )
        
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': message.to_dict(),
            'public_id': public_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_messages/<int:user_id>')
@login_required
@active_user_required
def get_messages(user_id):
    last_message_id = request.args.get('last_message_id', 0, type=int)
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id)),
        Message.id > last_message_id
    ).order_by(Message.timestamp.asc()).all()
    
    # Tandai pesan sebagai dibaca
    unread_messages = [msg for msg in messages if msg.receiver_id == current_user.id and not msg.is_read]
    for msg in unread_messages:
        msg.is_read = True
    
    if unread_messages:
        db.session.commit()
    
    return jsonify({
        'success': True,
        'messages': [msg.to_dict() for msg in messages]
    })

@app.route('/delete_message/<int:message_id>', methods=['POST'])
@login_required
@active_user_required
def delete_message(message_id):
    try:
        message = Message.query.get_or_404(message_id)
        
        # Cek apakah user adalah pengirim pesan
        if message.sender_id != current_user.id and not current_user.is_admin:
            return jsonify({'success': False, 'error': 'Anda tidak memiliki akses'})
        
        # Hapus file dari Cloudinary jika ada
        if message.media_url and current_user.is_admin:
            try:
                public_id = message.media_url.split('/')[-1].split('.')[0]
                cloudinary.uploader.destroy(f"chat_app/{public_id}")
            except:
                pass
        
        db.session.delete(message)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Routes - Profile
@app.route('/profile')
@login_required
def profile():
    # Hitung statistik untuk profile
    days_joined = (datetime.utcnow() - current_user.created_at).days if current_user.created_at else 0
    return render_template('profile.html', days_joined=days_joined)

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        bio = request.form.get('bio', '').strip()
        social_names = request.form.getlist('social_names[]')
        social_urls = request.form.getlist('social_urls[]')
        
        # Process social links - gabungkan nama dan URL
        social_links = []
        for name, url in zip(social_names, social_urls):
            name = name.strip()
            url = url.strip()
            
            # Hanya tambahkan jika kedua field terisi
            if name and url:
                # Validasi URL
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                social_links.append({
                    'name': name,
                    'url': url
                })
        
        current_user.bio = bio
        current_user.set_social_links(social_links)
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                # Validasi file type
                allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
                file_extension = file.filename.lower().split('.')[-1]
                
                if file_extension in allowed_extensions:
                    upload_result = upload_to_cloudinary(file, "profile_pictures")
                    if upload_result['success']:
                        current_user.profile_picture = upload_result['url']
                    else:
                        flash('Gagal mengupload foto profil.', 'error')
                else:
                    flash('Format file tidak didukung. Gunakan JPG, PNG, atau GIF.', 'error')
        
        db.session.commit()
        flash('Profil berhasil diperbarui!', 'success')
        
    except Exception as e:
        flash('Gagal memperbarui profil.', 'error')
        print(f"Error updating profile: {str(e)}")
    
    return redirect(url_for('profile'))

@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    if not current_user.check_password(current_password):
        flash('Password saat ini salah!', 'error')
    elif len(new_password) < 6:
        flash('Password baru harus minimal 6 karakter!', 'error')
    elif new_password != confirm_password:
        flash('Password baru tidak cocok!', 'error')
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash('Password berhasil diubah!', 'success')
    
    return redirect(url_for('profile'))

@app.route('/user/<int:user_id>')
@login_required
def view_user_profile(user_id):
    user = User.query.get_or_404(user_id)
    days_joined = (datetime.utcnow() - user.created_at).days if user.created_at else 0
    return render_template('user_profile.html', user=user, days_joined=days_joined)

# Routes - Admin
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.filter(User.id != current_user.id).order_by(User.created_at.desc()).all()
    
    # Hitung statistik
    total_users = User.query.count() - 1  # exclude admin
    active_users = User.query.filter_by(is_active=True).count() - 1
    blocked_users = User.query.filter_by(is_blocked=True).count()
    total_messages = Message.query.count()
    online_users = User.query.filter(User.last_seen >= datetime.utcnow() - timedelta(minutes=5)).count() - 1
    
    stats = {
        'total_users': total_users,
        'active_users': active_users,
        'blocked_users': blocked_users,
        'total_messages': total_messages,
        'online_users': online_users
    }
    
    return render_template('admin_dashboard.html', users=users, stats=stats)

@app.route('/admin/user/<int:user_id>/toggle_block')
@login_required
@admin_required
def toggle_block_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Tidak dapat memblokir admin lain!', 'error')
    else:
        user.is_blocked = not user.is_blocked
        db.session.commit()
        
        action = "diblokir" if user.is_blocked else "dibuka blokirnya"
        flash(f'User {user.username} berhasil {action}!', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/toggle_active')
@login_required
@admin_required
def toggle_active_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Tidak dapat menonaktifkan admin lain!', 'error')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        
        action = "dinonaktifkan" if not user.is_active else "diaktifkan"
        flash(f'User {user.username} berhasil {action}!', 'success')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/delete')
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('Tidak dapat menghapus admin lain!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Hapus semua pesan yang terkait dengan user
    Message.query.filter(
        (Message.sender_id == user_id) | (Message.receiver_id == user_id)
    ).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {user.username} berhasil dihapus!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    # Hitung statistik untuk template
    stats = {
        'total_users': User.query.count(),
        'total_messages': Message.query.count(),
        'active_users': User.query.filter_by(is_active=True).count(),
        'blocked_users': User.query.filter_by(is_blocked=True).count()
    }
    
    if request.method == 'POST':
        # Update admin profile
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        
        # Validasi username unique
        if new_username != current_user.username:
            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user:
                flash('Username sudah digunakan!', 'error')
                return redirect(url_for('admin_settings'))
            current_user.username = new_username
        
        # Validasi email unique
        if new_email != current_user.email:
            existing_email = User.query.filter_by(email=new_email).first()
            if existing_email:
                flash('Email sudah digunakan!', 'error')
                return redirect(url_for('admin_settings'))
            current_user.email = new_email
        
        current_user.bio = request.form.get('bio', '').strip()
        
        # Handle social links (sama seperti profile)
        social_names = request.form.getlist('social_names[]')
        social_urls = request.form.getlist('social_urls[]')
        
        social_links = []
        for name, url in zip(social_names, social_urls):
            name = name.strip()
            url = url.strip()
            
            if name and url:
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                social_links.append({
                    'name': name,
                    'url': url
                })
        
        current_user.set_social_links(social_links)
        
        # Handle profile picture
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                upload_result = upload_to_cloudinary(file, "profile_pictures")
                if upload_result['success']:
                    current_user.profile_picture = upload_result['url']
        
        db.session.commit()
        flash('Pengaturan admin berhasil diperbarui!', 'success')
        return redirect(url_for('admin_settings'))
    
    return render_template('admin_settings.html', stats=stats)

@app.route('/admin/delete_all_messages', methods=['POST'])
@login_required
@admin_required
def delete_all_messages():
    try:
        # Hapus semua pesan
        num_messages = Message.query.count()
        Message.query.delete()
        db.session.commit()
        
        flash(f'Berhasil menghapus {num_messages} pesan!', 'success')
    except Exception as e:
        flash('Gagal menghapus pesan.', 'error')
    
    return redirect(url_for('admin_dashboard'))

# Error Handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(413)
def too_large(error):
    flash('File terlalu besar. Maksimal 16MB.', 'error')
    return redirect(request.referrer or url_for('dashboard'))

# CSRF error handler
@app.errorhandler(400)
def bad_request(error):
    if 'CSRF' in str(error.description):
        flash('Session telah expired. Silakan coba lagi.', 'error')
        return redirect(url_for('login'))
    return render_template('400.html'), 400

# Initialize Database and Create Admin
def create_tables():
    with app.app_context():
        db.create_all()
        ensure_admin_exists()

# CSRF token route untuk AJAX
@app.route('/get_csrf')
def get_csrf():
    return jsonify({'csrf_token': generate_csrf()})

if __name__ == '__main__':
    create_tables()
    app.run(debug=True, host='0.0.0.0', port=5000)