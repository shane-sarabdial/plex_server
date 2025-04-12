import os
import stripe
import pages
from flask import Flask, request, jsonify, render_template, redirect
from plexapi.myplex import MyPlexAccount
from flask_mail import Mail, Message
import json
from helper import MyPlexHelper, is_customer_subscribed

# Load environment variables
# PLEX_SERVER_NAME = os.getenv("PLEX_SERVER_NAME")
# PLEX_EMAIL = os.getenv("PLEX_EMAIL")
# print(PLEX_EMAIL)
# PLEX_PASSWORD = os.getenv("PLEX_PASSWORD")
# print(PLEX_PASSWORD)
Plex = MyPlexHelper()
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
DOMAIN_URL = os.getenv("DOMAIN_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
SUCCESS = os.getenv("SUCCESS")

# Initialize Stripe
stripe.api_key = STRIPE_SECRET_KEY

# Connect to Plex
# plex_admin = MyPlexAccount(username=PLEX_EMAIL, password=PLEX_PASSWORD)
# plex_server = plex_admin.resource(PLEX_SERVER_NAME).connect()

app = Flask(__name__)

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS").lower() in ["true", "1", "t"]
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

mail = Mail(app)


@app.route('/', methods=["GET", "POST"])
def index():
    """Serve the signup page."""
    return render_template("index.html", public_key=STRIPE_PUBLIC_KEY)


@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """Create a Stripe Checkout session."""
    email = request.form["email"]
    subscribed, sub_data = is_customer_subscribed(email)
    if subscribed:
        return render_template("already_subscribed.html", email=email)

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        customer_email=email,
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Plex Server Subscription"},
                    "unit_amount": 500,  # $5.00 in cents
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url='http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=f"{DOMAIN_URL}/",
    )
    return redirect(session.url, code=303)


@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')
    # Replace with your endpoint's secret (you get this from your Stripe dashboard)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get("customer_email")
        # Alternatively, if needed, check within customer_details
        if not customer_email:
            customer_details = session.get("customer_details", {})
            customer_email = customer_details.get("email")
            print("not working")
        print("Customer Email:", customer_email)
        Plex.add_plex_user(customer_email)
        # You can fulfill the order here (e.g., update a database, send an email, etc.)
        print("Payment was successful for session:", session.get('id'))
    else:
        print("Payment not working")

    # Return a response to acknowledge receipt of the event
    return jsonify(success=True)


@app.route("/success", methods=['POST', 'GET'])
def success():
    customer_name = None
    session_id = request.args.get("session_id")
    email = request.args.get("email")
    print("email", request.args)
    # invite = Plex.pending_invite(email)
    if session_id:
        session = stripe.checkout.Session.retrieve(session_id)
        customer_details = session.get("customer_details", {})
        customer_name = customer_details.get("name", "Subscriber")
        return render_template("success.html", customer_name=customer_name)
    else:
        return render_template("error.html", error_message="Invalid signature")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/subscriptions", methods=["GET"])
def subscriptions():
    # List active subscriptions (you can adjust the limit as needed)
    active_subs = stripe.Subscription.list(status="active", limit=100)
    subs_data = []
    for sub in active_subs.auto_paging_iter():
        subs_data.append({
            "subscription_id": sub.id,
            "customer": sub.customer,
            "status": sub.status,
            "created": sub.created
        })
    # Return the data as JSON, or render it in a template if desired
    return jsonify(subs_data)


@app.route("/support", methods=["GET", "POST"])
def support():
    if request.method == "POST":
        # Get form fields
        name = request.form.get("name")
        email = request.form.get("email")
        subject = request.form.get("subject")
        message = request.form.get("message")
        support_email = os.getenv("SUPPORT_EMAIL")  # Email address where you'll receive support messages
        msg = Message(
            subject=f"Support Request: {subject}",
            recipients=[support_email],
            body=f"Support request from {name} <{email}>:\n\nSubject: {subject}\n\nMessage:\n{message}"
        )
        try:
            mail.send(msg)
            print("Support email sent successfully!")
        except Exception as e:
            print("Failed to send support email:", e)

        # For now, we'll simply print the message.
        # In a real implementation, you could use Flask-Mail or another email service.
        print(f"Support request from {name} <{email}>:")
        print(f"Subject: {subject}")
        print(f"Message: {message}")

        # Render a success/thank you page.
        return render_template("support_success.html", name=name)

    # GET method: Render the support form
    return render_template("support.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
