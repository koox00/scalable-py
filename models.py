#!/usr/bin/env python
"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb


class ConflictException(endpoints.ServiceException):
    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT


class Profile(ndb.Model):
    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    sessionWishlist = ndb.StringProperty(repeated=True)


class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)


class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    teeShirtSize = messages.EnumField('TeeShirtSize', 3)
    conferenceKeysToAttend = messages.StringField(4, repeated=True)
    sessionWishlist = messages.StringField(5, repeated=True)


class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)


class BooleanMessage(messages.Message):
    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)


class Conference(ndb.Model):
    """Conference -- Conference object"""
    name = ndb.StringProperty(required=True)
    description = ndb.StringProperty(indexed=False)
    organizerUserId = ndb.StringProperty()
    topics = ndb.StringProperty(repeated=True)
    city = ndb.StringProperty()
    startDate = ndb.DateProperty()
    month = ndb.IntegerProperty()
    endDate = ndb.DateProperty()
    maxAttendees = ndb.IntegerProperty()
    seatsAvailable = ndb.IntegerProperty()
    followedBy = ndb.StringProperty(repeated=True)
    # quick check for followers, typical usage in queries
    hasFollowers = ndb.ComputedProperty(lambda self: len(self.followedBy) != 0)

    @property
    def sessions(self):
        """Returns a Session query object with current conf as an ancestor.

        This is too be used when you want both Conference and Sessions,
        when used to get only sessions costs one RPC more (e.g: getConferenceSessions).
        However it returns a correct 404 when Conf doesn't exist
        """
        return Session.query(ancestor=self.key).order(Session.date, Session.startTime)

    @property
    def profile(self):
        """Returns a Profile query object with current conf as child."""
        return Profile.query(ancestor=self.key.parent())


class ConferenceForm(messages.Message):
    """ConferenceForm -- Conference outbound form message"""
    name = messages.StringField(1)
    description = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics = messages.StringField(4, repeated=True)
    city = messages.StringField(5)
    startDate = messages.StringField(6)  # DateTimeField()
    month = messages.IntegerField(7, variant=messages.Variant.INT32)
    maxAttendees = messages.IntegerField(8, variant=messages.Variant.INT32)
    seatsAvailable = messages.IntegerField(9, variant=messages.Variant.INT32)
    endDate = messages.StringField(10)  # DateTimeField()
    websafeKey = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)


class ConferenceForms(messages.Message):
    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)


class TeeShirtSize(messages.Enum):
    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15


class ConferenceQueryForm(messages.Message):
    """ConferenceQueryForm -- Conference query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)


class ConferenceQueryForms(messages.Message):
    """ConferenceQueryForms -- multiple ConferenceQueryForm inbound form message"""
    filters = messages.MessageField(ConferenceQueryForm, 1, repeated=True)


class Speaker(ndb.Model):
    """Speaker -- Speaker entity object"""
    fullName = ndb.StringProperty(required=True)
    email = ndb.StringProperty()
    featuredSessions = ndb.StringProperty(repeated=True)

    @property
    def featuredSessions(self):
        """Returns a Session query object for sessions this Speaker is featured"""
        return Session.query(Session.speaker == self.key)


class SpeakerForm(messages.Message):
    """SpeakerForm - Speaker outbound form message"""
    fullName = messages.StringField(1)
    email = messages.StringField(2)
    websafeKey = messages.StringField(4)


class SpeakerForms(messages.Message):
    """SpeakerForms

    Multiple Speakers  outbound form message
    """
    items = messages.MessageField(SpeakerForm, 1, repeated=True)


class Session(ndb.Model):
    """Session -- Session object"""
    name = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty(repeated=True)
    speaker = ndb.KeyProperty(Speaker)
    duration = ndb.IntegerProperty()
    typeOfSession = ndb.StringProperty()
    date = ndb.DateProperty()
    startTime = ndb.TimeProperty()

    @property
    def conference(self):
        """Returns parent ConferenceObject."""
        return Conference.query(ancestor=self.key.parent()).get()


class SessionForm(messages.Message):
    """SessionForm

    Session outbound form message
    Expects to have Conference's key as the parent key.
    """
    name = messages.StringField(1)
    highlights = messages.StringField(2, repeated=True)
    speaker = messages.StringField(3)
    duration = messages.IntegerField(4, variant=messages.Variant.INT32)
    typeOfSession = messages.StringField(5)
    date = messages.StringField(6)  # DateTimeField()
    startTime = messages.StringField(7)  # DateTimeField()
    websafeKey = messages.StringField(8)


class SessionForms(messages.Message):
    """SessionForms

    Multiple Conference Sessions  outbound form message
    """
    items = messages.MessageField(SessionForm, 1, repeated=True)


__authors__ = 'wesc+api@google.com (Wesley Chun), cooxlee@gmail.com (Koox00)'
