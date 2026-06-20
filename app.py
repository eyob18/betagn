from flask import Flask, render_template, request, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
import os

# Load secret keys from .env file
load_dotenv()

# Connect to Firebase
cred = credentials.Certificate('firebase_key.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Connect to Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

app = Flask(__name__)

@app.route('/')
def home():
    neighborhood = request.args.get('neighborhood', '')
    property_type = request.args.get('type', '')
    max_price = request.args.get('max_price', '')
    bedrooms = request.args.get('bedrooms', '')

    # Get all listings from Firebase
    listings_ref = db.collection('listings').stream()
    listings = []
    for doc in listings_ref:
        listing = doc.to_dict()
        listing['id'] = doc.id
        listing['id'] = doc.id
        listings.append(listing)

    # Filter by neighborhood
    if neighborhood:
        listings = [l for l in listings if l.get('neighborhood') == neighborhood]

    # Filter by property type
    if property_type:
        listings = [l for l in listings if l.get('type') == property_type]

    # Filter by max price
    if max_price:
        listings = [l for l in listings if l.get('price', 0) <= int(max_price)]

    # Filter by bedrooms
    if bedrooms:
        if bedrooms == '3+':
            listings = [l for l in listings if l.get('bedrooms', 0) >= 3]
        else:
            listings = [l for l in listings if l.get('bedrooms', 0) == int(bedrooms)]

    return render_template('index.html',
        listings=listings,
        neighborhood=neighborhood,
        property_type=property_type,
        max_price=max_price,
        bedrooms=bedrooms,
        total=len(listings)
    )

@app.route('/add', methods=['GET', 'POST'])
def add_listing():
    if request.method == 'POST':
        # Handle multiple photo uploads
        photo_urls = []
        if 'photos' in request.files:
            photos = request.files.getlist('photos')
            for photo in photos[:5]:  # max 5 photos
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
            'photo_urls': photo_urls
        }

        # Save to Firebase
        db.collection('listings').add(new_listing)
        return render_template('add_listing.html', success=True)

    return render_template('add_listing.html', success=False)

if __name__ == '__main__':
    app.run(debug=True)