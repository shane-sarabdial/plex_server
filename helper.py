import configparser
import os
import pages
from flask import Flask, request, jsonify, render_template, redirect
from plexapi.myplex import MyPlexAccount
from flask_mail import Message
import json
import stripe


class MyPlexHelper():
    def __init__(self):
        config_Plex = configparser.ConfigParser()
        config_Plex.read('config.conf')
        section = 'Default'
        self.PLEX_SERVER_NAME = config_Plex.get(section,'PLEX_SERVER_NAME')
        self.PLEX_EMAIL = config_Plex.get(section,'PLEX_EMAIL')
        self.PLEX_PASSWORD = config_Plex.get(section,'PLEX_PASSWORD')
        self.plex_admin = MyPlexAccount(username=self.PLEX_EMAIL, password=self.PLEX_PASSWORD)
        self.plex_server = self.plex_admin.resource(self.PLEX_SERVER_NAME).connect()

    def add_plex_user(self,email):
        """Invite the user to Plex."""
        try:
            user = self.plex_admin.inviteFriend(email, self.plex_server,)
            print(f"✅ Added {email} to Plex")
            # print(self.plex_admin.query())
        except Exception as e:
            print(f"❌ Failed to add {email}: {str(e)}")

    def remove_plex_user(self,email):
        """Remove the user from Plex."""
        try:
            friend = self.plex_admin.removeFriend(email)
            print(f"❌ Removed {email} from Plex")
        except Exception as e:
            print(f"⚠️ Error removing {email}: {str(e)}")

    def pending_invite(self,email):
        invite = False
        try:
            user = self.plex_admin.inviteFriend(email, self.plex_server, )
            # self.plex_admin.createExistingUser(email, self.plex_server)
        except Exception as e:
            if str(e).find("already exists") == -1:
                print('Invite Pending')
                print(e)
                invite = True
                return invite
            else:
                print("user not added")
                return invite


def is_customer_subscribed(email):
    # Search for the customer with the given email
    customers = stripe.Customer.list(limit=100)
    customer_id = None
    for customer in customers.auto_paging_iter():
        if customer.email == email:
            customer_id = customer.id
            break

    if not customer_id:
        print(f"No customer found with email {email}")
        return False, None

    # Retrieve active subscriptions for the found customer
    subscriptions = stripe.Subscription.list(customer=customer_id, status="active", limit=1)
    for sub in subscriptions.auto_paging_iter():
        if sub.status == "active":
            print(f"Customer {email} has an active subscription: {sub.id}")
            return True, sub

    print(f"Customer {email} does not have any active subscriptions.")
    return False, None


def msg(name, email, subject, message, support_email):
    return Message(subject=f"Support Request: {subject}",
                   recipients=[support_email],
                   body=f"Support request from {name} <{email}>:\n\nSubject: {subject}\n\nMessage:\n{message}")