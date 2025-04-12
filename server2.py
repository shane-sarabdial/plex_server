import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from plexapi.myplex import MyPlexAccount
from flask_mail import Mail, Message
import json
from pages import app_stripe
import configparser
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

page = app_stripe()
config_email = configparser.ConfigParser()
config_email.read('config.conf')
section = 'Default'
app = Flask(__name__)
app.config["MAIL_SERVER"] = config_email.get(section, 'MAIL_SERVER')
app.config["MAIL_PORT"] = int(config_email.get(section, 'MAIL_PORT'))
app.config["MAIL_USE_TLS"] = config_email.get(section, 'MAIL_USE_TLS').lower() in ["true", "1", "t"]
app.config["MAIL_USERNAME"] = config_email.get(section, 'MAIL_USERNAME')
app.config["MAIL_PASSWORD"] = config_email.get(section, 'MAIL_PASSWORD')
app.config["MAIL_DEFAULT_SENDER"] = config_email.get(section, 'MAIL_DEFAULT_SENDER')
app.config['MY_SECRET_KEY'] = config_email.get(section, 'MY_SECRET_KEY')
app.secret_key = config_email.get(section, 'MY_SECRET_KEY')
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['MY_SECRET_KEY'])


@app.route('/', methods=["GET", "POST"])
def p1():
    return page.index()

@app.route("/create-checkout-session", methods=["POST"])
def p2():
    return page.create_checkout_session()

@app.route('/webhook', methods=['POST'])
def p3():
    return page.webhook()

@app.route("/success", methods=['POST', 'GET'])
def p4():
    return page.success()

@app.route("/about")
def p5():
    return page.about()

@app.route("/subscriptions", methods=["GET"])
def p6():
    return page.subscriptions()

@app.route("/support", methods=["GET", "POST"])
def p7():
    return page.support(mail)


@app.route("/unsubscribe", methods=["GET", "POST"])
def p8():
    return page.unsubscribe()

@app.route("/account", methods=["GET", "POST"])
def account():
    return page.account()
@app.route('/login', methods=['GET', 'POST'])
def login():
    return page.login(serializer, mail)

@app.route('/cancel_subscription', methods=["POST"])
def cancel_subscription():
    return page.cancel_subscription()

@app.route('/magic/<token>')
def magic_link(token):
    print("here")
    try:
        # Validate the token and retrieve the email; expires after 15 minutes (900 seconds)
        email = serializer.loads(token, salt='magic-link', max_age=900)
        session['email'] = email  # Mark the user as "logged in"
        flash("You are now logged in!", "success")
        return redirect(url_for('account', email=email))
    except SignatureExpired:
        flash("The magic link has expired. Please request a new one.", "warning")
    except BadSignature:
        flash("Invalid magic link. Please try again.", "danger")
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
