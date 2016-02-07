#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from conference import ConferenceApi


class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._cacheAnnouncement()
        self.response.set_status(204)


class SetNotificationHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._notifyFollowers()
        self.response.set_status(204)


class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )


class SendFollowerEmail(webapp2.RequestHandler):
    def post(self):
        """Send email when ."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'Greate News!',                             # subj
            'A spot has opened in the following '       # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conference')
        )


class SetFeaturedSpeakerHandler(webapp2.RequestHandler):
    def post(self):
        """Set Featured Speaker in Memcache by websafeConfKey and SpeakersName"""
        ConferenceApi._cacheFeaturedSpeaker(self.request.get('wsck'), self.request.get('speaker'))
        self.response.set_status(204)


app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/crons/notify_users', SetNotificationHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/featured_speaker', SetFeaturedSpeakerHandler),
    ('/tasks/send_email_2_follower', SendFollowerEmail)
], debug=True)


__authors__ = 'wesc+api@google.com (Wesley Chun), cooxlee@gmail.com (Koox00)'
