import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from plexapi.myplex import MyPlexAccount
from flask_mail import Mail, Message
import json
from helper import MyPlexHelper, is_customer_subscribed,msg
import stripe
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import configparser
from sqldb import Customer, SubscriptionHistory, add_subscription_history, add_customer, engine, Base, find_customer, current_plex_status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

Plex = MyPlexHelper()
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
dbsession = Session()


class app_stripe():
    def __init__(self):
        config = configparser.ConfigParser()
        config.read('config.conf')
        section = 'Default'
        self.STRIPE_SECRET_KEY = config.get(section, 'STRIPE_SECRET_KEY')
        self.STRIPE_PUBLIC_KEY = config.get(section,'STRIPE_PUBLIC_KEY')
        self.DOMAIN_URL = config.get(section, 'DOMAIN_URL')
        self.WEBHOOK_SECRET = config.get(section, 'WEBHOOK_SECRET')
        stripe.api_key = self.STRIPE_SECRET_KEY
        self.support_email = config.get(section, 'SUPPORT_EMAIL')
        self.email = None
        self.customer = None
        self.session_id = None

    def index(self):
        """Serve the signup page."""
        return render_template("index.html", public_key=self.STRIPE_PUBLIC_KEY)

    def create_checkout_session(self):
        """Create a Stripe Checkout session."""
        self.email = request.form["email"]
        subscribed, sub_data = is_customer_subscribed(self.email)
        if subscribed:
            return render_template("already_subscribed.html", email=self.email)

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            customer_email=self.email,
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
            cancel_url=f"{self.DOMAIN_URL}/",
        )
        return redirect(session.url, code=303)

    def webhook(self):
        payload = request.data
        sig_header = request.headers.get('stripe-signature')
        # Replace with your endpoint's secret (you get this from your Stripe dashboard)
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.WEBHOOK_SECRET
            )
        except ValueError as e:
            # Invalid payload
            return "Invalid payload", 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            return "Invalid signature", 400

        # Handle the checkout.session.completed event
        if event['type'] == 'checkout.session.completed':
            self.session = event['data']['object']
            Plex.add_plex_user(self.email)
            add_customer(self.email, dbsession)
            # You can fulfill the order here (e.g., update a database, send an email, etc.)
            print("Payment was successful for session:", self.session.get('id'))
        else:
            print("Payment not working")

        # Return a response to acknowledge receipt of the event
        return jsonify(success=True)

    def cancel_subscription(self):
        payload = request.data
        sig_header = request.headers.get('stripe-signature')
        # Replace with your endpoint's secret (you get this from your Stripe dashboard)
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.WEBHOOK_SECRET
            )
        except ValueError as e:
            # Invalid payload
            return "Invalid payload", 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            return "Invalid signature", 400
        if event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            # Try to retrieve the customer email; sometimes it isn't directly in the event.
            customer_id = subscription.get("customer")
            # Optionally, you could check if the event data includes the email.
            customer_email = subscription.get("customer_email")
            if not customer_email and customer_id:
                # Retrieve the customer object from Stripe
                customer_obj = stripe.Customer.retrieve(customer_id)
                customer_email = customer_obj.get("email")
            if customer_email:
                print(f"Removing Plex access for {customer_email}")
                Plex.remove_plex_user(email=customer_email)
            else:
                print("Customer email not found in subscription cancellation event.")
        return jsonify(success=True)

    def success(self):
        customer_name = None
        session_id = request.args.get("session_id")
        invite = Plex.pending_invite(self.email)
        customer_id = find_customer(self.email, dbsession)
        if session_id and invite:
            session = stripe.checkout.Session.retrieve(session_id)
            customer_details = session.get("customer_details", {})
            customer_name = customer_details.get("name", "Subscriber")
            try:
                add_subscription_history(customer_id.id, "subscription", dbsession)
            except Exception as e:
                dbsession.rollback()
            return render_template("success.html", customer_name=customer_name)
        else:
            try:
                add_subscription_history(customer_id.id, "stripe_sub", dbsession)
            except Exception as e:
                dbsession.rollback()
            return render_template("error.html", error_message="Invalid signature")

    def about(self):
        return render_template("about.html") \

    def subscriptions(self):
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

    def support(self, mail):
        if request.method == "POST":
            # Get form fields
            name = request.form.get("name")
            email = request.form.get("email")
            subject = request.form.get("subject")
            message = request.form.get("message")
            support_email = self.support_email # Email address where you'll receive support messages
            payload = msg(name=name, email=email, subject=subject, message=message, support_email=support_email)
            try:
                mail.send(payload)
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
        return render_template("support.html")


    def unsubscribe(self):
        if request.method == "POST":
            email = request.form.get("email")
            if not email:
                return render_template("unsubscribe.html", error="Please provide an email address.")

            # Find the customer record in the database
            customer_record = find_customer(email, dbsession)
            if not customer_record:
                return render_template("unsubscribe.html",
                                       error="Email not found. Please check your email address.")

            # Check if the customer has an active subscription via Stripe
            subscribed, sub_data = is_customer_subscribed(email)
            if not subscribed:
                return render_template("unsubscribe.html", message="You do not have an active subscription.")


            # Cancel the subscription via Stripe
            subscription_id = sub_data.id
            try:
                # Cancel the subscription immediately (or set cancel_at_period_end=True if desired)
                subscription = stripe.Subscription.retrieve(subscription_id)
                status = subscription.status
                cancel_at_period_end = subscription.cancel_at_period_end
                end_time = subscription.current_period_end
                end_date = datetime.fromtimestamp(end_time).strftime('%m-%d-%Y')
                end_date_datetime = datetime.strptime(end_date, "%m-%d-%Y")
                if status and cancel_at_period_end:
                    return render_template("unsubscribe.html", message=f"Your subscription is set to end on {end_date}")

                stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)


                # Record the unsubscribe event in subscription history:
                add_subscription_history(customer_record.id, "unsubscribe", dbsession, end_date=end_date_datetime)

                # MyPlexHelper.remove_plex_user(email=email)
                return render_template("unsubscribe_success.html", email=email,
                                       end_date=end_date)
            except Exception as e:
                return render_template("unsubscribe.html", error=f"Error canceling subscription: {str(e)}")

        return render_template("unsubscribe.html")


    def login(self,serializer,mail):
        if request.method == 'POST':
            email = request.form.get('email')
            if not email:
                flash("Please enter an email address.", "warning")
                return redirect(url_for('login'))
            customer_record = find_customer(email, dbsession)
            if not customer_record:
                return render_template('error.html', msg="You do not have an account with that email. Please subscribe to create"
                                                         " an account")

            # Generate a token with a 15-minute expiration
            token = serializer.dumps(email, salt='magic-link')
            magic_link = url_for('magic_link', token=token, _external=True)

            # Prepare and send the email
            msg = Message("Your Magic Login Link", recipients=[email])
            msg.body = f"Click the link below to log in:\n\n{magic_link}\n\nThis link expires in 15 minutes."
            try:
                mail.send(msg)
                flash("A magic link has been sent to your email address. Please check your inbox.", "info")
            except Exception as e:
                flash(f"Error sending email: {e}", "danger")
            return redirect(url_for('login'))
        return render_template('login.html')

    def account(self):
        # Check if user is logged in; if not, redirect to login page.
        if 'email' not in session:
            flash("Please log in to access your account.", "warning")
            return redirect(url_for("login"))

        # Get the user's email from session.
        email = session['email']


        # Retrieve customer record from your database.
        customer_record = find_customer(email, dbsession)
        if not customer_record:
            flash("Customer record not found.", "danger")
            return redirect(url_for("login"))

        # Retrieve active subscription details from Stripe, if available.
        subscribed, subscription = is_customer_subscribed(email)
        next_due_date = None
        if subscription:
            next_due_date = datetime.fromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d")
        if subscription is None:
            session.clear()
            return render_template('error.html', msg="No subscription")


        # Retrieve current payment method (example: first card on file)
        payment_methods = stripe.PaymentMethod.list(
            customer= subscription.customer,
            type="card"
        )
        current_payment_method = None
        if payment_methods.data:
            card = payment_methods.data[0].card
            current_payment_method = f"{card['brand']} ending in {card['last4']}"

        # Retrieve subscription/payment history from your database
        active_on_plex = current_plex_status(customer_record.id, dbsession)
        active_on_plex = active_on_plex.exists_on_plex
        print(active_on_plex)

        # Additional account details from your app
        server_name = "Your Plex Server Name"  # Alternatively, pull from config
        access_status = "Active" if active_on_plex ==1 else "Inactive"

        # Link to update payment method (for example, your Stripe Customer Portal URL)
        update_payment_link = "https://billing.stripe.com/p/login/test_fZe4iP8fP9Iv80weUU"  # Replace with your actual link

        # Render the account template with all the necessary variables.
        return render_template("account.html",
                               email=email,
                               next_due_date=next_due_date,
                               current_payment_method=current_payment_method,
                               server_name=server_name,
                               access_status=access_status,
                               history=active_on_plex,
                               update_payment_link=update_payment_link)


