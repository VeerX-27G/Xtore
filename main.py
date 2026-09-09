import hashlib
import json
import os
from decimal import Decimal
from dotenv import load_dotenv
import secrets

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
import models, schemas # Files in the project

import stripe

load_dotenv()

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    columns = {column["name"] for column in inspect(engine).get_columns("items")}
    if "is_active" not in columns:
        default_value = "1" if engine.dialect.name == "sqlite" else "TRUE"
        connection.execute(text(
            f"ALTER TABLE items ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT {default_value}"
        ))

app = FastAPI(title="VeerG's Xtore API")

stripe.api_key = os.environ.get("STRIPE_API_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

CATALOG_IMAGES = {
    "Walnut Desk Organizer": "/img/Walnut%20Desk%20Organizer.jpg",
    "Linen Journal, Forest Green": "/img/Linen%20Journal%20Forest%20Green.jpg",
    "Brass Fountain Pen": "/img/brass_pen.jpg",
}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This line of code generates a password hash using the PBKDF2 algorithm.
def password_hash(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"veer-g-store-v1", 200_000).hex()

# This line of code generates a token hash using the SHA256 algorithm.
def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

# This line of code retrieves the current user based on the authorization token provided in the header.
def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in is required")
    session = db.query(models.AuthSession).filter_by(token_hash=token_hash(authorization[7:])).first()
    user = db.get(models.User, session.user_id) if session else None
    if not user:
        raise HTTPException(401, "Your session has expired")
    return user

def admin_api_key(api_key: str | None = Header(default=None, alias="X-Admin-Key")):
    expected_key = os.environ.get("ADMIN_API_KEY")
    if not expected_key or not api_key or not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(401, "Valid admin API key is required")

# This line of code serializes an item to a dictionary.
def serialize_item(item: models.Item):
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "price": item.price,
        "stock": item.stock,
        "image_url": item.img or CATALOG_IMAGES.get(item.title, "")
    }

# This line of code serializes an order to a dictionary.
def serialize_order(order: models.Order):
    return {
        "id": f"ORD-{order.id:06d}",
        "date": order.created_at.isoformat() if order.created_at else "",
        "items": json.loads(order.items_json),
        "totals": {
            "subtotal": order.subtotal,
            "shipping": order.shipping,
            "tax": order.tax,
            "total": order.total
        },
        "shipTo": order.ship_to,
        "status": order.status
    }

# ----------------- Auth Endpoints ----------------- #

@app.get("/auth/register")
def get_register_redirect():
    return RedirectResponse(url="/signup.html", status_code=307)

@app.get("/auth/login")
def get_login_redirect():
    return RedirectResponse(url="/login.html", status_code=307)

