import json
import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, session
import firebase_admin
from firebase_admin import credentials, firestore
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

firebase_key_env = os.getenv('FIREBASE_KEY')
if firebase_key_env:
    firebase_key = json.loads(firebase_key_env)
    cred = credentials.Certificate(firebase_key)
else:
    cred = credentials.Certificate('firebase_key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'betagn2026secretkey')

@app.template_filter('time_ago')
def time_ago_filter(dt):
    if dt is None:
        return ''
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = now - dt
    days = diff.days
    if days == 0:
        return 'today'
    if days == 1:
        return 'yesterday'
    if days < 7:
        return f'{days} days ago'
    if days < 30:
        weeks = days // 7
        return f'{weeks} week{"s" if weeks > 1 else ""} ago'
    if days < 365:
        months = days // 30
        return f'{months} month{"s" if months > 1 else ""} ago'
    years = days // 365
    return f'{years} year{"s" if years > 1 else ""} ago'

ADMIN_ID = 'hzeHSTreNf7Y0ivB4mpu'

@app.route('/')
def home():
    neighborhood = request.args.get('neighborhood', '')
    property_type = request.args.get('type', '')
    max_price = request.args.get('max_price', '')
    bedrooms = request.args.get('bedrooms', '')

    listings_ref = db.collection('listings').stream()
    listings = []
    for doc in listings_ref:
        listing = doc.to_dict()
        listing['id'] = doc.id
        if listing.get('status') == 'approved':
            listings.append(listing)

    if neighborhood:
        listings = [l for l in listings if l.get('neighborhood') == neighborhood]
    if property_type:
        listings = [l for l in listings if l.get('type') == property_type]
    if max_price:
        listings = [l for l in listings if l.get('price', 0) <= int(max_price)]
    if bedrooms:
        if bedrooms == '3+':
            listings = [l for l in listings if l.get('bedrooms', 0) >= 3]
        else:
            listings = [l for l in listings if l.get('bedrooms', 0) == int(bedrooms)]

    total = len(listings)
    per_page = 12
    page = max(1, int(request.args.get('page', 1)))
    total_pages = max(1, -(-total // per_page))  # ceiling division
    page = min(page, total_pages)
    start = (page - 1) * per_page
    listings = listings[start:start + per_page]

    return render_template('index.html',
        listings=listings,
        neighborhood=neighborhood,
        property_type=property_type,
        max_price=max_price,
        bedrooms=bedrooms,
        total=total,
        page=page,
        total_pages=total_pages,
        user=session.get('user')
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user'):
        return redirect(url_for('home'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email').lower().strip()
        password = request.form.get('password')

        users = db.collection('users').where('email', '==', email).stream()
        user_doc = None
        for u in users:
            user_doc = u

        if user_doc:
            user_data = user_doc.to_dict()
            if check_password_hash(user_data['password'], password):
                session['user'] = {
                    'uid': user_doc.id,
                    'email': user_data['email'],
                    'name': user_data.get('name', user_data['email'])
                }
                return redirect(url_for('home'))
            else:
                error = 'Incorrect password.'
        else:
            error = 'No account found with that email.'

    return render_template('login.html', error=error, mode='login')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user'):
        return redirect(url_for('home'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email').lower().strip()
        password = request.form.get('password')
        name = request.form.get('name').strip()

        existing = db.collection('users').where('email', '==', email).stream()
        if any(True for _ in existing):
            error = 'An account with this email already exists.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            hashed = generate_password_hash(password)
            new_user = {
                'email': email,
                'password': hashed,
                'name': name
            }
            doc_ref = db.collection('users').add(new_user)
            session['user'] = {
                'uid': doc_ref[1].id,
                'email': email,
                'name': name
            }
            return redirect(url_for('home'))

    return render_template('login.html', error=error, mode='signup')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/add', methods=['GET', 'POST'])
def add_listing():
    if not session.get('user'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        photo_urls = []
        if 'photos' in request.files:
            photos = request.files.getlist('photos')
            for photo in photos[:5]:
                if photo.filename != '':
                    result = cloudinary.uploader.upload(photo)
                    photo_urls.append(result['secure_url'])

        new_listing = {
            'title': request.form.get('title'),
            'type': request.form.get('type'),
            'neighborhood': request.form.get('neighborhood'),
            'price': int(request.form.get('price')),
            'size': int(request.form.get('size') or 0),
            'bedrooms': int(request.form.get('bedrooms')),
            'bathrooms': int(request.form.get('bathrooms') or 1),
            'description': request.form.get('description'),
            'phone': request.form.get('phone'),
            'photo_urls': photo_urls,
            'user_id': session['user']['uid'],
            'status': 'pending',
            'created_at': datetime.now(timezone.utc)
        }

        db.collection('listings').add(new_listing)
        return render_template('add_listing.html', success=True)

    return render_template('add_listing.html', success=False)

@app.route('/listing/<listing_id>')
def listing_detail(listing_id):
    doc = db.collection('listings').document(listing_id).get()
    if not doc.exists:
        return 'Listing not found', 404
    listing = doc.to_dict()
    listing['id'] = doc.id
    photos = listing.get('photo_urls') or ([listing.get('photo_url')] if listing.get('photo_url') else [])
    user = session.get('user')
    is_owner = user and user['uid'] == listing.get('user_id')
    return render_template('listing_detail.html',
        listing=listing,
        photos=photos,
        is_owner=is_owner
    )

@app.route('/listing/<listing_id>/edit', methods=['GET', 'POST'])
def edit_listing(listing_id):
    if not session.get('user'):
        return redirect(url_for('login'))
    doc = db.collection('listings').document(listing_id).get()
    if not doc.exists:
        return 'Listing not found', 404
    listing = doc.to_dict()
    listing['id'] = doc.id
    if listing.get('user_id') != session['user']['uid']:
        return 'Not authorized', 403

    if request.method == 'POST':
        updated = {
            'title': request.form.get('title'),
            'type': request.form.get('type'),
            'neighborhood': request.form.get('neighborhood'),
            'price': int(request.form.get('price')),
            'size': int(request.form.get('size') or 0),
            'bedrooms': int(request.form.get('bedrooms')),
            'bathrooms': int(request.form.get('bathrooms') or 1),
            'description': request.form.get('description'),
            'phone': request.form.get('phone'),
            'status': 'pending'
        }
        db.collection('listings').document(listing_id).update(updated)
        return redirect(url_for('listing_detail', listing_id=listing_id))

    return render_template('edit_listing.html', listing=listing)

@app.route('/listing/<listing_id>/delete', methods=['POST'])
def delete_listing(listing_id):
    if not session.get('user'):
        return redirect(url_for('login'))
    doc = db.collection('listings').document(listing_id).get()
    if not doc.exists:
        return 'Listing not found', 404
    listing = doc.to_dict()
    if listing.get('user_id') != session['user']['uid']:
        return 'Not authorized', 403
    db.collection('listings').document(listing_id).delete()
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    if not session.get('user'):
        return redirect(url_for('login'))

    user = session.get('user')
    listings_ref = db.collection('listings').where('user_id', '==', user['uid']).stream()
    listings = []
    for doc in listings_ref:
        listing = doc.to_dict()
        listing['id'] = doc.id
        listings.append(listing)

    return render_template('profile.html', user=user, listings=listings)

@app.route('/admin')
def admin():
    if not session.get('user') or session['user']['uid'] != ADMIN_ID:
        return 'Not authorized', 403

    pending = []
    approved = []
    rejected = []

    listings_ref = db.collection('listings').stream()
    for doc in listings_ref:
        listing = doc.to_dict()
        listing['id'] = doc.id
        status = listing.get('status', 'pending')
        if status == 'pending':
            pending.append(listing)
        elif status == 'approved':
            approved.append(listing)
        elif status == 'rejected':
            rejected.append(listing)

    return render_template('admin.html',
        pending=pending,
        approved=approved,
        rejected=rejected,
        user=session.get('user')
    )

@app.route('/admin/edit/<listing_id>', methods=['GET', 'POST'])
def admin_edit_listing(listing_id):
    if not session.get('user') or session['user']['uid'] != ADMIN_ID:
        return 'Not authorized', 403
    doc = db.collection('listings').document(listing_id).get()
    if not doc.exists:
        return 'Listing not found', 404
    listing = doc.to_dict()
    listing['id'] = doc.id

    if request.method == 'POST':
        updated = {
            'title': request.form.get('title'),
            'type': request.form.get('type'),
            'neighborhood': request.form.get('neighborhood'),
            'price': int(request.form.get('price')),
            'size': int(request.form.get('size') or 0),
            'bedrooms': int(request.form.get('bedrooms')),
            'bathrooms': int(request.form.get('bathrooms') or 1),
            'description': request.form.get('description'),
            'phone': request.form.get('phone'),
        }
        db.collection('listings').document(listing_id).update(updated)
        return redirect(url_for('admin'))

    return render_template('admin_edit.html', listing=listing)

@app.route('/admin/approve/<listing_id>', methods=['POST'])
def approve_listing(listing_id):
    if not session.get('user') or session['user']['uid'] != ADMIN_ID:
        return 'Not authorized', 403
    db.collection('listings').document(listing_id).update({'status': 'approved'})
    return redirect(url_for('admin'))

@app.route('/admin/reject/<listing_id>', methods=['POST'])
def reject_listing(listing_id):
    if not session.get('user') or session['user']['uid'] != ADMIN_ID:
        return 'Not authorized', 403
    db.collection('listings').document(listing_id).update({'status': 'rejected'})
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)