# 🪵 Xtore

An eCommerce web app for stationery and wooden storage goods such as drawers, boxes and desk organisers. It pairs a **FastAPI** backend with a green-themed **Bootstrap 5** storefront, user accounts with order history, and **Stripe** Checkout payments.

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap_5-7952B3?logo=bootstrap&logoColor=white)
![Stripe](https://img.shields.io/badge/Stripe-635BFF?logo=stripe&logoColor=white)

[![Xtore home page](images/home.png)](images/home.png)

## Features

**1. Product catalog.** Every item has a description, image, price and quantity in stock.

[![Catalog](images/catalog.png)](images/catalog.png)

**2. User accounts and order history.** Each user registers with a unique email and can review their past purchases.

[![Order history](images/private_orders.png)](images/private_orders.png)

**3. Persistent carts.** Items in your cart are still there after you log out, unless you add or remove them yourself.

[![Cart](images/sample_cart.png)](images/sample_cart.png)

**4. Private by design.** Passwords are hashed (PBKDF2-SHA256, 200,000 iterations) and sessions use random bearer tokens that are stored only as SHA-256 hashes. Cart and order endpoints are scoped to the signed-in user, so no one can see another customer's data.

[![Sign in](images/signin.png)](images/signin.png) [![Register](images/register.png)](images/register.png)

**5. Payments powered by [Stripe](https://stripe.com/).** Checkout runs through Stripe-hosted pages, and orders are recorded when payment completes.

[![Checkout](images/checkout.png)](images/checkout.png) [![Test payment](images/test_payment.png)](images/test_payment.png) [![Success](images/success.png)](images/success.png)

**Also included:** stock validation at checkout, free shipping on orders over $50 (otherwise $5.50), 6% estimated tax, and token-protected admin endpoints for managing the catalog.

## Tech stack

| Layer    | Choice                                                    |
| -------- | --------------------------------------------------------- |
| Backend  | FastAPI, Pydantic, SQLAlchemy, Stripe                     |
| Storage  | SQLite locally; PostgreSQL via `DATABASE_URL` in production |
| Frontend | HTML5, Bootstrap 5, CSS, JavaScript (served from `static/`) |

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/VeerX-27G/Xtore.git
cd Xtore

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`pyproject.toml` declares Python `>=3.14`; the code itself uses standard modern Python typing, so check your version if installs fail.

### 2. Configure environment variables

Create a `.env` file in the project root (it is already git-ignored):

```env
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
ADMIN_API_KEY=choose-a-long-random-string
# DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
```

| Variable | Required | Purpose |
|---|---|---|
| `STRIPE_API_KEY` | Yes, for payments | Your Stripe **test** secret key |
| `STRIPE_WEBHOOK_SECRET` | Strongly recommended | Verifies webhook signatures from Stripe |
| `ADMIN_API_KEY` | Yes, to manage items | Checked against the `X-Admin-Key` header on admin routes |
| `DATABASE_URL` | No | Use Postgres instead of the default local SQLite file `items.db` (`postgres://` URLs are converted automatically) |

### 3. Run the app

```bash
uvicorn main:app --reload
```

Open **http://127.0.0.1:8000**. Interactive API docs are at `/docs`.

Tables are created automatically on first start. The catalog starts empty, so add products using the admin API (see below). Stay on port **8000**, because the Stripe success and cancel redirects point to `http://127.0.0.1:8000`.

### 4. Add a product

```bash
curl -X POST http://127.0.0.1:8000/admin/items \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -d '{
    "title": "Walnut Desk Organizer",
    "description": "Hand-finished walnut organizer for pens and notes.",
    "price": 34.99,
    "stock": 12,
    "image_url": "/img/Walnut%20Desk%20Organizer.jpg"
  }'
```

### 5. Test payments with Stripe

> **Please do NOT use real credit or debit card details.** Use only the [test card numbers](https://stripe.com/docs/testing) provided by Stripe, for example `4242 4242 4242 4242` with any future expiry date and any CVC.

To receive `checkout.session.completed` events locally, forward them with the [Stripe CLI](https://stripe.com/docs/stripe-cli):

```bash
stripe listen --forward-to localhost:8000/webhook
```

Copy the `whsec_...` secret it prints into `STRIPE_WEBHOOK_SECRET`.

## API overview

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | None | Create an account and receive a session token |
| `POST` | `/auth/login` | None | Sign in and receive a session token |
| `GET` | `/items/` | None | List active catalog items |
| `POST` | `/orders` | Bearer token | Place an order directly and deduct stock |
| `GET` | `/orders` | Bearer token | Current user's order history, newest first |
| `POST` | `/create-checkout-session` | Bearer token | Start a Stripe Checkout session for the cart |
| `GET` | `/api/checkout-success` | None | Verify a Stripe session after payment and record the order |
| `POST` | `/webhook` | Stripe signature | Handle `checkout.session.completed` events |
| `POST` | `/admin/items` | `X-Admin-Key` | Create a catalog item |
| `PATCH` | `/admin/items/{id}` | `X-Admin-Key` | Update an item |
| `DELETE` | `/admin/items/{id}` | `X-Admin-Key` | Remove an item from the catalog (soft delete) |

Authenticated requests send `Authorization: Bearer <token>`.

## Project structure

```
.
├── main.py            # FastAPI app: routes, auth, orders, Stripe
├── models.py          # SQLAlchemy models: Item, User, AuthSession, Order
├── schemas.py         # Pydantic request/response schemas
├── database.py        # Engine and session setup (SQLite or Postgres)
├── static/            # Storefront: HTML, CSS, JavaScript, product images
├── images/            # Screenshots used in this README
├── requirements.txt
└── pyproject.toml
```

## Notes

- Prices are charged in **CAD**.
- Deleting an item hides it from the catalog rather than removing the row, so past orders keep their history.
- This is a learning and portfolio project. Review the security notes below before deploying anything real.

## Before deploying

- Always set `STRIPE_WEBHOOK_SECRET`. Without it, the webhook accepts unsigned requests.
- Change the Stripe `success_url` and `cancel_url` in `main.py` from `127.0.0.1:8000` to your real domain.
- Use a Stripe **live** key only on a properly secured production deployment.
![alt text](images/test_payment.png)
![alt text](images/success.png)

##  Note
**Please do NOT use real credit/debit card details** -- only use the test card numbers provided by [Stripe](https://stripe.com/docs/testing).