@app.post("/auth/register")
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if len(data.password) < 6:
        raise HTTPException(422, "Password must be at least 6 characters")
    if db.query(models.User).filter_by(email=email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = models.User(name=data.name.strip(), email=email, password_hash=password_hash(data.password))
    db.add(user)
    db.flush() # This line of code flushes the session, which means it writes the data to the database but does not commit it. It allows you to get the ID of the new user before committing the transaction.
    token = secrets.token_urlsafe(32)
    db.add(models.AuthSession(token_hash=token_hash(token), user_id=user.id))
    db.commit()
    return {"id": user.id, "name": user.name, "email": user.email, "token": token}

@app.post("/auth/login")
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(email=data.email.strip().lower()).first()
    if not user or not secrets.compare_digest(user.password_hash, password_hash(data.password)):
        raise HTTPException(401, "Invalid email or password")
    token = secrets.token_urlsafe(32)
    db.add(models.AuthSession(token_hash=token_hash(token), user_id=user.id))
    db.commit()
    return {"id": user.id, "name": user.name, "email": user.email, "token": token}

# ----------------- Catalog & Order Endpoints ----------------- #

@app.get("/items/", response_model=list[schemas.ItemResponse])
def read_items(db: Session = Depends(get_db)):
    return [serialize_item(item) for item in db.query(models.Item).filter_by(is_active=True).all()]

@app.post("/admin/items", response_model=schemas.ItemResponse, dependencies=[Depends(admin_api_key)])
def create_item(data: schemas.ItemCreate, db: Session = Depends(get_db)):
    item = models.Item(
        title=data.title.strip(),
        description=data.description.strip(),
        price=data.price,
        stock=data.stock,
        img=data.image_url.strip(),
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_item(item)

@app.patch("/admin/items/{item_id}", response_model=schemas.ItemResponse, dependencies=[Depends(admin_api_key)])
def update_item(item_id: int, data: schemas.ItemUpdate, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes:
        item.title = changes["title"].strip()
    if "description" in changes:
        item.description = changes["description"].strip()
    if "image_url" in changes:
        item.img = changes["image_url"].strip()
    if "price" in changes:
        item.price = changes["price"]
    if "stock" in changes:
        item.stock = changes["stock"]
    db.commit()
    db.refresh(item)
    return serialize_item(item)

@app.delete("/admin/items/{item_id}", dependencies=[Depends(admin_api_key)])
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    item.is_active = False
    db.commit()
    return {"message": "Item removed from catalog"}

@app.post("/orders")
def create_order(data: schemas.CheckoutRequest, user=Depends(current_user), db: Session = Depends(get_db)):
    if not data.lines:
        raise HTTPException(422, "Your cart is empty")
    lines, subtotal = [], 0.0
    for line in data.lines:
        item = db.query(models.Item).filter_by(id=line.item_id, is_active=True).first()
        if not item or line.quantity < 1 or line.quantity > item.stock:
            raise HTTPException(422, f"Item '{item.title if item else line.item_id}' has only {item.stock if item else 0} in stock.")
        item.stock -= line.quantity
        lines.append({"id": item.id, "name": item.title, "price": item.price, "qty": line.quantity})
        subtotal += item.price * line.quantity
    shipping = 0.0 if subtotal > 50 else 5.50
    tax = round(subtotal * 0.06, 2)
    total = round(subtotal + shipping + tax, 2)
    order = models.Order(
        user_id=user.id,
        items_json=json.dumps(lines),
        subtotal=Decimal(str(subtotal)),
        shipping=Decimal(str(shipping)),
        tax=Decimal(str(tax)),
        total=Decimal(str(total)),
        ship_to=data.ship_to.strip(),
        status="Confirmed"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return serialize_order(order)

@app.get("/orders")
def order_history(user=Depends(current_user), db: Session = Depends(get_db)):
    return [serialize_order(order) for order in db.query(models.Order).filter_by(user_id=user.id).order_by(models.Order.id.desc()).all()]

# ----------------- Stripe Payments Endpoints ----------------- #

@app.post("/create-checkout-session")
def create_checkout_session(data: schemas.CheckoutRequest, user=Depends(current_user), db: Session = Depends(get_db)):
    if not data.lines:
        raise HTTPException(422, "Your cart is empty")
    
    stripe_lines = []
    lines_summary = []
    subtotal = 0.0

    for line in data.lines:
        # This line of code queries the database for an item with the given ID and checks if it is active.
        item = db.query(models.Item).filter_by(id=line.item_id, is_active=True).first()
        if not item:
            raise HTTPException(404, f"Item with ID {line.item_id} not found in catalog")
        if line.quantity < 1:
            raise HTTPException(422, f"Invalid quantity for '{item.title}'")
        if line.quantity > item.stock:
            raise HTTPException(422, f"Cannot checkout {line.quantity} of '{item.title}'. Only {item.stock} in stock.")
        
        unit_amount = int(round(item.price * 100))
        stripe_lines.append({
            "price_data": {
                "currency": "cad",
                "product_data": {
                    "name": item.title,
                    "description": item.description[:200] if item.description else "",
                },
                "unit_amount": unit_amount,
            },
            "quantity": line.quantity,
        })
        lines_summary.append({"item_id": item.id, "name": item.title, "price": item.price, "quantity": line.quantity})
        subtotal += item.price * line.quantity

    shipping = 0.0 if subtotal > 50 else 5.50

    # This line of code adds shipping to the Stripe checkout session if the subtotal is less than $50.
    if shipping > 0:
        stripe_lines.append({
            "price_data": {
                "currency": "cad",
                "product_data": {
                    "name": "Standard Shipping",
                    "description": "Standard ground delivery",
                },
                "unit_amount": int(round(shipping * 100)),
            },
            "quantity": 1,
        })

    tax = round(subtotal * 0.06, 2)
    if tax > 0:
        stripe_lines.append({
            "price_data": {
                "currency": "cad",
                "product_data": {
                    "name": "Estimated Tax (6%)",
                    "description": "Applicable sales tax",
                },
                "unit_amount": int(round(tax * 100)),
            },
            "quantity": 1,
        })

    total = round(subtotal + shipping + tax, 2)

    try:
        # This line of code creates a Stripe checkout session.
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=stripe_lines,
            mode="payment",
            metadata={
                "user_id": str(user.id),
                "ship_to": data.ship_to.strip(),
                "cart_json": json.dumps(lines_summary),
                "subtotal": f"{subtotal:.2f}",
                "shipping": f"{shipping:.2f}",
                "tax": f"{tax:.2f}",
                "total": f"{total:.2f}"
            },
            success_url="http://127.0.0.1:8000/success.html?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="http://127.0.0.1:8000/cancel.html",
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(500, f"Stripe Checkout error: {str(e)}")

@app.get("/api/checkout-success")
def handle_checkout_success(session_id: str, db: Session = Depends(get_db)):
    if not session_id:
        raise HTTPException(400, "Missing session_id parameter")

    # This line of code retrieves the Stripe checkout session.
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(400, f"Unable to verify Stripe session: {str(e)}")

    if session.payment_status not in ("paid", "no_payment_required") and session.status != "complete":
        raise HTTPException(400, "Payment has not been completed")

    metadata = session.metadata or {}
    user_id_str = metadata.get("user_id")
    if not user_id_str:
        raise HTTPException(400, "Invalid session metadata: missing user_id")

    user_id = int(user_id_str)
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User associated with checkout session was not found")

    # This line of code retrieves the cart data from the metadata.
    cart_data = json.loads(metadata.get("cart_json", "[]"))
    subtotal = float(metadata.get("subtotal", 0))
    shipping = float(metadata.get("shipping", 0))
    tax = float(metadata.get("tax", 0))
    total = float(metadata.get("total", subtotal + shipping + tax))
    ship_to = metadata.get("ship_to", "Customer Delivery")

    # This line of code checks for an existing order with matching payment to avoid duplicate recording.
    recent_order = db.query(models.Order).filter_by(
        user_id=user.id,
        ship_to=ship_to,
        total=total,
        status="Paid via Stripe"
    ).order_by(models.Order.id.desc()).first()

    if recent_order:
        return serialize_order(recent_order)

    # This line of code deducts the stock of the items in the cart and saves the order.
    lines_record = []
    for item_spec in cart_data:
        item = db.query(models.Item).filter_by(id=item_spec["item_id"]).first()
        if item:
            item.stock = max(0, item.stock - item_spec["quantity"])
            lines_record.append({
                "id": item.id,
                "name": item.title,
                "price": item.price,
                "qty": item_spec["quantity"]
            })

    # This line of code creates a new order in the database.
    order = models.Order(
        user_id=user.id,
        items_json=json.dumps(lines_record),
        subtotal=Decimal(str(subtotal)),
        shipping=Decimal(str(shipping)),
        tax=Decimal(str(tax)),
        total=Decimal(str(total)),
        ship_to=ship_to,
        status="Paid via Stripe"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return serialize_order(order)

@app.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body() # await is used to wait for the request to complete.
    sig_header = request.headers.get("stripe-signature")

    # This line of code tries to construct the Stripe webhook event.
    try:
        if endpoint_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        else:
            data = json.loads(payload) # json.loads is used to convert a JSON string to a Python dictionary.
            event = data
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # This line of code checks if the event type is "checkout.session.completed".
    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id_str = metadata.get("user_id")

        # This line of code checks if the user ID is valid.
        if user_id_str:
            user_id = int(user_id_str)
            user = db.get(models.User, user_id)

            # This line of code checks if the user is valid.
            if user:
                cart_data = json.loads(metadata.get("cart_json", "[]"))
                subtotal = float(metadata.get("subtotal", 0))
                shipping = float(metadata.get("shipping", 0))
                tax = float(metadata.get("tax", 0))
                total = float(metadata.get("total", subtotal + shipping + tax))
                ship_to = metadata.get("ship_to", "Customer Delivery")

                # This line of code checks if there is an existing order with the same data.
                existing = db.query(models.Order).filter_by(
                    user_id=user.id,
                    ship_to=ship_to,
                    total=total,
                    status="Paid via Stripe"
                ).first()

                # This line of code checks if there is an existing order with the same data.
                if not existing:
                    lines_record = []
                    # This line of code iterates through the cart data.
                    for item_spec in cart_data:
                        item = db.query(models.Item).filter_by(id=item_spec["item_id"]).first()
                        if item:
                            item.stock = max(0, item.stock - item_spec["quantity"])
                            lines_record.append({
                                "id": item.id,
                                "name": item.title,
                                "price": item.price,
                                "qty": item_spec["quantity"]
                            })

                    # This line of code creates a new order in the database.
                    order = models.Order(
                        user_id=user.id,
                        items_json=json.dumps(lines_record),
                        subtotal=Decimal(str(subtotal)),
                        shipping=Decimal(str(shipping)),
                        tax=Decimal(str(tax)),
                        total=Decimal(str(total)),
                        ship_to=ship_to,
                        status="Paid via Stripe"
                    )
                    db.add(order)
                    db.commit()

    return {"status": "success"}

# ----------------- Static Files Mount (Placed at end of route definitions) ----------------- #
app.mount("/", StaticFiles(directory="static", html=True), name="static")