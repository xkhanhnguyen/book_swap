# BookSwap

A peer-to-peer book swapping platform built with Django. Users list books they own, discover books near them, and exchange them using a credit-based economy — no money changes hands.

## Features

- **Book catalog** — 200+ books imported from the Kaggle "Best Books Ever" dataset, ordered by popularity
- **Anonymous listings** — users are identified by `BookSwap #0042` style IDs, never real names
- **Distance-based discovery** — books sorted by proximity (km) using geocoded addresses
- **Private address encryption** — addresses are encrypted with AES-256-GCM at rest and never exposed to other users; only the distance in km is shown
- **Credit economy** — earn credits by shipping books (proportional to Shippo shipping cost), spend 1 credit to request a swap
- **Shippo integration** — generate prepaid shipping labels directly from the swap detail page
- **AI condition assessment** — Claude API evaluates book condition descriptions to flag inaccurate listings
- **Dispute resolution** — buyers can open condition disputes on completed swaps; admins resolve them
- **Wishlist & request board** — save wanted books and broadcast requests to potential swappers
- **Swap ratings** — rate your swap partner (1–5 stars) after a completed exchange
- **Reading lists & reviews** — track reading status (reading / completed / want to read) and leave book reviews
- **ML recommendations** — TF-IDF model trained on 52k+ books suggests similar titles on book detail pages and the dashboard
- **On-site notifications** — real-time alerts for swap requests, acceptances, rejections, and shipments
- **Social login** — sign in with GitHub via OAuth2
- **Display preference** — choose between your BookSwap ID (anonymous) or real name

## How swapping works

1. A user lists a book they own ("I have this book")
2. Another user requests a swap — costs **1 credit**
3. The owner accepts or rejects the request
4. On acceptance, the owner generates a Shippo shipping label
5. Downloading the label earns credits proportional to the shipping cost
6. The owner uploads a shipping receipt to mark the swap complete
7. Credits flow back into the system for future swaps

New accounts start with **3 free credits**.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2, Python 3.13 |
| Database | SQLite (dev) |
| Auth | django-environ, social-auth-app-django (GitHub OAuth) |
| Geocoding | geopy (Nominatim), pgeocode (Vietnamese zip codes) |
| Encryption | cryptography (AES-256-GCM) |
| Shipping | Shippo v3 API |
| Email | Gmail SMTP, SendGrid |
| AI | Anthropic Claude API (book condition assessment) |
| ML | scikit-learn TF-IDF, joblib, pandas |
| Images | Pillow |
| Deploy | Gunicorn, GitHub Actions (SSH + SCP) |

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd book_swap
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `book_swap/.env` (same directory as `settings.py`) and fill in the values:

```env
DJANGO_SECRET_KEY=your-secret-key

# GitHub OAuth (github.com/settings/developers)
SOCIAL_AUTH_GITHUB_KEY=
SOCIAL_AUTH_GITHUB_SECRET=

# Gmail SMTP
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# AES-256-GCM key for address encryption
# Generate: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_KEY=

# Shippo API key (goshippo.com)
SHIPPO_API_KEY=
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Import books

```bash
# Requires book_data.csv (Kaggle "Best Books Ever") in the project root
python manage.py import_books --limit 200
```

### 5. Add test data (optional)

Creates 4 test users with book listings across different Vietnamese cities:

```bash
python manage.py add_test_data
# Reset: python manage.py add_test_data --clear
```

Test accounts (password: `testpass123`):

| Username | City | Credits |
|---|---|---|
| alice_reads | Ho Chi Minh City | 5 |
| bob_books | Hanoi | 4 |
| carol_lit | Da Nang | 6 |
| dan_pages | Can Tho | 3 |

### 6. Build the recommendation model

```bash
# Requires book_data.csv in the project root (same CSV used for import_books)
python manage.py build_recommendation_model
```

This indexes the Django DB books + the full Kaggle dataset into a TF-IDF matrix and saves the model to `ml_models/book_recommender.pkl`. Re-run any time to rebuild from scratch. The `.pkl` file is excluded from git.

If the model file is missing the app still runs normally — recommendation sections are simply hidden.

### 7. Start the server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/catalog/`

## Deployment

The GitHub Actions workflow (`.github/workflows/ci.yml`) deploys on every push to `main`:

- Copies files to the server via SCP
- Restarts Gunicorn via SSH

**Required GitHub secrets:**

| Secret | Description |
|---|---|
| `SSH_PRIVATE_KEY` | Private key for server access |
| `SSH_KNOWN_HOSTS` | Output of `ssh-keyscan YOUR_SERVER_IP` |
| `SSH_SERVER` | Server IP or hostname |

> If deployment fails with "remote host identification has changed", regenerate `SSH_KNOWN_HOSTS` with `ssh-keyscan YOUR_SERVER_IP` and update the secret.

## Project structure

```
book_swap/
├── book_swap/          # Django project settings & URLs
├── catalog/            # Books, swaps, notifications, shipping
│   ├── models.py       # Book, BookInstance, SwapRequest, Dispute, Wishlist,
│   │                   # SwapRating, ReadingList, BookReview, CreditTransaction, Notification
│   ├── views.py        # Swap flow, disputes, wishlist, ratings, reviews, recommendations
│   ├── ml/
│   │   └── recommender.py   # TF-IDF RecommendationEngine (lazy singleton)
│   └── utils/
│       ├── encryption.py    # AES-256-GCM helpers
│       └── shippo_client.py # Shippo label generation
├── users/              # Auth, profiles, display preferences
│   ├── models.py       # Profile with encrypted address + credit balance
│   └── signals.py      # Auto-create profile on user signup
├── store/              # Basic e-commerce (cart, checkout)
├── ml_models/          # Saved model artifacts (*.pkl excluded from git)
├── static/             # CSS design system (dark minimalist theme)
└── templates/          # Base layout, navbar, shared components
```
